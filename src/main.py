"""JARVIS API — Flask application entry point.

This is the front door: every request comes in here and gets routed
to the right agent. Phase 0 wires up the Brainstorm agent with a
health/status pair of endpoints; Phase 1 adds Coder/Tester/Deployer.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

load_dotenv()

from src.agents.brainstorm_agent import BrainstormAgent  # noqa: E402
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
    logger.info("All clients initialized successfully")
except Exception as exc:
    logger.error("Failed to initialize clients: %s", exc)
    raise


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


# ============================================
# AGENT ENDPOINTS
# ============================================


@app.route("/api/agents/brainstorm", methods=["POST"])
def brainstorm():
    """Generate ideas for a topic.

    Request body:
        {"topic": "...", "context": "...", "style": "detailed"}
    """
    try:
        data = request.get_json(silent=True)
        if not data or "topic" not in data:
            raise APIError("Missing required field: 'topic'", 400)

        logger.info("Brainstorm request received: %s", data["topic"])

        result = brainstorm_agent.brainstorm(
            topic=data.get("topic"),
            context=data.get("context", ""),
            style=data.get("style", "detailed"),
        )

        task_id = result.get("task_id")

        # Persistence is best-effort: a working brainstorm result should
        # still reach the caller even if the DB/storage backends are
        # briefly unavailable.
        try:
            db_client.save_task(
                agent_type="brainstorm",
                input_data=data,
                output_data=result,
                status="completed",
                task_id=task_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist task to database: %s", exc)

        try:
            r2_client.save_task_output(task_id, result)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to back up task output to R2: %s", exc)

        response = {
            "task_id": task_id,
            "ideas": result.get("ideas", []),
            "reasoning": result.get("reasoning", ""),
            "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("Brainstorm completed: %s", task_id)
        return jsonify(response), 200

    except APIError as exc:
        body, code = handle_error(exc)
        return jsonify(body), code
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in /api/agents/brainstorm: %s", exc)
        body, code = handle_error(APIError("Internal server error", 500))
        return jsonify(body), code


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
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))

    logger.info("Starting Jarvis API...")
    logger.info("Debug: %s", debug_mode)
    logger.info("URL: http://localhost:%s", port)

    app.run(host=host, port=port, debug=debug_mode, use_reloader=debug_mode)
