"""Base class every agent (Brainstorm now; Coder/Tester/Deployer in
later phases) inherits from, so they all track tasks the same way."""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict

from src.settings import render_skill_template

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Common lifecycle (create/complete/fail a task) for all agents."""

    def __init__(self, agent_type: str, model_name: str):
        self.agent_type = agent_type
        self.model_name = model_name
        self.created_at = datetime.now(timezone.utc)
        self.current_task: Dict[str, Any] = {}
        # Populated by main.py (via settings.resolve_agent_settings) before
        # process() runs. Left empty for agents used directly — e.g. in
        # tests — so every override below is simply a no-op by default.
        self.settings: Dict[str, Any] = {}
        logger.info("%s agent initialized with %s", self.agent_type, model_name)

    @abstractmethod
    def process(self, **kwargs) -> Dict[str, Any]:
        """Run the agent's main operation. Implemented by each subclass."""
        raise NotImplementedError

    def create_task(self, input_data: Dict[str, Any]) -> str:
        """Start tracking a new task; returns its id."""
        task_id = str(uuid.uuid4())
        self.current_task = {
            "task_id": task_id,
            "agent_type": self.agent_type,
            "status": "running",
            "input": input_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return task_id

    def complete_task(self, output_data: Dict[str, Any]) -> Dict[str, Any]:
        """Mark the current task as completed with its output."""
        self.current_task["output"] = output_data
        self.current_task["status"] = "completed"
        self.current_task["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("Task %s completed", self.current_task["task_id"])
        return self.current_task

    def fail_task(self, error_message: str) -> Dict[str, Any]:
        """Mark the current task as failed with an error message."""
        self.current_task["status"] = "failed"
        self.current_task["error"] = error_message
        self.current_task["failed_at"] = datetime.now(timezone.utc).isoformat()
        logger.error("Task %s failed: %s", self.current_task["task_id"], error_message)
        return self.current_task

    def resolve_prompt(self, built_prompt: str, template_vars: Dict[str, Any]) -> str:
        """Applies settings on top of an agent's normal built prompt:
        an active Skill's template replaces it entirely (falling back to
        `built_prompt` if the skill has no template), then Custom
        Instructions (if any) are prepended. Called with self.settings
        empty (the default), this is just `return built_prompt`.
        """
        prompt = built_prompt
        skill_template = self.settings.get("skill_template")
        if skill_template:
            prompt = render_skill_template(skill_template, template_vars)

        custom_instructions = self.settings.get("custom_instructions")
        if custom_instructions:
            prompt = f"{custom_instructions}\n\n{prompt}"

        return prompt

    def temperature_or(self, default: float) -> float:
        """The Agent Defaults temperature override if one is set,
        otherwise `default`. A small helper mainly so "is there an
        override" isn't a `is not None` check duplicated in every agent."""
        override = self.settings.get("temperature")
        return override if override is not None else default

    def max_tokens_or(self, default: int) -> int:
        """Same as `temperature_or`, for the max-tokens override."""
        override = self.settings.get("max_tokens")
        return override if override is not None else default
