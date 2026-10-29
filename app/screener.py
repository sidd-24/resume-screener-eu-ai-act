import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timezone

from app.anonymizer import anonymize
from app.config import Settings
from app.llm import LLMAuthError, LLMClient, LLMRateLimitError
from app.models import (
    CandidateResult,
    MatchLevel,
    MatchStatus,
    Priority,
    Requirement,
    ScreeningResponse,
)
from app.parser import CVParseError, extract_text_from_pdf
from app.safety import detect_prompt_injection
from app.scoring import build_assessments, compute_score, match_level


MIN_CV_TEXT_CHARS = 200
MAX_REQUIREMENTS = 12

HUMAN_REVIEW_NOTICE = (
    "Decision support only. Scores rank how well each CV evidences the listed requirements. "
    "They are not hiring decisions. A recruiter must review every candidate before any decision "
    "(GDPR Art. 22, EU AI Act Art. 14)."
)

MATCH_LEVEL_ORDER = {
    MatchLevel.STRONG: 0,
    MatchLevel.PARTIAL: 1,
    MatchLevel.WEAK: 2,
    MatchLevel.MANUAL_REVIEW: 3,
}


class RequirementExtractionError(Exception):
    """The job description could not be turned into a list of requirements."""


def parse_requirement_list(must_have: str | None, nice_to_have: str | None) -> list[Requirement]:
    """
    Builds requirements from comma- or newline-separated text entered by the recruiter.
    """
    def split(value: str | None) -> list[str]:
        return [item.strip() for item in re.split(r"[,\n;]", value or "") if item.strip()]

    requirements = [Requirement(name=n, priority=Priority.MUST_HAVE) for n in split(must_have)]
    requirements += [Requirement(name=n, priority=Priority.NICE_TO_HAVE) for n in split(nice_to_have)]
    return requirements[:MAX_REQUIREMENTS]


async def _get_requirements(
    llm: LLMClient, job_title: str, job_description: str, must_have: str | None, nice_to_have: str | None
) -> tuple[list[Requirement], str]:
    user_requirements = parse_requirement_list(must_have, nice_to_have)
    if user_requirements:
        return user_requirements, "recruiter"

    try:
        profile = await llm.extract_requirements(job_title, job_description)
    except (LLMAuthError, LLMRateLimitError):
        raise
    except Exception as e:
        raise RequirementExtractionError(f"Could not extract requirements: {e}") from e

    requirements = [r for r in profile.requirements if r.name.strip()][:MAX_REQUIREMENTS]
    if not requirements:
        raise RequirementExtractionError("No requirements found in the job description.")
    return requirements, "llm_extracted"


def _manual_review_result(
    candidate_id: str, filename: str, file_hash: str, requirements: list[Requirement], flag: str, summary: str
) -> CandidateResult:
    must_have_total = sum(r.priority == Priority.MUST_HAVE for r in requirements)
    return CandidateResult(
        candidate_id=candidate_id,
        filename=filename,
        file_sha256=file_hash,
        score=0,
        match_level=MatchLevel.MANUAL_REVIEW,
        must_haves_met=0,
        must_haves_total=must_have_total,
        assessments=[],
        summary=summary,
        flags=[flag],
        redactions={},
    )


async def _screen_one(
    candidate_id: str,
    filename: str,
    content: bytes,
    job_title: str,
    requirements: list[Requirement],
    llm: LLMClient,
    semaphore: asyncio.Semaphore,
    settings: Settings,
) -> CandidateResult:
    file_hash = hashlib.sha256(content).hexdigest()

    try:
        text = await asyncio.to_thread(extract_text_from_pdf, content)
    except CVParseError as e:
        return _manual_review_result(candidate_id, filename, file_hash, requirements, "unreadable_file", str(e))

    if len(text) < MIN_CV_TEXT_CHARS:
        return _manual_review_result(
            candidate_id, filename, file_hash, requirements, "no_extractable_text",
            "Little or no text could be extracted. The CV may be a scanned image; review it manually.",
        )

    flags: list[str] = []
    if detect_prompt_injection(text):
        flags.append("possible_prompt_injection")

    anonymized = anonymize(text, filename)
    cv_text = anonymized.text
    if len(cv_text) > settings.max_cv_chars:
        cv_text = cv_text[: settings.max_cv_chars]
        flags.append("truncated")

    try:
        async with semaphore:
            answer = await llm.assess_candidate(job_title, requirements, cv_text)
    except (LLMAuthError, LLMRateLimitError):
        raise
    except Exception as e:
        result = _manual_review_result(
            candidate_id, filename, file_hash, requirements, "screening_failed",
            f"Automatic screening failed ({type(e).__name__}); review this CV manually.",
        )
        result.redactions = anonymized.redactions
        return result

    assessments, downgraded = build_assessments(requirements, answer.assessments, cv_text)
    if downgraded:
        flags.append("unverified_evidence")

    score = compute_score(assessments)
    must_haves = [a for a in assessments if a.priority == Priority.MUST_HAVE]

    return CandidateResult(
        candidate_id=candidate_id,
        filename=filename,
        file_sha256=file_hash,
        score=score,
        match_level=match_level(score, assessments, flags),
        must_haves_met=sum(a.status == MatchStatus.MET for a in must_haves),
        must_haves_total=len(must_haves),
        assessments=assessments,
        summary=answer.summary,
        flags=flags,
        redactions=anonymized.redactions,
    )


async def screen_candidates(
    uploads: list[tuple[str, bytes]],
    job_title: str,
    job_description: str,
    llm: LLMClient,
    settings: Settings,
    must_have: str | None = None,
    nice_to_have: str | None = None,
) -> ScreeningResponse:
    """
    Screens every uploaded CV against the job requirements.
    uploads is a list of (filename, file_bytes) tuples.
    """
    requirements, source = await _get_requirements(llm, job_title, job_description, must_have, nice_to_have)

    semaphore = asyncio.Semaphore(settings.max_concurrency)
    results = await asyncio.gather(*[
        _screen_one(f"Candidate {i}", filename, content, job_title, requirements, llm, semaphore, settings)
        for i, (filename, content) in enumerate(uploads, start=1)
    ])

    ranked = sorted(results, key=lambda r: (MATCH_LEVEL_ORDER[r.match_level], -r.score))

    return ScreeningResponse(
        run_id=uuid.uuid4().hex,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        job_title=job_title,
        model=llm.model_name,
        requirements_source=source,
        requirements=requirements,
        total_candidates=len(ranked),
        ranked_candidates=ranked,
        human_review_notice=HUMAN_REVIEW_NOTICE,
    )
