"""Tests for the Flask API endpoints. All Replicate/DB/R2 calls are
stubbed by the `client` fixture (see conftest.py), so these run
offline and cost nothing."""

import json


def test_dashboard_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"JARVIS" in response.data
    assert response.content_type.startswith("text/html")


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_status_endpoint(client):
    response = client.get("/status")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "operational"
    assert data["components"] == {
        "database": "healthy",
        "replicate": "healthy",
        "storage": "healthy",
    }


def test_usage_endpoint(client):
    response = client.get("/api/usage")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "tokens_used_today" in data
    assert "tokens_used_total" in data
    assert "estimated_cost_usd_total" in data
    assert "credit_limit_usd" in data
    assert "cost_note" in data


def test_usage_endpoint_no_limit_set_means_no_remaining(client, monkeypatch):
    from src.config import config

    monkeypatch.setattr(config, "REPLICATE_CREDIT_LIMIT_USD", None)
    response = client.get("/api/usage")
    data = json.loads(response.data)
    assert data["credit_limit_usd"] is None
    assert data["credit_remaining_usd"] is None


def test_usage_endpoint_computes_remaining_when_limit_set(client, monkeypatch):
    from src.config import config

    monkeypatch.setattr(config, "REPLICATE_CREDIT_LIMIT_USD", 10.0)
    response = client.get("/api/usage")
    data = json.loads(response.data)
    assert data["credit_limit_usd"] == 10.0
    assert data["credit_remaining_usd"] == 10.0 - data["estimated_cost_usd_total"]


def test_usage_endpoint_includes_by_agent_breakdown(client, monkeypatch):
    from src.main import db_client

    monkeypatch.setattr(
        db_client,
        "get_usage_by_agent_today",
        lambda: [{"agent_type": "coder", "tokens_used": 50, "cost": 0.005}],
    )
    data = json.loads(client.get("/api/usage").data)
    assert data["by_agent"] == [
        {"agent_type": "coder", "tokens_used": 50, "cost": 0.005}
    ]


def test_usage_endpoint_includes_rate_limit_status_when_configured(client):
    client.post(
        "/api/settings",
        data=json.dumps({"rate_limit_per_minute": 5}),
        content_type="application/json",
    )
    data = json.loads(client.get("/api/usage").data)
    assert data["rate_limit"]["limit_per_minute"] == 5
    assert data["rate_limit"]["current"] == 0


def test_usage_endpoint_rate_limit_status_null_when_unset(client):
    data = json.loads(client.get("/api/usage").data)
    assert data["rate_limit"] == {"limit_per_minute": None, "current": 0}


def test_storage_endpoint_returns_r2_and_supabase_stats(client, monkeypatch):
    from src.main import db_client, r2_client

    monkeypatch.setattr(
        r2_client,
        "get_storage_stats",
        lambda max_objects=5000: {
            "total_bytes": 4096,
            "object_count": 3,
            "truncated": False,
        },
    )
    monkeypatch.setattr(
        db_client, "get_table_counts", lambda: {"tasks": 12, "usage": 3, "skills": 2}
    )
    response = client.get("/api/storage")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["r2"] == {"total_bytes": 4096, "object_count": 3, "truncated": False}
    assert data["supabase_tables"] == {"tasks": 12, "usage": 3, "skills": 2}


# ---- Dropbox connector ----


def test_dropbox_status_not_configured_by_default(client):
    response = client.get("/api/connectors/dropbox/status")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data == {"configured": False, "connected": False, "account_email": None}


def test_dropbox_status_connected(client, monkeypatch):
    from src.main import db_client, dropbox_client

    monkeypatch.setattr(dropbox_client, "is_configured", lambda: True)
    db_client.set_setting("dropbox_refresh_token", "rt")
    db_client.set_setting("dropbox_account_email", "user@example.com")

    response = client.get("/api/connectors/dropbox/status")
    data = json.loads(response.data)
    assert data == {
        "configured": True,
        "connected": True,
        "account_email": "user@example.com",
    }


def test_dropbox_authorize_rejects_when_not_configured(client):
    response = client.get("/api/connectors/dropbox/authorize")
    assert response.status_code == 400


def test_dropbox_authorize_redirects_when_configured(client, monkeypatch):
    from src.main import dropbox_client

    monkeypatch.setattr(dropbox_client, "is_configured", lambda: True)
    response = client.get("/api/connectors/dropbox/authorize")
    assert response.status_code == 302
    assert "dropbox.com/oauth2/authorize" in response.headers["Location"]


def test_dropbox_callback_saves_tokens_and_redirects(client, monkeypatch):
    from src.main import db_client, dropbox_client

    monkeypatch.setattr(
        dropbox_client,
        "exchange_code",
        lambda code, redirect_uri: {"access_token": "at", "refresh_token": "rt"},
    )
    monkeypatch.setattr(
        dropbox_client, "get_account_email", lambda access_token: "user@example.com"
    )

    response = client.get("/api/connectors/dropbox/callback?code=abc123")
    assert response.status_code == 302
    assert "status=connected" in response.headers["Location"]
    assert db_client.get_setting("dropbox_refresh_token") == "rt"
    assert db_client.get_setting("dropbox_account_email") == "user@example.com"


def test_dropbox_callback_handles_denied_access(client):
    response = client.get("/api/connectors/dropbox/callback?error=access_denied")
    assert response.status_code == 302
    assert "status=error" in response.headers["Location"]


def test_dropbox_callback_handles_exchange_failure(client, monkeypatch):
    from src.main import dropbox_client

    def _boom(code, redirect_uri):
        raise RuntimeError("network error")

    monkeypatch.setattr(dropbox_client, "exchange_code", _boom)
    response = client.get("/api/connectors/dropbox/callback?code=abc123")
    assert response.status_code == 302
    assert "status=error" in response.headers["Location"]


def test_dropbox_disconnect_clears_stored_tokens(client):
    from src.main import db_client

    db_client.set_setting("dropbox_refresh_token", "rt")
    db_client.set_setting("dropbox_account_email", "user@example.com")

    response = client.post("/api/connectors/dropbox/disconnect")
    assert response.status_code == 200
    assert db_client.get_setting("dropbox_refresh_token") == ""

    status = json.loads(client.get("/api/connectors/dropbox/status").data)
    assert status["connected"] is False


def test_dropbox_files_requires_connection(client):
    response = client.get("/api/connectors/dropbox/files")
    assert response.status_code == 400


def test_dropbox_files_lists_entries_when_connected(client, monkeypatch):
    from src.main import db_client, dropbox_client

    db_client.set_setting("dropbox_refresh_token", "rt")
    monkeypatch.setattr(
        dropbox_client, "refresh_access_token", lambda refresh_token: "fresh-at"
    )
    monkeypatch.setattr(
        dropbox_client,
        "list_folder",
        lambda access_token, path="": [
            {"name": "notes.txt", "path": "/notes.txt", "is_folder": False, "size": 42}
        ],
    )

    response = client.get("/api/connectors/dropbox/files")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["entries"][0]["name"] == "notes.txt"


def test_dropbox_pull_requires_path(client):
    from src.main import db_client

    db_client.set_setting("dropbox_refresh_token", "rt")
    response = client.post("/api/connectors/dropbox/pull", json={})
    assert response.status_code == 400


def test_dropbox_pull_returns_file_content(client, monkeypatch):
    from src.main import db_client, dropbox_client

    db_client.set_setting("dropbox_refresh_token", "rt")
    monkeypatch.setattr(
        dropbox_client, "refresh_access_token", lambda refresh_token: "fresh-at"
    )
    monkeypatch.setattr(
        dropbox_client,
        "download_file_text",
        lambda access_token, path: "file contents here",
    )

    response = client.post("/api/connectors/dropbox/pull", json={"path": "/notes.txt"})
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["content"] == "file contents here"


def test_set_credit_limit_saves_and_usage_reflects_it(client):
    response = client.post(
        "/api/settings/credit-limit",
        data=json.dumps({"credit_limit_usd": 15.5}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert json.loads(response.data)["credit_limit_usd"] == 15.5

    usage = json.loads(client.get("/api/usage").data)
    assert usage["credit_limit_usd"] == 15.5


def test_set_credit_limit_overrides_env_var(client, monkeypatch):
    from src.config import config

    monkeypatch.setattr(config, "REPLICATE_CREDIT_LIMIT_USD", 5.0)
    client.post(
        "/api/settings/credit-limit",
        data=json.dumps({"credit_limit_usd": 50.0}),
        content_type="application/json",
    )
    usage = json.loads(client.get("/api/usage").data)
    assert usage["credit_limit_usd"] == 50.0


def test_set_credit_limit_null_clears_override(client):
    client.post(
        "/api/settings/credit-limit",
        data=json.dumps({"credit_limit_usd": 20.0}),
        content_type="application/json",
    )
    response = client.post(
        "/api/settings/credit-limit",
        data=json.dumps({"credit_limit_usd": None}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert json.loads(response.data)["credit_limit_usd"] is None

    usage = json.loads(client.get("/api/usage").data)
    assert usage["credit_limit_usd"] is None


def test_set_credit_limit_rejects_negative(client):
    response = client.post(
        "/api/settings/credit-limit",
        data=json.dumps({"credit_limit_usd": -5}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_set_credit_limit_rejects_non_numeric(client):
    response = client.post(
        "/api/settings/credit-limit",
        data=json.dumps({"credit_limit_usd": "not a number"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_get_settings_returns_categories_and_schema(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["categories"]
    keys = [s["key"] for s in data["settings"]]
    assert "credit_limit_usd" in keys
    assert "custom_instructions" in keys
    for entry in data["settings"]:
        assert "note" in entry
        assert "costs_tokens" in entry


def test_post_settings_bulk_update_saves_and_validates(client):
    response = client.post(
        "/api/settings",
        data=json.dumps(
            {"rate_limit_per_minute": 10, "webhook_url": "https://example.com/hook"}
        ),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert set(json.loads(response.data)["saved"]) == {
        "rate_limit_per_minute",
        "webhook_url",
    }

    settings = {
        s["key"]: s["value"]
        for s in json.loads(client.get("/api/settings").data)["settings"]
    }
    assert settings["rate_limit_per_minute"] == 10.0
    assert settings["webhook_url"] == "https://example.com/hook"


def test_post_settings_rejects_bad_value_in_batch(client):
    response = client.post(
        "/api/settings",
        data=json.dumps({"budget_alert_threshold_pct": 500}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_post_settings_rejects_empty_body(client):
    response = client.post(
        "/api/settings", data=json.dumps({}), content_type="application/json"
    )
    assert response.status_code == 400


def test_settings_reset_clears_saved_values(client):
    client.post(
        "/api/settings",
        data=json.dumps({"custom_instructions": "be terse"}),
        content_type="application/json",
    )
    response = client.post("/api/settings/reset")
    assert response.status_code == 200

    settings = {
        s["key"]: s["value"]
        for s in json.loads(client.get("/api/settings").data)["settings"]
    }
    assert settings["custom_instructions"] == ""


def test_get_agent_config_returns_agents_and_defaults(client):
    response = client.get("/api/settings/agent-config")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert {a["id"] for a in data["agents"]} == {
        "brainstorm",
        "coder",
        "tester",
        "deployer",
        "document",
        "qa",
    }
    assert "brainstorm" in data["defaults"]
    assert data["cheaper_model"]
    assert data["config"] == {}


def test_post_agent_config_saves_and_round_trips(client):
    payload = {
        "coder": {
            "enabled": False,
            "model": "cheaper",
            "temperature": 0.5,
            "max_tokens": 300,
        }
    }
    response = client.post(
        "/api/settings/agent-config",
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert json.loads(response.data)["config"]["coder"]["enabled"] is False

    data = json.loads(client.get("/api/settings/agent-config").data)
    assert data["config"]["coder"]["model"] == "cheaper"


def test_post_agent_config_rejects_invalid_entry(client):
    response = client.post(
        "/api/settings/agent-config",
        data=json.dumps({"coder": {"temperature": 99}}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_disabled_agent_rejects_requests(client):
    client.post(
        "/api/settings/agent-config",
        data=json.dumps({"coder": {"enabled": False}}),
        content_type="application/json",
    )
    response = client.post(
        "/api/agents/code",
        data=json.dumps({"requirements": "a function"}),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_rate_limit_rejects_over_threshold(client, monkeypatch):
    from src.main import db_client

    client.post(
        "/api/settings",
        data=json.dumps({"rate_limit_per_minute": 1}),
        content_type="application/json",
    )
    monkeypatch.setattr(db_client, "count_recent_tasks", lambda seconds: 5)

    response = client.post(
        "/api/agents/brainstorm",
        data=json.dumps({"topic": "test"}),
        content_type="application/json",
    )
    assert response.status_code == 429


def test_rate_limit_disabled_by_default(client, monkeypatch):
    from src.main import db_client

    monkeypatch.setattr(db_client, "count_recent_tasks", lambda seconds: 999)
    response = client.post(
        "/api/agents/brainstorm",
        data=json.dumps({"topic": "test"}),
        content_type="application/json",
    )
    assert response.status_code == 200


def test_list_tasks_endpoint(client):
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert json.loads(response.data)["tasks"] == []


def test_delete_task_endpoint(client):
    response = client.delete("/api/tasks/some-id")
    assert response.status_code == 200
    assert json.loads(response.data)["deleted"] == "some-id"


def test_purge_requires_positive_days(client):
    response = client.post(
        "/api/data/purge", data=json.dumps({}), content_type="application/json"
    )
    assert response.status_code == 400


def test_purge_with_explicit_days(client):
    response = client.post(
        "/api/data/purge",
        data=json.dumps({"older_than_days": 30}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert json.loads(response.data)["deleted_count"] == 0


def test_usage_reset_endpoint(client):
    response = client.post("/api/usage/reset")
    assert response.status_code == 200
    assert json.loads(response.data)["reset"] is True


def test_skills_crud_and_activation_flow(client):
    create_res = client.post(
        "/api/skills",
        data=json.dumps(
            {
                "agent_type": "brainstorm",
                "skill_name": "Terse ideas",
                "template": "Ideas for $topic, keep it short.",
                "description": "Shorter brainstorm output",
            }
        ),
        content_type="application/json",
    )
    assert create_res.status_code == 201
    skill_id = json.loads(create_res.data)["id"]

    list_res = client.get("/api/skills?agent_type=brainstorm")
    body = json.loads(list_res.data)
    assert any(s["id"] == skill_id for s in body["skills"])
    assert body["active_by_agent"]["brainstorm"] is None

    activate_res = client.post(f"/api/skills/{skill_id}/activate")
    assert activate_res.status_code == 200

    list_res2 = json.loads(client.get("/api/skills?agent_type=brainstorm").data)
    assert list_res2["active_by_agent"]["brainstorm"] == skill_id

    deactivate_res = client.post(
        "/api/skills/deactivate",
        data=json.dumps({"agent_type": "brainstorm"}),
        content_type="application/json",
    )
    assert deactivate_res.status_code == 200

    update_res = client.put(
        f"/api/skills/{skill_id}",
        data=json.dumps({"description": "Updated"}),
        content_type="application/json",
    )
    assert update_res.status_code == 200

    delete_res = client.delete(f"/api/skills/{skill_id}")
    assert delete_res.status_code == 200
    final_list = json.loads(client.get("/api/skills?agent_type=brainstorm").data)
    assert not any(s["id"] == skill_id for s in final_list["skills"])


def test_create_skill_requires_valid_agent_type(client):
    response = client.post(
        "/api/skills",
        data=json.dumps({"agent_type": "not-real", "skill_name": "x", "template": "y"}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_create_skill_requires_name_and_template(client):
    response = client.post(
        "/api/skills",
        data=json.dumps({"agent_type": "coder", "skill_name": "", "template": ""}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_activate_nonexistent_skill_returns_404(client):
    response = client.post("/api/skills/does-not-exist/activate")
    assert response.status_code == 404


def test_active_skill_is_actually_used_in_prompt(client, monkeypatch):
    """End-to-end: activating a skill changes the real prompt sent to
    Replicate for that agent's next request."""
    from src.agents.brainstorm_agent import BrainstormAgent
    from src.main import brainstorm_agent

    create_res = client.post(
        "/api/skills",
        data=json.dumps(
            {
                "agent_type": "brainstorm",
                "skill_name": "Custom",
                "template": "SKILL TEMPLATE for $topic",
            }
        ),
        content_type="application/json",
    )
    skill_id = json.loads(create_res.data)["id"]
    client.post(f"/api/skills/{skill_id}/activate")

    captured = {}

    def fake_run(model, input_data, version=None):
        captured["prompt"] = input_data["prompt"]
        return {
            "output": "ok",
            "usage": {
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
                "predict_time_seconds": 0.1,
                "estimated_cost_usd": 0.0001,
            },
        }

    monkeypatch.setattr(brainstorm_agent.replicate_client, "run", fake_run)
    monkeypatch.setattr(BrainstormAgent, "verify_api_key", lambda self: True)

    response = client.post(
        "/api/agents/brainstorm",
        data=json.dumps({"topic": "warehouses"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert captured["prompt"] == "SKILL TEMPLATE for warehouses"


def test_test_webhook_requires_url_configured(client):
    response = client.post("/api/settings/test-webhook")
    assert response.status_code == 400


def test_test_webhook_reports_delivery_failure_gracefully(client):
    client.post(
        "/api/settings",
        data=json.dumps({"webhook_url": "http://127.0.0.1:1/unreachable"}),
        content_type="application/json",
    )
    response = client.post("/api/settings/test-webhook")
    assert response.status_code == 200
    assert json.loads(response.data)["delivered"] is False


def test_webhook_delivered_after_agent_completes(client, monkeypatch):
    delivered = {}

    class FakeResponse:
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        delivered["url"] = url
        delivered["payload"] = json
        return FakeResponse()

    monkeypatch.setattr("src.main.requests.post", fake_post)
    client.post(
        "/api/settings",
        data=json.dumps({"webhook_url": "https://example.com/hook"}),
        content_type="application/json",
    )

    response = client.post(
        "/api/agents/brainstorm",
        data=json.dumps({"topic": "test"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert delivered["url"] == "https://example.com/hook"
    assert delivered["payload"]["agent_type"] == "brainstorm"


def test_brainstorm_endpoint(client, sample_brainstorm_input):
    response = client.post(
        "/api/agents/brainstorm",
        data=json.dumps(sample_brainstorm_input),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["task_id"]
    assert data["output"] == "mocked model output"


def test_brainstorm_missing_topic(client):
    response = client.post(
        "/api/agents/brainstorm",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "error" in data


def test_code_endpoint(client):
    response = client.post(
        "/api/agents/code",
        data=json.dumps({"requirements": "a function that adds two numbers"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["task_id"]


def test_code_missing_requirements(client):
    response = client.post(
        "/api/agents/code", data=json.dumps({}), content_type="application/json"
    )
    assert response.status_code == 400


def test_test_endpoint(client):
    response = client.post(
        "/api/agents/test",
        data=json.dumps({"code": "def add(a, b): return a + b"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["task_id"]


def test_deploy_endpoint(client):
    response = client.post(
        "/api/agents/deploy",
        data=json.dumps({"change_summary": "Add login page"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["task_id"]


def test_document_endpoint(client):
    response = client.post(
        "/api/agents/document",
        data=json.dumps({"subject": "How the login page works"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["task_id"]


def test_qa_endpoint(client):
    response = client.post(
        "/api/agents/qa",
        data=json.dumps({"code": "def add(a, b): return a + b"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["task_id"]


def test_not_found(client):
    response = client.get("/nonexistent")
    assert response.status_code == 404
