"""Resolves user-configurable settings into the values that actually
change what happens on a single agent request: whether the agent is
enabled, which model it calls, temperature/max-token overrides, the
global custom-instructions prefix, and an active skill template.

`main.py` calls `resolve_agent_settings()` once per request and hands the
result to the agent as `agent.settings` — agents themselves never touch
the settings table's key/JSON shape directly, so that shape only has to
be known in one place.
"""

import json
import logging
from string import Template
from typing import Any, Dict, Optional

from src.settings_schema import CHEAPER_MODEL

logger = logging.getLogger(__name__)


def get_agent_config(db_client) -> Dict[str, Dict[str, Any]]:
    """The full per-agent config matrix (enabled/model/temperature/
    max_tokens for every agent), stored as one JSON blob under the
    `agent_config` setting key so a single request loads it in one
    round trip instead of five."""
    raw = db_client.get_setting("agent_config")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        logger.error("agent_config setting is not valid JSON: %r", raw)
        return {}


def is_agent_enabled(db_client, agent_type: str) -> bool:
    """Checked before an agent even starts a task — disabling an agent
    should reject the request outright, not run it and discard the
    result."""
    return bool(get_agent_config(db_client).get(agent_type, {}).get("enabled", True))


def resolve_agent_settings(db_client, agent_type: str) -> Dict[str, Any]:
    """Every setting that can influence a single agent call, resolved
    once per request into a plain dict the agent can read without
    knowing anything about how settings are stored.

    Never raises — a broken setting should degrade to "use the agent's
    built-in default", not break the request.
    """
    cfg = get_agent_config(db_client).get(agent_type, {})

    skill_template = None
    try:
        skill_id = db_client.get_setting(f"active_skill:{agent_type}")
        if skill_id:
            skill = db_client.get_skill(skill_id)
            if skill and skill.get("template") and skill.get("is_active", True):
                skill_template = skill["template"]
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to resolve active skill for %s: %s", agent_type, exc)

    return {
        "enabled": cfg.get("enabled", True),
        "model": CHEAPER_MODEL if cfg.get("model") == "cheaper" else None,
        "temperature": cfg.get("temperature"),
        "max_tokens": cfg.get("max_tokens"),
        "custom_instructions": (
            db_client.get_setting("custom_instructions") or ""
        ).strip(),
        "skill_template": skill_template,
    }


def resolve_model_and_version(
    settings: Dict[str, Any], default_model: str, default_version: Optional[str] = None
) -> tuple:
    """(model, version) to actually call, given an already-resolved
    settings dict. The one available override (`CHEAPER_MODEL`) is always
    an official Replicate model, so it never takes a version id — passing
    the old community model's version alongside a different model would
    silently break the call."""
    if settings.get("model"):
        return settings["model"], None
    return default_model, default_version


def render_skill_template(template: str, variables: Dict[str, Any]) -> str:
    """Fills a skill's `$variable`-style template. `safe_substitute`
    (not `substitute`) leaves any placeholder the caller didn't supply
    as literal text instead of raising — a skill referencing an unknown
    variable should degrade visibly, not 500 the request."""
    return Template(template).safe_substitute(**variables)
