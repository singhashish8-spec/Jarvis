"""Tests for the Flask API endpoints."""

import json


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
    assert "task_id" in data
    assert isinstance(data["ideas"], list)
    assert len(data["ideas"]) > 0


def test_brainstorm_missing_topic(client):
    response = client.post(
        "/api/agents/brainstorm",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "error" in data


def test_not_found(client):
    response = client.get("/nonexistent")
    assert response.status_code == 404
