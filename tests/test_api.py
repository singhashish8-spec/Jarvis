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
