"""Brainstorm Agent — generates ideas for a given topic.

Model: Llama 3 70B (meta/meta-llama-3-70b-instruct on Replicate),
called directly through Replicate's shortcut endpoint for official
models (no version pinning needed).
"""

import logging
from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.agents.replicate_client import ReplicateClient

logger = logging.getLogger(__name__)

MODEL = "meta/meta-llama-3-70b-instruct"


class BrainstormAgent(BaseAgent):
    """Generates ideas, options, and design/strategy recommendations."""

    def __init__(self):
        super().__init__(agent_type="brainstorm", model_name="llama-3-70b")
        self.replicate_client = ReplicateClient()

    def process(self, **kwargs) -> Dict[str, Any]:
        """Satisfies BaseAgent's abstract interface by delegating to brainstorm()."""
        return self.brainstorm(**kwargs)

    def brainstorm(
        self, topic: str, context: str = "", style: str = "detailed"
    ) -> Dict[str, Any]:
        """Generate ideas for `topic`.

        Args:
            topic: What to brainstorm about.
            context: Extra background (project size, constraints, etc.).
            style: "detailed", "concise", or "bullet_points".

        Returns a dict with `output` (the model's raw response) and `task_id`.
        """
        task_id = self.create_task({"topic": topic, "context": context, "style": style})
        logger.info("Brainstorming: %s", topic)

        try:
            prompt = self._build_prompt(topic, context, style)
            run_result = self.replicate_client.run(
                MODEL,
                {"prompt": prompt, "max_tokens": 1024, "temperature": 0.7},
            )
            result = {
                "task_id": task_id,
                "output": run_result["output"],
                "usage": run_result["usage"],
            }
            self.complete_task(result)
            return result
        except Exception as exc:
            logger.error("Brainstorm failed: %s", exc)
            self.fail_task(str(exc))
            raise

    def _build_prompt(self, topic: str, context: str, style: str) -> str:
        return f"""
        Generate creative and practical ideas for: {topic}

        Context: {context}

        Style: {style} (detailed/concise/bullet_points)

        Please provide:
        1. At least 5 distinct ideas
        2. Why each idea works
        3. Potential challenges
        4. Implementation tips
        """.strip()

    def verify_api_key(self) -> bool:
        """Used by the /status endpoint to check Replicate is configured."""
        return self.replicate_client.is_configured()
