import json

from app.llm import LLMAuthError, LLMRateLimitError
from tests.helpers import INJECTION_CV, STRONG_CV, WEAK_CV, make_pdf


JOB = {"job_title": "Data Engineer", "job_description": "We need Python and SQL. Airflow and Kubernetes are a plus."}
HEADERS = {"x-api-key": "fake-key"}


def pdf_file(name: str, text: str):
    return ("files", (name, make_pdf(text), "application/pdf"))


def screen(client, files, **extra):
    return client.post("/screen", data={**JOB, **extra}, files=files, headers=HEADERS)


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_screen_missing_api_key(client):
    response = client.post("/screen", data=JOB, files=[pdf_file("cv.pdf", STRONG_CV)])
    assert response.status_code == 422


def test_ranks_strong_candidate_first(client):
    response = screen(client, [pdf_file("erika.pdf", WEAK_CV), pdf_file("max.pdf", STRONG_CV)])

    assert response.status_code == 200
    data = response.json()
    assert data["total_candidates"] == 2
    assert data["requirements_source"] == "llm_extracted"
    assert "human_review_notice" in data and data["human_review_notice"]

    first, second = data["ranked_candidates"]
    assert first["filename"] == "max.pdf"
    assert first["score"] == 100
    assert first["match_level"] == "strong_match"
    assert first["must_haves_met"] == first["must_haves_total"] == 2
    assert all(a["evidence_verified"] for a in first["assessments"])

    assert second["filename"] == "erika.pdf"
    assert second["score"] == 0
    assert second["match_level"] == "weak_match"


def test_response_has_no_hire_decision(client):
    data = screen(client, [pdf_file("max.pdf", STRONG_CV)]).json()
    candidate = data["ranked_candidates"][0]
    assert "recommendation" not in candidate
    assert "Hire" not in json.dumps(data)


def test_llm_never_sees_personal_data(client, fake_llm):
    screen(client, [pdf_file("max_mustermann_cv.pdf", STRONG_CV)])

    seen = fake_llm.seen_cv_texts[0]
    for personal in ["Max", "Mustermann", "max.mustermann@example.com", "1234567", "01.02.1995", "German", "Mr."]:
        assert personal not in seen
    assert "Python" in seen and "Airflow" in seen


def test_redaction_counts_are_reported(client):
    candidate = screen(client, [pdf_file("max.pdf", STRONG_CV)]).json()["ranked_candidates"][0]
    redactions = candidate["redactions"]
    for category in ["email", "phone", "date_of_birth", "personal_attribute", "name"]:
        assert redactions.get(category, 0) >= 1, category


def test_hallucinated_evidence_is_downgraded(client, fake_llm):
    fake_llm.hallucinate = True
    candidate = screen(client, [pdf_file("erika.pdf", WEAK_CV)]).json()["ranked_candidates"][0]

    assert "unverified_evidence" in candidate["flags"]
    assert all(a["status"] == "partial" and not a["evidence_verified"] for a in candidate["assessments"])
    assert candidate["score"] == 50
    assert candidate["match_level"] != "strong_match"


def test_prompt_injection_goes_to_manual_review(client):
    data = screen(client, [pdf_file("max.pdf", STRONG_CV), pdf_file("sneaky.pdf", INJECTION_CV)]).json()
    sneaky = data["ranked_candidates"][-1]

    assert sneaky["filename"] == "sneaky.pdf"
    assert "possible_prompt_injection" in sneaky["flags"]
    assert sneaky["match_level"] == "manual_review_required"


def test_non_pdf_file_is_flagged_not_crashed(client):
    files = [pdf_file("max.pdf", STRONG_CV), ("files", ("cv.docx", b"not a pdf", "application/pdf"))]
    data = screen(client, files).json()
    broken = data["ranked_candidates"][-1]

    assert broken["filename"] == "cv.docx"
    assert broken["flags"] == ["unreadable_file"]
    assert broken["match_level"] == "manual_review_required"


def test_scanned_cv_without_text_is_flagged(client):
    data = screen(client, [pdf_file("scan.pdf", "")]).json()
    assert data["ranked_candidates"][0]["flags"] == ["no_extractable_text"]


def test_recruiter_requirements_skip_extraction(client, fake_llm):
    data = screen(
        client, [pdf_file("max.pdf", STRONG_CV)], must_have="Python, Docker", nice_to_have="Spark"
    ).json()

    assert fake_llm.extract_calls == 0
    assert data["requirements_source"] == "recruiter"
    assert [(r["name"], r["priority"]) for r in data["requirements"]] == [
        ("Python", "must_have"), ("Docker", "must_have"), ("Spark", "nice_to_have"),
    ]


def test_invalid_api_key_returns_401(client, fake_llm):
    fake_llm.error = LLMAuthError("The Groq API key was rejected.")
    response = screen(client, [pdf_file("max.pdf", STRONG_CV)])
    assert response.status_code == 401


def test_rate_limit_returns_429(client, fake_llm):
    fake_llm.error = LLMRateLimitError("Groq rate limit reached.")
    response = screen(client, [pdf_file("max.pdf", STRONG_CV)])
    assert response.status_code == 429


def test_too_many_files_rejected(client):
    response = screen(client, [pdf_file(f"cv{i}.pdf", STRONG_CV) for i in range(6)])
    assert response.status_code == 400


def test_oversized_file_rejected(client):
    big = ("files", ("big.pdf", b"%PDF" + b"0" * (2 * 1024 * 1024), "application/pdf"))
    response = screen(client, [big])
    assert response.status_code == 413


def test_audit_log_has_no_personal_data(client, settings):
    data = screen(client, [pdf_file("max_mustermann_cv.pdf", STRONG_CV)]).json()

    entry = client.get(f"/audit/{data['run_id']}").json()
    assert entry["run_id"] == data["run_id"]
    assert entry["model"] == "fake-model"
    assert entry["candidates"][0]["score"] == data["ranked_candidates"][0]["score"]
    assert len(entry["candidates"][0]["file_sha256"]) == 64

    raw_log = open(settings.audit_log_path, encoding="utf-8").read()
    for personal in ["Mustermann", "max_mustermann_cv.pdf", "example.com", "Built ETL pipelines"]:
        assert personal not in raw_log


def test_unknown_audit_run_returns_404(client):
    assert client.get("/audit/does-not-exist").status_code == 404
