"""JARVIS API — Flask application entry point.

This is the front door: every request comes in here and gets routed
to the right agent. Five agents are wired up: Brainstorm, Coder,
Tester, Deployer, and Document/QA — each calling a real model on
Replicate (see docs/AGENTS.md for which model and why).
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

from src.agents.base_agent import BaseAgent  # noqa: E402
from src.agents.brainstorm_agent import BrainstormAgent  # noqa: E402
from src.agents.coder_agent import CoderAgent  # noqa: E402
from src.agents.deployer_agent import DeployerAgent  # noqa: E402
from src.agents.document_agent import DocumentAgent  # noqa: E402
from src.agents.qa_agent import QAAgent  # noqa: E402
from src.agents.tester_agent import TesterAgent  # noqa: E402
from src.config import config  # noqa: E402
from src.database.client import DatabaseClient  # noqa: E402
from src.settings import is_agent_enabled, resolve_agent_settings  # noqa: E402
from src.settings_schema import (  # noqa: E402
    AGENT_BUILTIN_DEFAULTS,
    AGENT_TYPES,
    CATEGORIES,
    CHEAPER_MODEL,
    SETTINGS_SCHEMA,
    validate_agent_config,
    validate_setting_value,
)
from src.storage.r2_client import R2Client  # noqa: E402
from src.utils.errors import APIError, RateLimitError, handle_error  # noqa: E402
from src.utils.logger import setup_logger  # noqa: E402

app = Flask(__name__)
app.config.from_object(config)

CORS(app, origins=config.CORS_ORIGINS)

logger = setup_logger(__name__)

try:
    db_client = DatabaseClient()
    r2_client = R2Client()
    brainstorm_agent = BrainstormAgent()
    coder_agent = CoderAgent()
    tester_agent = TesterAgent()
    deployer_agent = DeployerAgent()
    document_agent = DocumentAgent()
    qa_agent = QAAgent()
    logger.info("All clients initialized successfully")
except Exception as exc:
    logger.error("Failed to initialize clients: %s", exc)
    raise

AGENTS_BY_TYPE: Dict[str, BaseAgent] = {
    "brainstorm": brainstorm_agent,
    "coder": coder_agent,
    "tester": tester_agent,
    "deployer": deployer_agent,
    "document": document_agent,
    "qa": qa_agent,
}


# ============================================
# DASHBOARD
# ============================================


@app.route("/", methods=["GET"])
def dashboard():
    """Serves the web dashboard — a plain HTML/JS page (no build step,
    no Node/npm dependency) so `make dev` alone is enough to use it."""
    return app.send_static_file("dashboard.html")


# ============================================
# HEALTH & STATUS
# ============================================


@app.route("/health", methods=["GET"])
def health_check():
    """Liveness check — used by uptime monitors and Vercel."""
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "Jarvis API",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "0.1.0",
            }
        ),
        200,
    )


@app.route("/status", methods=["GET"])
def status_check():
    """Readiness check — verifies the database, storage, and Replicate
    are all reachable, not just that the process is running."""
    status = {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {},
    }

    checks = {
        "database": db_client.health_check,
        "replicate": brainstorm_agent.verify_api_key,
        "storage": r2_client.health_check,
    }

    for name, check in checks.items():
        try:
            healthy = check()
        except Exception as exc:  # noqa: BLE001
            healthy = False
            logger.error("%s health check raised: %s", name, exc)

        status["components"][name] = "healthy" if healthy else "unavailable"
        if not healthy:
            status["status"] = "degraded"

    http_code = 200 if status["status"] == "operational" else 503
    return jsonify(status), http_code


def _get_credit_limit() -> Any:
    """Credit limit the dashboard tracks spend against. A value saved from
    the dashboard's own settings UI (stored in the DB) takes precedence
    over the REPLICATE_CREDIT_LIMIT_USD env var, so non-technical users
    aren't required to touch Vercel/`.env` to set a budget."""
    saved = db_client.get_setting("credit_limit_usd")
    if saved:
        try:
            return float(saved)
        except ValueError:
            logger.error("Stored credit_limit_usd %r isn't a number", saved)
    return config.REPLICATE_CREDIT_LIMIT_USD


def _get_gpu_rate_override() -> Any:
    """Non-default $/sec rate saved from Usage & Billing, or None to use
    ReplicateClient's own default (REPLICATE_GPU_RATE_PER_SECOND / the
    published A100 rate)."""
    saved = db_client.get_setting("gpu_rate_per_second_usd")
    if saved:
        try:
            return float(saved)
        except ValueError:
            logger.error("Stored gpu_rate_per_second_usd %r isn't a number", saved)
    return None


def _get_budget_alert_threshold() -> Any:
    saved = db_client.get_setting("budget_alert_threshold_pct")
    if saved:
        try:
            return float(saved)
        except ValueError:
            logger.error("Stored budget_alert_threshold_pct %r isn't a number", saved)
    return None


@app.route("/api/usage", methods=["GET"])
def usage_check():
    """Live token usage and estimated spend, for the dashboard's usage
    widget. Replicate has no API for real account balance/credit (only
    /v1/account, which returns username/type) — cost here is an estimate
    computed from each prediction's own reported token counts or compute
    time (see replicate_client.py), rolled up as tasks complete.

    `credit_limit_usd` is a budget the user sets themselves (dashboard UI,
    persisted via POST /api/settings/credit-limit, falling back to the
    REPLICATE_CREDIT_LIMIT_USD env var) to match what they've actually
    loaded on replicate.com/account/billing; it's null (no bar shown)
    until set either way.
    """
    summary = db_client.get_usage_summary()
    limit = _get_credit_limit()
    summary["credit_limit_usd"] = limit
    summary["credit_remaining_usd"] = (
        round(limit - summary["estimated_cost_usd_total"], 4)
        if limit is not None
        else None
    )
    summary["cost_note"] = (
        "Estimated from Replicate's own per-prediction metrics (tokens or "
        "compute time) — Replicate's API does not expose real account "
        "balance. See replicate.com/account/billing for the authoritative "
        "figure."
    )

    threshold_pct = _get_budget_alert_threshold()
    current_pct = (
        round(summary["estimated_cost_usd_total"] / limit * 100, 1) if limit else None
    )
    summary["budget_alert"] = {
        "threshold_pct": threshold_pct,
        "current_pct": current_pct,
        "triggered": bool(
            threshold_pct is not None
            and current_pct is not None
            and current_pct >= threshold_pct
        ),
    }
    return jsonify(summary), 200


def _save_setting(key: str, raw_value: Any) -> str:
    """Validate (settings_schema.py) then persist one setting. Returns
    the normalized string that was saved (possibly ""). Raises APIError
    on anything invalid or if the write itself fails."""
    try:
        normalized = validate_setting_value(key, raw_value)
    except ValueError as exc:
        raise APIError(str(exc), 400)

    try:
        db_client.set_setting(key, normalized)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save setting %s: %s", key, exc)
        raise APIError(
            "Couldn't save — the database's `settings` table may not exist "
            "yet. See docs/DATABASE.md.",
            500,
        )
    return normalized


@app.route("/api/settings/credit-limit", methods=["POST"])
def set_credit_limit():
    """Kept for backward compatibility with the sidebar's pencil-icon
    editor next to "Est. spend" — POST /api/settings now also accepts
    credit_limit_usd as part of a bulk update, using the same validation.
    `{"credit_limit_usd": null}` clears the override back to whatever
    REPLICATE_CREDIT_LIMIT_USD (if anything) is set to.
    """
    data = request.get_json(silent=True) or {}
    normalized = _save_setting("credit_limit_usd", data.get("credit_limit_usd"))
    return jsonify({"credit_limit_usd": float(normalized) if normalized else None}), 200


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Every generic scalar setting's current value plus the metadata the
    dashboard's Settings page renders itself from — label, input type,
    whether it costs tokens, and the (i)-tooltip note. settings_schema.py
    is the single source of truth for all of it, so the frontend never
    hardcodes a second copy that could drift out of sync."""
    settings_payload = []
    for entry in SETTINGS_SCHEMA:
        raw = db_client.get_setting(entry["key"])
        if entry["type"] == "number":
            try:
                value = float(raw) if raw else entry.get("default")
            except ValueError:
                value = entry.get("default")
        else:
            value = raw if raw else entry.get("default")
        settings_payload.append({**entry, "value": value})

    return jsonify({"categories": CATEGORIES, "settings": settings_payload}), 200


@app.route("/api/settings", methods=["POST"])
def update_settings():
    """Bulk-update one or more generic settings: `{"key": value, ...}`.
    Every key is validated against settings_schema.py before anything is
    saved, so one bad value in the batch doesn't partially apply the
    rest."""
    data = request.get_json(silent=True) or {}
    if not data:
        raise APIError("Request body must be a non-empty object", 400)

    normalized: Dict[str, str] = {}
    for key, raw_value in data.items():
        try:
            normalized[key] = validate_setting_value(key, raw_value)
        except ValueError as exc:
            raise APIError(str(exc), 400)

    for key, value in normalized.items():
        try:
            db_client.set_setting(key, value)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to save setting %s: %s", key, exc)
            raise APIError(
                "Couldn't save — the database's `settings` table may not "
                "exist yet. See docs/DATABASE.md.",
                500,
            )

    return jsonify({"saved": list(normalized.keys())}), 200


@app.route("/api/settings/reset", methods=["POST"])
def reset_settings():
    """Advanced / Danger Zone: revert every setting to its schema default
    or env-var fallback, including every agent's Agent Defaults overrides
    and active Skill selections (all stored in the same `settings`
    table). Does not touch the `skills` table itself or usage history —
    see /api/usage/reset for that."""
    try:
        db_client.reset_all_settings()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to reset settings: %s", exc)
        raise APIError("Couldn't reset settings", 500)
    return jsonify({"reset": True}), 200


@app.route("/api/settings/agent-config", methods=["GET"])
def get_agent_config_endpoint():
    """The full per-agent overrides matrix (enabled/model/temperature/
    max_tokens), each agent's built-in defaults, and the one available
    model override — everything the Agent Defaults settings page needs."""
    raw = db_client.get_setting("agent_config")
    try:
        current = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        current = {}
    return (
        jsonify(
            {
                "agents": AGENT_TYPES,
                "defaults": AGENT_BUILTIN_DEFAULTS,
                "cheaper_model": CHEAPER_MODEL,
                "config": current,
            }
        ),
        200,
    )


@app.route("/api/settings/agent-config", methods=["POST"])
def update_agent_config():
    """Saves the full Agent Defaults matrix in one call — the dashboard
    always sends the whole matrix, not a per-agent patch, so a bad entry
    for one agent can't get merged on top of stale saved data."""
    data = request.get_json(silent=True) or {}
    try:
        cleaned = validate_agent_config(data)
    except ValueError as exc:
        raise APIError(str(exc), 400)

    try:
        db_client.set_setting("agent_config", json.dumps(cleaned))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save agent config: %s", exc)
        raise APIError(
            "Couldn't save — the database's `settings` table may not exist "
            "yet. See docs/DATABASE.md.",
            500,
        )

    return jsonify({"config": cleaned}), 200


@app.route("/api/tasks", methods=["GET"])
def list_tasks_endpoint():
    """Recent tasks for the dashboard's Data Controls task browser.
    Optional `?agent_type=` filter and `?limit=` (default 50, capped at
    200 so a stray typo doesn't pull the whole table)."""
    agent_type = request.args.get("agent_type") or None
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
    except ValueError:
        limit = 50
    tasks = db_client.list_tasks(agent_type=agent_type, limit=limit)
    return jsonify({"tasks": tasks}), 200


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task_endpoint(task_id):
    """Deletes one saved task — Data Controls' per-row delete button."""
    if not db_client.delete_task(task_id):
        raise APIError("Failed to delete task", 500)
    return jsonify({"deleted": task_id}), 200


@app.route("/api/data/purge", methods=["POST"])
def purge_old_data():
    """Manual trigger behind the "Auto-purge tasks older than" setting —
    deletes tasks older than the given (or saved) number of days. Named
    "purge now" deliberately: Vercel has no background scheduler wired
    up here, so nothing is ever deleted unless this is called."""
    data = request.get_json(silent=True) or {}
    days = data.get("older_than_days")
    if days is None:
        saved = db_client.get_setting("retention_days")
        days = float(saved) if saved else None
    if days is None or float(days) <= 0:
        raise APIError(
            "older_than_days must be a positive number (or set the "
            "'Auto-purge tasks older than' setting first)",
            400,
        )
    try:
        deleted = db_client.purge_tasks_older_than(int(days))
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to purge old tasks: %s", exc)
        raise APIError("Purge failed", 500)
    return jsonify({"deleted_count": deleted}), 200


@app.route("/api/usage/reset", methods=["POST"])
def reset_usage_endpoint():
    """Advanced / Danger Zone: wipe all usage rollups (e.g. to start a
    fresh spend count for a new month). Does not touch task history —
    see /api/data/purge for that."""
    try:
        db_client.reset_usage()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to reset usage: %s", exc)
        raise APIError("Couldn't reset usage stats", 500)
    return jsonify({"reset": True}), 200


# ============================================
# SKILLS
# ============================================


@app.route("/api/skills", methods=["GET"])
def list_skills_endpoint():
    """Every saved skill, optionally filtered to one agent via
    `?agent_type=`, plus which skill (if any) is currently active per
    agent."""
    agent_type = request.args.get("agent_type") or None
    skills = db_client.list_skills(agent_type=agent_type)
    active_by_agent = {
        a["id"]: (db_client.get_setting(f"active_skill:{a['id']}") or None)
        for a in AGENT_TYPES
    }
    return (
        jsonify(
            {
                "skills": skills,
                "active_by_agent": active_by_agent,
                "agents": AGENT_TYPES,
            }
        ),
        200,
    )


@app.route("/api/skills", methods=["POST"])
def create_skill_endpoint():
    """Creates a new skill (a named, versioned prompt template). Doesn't
    activate it — POST /api/skills/<id>/activate does that separately,
    so you can save a draft without it immediately taking over an
    agent's real requests."""
    data = request.get_json(silent=True) or {}
    agent_type = data.get("agent_type")
    skill_name = (data.get("skill_name") or "").strip()
    template = (data.get("template") or "").strip()

    valid_agent_ids = {a["id"] for a in AGENT_TYPES}
    if agent_type not in valid_agent_ids:
        raise APIError(f"agent_type must be one of {sorted(valid_agent_ids)}", 400)
    if not skill_name:
        raise APIError("skill_name is required", 400)
    if not template:
        raise APIError("template is required", 400)

    try:
        skill_id = db_client.create_skill(
            agent_type=agent_type,
            skill_name=skill_name,
            template=template,
            description=data.get("description", ""),
            version=data.get("version") or "1.0",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create skill: %s", exc)
        raise APIError(
            "Couldn't save — the `skills` table may be missing the "
            "`template` column. See docs/DATABASE.md.",
            500,
        )
    return jsonify({"id": skill_id}), 201


@app.route("/api/skills/<skill_id>", methods=["PUT"])
def update_skill_endpoint(skill_id):
    """Edits an existing skill. Only whitelisted columns are writable."""
    data = request.get_json(silent=True) or {}
    fields = {
        k: v
        for k, v in data.items()
        if k in ("skill_name", "description", "template", "version", "is_active")
    }
    if not fields:
        raise APIError("No valid fields to update", 400)
    try:
        db_client.update_skill(skill_id, **fields)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to update skill %s: %s", skill_id, exc)
        raise APIError("Couldn't save skill", 500)
    return jsonify({"updated": skill_id}), 200


@app.route("/api/skills/<skill_id>", methods=["DELETE"])
def delete_skill_endpoint(skill_id):
    try:
        db_client.delete_skill(skill_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete skill %s: %s", skill_id, exc)
        raise APIError("Couldn't delete skill", 500)
    return jsonify({"deleted": skill_id}), 200


@app.route("/api/skills/<skill_id>/activate", methods=["POST"])
def activate_skill_endpoint(skill_id):
    """Makes this skill the one actually used for its agent's future
    requests, replacing that agent's built-in hardcoded prompt. Free —
    activating doesn't call any model."""
    skill = db_client.get_skill(skill_id)
    if not skill:
        raise APIError("Skill not found", 404)
    try:
        db_client.set_setting(f"active_skill:{skill['agent_type']}", skill_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to activate skill %s: %s", skill_id, exc)
        raise APIError("Couldn't activate skill", 500)
    return jsonify({"active_skill": skill_id, "agent_type": skill["agent_type"]}), 200


@app.route("/api/skills/deactivate", methods=["POST"])
def deactivate_skill_endpoint():
    """Reverts an agent back to its built-in hardcoded prompt."""
    data = request.get_json(silent=True) or {}
    agent_type = data.get("agent_type")
    valid_agent_ids = {a["id"] for a in AGENT_TYPES}
    if agent_type not in valid_agent_ids:
        raise APIError(f"agent_type must be one of {sorted(valid_agent_ids)}", 400)
    try:
        db_client.set_setting(f"active_skill:{agent_type}", "")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to deactivate skill for %s: %s", agent_type, exc)
        raise APIError("Couldn't deactivate skill", 500)
    return jsonify({"agent_type": agent_type, "active_skill": None}), 200


@app.route("/api/settings/test-webhook", methods=["POST"])
def test_webhook_endpoint():
    """Sends one real test payload to the saved webhook_url so you can
    confirm it's reachable before relying on it. Costs nothing — it's a
    plain HTTP POST with fake data, no Replicate call involved."""
    url = db_client.get_setting("webhook_url")
    if not url:
        raise APIError("No webhook_url is set", 400)
    payload = {
        "task_id": f"test-{int(datetime.now(timezone.utc).timestamp())}",
        "agent_type": "test",
        "status": "completed",
        "cost": 0.0,
        "output": "This is a test delivery from Jarvis's Settings page.",
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return jsonify({"delivered": True, "status_code": response.status_code}), 200
    except requests.RequestException as exc:
        return jsonify({"delivered": False, "error": str(exc)}), 200


# ============================================
# AGENT ENDPOINTS
# ============================================


def _deliver_webhook(agent_type: str, response: Dict[str, Any], cost: float) -> None:
    """Fire-and-forget POST to the saved webhook_url, if any. Runs after
    the real response is already fully computed, using data Jarvis
    already has — this never adds a Replicate call and must never fail
    (or even slow down) the actual response to the caller."""
    url = db_client.get_setting("webhook_url")
    if not url:
        return
    try:
        requests.post(
            url,
            json={
                "task_id": response.get("task_id"),
                "agent_type": agent_type,
                "status": response.get("status"),
                "cost": cost,
                "output": response.get("output"),
            },
            timeout=5,
        )
    except requests.RequestException as exc:
        logger.error("Webhook delivery to %s failed: %s", url, exc)


def _run_agent(
    agent: BaseAgent, agent_type: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Shared request-handling logic for every agent endpoint: resolve
    settings onto the agent, call it, persist the result best-effort,
    and shape the response.

    Every agent implements `process(**kwargs)`, so the JSON body's keys
    are passed straight through as that agent's arguments.
    """
    agent.settings = resolve_agent_settings(db_client, agent_type)

    result = agent.process(**data)
    task_id = result.get("task_id")
    usage = result.get("usage") or {}

    gpu_rate_override = _get_gpu_rate_override()
    if gpu_rate_override is not None and "predict_time_seconds" in usage:
        cost = round(usage["predict_time_seconds"] * gpu_rate_override, 6)
    else:
        cost = usage.get("estimated_cost_usd", 0.0)

    # Persistence is best-effort: a working result should still reach
    # the caller even if the DB/storage backends are briefly unavailable.
    try:
        db_client.save_task(
            agent_type=agent_type,
            input_data=data,
            output_data=result,
            status="completed",
            cost=cost,
            task_id=task_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to persist task to database: %s", exc)

    try:
        db_client.record_usage(
            agent_type=agent_type,
            model_name=agent.model_name,
            tokens_used=usage.get("total_tokens", 0),
            cost=cost,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to record usage: %s", exc)

    try:
        r2_client.save_task_output(task_id, result)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to back up task output to R2: %s", exc)

    response = {
        "task_id": task_id,
        "output": result.get("output", ""),
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _deliver_webhook(agent_type, response, cost)

    return response


def _check_rate_limit() -> None:
    """Raises RateLimitError (429) if Rate Limiting's "max requests per
    minute" is set and exceeded, counted from real task history rather
    than in-memory state (see DatabaseClient.count_recent_tasks — Vercel
    serverless functions don't reliably keep process memory between
    requests, so an in-memory counter would silently do nothing)."""
    saved = db_client.get_setting("rate_limit_per_minute")
    try:
        limit = int(float(saved)) if saved else 0
    except ValueError:
        limit = 0
    if limit > 0 and db_client.count_recent_tasks(60) >= limit:
        raise RateLimitError(
            f"Rate limit exceeded: max {limit} requests/minute. "
            "Adjust this in Settings > Rate Limiting."
        )


def _make_agent_route(agent: BaseAgent, agent_type: str, required_field: str):
    """Build a Flask view function for a simple `{field: ...}` -> agent
    endpoint, so each route below doesn't repeat the same boilerplate."""

    def view():
        try:
            if not is_agent_enabled(db_client, agent_type):
                raise APIError(
                    f"The {agent_type} agent is disabled in Settings > Agent Defaults.",
                    403,
                )
            _check_rate_limit()

            data = request.get_json(silent=True)
            if not data or required_field not in data:
                raise APIError(f"Missing required field: '{required_field}'", 400)

            logger.info("%s request received", agent_type)
            response = _run_agent(agent, agent_type, data)
            logger.info("%s completed: %s", agent_type, response["task_id"])
            return jsonify(response), 200

        except APIError as exc:
            body, code = handle_error(exc)
            return jsonify(body), code
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error in %s endpoint: %s", agent_type, exc)
            body, code = handle_error(APIError("Internal server error", 500))
            return jsonify(body), code

    view.__name__ = f"{agent_type}_endpoint"
    return view


app.add_url_rule(
    "/api/agents/brainstorm",
    view_func=_make_agent_route(brainstorm_agent, "brainstorm", "topic"),
    methods=["POST"],
)
app.add_url_rule(
    "/api/agents/code",
    view_func=_make_agent_route(coder_agent, "coder", "requirements"),
    methods=["POST"],
)
app.add_url_rule(
    "/api/agents/test",
    view_func=_make_agent_route(tester_agent, "tester", "code"),
    methods=["POST"],
)
app.add_url_rule(
    "/api/agents/deploy",
    view_func=_make_agent_route(deployer_agent, "deployer", "change_summary"),
    methods=["POST"],
)
app.add_url_rule(
    "/api/agents/document",
    view_func=_make_agent_route(document_agent, "document", "subject"),
    methods=["POST"],
)
app.add_url_rule(
    "/api/agents/qa",
    view_func=_make_agent_route(qa_agent, "qa", "code"),
    methods=["POST"],
)


# ============================================
# ERROR HANDLERS
# ============================================


@app.errorhandler(APIError)
def api_error(error):
    """Catches APIError raised outside `_make_agent_route` (which has its
    own try/except) — e.g. /api/settings/credit-limit — so those routes
    don't need to duplicate that handling."""
    body, code = handle_error(error)
    return jsonify(body), code


@app.errorhandler(404)
def not_found(_error):
    return (
        jsonify(
            {
                "error": "Endpoint not found",
                "status": 404,
                "message": "The requested endpoint does not exist. Check docs/API_SPEC.md.",
            }
        ),
        404,
    )


@app.errorhandler(500)
def internal_error(error):
    logger.error("Internal server error: %s", error)
    return (
        jsonify(
            {
                "error": "Internal server error",
                "status": 500,
                "message": "Something went wrong. Check logs/jarvis.log for details.",
            }
        ),
        500,
    )


# ============================================
# REQUEST LOGGING
# ============================================


@app.before_request
def log_request():
    logger.debug("%s %s", request.method, request.path)


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


if __name__ == "__main__":
    debug_mode = os.getenv("DEBUG", "False") == "True"
    host = os.getenv("HOST") or "0.0.0.0"
    port = int(os.getenv("PORT") or 5000)

    logger.info("Starting Jarvis API...")
    logger.info("Debug: %s", debug_mode)
    logger.info("URL: http://localhost:%s", port)

    app.run(host=host, port=port, debug=debug_mode, use_reloader=debug_mode)
