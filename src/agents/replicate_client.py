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

Replicate has no API for account credit/balance (confirmed against their
docs — /v1/account only returns username/type), so "cost" here is always
an estimate derived from what a finished prediction actually reports:
token counts when the model provides them, and compute time otherwise.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

REPLICATE_API_BASE = "https://api.replicate.com/v1"
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
MAX_NETWORK_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0

# Replicate bills most models by hardware-time, not tokens (see
# replicate.com/pricing). Used to turn `predict_time` into a rough USD
# estimate when a model doesn't report token counts. Defaults to
# Replicate's published Nvidia A100 (80GB) rate; override via env if your
# agents run on different hardware.
GPU_RATE_PER_SECOND_USD = float(os.getenv("REPLICATE_GPU_RATE_PER_SECOND") or 0.0014)


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

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """requests.request with retries for transient network failures
        (connection resets, timeouts) — not for a model actually failing,
        which should surface immediately rather than be retried."""
        last_exc: Optional[RequestException] = None
        for attempt in range(1, MAX_NETWORK_RETRIES + 1):
            try:
                return requests.request(method, url, **kwargs)
            except RequestException as exc:
                last_exc = exc
                logger.warning(
                    "Replicate request attempt %d/%d failed: %s",
                    attempt,
                    MAX_NETWORK_RETRIES,
                    exc,
                )
                if attempt < MAX_NETWORK_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise last_exc

    def run(
        self,
        model: str,
        input_data: Dict[str, Any],
        version: Optional[str] = None,
        timeout: int = 180,
        poll_interval: float = 2.0,
    ) -> Dict[str, Any]:
        """Run a model on Replicate and return its output plus usage.

        Args:
            model: "owner/name", e.g. "meta/meta-llama-3-70b-instruct".
            input_data: model-specific input (prompt, max_tokens, ...).
            version: required for most community models — see the
                module docstring. Official models leave this unset.

        Returns:
            {"output": <joined text>, "usage": {"input_tokens", "output_tokens",
            "total_tokens", "predict_time_seconds", "estimated_cost_usd"}}.
            Token counts are 0 when the model doesn't report them (Replicate
            only returns `metrics.input_token_count` / `output_token_count`
            for language models); `estimated_cost_usd` falls back to
            `predict_time_seconds * GPU_RATE_PER_SECOND_USD` in that case.
        """
        if not self.api_key:
            raise ValueError("REPLICATE_API_KEY is not set")

        if version:
            create_url = f"{REPLICATE_API_BASE}/predictions"
            payload: Dict[str, Any] = {"version": version, "input": input_data}
        else:
            create_url = f"{REPLICATE_API_BASE}/models/{model}/predictions"
            payload = {"input": input_data}

        response = self._request(
            "POST", create_url, headers=self._headers(), json=payload, timeout=30
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
            response = self._request(
                "GET", get_url, headers=self._headers(), timeout=30
            )
            response.raise_for_status()
            prediction = response.json()

        if prediction["status"] != "succeeded":
            raise RuntimeError(
                f"Replicate prediction for {model} {prediction['status']}: {prediction.get('error')}"
            )

        output = self._normalize_output(prediction.get("output"))
        usage = self._extract_usage(prediction.get("metrics") or {})
        return {"output": output, "usage": usage}

    @staticmethod
    def _extract_usage(metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Turn a prediction's `metrics` block into token/cost usage.

        Language models report `input_token_count` / `output_token_count`;
        every model reports `predict_time` (compute seconds). When token
        counts are absent, cost falls back to compute-time billing.
        """
        input_tokens = int(metrics.get("input_token_count") or 0)
        output_tokens = int(metrics.get("output_token_count") or 0)
        predict_time = float(metrics.get("predict_time") or 0.0)
        estimated_cost = round(predict_time * GPU_RATE_PER_SECOND_USD, 6)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "predict_time_seconds": predict_time,
            "estimated_cost_usd": estimated_cost,
        }

    @staticmethod
    def _normalize_output(output: Any) -> str:
        """Most text models stream output as a list of string chunks;
        join them into one string. A plain string passes through as-is."""
        if isinstance(output, list):
            return "".join(str(chunk) for chunk in output)
        if output is None:
            return ""
        return str(output)
