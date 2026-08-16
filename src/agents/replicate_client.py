"""Thin wrapper around the Replicate API.

Phase 0: not called yet — BrainstormAgent returns example data so the
whole system can be tested with zero API cost.
Phase 1: BrainstormAgent switches to calling `run()` below, which
actually invokes a model (e.g. Llama 70B) on Replicate.
"""

import logging
import os
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

REPLICATE_API_BASE = "https://api.replicate.com/v1"


class ReplicateClient:
    """Minimal client for calling hosted models on Replicate."""

    def __init__(self):
        self.api_key = os.getenv("REPLICATE_API_KEY")

    def is_configured(self) -> bool:
        """True if an API key is present (does not verify it's valid)."""
        return bool(self.api_key)

    def run(
        self, model: str, input_data: Dict[str, Any], timeout: int = 300
    ) -> Dict[str, Any]:
        """Run a model on Replicate and return its prediction output.

        Not used in Phase 0. Kept here, tested against a real key, and
        ready for BrainstormAgent to call once Phase 1 begins.
        """
        if not self.api_key:
            raise ValueError("REPLICATE_API_KEY is not set")

        response = requests.post(
            f"{REPLICATE_API_BASE}/models/{model}/predictions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
            json={"input": input_data},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
