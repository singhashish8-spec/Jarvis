"""JARVIS API — Flask application entry point.

This is the front door: every request comes in here and gets routed
to the right agent. Five agents are wired up: Brainstorm, Coder,
Tester, Deployer, and Document/QA — each calling a real model on
Replicate (see docs/AGENTS.md for which model and why).
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict

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
from src.storage.r2_client import R2Client  # noqa: E402
from src.utils.errors import APIError, handle_error  # noqa: E402
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


@app.route("/api/usage", methods=["GET"])
def usage_check():
    """Live token usage and estimated spend, for the dashboard's usage
    widget. Replicate has no API for real account balance/credit (only
    /v1/account, which returns username/type) — cost here is an estimate
    computed from each prediction's own reported token counts or compute
    time (see replicate_client.py), rolled up as tasks complete.

    `credit_limit_usd` is whatever the user sets in REPLICATE_CREDIT_LIMIT_USD
    to match what they've actually loaded on replicate.com/account/billing;
    it's null (no bar shown) until set.
    """
    summary = db_client.get_usage_summary()
    limit = config.REPLICATE_CREDIT_LIMIT_USD
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
    return jsonify(summary), 200


# ============================================
# AGENT ENDPOINTS
# ============================================


def _run_agent(
    agent: BaseAgent, agent_type: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Shared request-handling logic for every agent endpoint: call the
    agent, persist the result best-effort, and shape the response.

    Every agent implements `process(**kwargs)`, so the JSON body's keys
    are passed straight through as that agent's arguments.
    """
    result = agent.process(**data)
    task_id = result.get("task_id")
    usage = result.get("usage") or {}
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

    return {
        "task_id": task_id,
        "output": result.get("output", ""),
        "status": "completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _make_agent_route(agent: BaseAgent, agent_type: str, required_field: str):
    """Build a Flask view function for a simple `{field: ...}` -> agent
    endpoint, so each route below doesn't repeat the same boilerplate."""

    def view():
        try:
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
