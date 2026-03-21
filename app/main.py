from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from app.models import ScreeningResponse
from app.parser import extract_text_from_pdf
from app.screener import screen_all_candidates


app = FastAPI(
    title="Resume Screener API",
    description="Upload a job description and multiple CVs to get ranked candidates.",
    version="1.0.0",
)


@app.get("/")
def root():
    return {"status": "ok", "message": "Resume Screener API is running."}


@app.post("/screen", response_model=ScreeningResponse)
async def screen_resumes(
    job_description: str = Form(...),
    job_title: str = Form(...),
    files: list[UploadFile] = File(...),
    x_api_key: str = Header(...),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key is required.")

    if not files:
        raise HTTPException(status_code=400, detail="At least one CV is required.")

    cv_texts = []
    for file in files:
        content = await file.read()
        text = extract_text_from_pdf(content)
        cv_texts.append((file.filename, text))

    ranked = screen_all_candidates(cv_texts, job_description, x_api_key)

    return ScreeningResponse(
        job_title=job_title,
        total_candidates=len(ranked),
        ranked_candidates=ranked,
    )