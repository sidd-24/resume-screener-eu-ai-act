from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from app.models import CandidateResult
import json


PROMPT_TEMPLATE = """
You are an expert HR recruiter and technical hiring manager.

Analyze the following CV against the job description and return a structured evaluation.

Job Description:
{job_description}

Candidate CV:
{cv_text}

Respond ONLY with a valid JSON object in this exact format, no extra text:
{{
    "name": "candidate full name or Unknown if not found",
    "score": <integer from 0 to 100>,
    "matching_skills": ["skill1", "skill2"],
    "missing_skills": ["skill1", "skill2"],
    "summary": "2 sentence summary of the candidate",
    "recommendation": "Hire" or "No Hire"
}}
"""


def screen_candidate(cv_text: str, job_description: str, api_key: str) -> CandidateResult:
    llm = ChatGroq(
        api_key=api_key,
        model_name="llama-3.3-70b-versatile",
        temperature=0.1,
    )

    prompt = PromptTemplate.from_template(PROMPT_TEMPLATE)
    chain = prompt | llm

    result = chain.invoke({
        "job_description": job_description,
        "cv_text": cv_text,
    })

    raw = result.content.strip()

    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    data = json.loads(raw)
    return CandidateResult(**data)


def screen_all_candidates(
    cv_texts: list[tuple[str, str]],
    job_description: str,
    api_key: str,
) -> list[CandidateResult]:
    """
    Screen multiple candidates and return them ranked by score.
    cv_texts is a list of (filename, extracted_text) tuples.
    """
    results = []
    for filename, text in cv_texts:
        try:
            result = screen_candidate(text, job_description, api_key)
            results.append(result)
        except Exception as e:
            results.append(CandidateResult(
                name=filename,
                score=0,
                matching_skills=[],
                missing_skills=[],
                summary=f"Could not parse this CV: {str(e)}",
                recommendation="No Hire",
            ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results