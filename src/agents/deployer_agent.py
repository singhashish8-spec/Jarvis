"""Deployer Agent — drafts a deployment plan for a change.

Model: Mistral 7B, an OpenOrca fine-tune
(nateraw/mistral-7b-openorca on Replicate). The "official"
mistralai/mistral-7b-instruct-v0.1 listing has no runnable version
anymore (archived), so this uses a verified-working substitute.

This agent drafts a deployment checklist — it does not execute real
deployments (pushing to Vercel, running migrations, etc.). Actually
deploying is a hard-to-reverse action that belongs behind a human
decision point, not something an agent runs autonomously.
"""

import logging
from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.agents.replicate_client import ReplicateClient

logger = logging.getLogger(__name__)

MODEL = "nateraw/mistral-7b-openorca"
MODEL_VERSION = "7afe21847d582f7811327c903433e29334c31fe861a7cf23c62882b181bacb88"


class DeployerAgent(BaseAgent):
    """Drafts a deployment plan/checklist for a change — does not run it."""

    def __init__(self):
        super().__init__(agent_type="deployer", model_name="mistral-7b-openorca")
        self.replicate_client = ReplicateClient()

    def process(self, **kwargs) -> Dict[str, Any]:
        return self.plan_deployment(**kwargs)

    def plan_deployment(
        self, change_summary: str, target: str = "Vercel", context: str = ""
    ) -> Dict[str, Any]:
        """Draft a deployment plan for `change_summary` targeting `target`.

        `context` carries prior conversation turns for follow-up requests
        — see BrainstormAgent for the same pattern.
        """
        task_id = self.create_task(
            {"change_summary": change_summary, "target": target, "context": context}
        )
        logger.info("Planning deployment: %s", change_summary)

        try:
            prompt = self._build_prompt(change_summary, target, context)
            run_result = self.replicate_client.run(
                MODEL,
                {"prompt": prompt, "max_new_tokens": 512, "temperature": 0.3},
                version=MODEL_VERSION,
            )
            result = {
                "task_id": task_id,
                "output": run_result["output"],
                "usage": run_result["usage"],
                "target": target,
            }
            self.complete_task(result)
            return result
        except Exception as exc:
            logger.error("Deployment planning failed: %s", exc)
            self.fail_task(str(exc))
            raise

    def _build_prompt(self, change_summary: str, target: str, context: str) -> str:
        context_line = f"Earlier in this conversation:\n{context}\n" if context else ""
        return f"""
        {context_line}
        Draft a deployment checklist for deploying this change to {target}:
        {change_summary}

        Include: pre-deploy checks, the deploy steps, and a rollback plan.
        Keep it concise and actionable.
        """.strip()

    def verify_api_key(self) -> bool:
        return self.replicate_client.is_configured()
