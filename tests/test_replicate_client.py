"""Tests for ReplicateClient, especially the retry logic that a real
connection reset (seen live while testing the dashboard) exposed as
missing. requests.request is mocked throughout — no real network calls."""

import os
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

from src.agents.replicate_client import ReplicateClient

os.environ.setdefault("REPLICATE_API_KEY", "test-replicate-key")


def _response(json_body, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_body
    resp.raise_for_status = (
        MagicMock() if status_ok else MagicMock(side_effect=Exception("bad status"))
    )
    return resp


def test_run_retries_after_transient_connection_error():
    """A connection reset on one poll shouldn't fail the whole request
    if a retry succeeds — this is exactly what happened live: Replicate
    kept running the prediction, only our GET got dropped."""
    client = ReplicateClient()

    create_resp = _response(
        {
            "status": "starting",
            "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
        }
    )
    poll_fail = RequestsConnectionError("Connection reset by peer")
    poll_success = _response(
        {
            "status": "succeeded",
            "output": ["hello", " world"],
            "metrics": {
                "input_token_count": 5,
                "output_token_count": 2,
                "predict_time": 1.5,
            },
        }
    )

    with patch("requests.request", side_effect=[create_resp, poll_fail, poll_success]):
        with patch("time.sleep"):  # don't actually wait during tests
            result = client.run("meta/meta-llama-3-70b-instruct", {"prompt": "hi"})

    assert result["output"] == "hello world"
    assert result["usage"]["input_tokens"] == 5
    assert result["usage"]["output_tokens"] == 2
    assert result["usage"]["total_tokens"] == 7
    assert result["usage"]["predict_time_seconds"] == 1.5
    assert result["usage"]["estimated_cost_usd"] > 0


def test_run_defaults_usage_to_zero_when_metrics_missing():
    """Some models (e.g. image models, or an unexpected API response)
    don't report metrics at all — usage should degrade to zeros rather
    than raising."""
    client = ReplicateClient()
    create_resp = _response(
        {
            "status": "starting",
            "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
        }
    )
    success_resp = _response({"status": "succeeded", "output": "no metrics here"})

    with patch("requests.request", side_effect=[create_resp, success_resp]):
        with patch("time.sleep"):
            result = client.run("meta/meta-llama-3-70b-instruct", {"prompt": "hi"})

    assert result["output"] == "no metrics here"
    assert result["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "predict_time_seconds": 0.0,
        "estimated_cost_usd": 0.0,
    }


def test_run_raises_after_exhausting_retries():
    client = ReplicateClient()
    create_resp = _response(
        {
            "status": "starting",
            "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
        }
    )

    with patch(
        "requests.request",
        side_effect=[create_resp] + [RequestsConnectionError("down")] * 5,
    ):
        with patch("time.sleep"):
            with pytest.raises(RequestsConnectionError):
                client.run("meta/meta-llama-3-70b-instruct", {"prompt": "hi"})


def test_run_raises_on_model_failure_without_retrying():
    """A model that actually fails (not a network blip) should raise
    immediately — retrying wouldn't help and would just waste time."""
    client = ReplicateClient()
    create_resp = _response(
        {
            "status": "starting",
            "urls": {"get": "https://api.replicate.com/v1/predictions/abc"},
        }
    )
    fail_resp = _response({"status": "failed", "error": "model exploded"})

    with patch("requests.request", side_effect=[create_resp, fail_resp]):
        with patch("time.sleep"):
            with pytest.raises(RuntimeError, match="model exploded"):
                client.run("meta/meta-llama-3-70b-instruct", {"prompt": "hi"})
