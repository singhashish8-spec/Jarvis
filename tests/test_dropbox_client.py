"""Tests for DropboxClient. requests.post is mocked throughout — no
real network calls, no real Dropbox account needed."""

import os
from unittest.mock import MagicMock, patch

from src.connectors.dropbox_client import DropboxClient


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
        os.environ["DROPBOX_APP_KEY"] = "test-app-key"
        os.environ["DROPBOX_APP_SECRET"] = "test-app-secret"
    else:
        os.environ.pop("DROPBOX_APP_KEY", None)
        os.environ.pop("DROPBOX_APP_SECRET", None)
    return DropboxClient()


def test_is_configured_true_when_both_env_vars_set():
    assert _client(configured=True).is_configured() is True


def test_is_configured_false_when_missing():
    assert _client(configured=False).is_configured() is False


def test_get_authorize_url_includes_offline_access_and_redirect():
    client = _client()
    url = client.get_authorize_url(
        "https://jarvis.example.com/api/connectors/dropbox/callback"
    )
    assert url.startswith("https://www.dropbox.com/oauth2/authorize?")
    assert "token_access_type=offline" in url
    assert "client_id=test-app-key" in url
    assert "callback" in url


def test_exchange_code_returns_tokens():
    client = _client()
    with patch(
        "requests.post",
        return_value=_response({"access_token": "at", "refresh_token": "rt"}),
    ):
        tokens = client.exchange_code("auth-code", "https://example.com/callback")
    assert tokens["access_token"] == "at"
    assert tokens["refresh_token"] == "rt"


def test_refresh_access_token_returns_access_token():
    client = _client()
    with patch(
        "requests.post", return_value=_response({"access_token": "fresh-token"})
    ):
        token = client.refresh_access_token("stored-refresh-token")
    assert token == "fresh-token"


def test_get_account_email():
    client = _client()
    with patch("requests.post", return_value=_response({"email": "user@example.com"})):
        email = client.get_account_email("at")
    assert email == "user@example.com"


def test_list_folder_normalizes_entries():
    client = _client()
    raw = {
        "entries": [
            {"name": "Projects", "path_display": "/Projects", ".tag": "folder"},
            {
                "name": "notes.txt",
                "path_display": "/notes.txt",
                ".tag": "file",
                "size": 1234,
            },
        ]
    }
    with patch("requests.post", return_value=_response(raw)):
        entries = client.list_folder("at", path="")
    assert entries == [
        {"name": "Projects", "path": "/Projects", "is_folder": True, "size": None},
        {"name": "notes.txt", "path": "/notes.txt", "is_folder": False, "size": 1234},
    ]


def test_download_file_text_decodes_and_caps_size():
    client = _client()
    big_content = ("x" * 50).encode("utf-8")
    with patch("requests.post", return_value=_response(content=big_content)):
        result = client.download_file_text("at", "/notes.txt")
    assert result == {"content": "x" * 50, "truncated": False}


def test_download_file_text_truncates_to_max_bytes():
    client = _client()
    from src.connectors.dropbox_client import MAX_FILE_BYTES

    oversized = b"a" * (MAX_FILE_BYTES + 500)
    with patch("requests.post", return_value=_response(content=oversized)):
        result = client.download_file_text("at", "/big.txt")
    assert len(result["content"]) == MAX_FILE_BYTES
    assert result["truncated"] is True
