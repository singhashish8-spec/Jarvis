"""Thin wrapper around GitHub's OAuth + REST API.

Second real connector, same shape as dropbox_client.py: connect once,
browse a repo, pull a file's text content in as context instead of
pasting it by hand. Scope matches exactly what the placeholder
promised — "Let Coder/QA read real files from a repo instead of
pasted code."

Auth model: a classic GitHub OAuth App (not a GitHub App/installation
flow — this is a single-user tool acting on one person's own repos,
so the simpler app-to-user OAuth flow is enough). Classic OAuth App
tokens don't expire by default, so unlike Dropbox there's no refresh
step: the access token returned from the code exchange is the token
used for every subsequent call, stored as-is.
"""

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"

# Caps a single pulled file at ~50k tokens worth of text, same budget
# as the Dropbox connector.
MAX_FILE_BYTES = 200_000

REQUEST_TIMEOUT_SECONDS = 20


class GitHubClient:
    """Client for the OAuth handshake and the handful of REST calls
    the connector needs (list repos, list a path, download a file)."""

    def __init__(self):
        self.client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET")

    def is_configured(self) -> bool:
        """True if a client id/secret pair is present (does not verify
        they're valid — that only happens on the first real OAuth
        round trip)."""
        return bool(self.client_id and self.client_secret)

    def get_authorize_url(self, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            # "repo" covers both public and private repos the user
            # can access — needed since most real project repos aren't public.
            "scope": "repo",
        }
        return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Trades a one-time authorization code for {access_token, ...}."""
        resp = requests.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise ValueError(body.get("error_description", body["error"]))
        return body

    def get_account_login(self, access_token: str) -> Optional[str]:
        resp = requests.get(
            f"{GITHUB_API_BASE}/user",
            headers=self._headers(access_token),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json().get("login")

    def list_repos(self, access_token: str) -> List[Dict[str, Any]]:
        """The user's own repos (owned + collaborator), most recently
        pushed first, capped at 100 — plenty for a picker list."""
        resp = requests.get(
            f"{GITHUB_API_BASE}/user/repos",
            headers=self._headers(access_token),
            params={"sort": "pushed", "per_page": 100},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return [
            {
                "full_name": repo["full_name"],
                "private": repo["private"],
                "default_branch": repo["default_branch"],
            }
            for repo in resp.json()
        ]

    def list_path(
        self, access_token: str, repo: str, path: str = ""
    ) -> List[Dict[str, Any]]:
        """Lists one directory's immediate children in `repo`
        (`owner/name`). `path=""` is the repo root."""
        resp = requests.get(
            f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}",
            headers=self._headers(access_token),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        entries = resp.json()
        if isinstance(entries, dict):
            # A file path was given instead of a directory — GitHub
            # returns a single object rather than a list.
            entries = [entries]
        return [
            {
                "name": entry["name"],
                "path": entry["path"],
                "is_folder": entry["type"] == "dir",
                "size": entry.get("size"),
            }
            for entry in entries
        ]

    def download_file_text(
        self, access_token: str, repo: str, path: str
    ) -> Dict[str, Any]:
        """Downloads a file's raw content (not the base64-wrapped
        contents API), capped at MAX_FILE_BYTES. Returns
        {"content", "truncated"} so callers can tell the user when a
        file was cut off rather than silently handing back a partial
        copy."""
        resp = requests.get(
            f"{GITHUB_API_BASE}/repos/{repo}/contents/{path}",
            headers={
                **self._headers(access_token),
                "Accept": "application/vnd.github.raw+json",
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
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
