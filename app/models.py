from pydantic import BaseModel


class CandidateResult(BaseModel):
    name: str
    score: int
    matching_skills: list[str]
    missing_skills: list[str]
    summary: str
    recommendation: str


class ScreeningResponse(BaseModel):
    job_title: str
    total_candidates: int
    ranked_candidates: list[CandidateResult]