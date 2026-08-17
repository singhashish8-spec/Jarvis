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
    monkeypatch.setattr(db_client, "record_usage", lambda **kwargs: None)
    monkeypatch.setattr(
        db_client,
        "get_usage_summary",
        lambda: {
            "tokens_used_today": 0,
            "tokens_used_total": 0,
            "estimated_cost_usd_today": 0.0,
            "estimated_cost_usd_total": 0.0,
        },
    )
    monkeypatch.setattr(db_client, "get_usage_by_agent_today", lambda: [])
    monkeypatch.setattr(
        db_client,
        "get_table_counts",
        lambda: {"tasks": 0, "usage": 0, "skills": 0},
    )
    monkeypatch.setattr(
        r2_client,
        "get_storage_stats",
        lambda max_objects=5000: {
            "total_bytes": 0,
            "object_count": 0,
            "truncated": False,
        },
    )
    monkeypatch.setattr(r2_client, "save_task_output", lambda *args, **kwargs: True)

    # Fake settings store, in-memory per test, so POST -> GET round trips
    # (e.g. saving a credit limit) behave like the real DB without one.
    fake_settings: dict = {}
    monkeypatch.setattr(db_client, "get_setting", lambda key: fake_settings.get(key))
    monkeypatch.setattr(
        db_client,
        "set_setting",
        lambda key, value: fake_settings.__setitem__(key, value),
    )
    monkeypatch.setattr(db_client, "reset_all_settings", lambda: fake_settings.clear())

    # Fake tasks store, so Data Controls' task browser and rate limiting
    # have something real to read without a live DB.
    fake_tasks: list = []
    monkeypatch.setattr(
        db_client, "list_tasks", lambda agent_type=None, limit=100: list(fake_tasks)
    )

    def _delete_task(task_id):
        # Matches the real DatabaseClient: a Supabase `delete().eq(...)`
        # call succeeds (True) whether or not a row actually matched —
        # there's no server-side "not found" signal to check against.
        fake_tasks[:] = [t for t in fake_tasks if t["id"] != task_id]
        return True

    monkeypatch.setattr(db_client, "delete_task", _delete_task)
    monkeypatch.setattr(
        db_client, "count_recent_tasks", lambda seconds: len(fake_tasks)
    )
    monkeypatch.setattr(db_client, "purge_tasks_older_than", lambda days: 0)
    monkeypatch.setattr(db_client, "reset_usage", lambda: None)

    # Fake skills store, in-memory per test.
    fake_skills: list = []

    def _create_skill(agent_type, skill_name, template, description="", version="1.0"):
        skill_id = f"skill-{len(fake_skills) + 1}"
        fake_skills.append(
            {
                "id": skill_id,
                "agent_type": agent_type,
                "skill_name": skill_name,
                "template": template,
                "description": description,
                "version": version,
                "is_active": True,
            }
        )
        return skill_id

    def _get_skill(skill_id):
        return next((s for s in fake_skills if s["id"] == skill_id), None)

    def _update_skill(skill_id, **fields):
        skill = _get_skill(skill_id)
        if skill:
            skill.update(fields)

    def _delete_skill(skill_id):
        fake_skills[:] = [s for s in fake_skills if s["id"] != skill_id]

    monkeypatch.setattr(
        db_client,
        "list_skills",
        lambda agent_type=None: [
            s for s in fake_skills if not agent_type or s["agent_type"] == agent_type
        ],
    )
    monkeypatch.setattr(db_client, "create_skill", _create_skill)
    monkeypatch.setattr(db_client, "get_skill", _get_skill)
    monkeypatch.setattr(db_client, "update_skill", _update_skill)
    monkeypatch.setattr(db_client, "delete_skill", _delete_skill)

    mocked_run_result = {
        "output": "mocked model output",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "predict_time_seconds": 1.0,
            "estimated_cost_usd": 0.0014,
        },
    }
    for agent in ALL_AGENTS:
        monkeypatch.setattr(agent, "verify_api_key", lambda: True)
        monkeypatch.setattr(
            agent.replicate_client, "run", lambda *a, **kw: mocked_run_result
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
