from typing import Callable

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile

from app.audit import AuditLog
from app.config import Settings, get_settings
from app.llm import GroqLLMClient, LLMAuthError, LLMClient, LLMRateLimitError
from app.models import ScreeningResponse
from app.screener import RequirementExtractionError, screen_candidates


app = FastAPI(
    title="Resume Screener under EU AI Act API",
    description=(
        "Ranks CVs against a job description as decision support for recruiters. "
        "Personal data is removed before the LLM sees a CV, every claim is backed by a quote "
        "from the CV, and every run is written to an audit log."
    ),
    version="2.0.0",
)


def get_llm_factory(settings: Settings = Depends(get_settings)) -> Callable[[str], LLMClient]:
    return lambda api_key: GroqLLMClient(api_key=api_key, model_name=settings.groq_model)


def get_audit_log(settings: Settings = Depends(get_settings)) -> AuditLog:
    return AuditLog(settings.audit_log_path)


@app.get("/")
def root():
    return {"status": "ok", "message": "Resume Screener under EU AI Act API is running."}


@app.post("/screen", response_model=ScreeningResponse)
async def screen_resumes(
    job_description: str = Form(...),
    job_title: str = Form(...),
    files: list[UploadFile] = File(...),
    x_api_key: str = Header(...),
    must_have: str | None = Form(None, description="Optional comma-separated must-have requirements"),
    nice_to_have: str | None = Form(None, description="Optional comma-separated nice-to-have requirements"),
    settings: Settings = Depends(get_settings),
    llm_factory: Callable[[str], LLMClient] = Depends(get_llm_factory),
    audit_log: AuditLog = Depends(get_audit_log),
):
    if not x_api_key.strip():
        raise HTTPException(status_code=401, detail="API key is required.")
    if not job_description.strip():
        raise HTTPException(status_code=400, detail="Job description is empty.")
    if len(files) > settings.max_files:
        raise HTTPException(status_code=400, detail=f"Upload at most {settings.max_files} CVs at once.")

    max_bytes = int(settings.max_file_mb * 1024 * 1024)
    uploads = []
    for file in files:
        content = await file.read()
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413, detail=f"{file.filename} is larger than {settings.max_file_mb:g} MB."
            )
        uploads.append((file.filename or "unnamed.pdf", content))

    try:
        response = await screen_candidates(
            uploads=uploads,
            job_title=job_title,
            job_description=job_description,
            llm=llm_factory(x_api_key),
            settings=settings,
            must_have=must_have,
            nice_to_have=nice_to_have,
        )
    except LLMAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except LLMRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except RequirementExtractionError as e:
        raise HTTPException(status_code=502, detail=str(e))

    audit_log.record(response, job_description)
    return response


@app.get("/audit/{run_id}")
def get_audit_entry(run_id: str, audit_log: AuditLog = Depends(get_audit_log)):
    entry = audit_log.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return entry
