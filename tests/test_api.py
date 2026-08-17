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
