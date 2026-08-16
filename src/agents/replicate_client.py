"""Thin wrapper around the Replicate API.

Replicate has two ways to run a model, and this handles both:
  - "Official" models (e.g. meta/meta-llama-3-70b-instruct) support a
    shortcut endpoint that runs the model's default version directly —
    call with no `version`.
  - Most community models reject that shortcut and require pinning an
    explicit version id via the classic /v1/predictions endpoint —
    call with `version=<id>`.

Either way, a prediction can take anywhere from ~1s to 90+s (cold start
included if the model hasn't run recently), so this always polls until
the prediction reaches a terminal state rather than assuming a single
request will return a finished result.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

REPLICATE_API_BASE = "https://api.replicate.com/v1"
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}


class ReplicateClient:
    """Client for running models on Replicate, with polling built in."""

    def __init__(self):
        self.api_key = os.getenv("REPLICATE_API_KEY")

    def is_configured(self) -> bool:
        """True if an API key is present (does not verify it's valid)."""
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def run(
        self,
        model: str,
        input_data: Dict[str, Any],
        version: Optional[str] = None,
        timeout: int = 180,
        poll_interval: float = 2.0,
    ) -> str:
        """Run a model on Replicate and return its text output as a
        single string.

        Args:
            model: "owner/name", e.g. "meta/meta-llama-3-70b-instruct".
            input_data: model-specific input (prompt, max_tokens, ...).
            version: required for most community models — see the
                module docstring. Official models leave this unset.
        """
        if not self.api_key:
            raise ValueError("REPLICATE_API_KEY is not set")

        if version:
            create_url = f"{REPLICATE_API_BASE}/predictions"
            payload: Dict[str, Any] = {"version": version, "input": input_data}
        else:
            create_url = f"{REPLICATE_API_BASE}/models/{model}/predictions"
            payload = {"input": input_data}

        response = requests.post(
            create_url, headers=self._headers(), json=payload, timeout=30
        )
        response.raise_for_status()
        prediction = response.json()
        get_url = prediction["urls"]["get"]

        elapsed = 0.0
        while prediction.get("status") not in TERMINAL_STATUSES:
            if elapsed >= timeout:
                raise TimeoutError(
                    f"Replicate prediction for {model} timed out after {timeout}s"
                )
            time.sleep(poll_interval)
            elapsed += poll_interval
            response = requests.get(get_url, headers=self._headers(), timeout=30)
            response.raise_for_status()
            prediction = response.json()

        if prediction["status"] != "succeeded":
            raise RuntimeError(
                f"Replicate prediction for {model} {prediction['status']}: {prediction.get('error')}"
            )

        return self._normalize_output(prediction.get("output"))

    @staticmethod
    def _normalize_output(output: Any) -> str:
        """Most text models stream output as a list of string chunks;
        join them into one string. A plain string passes through as-is."""
        if isinstance(output, list):
            return "".join(str(chunk) for chunk in output)
        if output is None:
            return ""
        return str(output)
