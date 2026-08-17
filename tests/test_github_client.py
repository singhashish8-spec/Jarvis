"""Tests for GitHubClient. requests.get/post are mocked throughout —
no real network calls, no real GitHub account needed."""

import os
from unittest.mock import MagicMock, patch

from src.connectors.github_client import GitHubClient


def _response(json_body=None, content=None):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    if json_body is not None:
        resp.json.return_value = json_body
    if content is not None:
        resp.content = content
    return resp


def _client(configured=True):
    if configured:
        os.environ["GITHUB_OAUTH_CLIENT_ID"] = "test-client-id"
        os.environ["GITHUB_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    else:
        os.environ.pop("GITHUB_OAUTH_CLIENT_ID", None)
        os.environ.pop("GITHUB_OAUTH_CLIENT_SECRET", None)
    return GitHubClient()


def test_is_configured_true_when_both_env_vars_set():
    assert _client(configured=True).is_configured() is True


def test_is_configured_false_when_missing():
    assert _client(configured=False).is_configured() is False


def test_get_authorize_url_includes_repo_scope_and_redirect():
    client = _client()
    url = client.get_authorize_url(
        "https://jarvis.example.com/api/connectors/github/callback"
    )
    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "scope=repo" in url
    assert "client_id=test-client-id" in url
    assert "callback" in url


def test_exchange_code_returns_access_token():
    client = _client()
    with patch("requests.post", return_value=_response({"access_token": "gho_at"})):
        tokens = client.exchange_code("auth-code", "https://example.com/callback")
    assert tokens["access_token"] == "gho_at"


def test_exchange_code_raises_on_oauth_error():
    client = _client()
    with patch(
        "requests.post",
        return_value=_response(
            {"error": "bad_verification_code", "error_description": "expired code"}
        ),
    ):
        try:
            client.exchange_code("bad-code", "https://example.com/callback")
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "expired code" in str(exc)


def test_get_account_login():
    client = _client()
    with patch("requests.get", return_value=_response({"login": "someuser"})):
        login = client.get_account_login("at")
    assert login == "someuser"


def test_list_repos_normalizes_entries():
    client = _client()
    raw = [
        {"full_name": "someuser/jarvis", "private": True, "default_branch": "main"},
        {"full_name": "someuser/notes", "private": False, "default_branch": "master"},
    ]
    with patch("requests.get", return_value=_response(raw)):
        repos = client.list_repos("at")
    assert repos == [
        {"full_name": "someuser/jarvis", "private": True, "default_branch": "main"},
        {"full_name": "someuser/notes", "private": False, "default_branch": "master"},
    ]


def test_list_path_normalizes_directory_listing():
    client = _client()
    raw = [
        {"name": "src", "path": "src", "type": "dir", "size": 0},
        {"name": "README.md", "path": "README.md", "type": "file", "size": 512},
    ]
    with patch("requests.get", return_value=_response(raw)):
        entries = client.list_path("at", "someuser/jarvis", path="")
    assert entries == [
        {"name": "src", "path": "src", "is_folder": True, "size": 0},
        {"name": "README.md", "path": "README.md", "is_folder": False, "size": 512},
    ]


def test_list_path_wraps_single_file_response_in_a_list():
    client = _client()
    raw = {"name": "README.md", "path": "README.md", "type": "file", "size": 512}
    with patch("requests.get", return_value=_response(raw)):
        entries = client.list_path("at", "someuser/jarvis", path="README.md")
    assert entries == [
        {"name": "README.md", "path": "README.md", "is_folder": False, "size": 512}
    ]


def test_download_file_text_decodes_and_caps_size():
    client = _client()
    content = ("y" * 50).encode("utf-8")
    with patch("requests.get", return_value=_response(content=content)):
        text = client.download_file_text("at", "someuser/jarvis", "README.md")
    assert text == "y" * 50


def test_download_file_text_truncates_to_max_bytes():
    client = _client()
    from src.connectors.github_client import MAX_FILE_BYTES

    oversized = b"a" * (MAX_FILE_BYTES + 500)
    with patch("requests.get", return_value=_response(content=oversized)):
        text = client.download_file_text("at", "someuser/jarvis", "big.txt")
    assert len(text) == MAX_FILE_BYTES
