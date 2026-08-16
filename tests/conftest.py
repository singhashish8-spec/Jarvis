"""Shared pytest fixtures.

Tests run fully offline: placeholder-but-valid credentials let the
Supabase/boto3 clients construct without error, and the `client`
fixture stubs out every external network call (Supabase, R2, and every
agent's Replicate call) so CI never depends on — or pays for — real
external services.
"""

import os

os.environ.setdefault("ENV", "testing")
os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
# supabase-py validates the key looks like a JWT (header.payload.signature)
# before it will construct a client, so a plain string won't pass.
os.environ.setdefault("SUPABASE_KEY", "test.payload.signature")
os.environ.setdefault("CLOUDFLARE_R2_ACCOUNT_ID", "test-account-id")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-access-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret-key")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET_NAME", "jarvis-data-test")
os.environ.setdefault(
    "CLOUDFLARE_R2_ENDPOINT", "https://test-account-id.r2.cloudflarestorage.com"
)
os.environ.setdefault("REPLICATE_API_KEY", "test-replicate-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-flask-sessions")

import pytest  # noqa: E402

from src.main import (  # noqa: E402
    app,
    brainstorm_agent,
    coder_agent,
    db_client,
    deployer_agent,
    document_agent,
    qa_agent,
    r2_client,
    tester_agent,
)

ALL_AGENTS = [
    brainstorm_agent,
    coder_agent,
    tester_agent,
    deployer_agent,
    document_agent,
    qa_agent,
]


@pytest.fixture
def client(monkeypatch):
    """Flask test client with every external call stubbed."""
    app.config["TESTING"] = True

    monkeypatch.setattr(db_client, "health_check", lambda: True)
    monkeypatch.setattr(r2_client, "health_check", lambda: True)
    monkeypatch.setattr(db_client, "save_task", lambda **kwargs: "test-task-id")
    monkeypatch.setattr(r2_client, "save_task_output", lambda *args, **kwargs: True)

    for agent in ALL_AGENTS:
        monkeypatch.setattr(agent, "verify_api_key", lambda: True)
        monkeypatch.setattr(
            agent.replicate_client, "run", lambda *a, **kw: "mocked model output"
        )

    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def sample_brainstorm_input():
    return {
        "topic": "Warehouse design",
        "context": "50,000 sq ft industrial",
        "style": "detailed",
    }
