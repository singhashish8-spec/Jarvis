"""Document Agent — generates documentation for code or a feature.

Model: Llama 3 70B (meta/meta-llama-3-70b-instruct on Replicate). Not
specified in the original planning docs — chosen for strong general
writing quality, reusing the same model already validated for
Brainstorm/Tester.
"""

import logging
from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.agents.replicate_client import ReplicateClient
from src.settings import resolve_model_and_version

logger = logging.getLogger(__name__)

MODEL = "meta/meta-llama-3-70b-instruct"


class DocumentAgent(BaseAgent):
    """Generates documentation (README sections, guides, explanations)."""

    def __init__(self):
        super().__init__(agent_type="document", model_name="llama-3-70b")
        self.replicate_client = ReplicateClient()

    def process(self, **kwargs) -> Dict[str, Any]:
        return self.write_docs(**kwargs)

    def write_docs(
        self, subject: str, content: str = "", doc_type: str = "README section"
    ) -> Dict[str, Any]:
        """Write a `doc_type` document about `subject`."""
        task_id = self.create_task(
            {"subject": subject, "content": content, "doc_type": doc_type}
        )
        logger.info("Writing docs: %s", subject)

        try:
            prompt = self.resolve_prompt(
                self._build_prompt(subject, content, doc_type),
                {"subject": subject, "content": content, "doc_type": doc_type},
            )
            model, version = resolve_model_and_version(self.settings, MODEL)
            run_result = self.replicate_client.run(
                model,
                {
                    "prompt": prompt,
                    "max_tokens": self.max_tokens_or(1024),
                    "temperature": self.temperature_or(0.4),
                },
                version=version,
            )
            result = {
                "task_id": task_id,
                "output": run_result["output"],
                "usage": run_result["usage"],
                "doc_type": doc_type,
            }
            self.complete_task(result)
            return result
        except Exception as exc:
            logger.error("Documentation generation failed: %s", exc)
            self.fail_task(str(exc))
            raise

    def _build_prompt(self, subject: str, content: str, doc_type: str) -> str:
        context_line = f"Source material / context: {content}" if content else ""
        return f"""
        Write a {doc_type} for: {subject}

        {context_line}

        Use clear, simple language. Avoid unnecessary jargon.
        """.strip()

    def verify_api_key(self) -> bool:
        return self.replicate_client.is_configured()
