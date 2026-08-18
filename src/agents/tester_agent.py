"""Tester Agent — writes test cases for a piece of code.

Model: Llama 3 70B (meta/meta-llama-3-70b-instruct on Replicate). The
original planning docs disagreed on 7B vs 70B for this agent; 70B is
used here since writing tests that actually catch bugs needs real
reasoning about edge cases, not just fast/cheap generation.
"""

import logging
from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.agents.replicate_client import ReplicateClient
from src.settings import resolve_model_and_version

logger = logging.getLogger(__name__)

MODEL = "meta/meta-llama-3-70b-instruct"


class TesterAgent(BaseAgent):
    """Generates test cases for a given piece of code."""

    def __init__(self):
        super().__init__(agent_type="tester", model_name="llama-3-70b")
        self.replicate_client = ReplicateClient()

    def process(self, **kwargs) -> Dict[str, Any]:
        return self.write_tests(**kwargs)

    def write_tests(
        self, code: str, description: str = "", framework: str = "pytest"
    ) -> Dict[str, Any]:
        """Generate `framework` tests for `code`."""
        task_id = self.create_task(
            {"code": code, "description": description, "framework": framework}
        )
        logger.info("Writing tests: %s", description or "submitted code")

        try:
            prompt = self.resolve_prompt(
                self._build_prompt(code, description, framework),
                {"code": code, "description": description, "framework": framework},
            )
            model, version = resolve_model_and_version(self.settings, MODEL)
            self.model_name = model
            run_result = self.replicate_client.run(
                model,
                {
                    "prompt": prompt,
                    "max_tokens": self.max_tokens_or(1024),
                    "temperature": self.temperature_or(0.2),
                },
                version=version,
            )
            result = {
                "task_id": task_id,
                "output": run_result["output"],
                "usage": run_result["usage"],
                "framework": framework,
            }
            self.complete_task(result)
            return result
        except Exception as exc:
            logger.error("Test generation failed: %s", exc)
            self.fail_task(str(exc))
            raise

    def _build_prompt(self, code: str, description: str, framework: str) -> str:
        context_line = f"Context: {description}" if description else ""
        return f"""
        Write complete {framework} test cases for the following code.
        {context_line}

        Code:
        {code}

        Cover the normal case, edge cases, and at least one failure case.
        Return only the test code.
        """.strip()

    def verify_api_key(self) -> bool:
        return self.replicate_client.is_configured()
