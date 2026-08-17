"""Supabase database client.

Wraps the supabase-py SDK so the rest of the app calls simple methods
like `save_task(...)` instead of talking to Supabase's query builder
directly — makes it easy to swap the backend later if needed.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
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

    def get_usage_by_agent_today(self) -> List[Dict[str, Any]]:
        """Today's usage, one row per agent_type (the `usage` table's own
        shape — see UNIQUE(date, agent_type)) — backs the sidebar's
        per-agent spend breakdown. Degrades to an empty list on failure;
        the popover just shows no breakdown rather than erroring."""
        today = datetime.now(timezone.utc).date().isoformat()
        try:
            result = (
                self.client.table("usage")
                .select("agent_type, tokens_used, cost")
                .eq("date", today)
                .execute()
            )
            return result.data or []
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get today's usage by agent: %s", exc)
            return []

    def get_table_counts(self) -> Dict[str, int]:
        """Row counts for the tables the dashboard's storage popover
        shows — not disk bytes (Postgres only exposes that via a raw SQL
        connection or a pre-created RPC function, neither of which this
        REST-only client has), but the number of tasks/usage-days/skills
        actually saved. Each table counted independently so one failing
        doesn't zero out the others."""
        counts: Dict[str, int] = {}
        for table in ("tasks", "usage", "skills"):
            try:
                result = (
                    self.client.table(table)
                    .select("*", count="exact", head=True)
                    .execute()
                )
                counts[table] = result.count or 0
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to count %s: %s", table, exc)
                counts[table] = 0
        return counts

    def get_setting(self, key: str) -> Optional[str]:
        """Fetch a user-configurable setting (e.g. the credit-limit budget
        set from the dashboard). None if unset or the table/DB is
        unreachable — callers should fall back to an env-var default."""
        try:
            result = (
                self.client.table("settings").select("value").eq("key", key).execute()
            )
            return result.data[0]["value"] if result.data else None
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get setting %s: %s", key, exc)
            return None

    def set_setting(self, key: str, value: str) -> None:
        """Persist a user-configurable setting. Unlike most writes in this
        client, this one re-raises on failure — the dashboard's edit
        action needs to know it didn't actually save (e.g. because the
        `settings` table hasn't been created yet — see docs/DATABASE.md)."""
        self.client.table("settings").upsert({"key": key, "value": value}).execute()

    def delete_task(self, task_id: str) -> bool:
        """Delete a single task row — backs the dashboard's task browser
        (Data Controls). Returns True on success."""
        try:
            self.client.table("tasks").delete().eq("id", task_id).execute()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to delete task %s: %s", task_id, exc)
            return False

    def count_recent_tasks(self, seconds: int) -> int:
        """Count tasks created in the trailing `seconds` — backs rate
        limiting. Reuses `tasks.created_at` instead of an in-memory
        counter: Vercel's serverless functions don't reliably keep
        process memory between requests, but the DB always has the
        real history."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
        try:
            result = (
                self.client.table("tasks")
                .select("id")
                .gte("created_at", cutoff)
                .execute()
            )
            return len(result.data or [])
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to count recent tasks: %s", exc)
            return 0

    def purge_tasks_older_than(self, days: int) -> int:
        """Delete tasks older than `days`. Returns how many were removed.
        Manual-trigger only (Data Controls' "Purge now" button) — Vercel
        has no background scheduler wired up for this to run on its own
        yet, so it never happens unless you click the button."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = self.client.table("tasks").delete().lt("created_at", cutoff).execute()
        return len(result.data or [])

    def reset_usage(self) -> None:
        """Wipe every row from the `usage` table — danger-zone action for
        starting a fresh spend count (e.g. a new month). Re-raises on
        failure so the caller can tell the user it didn't work."""
        self.client.table("usage").delete().neq(
            "id", "00000000-0000-0000-0000-000000000000"
        ).execute()

    def reset_all_settings(self) -> None:
        """Delete every row from the `settings` table, reverting every
        dashboard-configured setting back to its schema default (or its
        env-var fallback, for credit_limit_usd/gpu_rate_per_second_usd)."""
        self.client.table("settings").delete().neq("key", "__never_matches__").execute()

    def list_skills(self, agent_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List skills (prompt-template overrides), optionally filtered to
        one agent. Read path degrades to an empty list on failure, same
        as list_tasks — a broken settings feature shouldn't take agents
        down with it."""
        try:
            query = self.client.table("skills").select("*")
            if agent_type:
                query = query.eq("agent_type", agent_type)
            result = query.order("created_at", desc=True).execute()
            return result.data or []
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to list skills: %s", exc)
            return []

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one skill by id, or None if missing/unreachable — agents
        read this on every request to check for an active override, so
        it must never raise."""
        try:
            result = (
                self.client.table("skills").select("*").eq("id", skill_id).execute()
            )
            return result.data[0] if result.data else None
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get skill %s: %s", skill_id, exc)
            return None

    def create_skill(
        self,
        agent_type: str,
        skill_name: str,
        template: str,
        description: str = "",
        version: str = "1.0",
    ) -> Optional[str]:
        """Create a new skill (prompt template). Re-raises on failure —
        the settings UI needs to know a save didn't take."""
        result = (
            self.client.table("skills")
            .insert(
                {
                    "agent_type": agent_type,
                    "skill_name": skill_name,
                    "description": description,
                    "template": template,
                    "version": version,
                    "is_active": True,
                }
            )
            .execute()
        )
        return result.data[0]["id"] if result.data else None

    def update_skill(self, skill_id: str, **fields: Any) -> None:
        """Update arbitrary columns on a skill. Re-raises on failure."""
        self.client.table("skills").update(fields).eq("id", skill_id).execute()

    def delete_skill(self, skill_id: str) -> None:
        """Delete a skill. Re-raises on failure."""
        self.client.table("skills").delete().eq("id", skill_id).execute()

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
