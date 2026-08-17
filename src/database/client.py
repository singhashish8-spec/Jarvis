"""Supabase database client.

Wraps the supabase-py SDK so the rest of the app calls simple methods
like `save_task(...)` instead of talking to Supabase's query builder
directly — makes it easy to swap the backend later if needed.
"""

import logging
import os
from datetime import datetime, timezone
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
        cost_currency: str = "USD",
        task_id: Optional[str] = None,
    ) -> Optional[str]:
        """Insert a task execution record. Returns the new task's id.

        Pass `task_id` when the caller already has an id it wants this row
        to use (e.g. the id an agent generated in memory) — otherwise the
        two ids drift apart and `get_task()` can never find the row again.

        `cost` is an estimate (see replicate_client.py) — Replicate's API
        has no endpoint for real billing data.
        """
        try:
            data = {
                "agent_type": agent_type,
                "status": status,
                "input": input_data,
                "output": output_data or {},
                "cost": cost,
                "cost_currency": cost_currency,
            }
            if task_id:
                data["id"] = task_id
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

    def record_usage(
        self, agent_type: str, model_name: str, tokens_used: int, cost: float
    ) -> None:
        """Roll a task's token/cost usage into today's `usage` row for this
        agent_type (one row per day per agent, per the table's UNIQUE
        constraint) so the dashboard can show live totals without summing
        every task row on each request.

        Best-effort like the rest of persistence: a failure here should
        never fail the request that already succeeded.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            existing = (
                self.client.table("usage")
                .select("id, calls_count, tokens_used, cost")
                .eq("date", today)
                .eq("agent_type", agent_type)
                .execute()
            )
            if existing.data:
                row = existing.data[0]
                self.client.table("usage").update(
                    {
                        "model_name": model_name,
                        "calls_count": (row.get("calls_count") or 0) + 1,
                        "tokens_used": (row.get("tokens_used") or 0) + tokens_used,
                        "cost": float(row.get("cost") or 0) + cost,
                    }
                ).eq("id", row["id"]).execute()
            else:
                self.client.table("usage").insert(
                    {
                        "date": today,
                        "agent_type": agent_type,
                        "model_name": model_name,
                        "calls_count": 1,
                        "tokens_used": tokens_used,
                        "cost": cost,
                        "cost_currency": "USD",
                    }
                ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to record usage: %s", exc)

    def get_usage_summary(self) -> Dict[str, Any]:
        """Aggregate token/cost totals across the `usage` table — today's
        and all-time. Small table (one row per day per agent_type), so
        summing in Python beats round-tripping several aggregate queries.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            result = (
                self.client.table("usage").select("date, tokens_used, cost").execute()
            )
            rows = result.data or []
            return {
                "tokens_used_today": sum(
                    r.get("tokens_used") or 0 for r in rows if r.get("date") == today
                ),
                "tokens_used_total": sum(r.get("tokens_used") or 0 for r in rows),
                "estimated_cost_usd_today": round(
                    sum(
                        float(r.get("cost") or 0)
                        for r in rows
                        if r.get("date") == today
                    ),
                    4,
                ),
                "estimated_cost_usd_total": round(
                    sum(float(r.get("cost") or 0) for r in rows), 4
                ),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get usage summary: %s", exc)
            return {
                "tokens_used_today": 0,
                "tokens_used_total": 0,
                "estimated_cost_usd_today": 0.0,
                "estimated_cost_usd_total": 0.0,
            }

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
