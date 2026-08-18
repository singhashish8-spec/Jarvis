"""Thin wrapper around Dropbox's OAuth + Files API.

The first real Connector (the other three — Google Drive, Slack,
GitHub — are still placeholders in the dashboard). Scope matches
exactly what the placeholder promised: connect once, browse your
Dropbox, pull a file's text content in as context instead of copying
it by hand.

Auth model: standard OAuth 2.0 authorization-code flow with
`token_access_type=offline`, so the code exchange returns both a
short-lived access token and a long-lived refresh token. Only the
refresh token gets persisted (in the `settings` table, under a key
that isn't part of SETTINGS_SCHEMA — see main.py — so it can never
leak back out through GET /api/settings). Every actual API call first
exchanges that refresh token for a fresh access token rather than
caching one in memory, since Vercel's serverless functions don't
reliably keep process memory between requests (same reasoning as the
rate limiter in main.py).
"""

import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

DROPBOX_AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_API_BASE = "https://api.dropboxapi.com/2"
DROPBOX_CONTENT_BASE = "https://content.dropboxapi.com/2"

# Caps a single pulled file at ~50k tokens worth of text so one click
# can't accidentally blow up a prompt (or the response payload).
MAX_FILE_BYTES = 200_000

REQUEST_TIMEOUT_SECONDS = 20


class DropboxClient:
    """Client for the OAuth handshake and the handful of Files API
    calls the connector needs (list a folder, download a file)."""

    def __init__(self):
        self.app_key = os.getenv("DROPBOX_APP_KEY")
        self.app_secret = os.getenv("DROPBOX_APP_SECRET")

    def is_configured(self) -> bool:
        """True if an app key/secret pair is present (does not verify
        they're valid — that only happens on the first real OAuth
        round trip)."""
        return bool(self.app_key and self.app_secret)

    def get_authorize_url(self, redirect_uri: str) -> str:
        params = {
            "client_id": self.app_key,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "token_access_type": "offline",
        }
        return f"{DROPBOX_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Trades a one-time authorization code for {access_token,
        refresh_token, expires_in, ...}."""
        resp = requests.post(
            DROPBOX_TOKEN_URL,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": self.app_key,
                "client_secret": self.app_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    def refresh_access_token(self, refresh_token: str) -> str:
        """Exchanges the long-lived refresh token for a fresh
        short-lived access token, called before every real API call."""
        resp = requests.post(
            DROPBOX_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.app_key,
                "client_secret": self.app_secret,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def get_account_email(self, access_token: str) -> Optional[str]:
        resp = requests.post(
            f"{DROPBOX_API_BASE}/users/get_current_account",
            headers=self._headers(access_token),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json().get("email")

    def list_folder(self, access_token: str, path: str = "") -> List[Dict[str, Any]]:
        """Lists one folder's immediate children (not recursive).
        `path=""` is Dropbox's own convention for the account root."""
        resp = requests.post(
            f"{DROPBOX_API_BASE}/files/list_folder",
            headers=self._headers(access_token),
            json={"path": path},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        entries = resp.json().get("entries", [])
        return [
            {
                "name": entry["name"],
                "path": entry["path_display"],
                "is_folder": entry.get(".tag") == "folder",
                "size": entry.get("size"),
            }
            for entry in entries
        ]

    def download_file_text(self, access_token: str, path: str) -> Dict[str, Any]:
        """Downloads a file and decodes it as text, capped at
        MAX_FILE_BYTES. Non-text files will just decode to noise —
        this is meant for docs/code/notes, not binaries. Returns
        {"content", "truncated"} so callers can tell the user when a
        file was cut off rather than silently handing back a partial
        copy."""
        resp = requests.post(
            f"{DROPBOX_CONTENT_BASE}/files/download",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Dropbox-API-Arg": json.dumps({"path": path}),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.content
        return {
            "content": content[:MAX_FILE_BYTES].decode("utf-8", errors="replace"),
            "truncated": len(content) > MAX_FILE_BYTES,
        }

    def _headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
