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
    poll_success = _response({"status": "succeeded", "output": ["hello", " world"]})

    with patch("requests.request", side_effect=[create_resp, poll_fail, poll_success]):
        with patch("time.sleep"):  # don't actually wait during tests
            output = client.run("meta/meta-llama-3-70b-instruct", {"prompt": "hi"})

    assert output == "hello world"


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
