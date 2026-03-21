from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.models import CandidateResult
import io

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_screen_missing_api_key():
    response = client.post(
        "/screen",
        data={
            "job_description": "We need a Python developer.",
            "job_title": "Python Developer",
        },
        files=[("files", ("cv.pdf", b"fake pdf content", "application/pdf"))],
    )
    assert response.status_code == 422


def test_screen_with_mock():
    mock_result = CandidateResult(
        name="John Doe",
        score=85,
        matching_skills=["Python", "FastAPI"],
        missing_skills=["Docker"],
        summary="Strong candidate with relevant experience.",
        recommendation="Hire",
    )

    with patch("app.main.screen_all_candidates") as mock_screen, \
         patch("app.main.extract_text_from_pdf") as mock_parse:

        mock_parse.return_value = "Fake CV text"
        mock_screen.return_value = [mock_result]

        response = client.post(
            "/screen",
            data={
                "job_description": "We need a Python developer.",
                "job_title": "Python Developer",
            },
            files=[("files", ("cv.pdf", b"fake pdf content", "application/pdf"))],
            headers={"x-api-key": "fake-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_candidates"] == 1
        assert data["ranked_candidates"][0]["name"] == "John Doe"
        assert data["ranked_candidates"][0]["score"] == 85
        assert data["ranked_candidates"][0]["recommendation"] == "Hire"