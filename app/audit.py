"""
Append-only audit trail of screening runs (JSON Lines).

Records what was decided and how, without storing CV text or personal
data: files are identified by their SHA-256 hash, the job description
by its hash, and evidence quotes and summaries are left out.
"""
import hashlib
import json
import threading
from pathlib import Path

from app.llm import PROMPT_VERSION
from app.models import ScreeningResponse


class AuditLog:
    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(self, response: ScreeningResponse, job_description: str) -> dict:
        entry = {
            "run_id": response.run_id,
            "created_at": response.created_at,
            "job_title": response.job_title,
            "job_description_sha256": hashlib.sha256(job_description.encode("utf-8")).hexdigest(),
            "model": response.model,
            "prompt_version": PROMPT_VERSION,
            "requirements_source": response.requirements_source,
            "requirements": [r.model_dump(mode="json") for r in response.requirements],
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "file_sha256": c.file_sha256,
                    "score": c.score,
                    "match_level": c.match_level.value,
                    "flags": c.flags,
                    "redactions": c.redactions,
                    "assessments": [
                        {
                            "requirement": a.requirement,
                            "status": a.status.value,
                            "evidence_verified": a.evidence_verified,
                        }
                        for a in c.assessments
                    ],
                }
                for c in response.ranked_candidates
            ],
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def get(self, run_id: str) -> dict | None:
        if not self.path.exists():
            return None
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("run_id") == run_id:
                    return entry
        return None
