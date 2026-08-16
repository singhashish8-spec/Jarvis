"""Supabase database client.

Wraps the supabase-py SDK so the rest of the app calls simple methods
like `save_task(...)` instead of talking to Supabase's query builder
directly — makes it easy to swap the backend later if needed.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class DatabaseClient:
    """Thin wrapper around the Supabase client for the `tasks` table."""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY are required")

        self.client: Client = create_client(url, key)
        logger.info("Database client initialized")

    def health_check(self) -> bool:
        """True if the `tasks` table is reachable."""
        try:
            self.client.table("tasks").select("id").limit(1).execute()
            return True
        except Exception as exc:  # noqa: BLE001 - health check must never raise
            logger.error("Database health check failed: %s", exc)
            return False

    def save_task(
        self,
        agent_type: str,
        input_data: Dict[str, Any],
        output_data: Optional[Dict[str, Any]] = None,
        status: str = "completed",
        cost: float = 0.0,
    ) -> Optional[str]:
        """Insert a task execution record. Returns the new task's id."""
        try:
            data = {
                "agent_type": agent_type,
                "status": status,
                "input": input_data,
                "output": output_data or {},
                "cost": cost,
                "cost_currency": "INR",
            }
            result = self.client.table("tasks").insert(data).execute()
            task_id = result.data[0]["id"] if result.data else None
            logger.info("Task saved: %s", task_id)
            return task_id
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to save task: %s", exc)
            raise

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single task by id, or None if not found/unreachable."""
        try:
            result = self.client.table("tasks").select("*").eq("id", task_id).execute()
            return result.data[0] if result.data else None
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get task %s: %s", task_id, exc)
            return None

    def list_tasks(
        self, agent_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List recent tasks, optionally filtered by agent type."""
        try:
            query = self.client.table("tasks").select("*")
            if agent_type:
                query = query.eq("agent_type", agent_type)
            result = query.order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to list tasks: %s", exc)
            return []

    def get_daily_cost(self, date_str: str) -> float:
        """Total cost (INR) of all tasks created on a given date (YYYY-MM-DD)."""
        try:
            result = (
                self.client.table("tasks")
                .select("cost")
                .gte("created_at", f"{date_str}T00:00:00")
                .lte("created_at", f"{date_str}T23:59:59")
                .execute()
            )
            return sum(task.get("cost", 0) or 0 for task in result.data or [])
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get daily cost: %s", exc)
            return 0.0
