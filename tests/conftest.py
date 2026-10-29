import pytest
from fastapi.testclient import TestClient

from app.audit import AuditLog
from app.config import Settings, get_settings
from app.main import app, get_audit_log, get_llm_factory
from tests.helpers import FakeLLM


@pytest.fixture
def settings(tmp_path):
    return Settings(
        groq_model="fake-model",
        max_files=5,
        max_file_mb=1,
        max_concurrency=2,
        max_cv_chars=15000,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(settings, fake_llm):
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_llm_factory] = lambda: (lambda api_key: fake_llm)
    app.dependency_overrides[get_audit_log] = lambda: AuditLog(settings.audit_log_path)
    yield TestClient(app)
    app.dependency_overrides.clear()

