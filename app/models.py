from enum import Enum
from pydantic import BaseModel, Field


class Priority(str, Enum):
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class MatchStatus(str, Enum):
    MET = "met"
    PARTIAL = "partial"
    NOT_MET = "not_met"


class MatchLevel(str, Enum):
    STRONG = "strong_match"
    PARTIAL = "partial_match"
    WEAK = "weak_match"
    MANUAL_REVIEW = "manual_review_required"


class Requirement(BaseModel):
    name: str = Field(description="Short name of one skill, qualification or experience requirement")
    priority: Priority


class JobProfile(BaseModel):
    """Requirements extracted from a job description."""
    requirements: list[Requirement]


class LLMRequirementAssessment(BaseModel):
    requirement: str = Field(description="The requirement name, exactly as given")
    status: MatchStatus
    evidence: str = Field(
        default="",
        description="A short quote copied word for word from the CV that proves the status. Empty if not met.",
    )


class LLMCandidateAssessment(BaseModel):
    """Assessment of one CV against the job requirements."""
    assessments: list[LLMRequirementAssessment]
    summary: str = Field(description="Two sentences on job-relevant experience only. No personal attributes.")


class RequirementAssessment(BaseModel):
    requirement: str
    priority: Priority
    status: MatchStatus
    evidence: str = ""
    evidence_verified: bool = False


class CandidateResult(BaseModel):
    candidate_id: str
    filename: str
    file_sha256: str
    score: int = Field(ge=0, le=100)
    match_level: MatchLevel
    must_haves_met: int
    must_haves_total: int
    assessments: list[RequirementAssessment]
    summary: str
    flags: list[str]
    redactions: dict[str, int]


class ScreeningResponse(BaseModel):
    run_id: str
    created_at: str
    job_title: str
    model: str
    requirements_source: str
    requirements: list[Requirement]
    total_candidates: int
    ranked_candidates: list[CandidateResult]
    human_review_notice: str
