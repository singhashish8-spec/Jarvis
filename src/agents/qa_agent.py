"""QA Agent — reviews code for bugs, style issues, and security concerns.

Model: DeepSeek-Coder 33B (same community build the Coder agent uses —
see coder_agent.py for why). Code review is itself a code-specialized
task, so it reuses the code model rather than a general-purpose one.
"""

import logging
from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.agents.replicate_client import ReplicateClient

logger = logging.getLogger(__name__)

MODEL = "kcaverly/deepseek-coder-33b-instruct-gguf"
MODEL_VERSION = "ea964345066a8868e43aca432f314822660b72e29cab6b4b904b779014fe58fd"


class QAAgent(BaseAgent):
    """Reviews code for correctness, style, and security issues."""

    def __init__(self):
        super().__init__(agent_type="qa", model_name="deepseek-coder-33b")
        self.replicate_client = ReplicateClient()

    def process(self, **kwargs) -> Dict[str, Any]:
        return self.review_code(**kwargs)

    def review_code(self, code: str, context: str = "") -> Dict[str, Any]:
        """Review `code` and return findings."""
        task_id = self.create_task({"code": code, "context": context})
        logger.info("Reviewing code%s", f" ({context})" if context else "")

        try:
            prompt = self._build_prompt(code, context)
            output = self.replicate_client.run(
                MODEL,
                {
                    "prompt": prompt,
                    "system_prompt": (
                        "You are a meticulous senior code reviewer. "
                        "Always respond in English."
                    ),
                    "max_new_tokens": 1024,
                    "temperature": 0.2,
                },
                version=MODEL_VERSION,
            )
            result = {"task_id": task_id, "output": output}
            self.complete_task(result)
            return result
        except Exception as exc:
            logger.error("Code review failed: %s", exc)
            self.fail_task(str(exc))
            raise

    def _build_prompt(self, code: str, context: str) -> str:
        context_line = f"Context: {context}" if context else ""
        return f"""
        Review the following code for bugs, style issues, and security
        concerns. {context_line}

        Code:
        {code}

        List findings with severity (critical/major/minor). If nothing
        is wrong, say so explicitly.
        """.strip()

    def verify_api_key(self) -> bool:
        return self.replicate_client.is_configured()
