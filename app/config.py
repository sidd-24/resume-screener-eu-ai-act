import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    groq_model: str
    max_files: int
    max_file_mb: float
    max_concurrency: int
    max_cv_chars: int
    audit_log_path: str


def get_settings() -> Settings:
    """
    Reads settings from environment variables, falling back to safe defaults.
    """
    return Settings(
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        max_files=int(os.getenv("MAX_FILES", "20")),
        max_file_mb=float(os.getenv("MAX_FILE_MB", "5")),
        max_concurrency=int(os.getenv("MAX_CONCURRENCY", "3")),
        max_cv_chars=int(os.getenv("MAX_CV_CHARS", "15000")),
        audit_log_path=os.getenv("AUDIT_LOG_PATH", "audit/screening_log.jsonl"),
    )
