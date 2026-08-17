"""Coder Agent — generates code from requirements.

Model: DeepSeek-Coder 33B, a community GGUF build
(kcaverly/deepseek-coder-33b-instruct-gguf on Replicate). The official
deepseek-ai listing's hosted version currently fails on every request
("cannot pickle 'async_generator' object" — a bug in their Cog
wrapper), so this uses a verified-working alternative instead. Because
it's a community model (not an "official model"), Replicate requires
pinning an explicit version id rather than using the shortcut endpoint.
"""

import logging
from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.agents.replicate_client import ReplicateClient
from src.settings import resolve_model_and_version

logger = logging.getLogger(__name__)

MODEL = "kcaverly/deepseek-coder-33b-instruct-gguf"
MODEL_VERSION = "ea964345066a8868e43aca432f314822660b72e29cab6b4b904b779014fe58fd"


class CoderAgent(BaseAgent):
    """Generates code for a given set of requirements."""

    def __init__(self):
        super().__init__(agent_type="coder", model_name="deepseek-coder-33b")
        self.replicate_client = ReplicateClient()

    def process(self, **kwargs) -> Dict[str, Any]:
        return self.generate_code(**kwargs)

    def generate_code(
        self,
        requirements: str,
        tech_stack: str = "Python",
        style: str = "",
        context: str = "",
    ) -> Dict[str, Any]:
        """Generate code satisfying `requirements` in `tech_stack`.

        `context` carries prior conversation turns for follow-up requests
        ("now add error handling to that") — see BrainstormAgent for the
        same pattern.
        """
        task_id = self.create_task(
            {
                "requirements": requirements,
                "tech_stack": tech_stack,
                "style": style,
                "context": context,
            }
        )
        logger.info("Generating code: %s", requirements)

        try:
            prompt = self.resolve_prompt(
                self._build_prompt(requirements, tech_stack, style, context),
                {
                    "requirements": requirements,
                    "tech_stack": tech_stack,
                    "style": style,
                    "context": context,
                },
            )
            model, version = resolve_model_and_version(
                self.settings, MODEL, MODEL_VERSION
            )
            run_result = self.replicate_client.run(
                model,
                {
                    "prompt": prompt,
                    # This model defaults to Chinese-language output on some
                    # prompts without an explicit instruction to use English.
                    "system_prompt": (
                        "You are a senior software engineer. Always respond "
                        "in English with working, production-quality code."
                    ),
                    "max_new_tokens": self.max_tokens_or(1024),
                    "temperature": self.temperature_or(0.2),
                },
                version=version,
            )
            result = {
                "task_id": task_id,
                "output": run_result["output"],
                "usage": run_result["usage"],
                "tech_stack": tech_stack,
            }
            self.complete_task(result)
            return result
        except Exception as exc:
            logger.error("Code generation failed: %s", exc)
            self.fail_task(str(exc))
            raise

    def _build_prompt(
        self, requirements: str, tech_stack: str, style: str, context: str
    ) -> str:
        style_line = f"Style: {style}" if style else ""
        context_line = f"Earlier in this conversation:\n{context}\n" if context else ""
        return f"""
        {context_line}
        Generate production-ready {tech_stack} code for:
        {requirements}

        {style_line}

        Return complete, working code with brief comments explaining any
        non-obvious logic. Do not include unrelated boilerplate.
        """.strip()

    def verify_api_key(self) -> bool:
        return self.replicate_client.is_configured()
