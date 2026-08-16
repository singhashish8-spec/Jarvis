"""Brainstorm Agent — generates ideas for a given topic.

Phase 0 (now): returns realistic example data, so the API/DB/storage
pipeline can be built and tested without spending anything on Replicate.
Phase 1: `brainstorm()` switches to calling `self.replicate_client.run()`
with the prompt built by `_build_prompt()`, using Llama 70B.
"""

import logging
from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.agents.replicate_client import ReplicateClient

logger = logging.getLogger(__name__)


class BrainstormAgent(BaseAgent):
    """Generates ideas, options, and design/strategy recommendations."""

    def __init__(self):
        super().__init__(agent_type="brainstorm", model_name="llama-70b")
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

        Returns a dict with `ideas`, `reasoning`, and `task_id`.
        """
        task_id = self.create_task({"topic": topic, "context": context, "style": style})
        logger.info("Brainstorming: %s", topic)

        try:
            # Phase 0: example data (no API cost).
            result = self._get_example_result(topic, context, style)

            # Phase 1 will replace the line above with:
            # result = self.replicate_client.run(
            #     "meta/llama-2-70b-chat",
            #     {"prompt": self._build_prompt(topic, context, style)},
            # )

            self.complete_task(result)
            return result
        except Exception as exc:
            logger.error("Brainstorm failed: %s", exc)
            self.fail_task(str(exc))
            raise

    def _build_prompt(self, topic: str, context: str, style: str) -> str:
        """Prompt template used once Phase 1 wires up the real model call."""
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

    def _get_example_result(
        self, topic: str, context: str, style: str
    ) -> Dict[str, Any]:
        """Example response, shaped exactly like the real Phase 1 output
        will be, so downstream code doesn't need to change later."""
        ideas = [
            "Multi-level rack storage system for maximum density",
            "Automated conveyor system for goods movement",
            "Climate-controlled zone for sensitive items",
            "Cross-docking area for rapid inventory turnover",
            "Advanced inventory tracking with RFID or barcode systems",
        ]

        return {
            "task_id": self.current_task["task_id"],
            "ideas": ideas,
            "reasoning": (
                "These ideas balance space optimization, efficiency, flexibility, "
                "cost-effectiveness, and safety for the given topic and context."
            ),
            "implementation_tips": [
                "Start with the highest-impact idea first",
                "Validate assumptions with a small pilot before full rollout",
                "Track cost and timeline against the estimate below",
            ],
            "estimated_cost": "Varies by scope",
            "phase": "0-EXAMPLE-DATA",
            "note": "Phase 0: this is example data. Phase 1 will call the real Llama 70B model.",
        }

    def verify_api_key(self) -> bool:
        """Used by the /status endpoint. Phase 0: just checks a key is
        present; Phase 1 will make a lightweight real API call instead."""
        return self.replicate_client.is_configured()
