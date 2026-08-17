"""Single source of truth for every user-configurable setting.

Each entry drives three things at once, so they can never drift apart:
  1. `GET /api/settings` — the frontend renders the settings page's
     generic fields straight from this list (label, input type, current
     value) instead of the HTML hardcoding a second copy of it.
  2. Validation on `POST /api/settings` — every incoming value is checked
     against its entry's `type`/`min`/`max`/`options` here, in one place,
     rather than once per field in the view function.
  3. The (i) tooltip shown next to every field in the dashboard — `note`
     is written to always say what the setting does, how it takes
     effect, and — the point of this whole exercise — whether it costs
     Replicate tokens/compute and why.

Settings that aren't a single scalar (the agent model/temperature/enabled
matrix, Skills, the Connectors placeholder, System Status, the task
browser, and the danger-zone actions) have their own dedicated endpoints
and UI instead of living here — forcing genuinely structured data through
a flat key/value schema would make it harder to read, not easier.
"""

from typing import Any, Dict, List

SETTINGS_SCHEMA: List[Dict[str, Any]] = [
    {
        "key": "credit_limit_usd",
        "category": "usage_billing",
        "label": "Credit limit",
        "type": "number",
        "min": 0,
        "unit": "$",
        "default": None,
        "costs_tokens": False,
        "note": (
            "A budget you set yourself, in USD, to track estimated spend "
            "against. Replicate has no API for your real account balance "
            "(only /v1/account, which returns just your username) — this "
            "number never touches Replicate, it's purely local bookkeeping "
            "against the cost estimates Jarvis already computes from each "
            "prediction's own reported tokens/compute time. Match it to "
            "what you've actually loaded at replicate.com/account/billing. "
            "Costs nothing to set — it's just a comparison threshold."
        ),
    },
    {
        "key": "gpu_rate_per_second_usd",
        "category": "usage_billing",
        "label": "GPU rate override ($/sec)",
        "type": "number",
        "min": 0,
        "step": 0.0001,
        "unit": "$/sec",
        "default": None,
        "costs_tokens": False,
        "note": (
            "Most of Jarvis's models are billed by Replicate per second of "
            "compute rather than per token. Cost estimates use Replicate's "
            "published Nvidia A100 rate ($0.0014/sec) by default — override "
            "this only if you know your models actually run on different "
            "hardware. Changes the estimate shown, not what Replicate "
            "charges you. Costs nothing to set."
        ),
    },
    {
        "key": "budget_alert_threshold_pct",
        "category": "usage_billing",
        "label": "Budget alert threshold",
        "type": "number",
        "min": 1,
        "max": 100,
        "unit": "%",
        "default": None,
        "costs_tokens": False,
        "note": (
            "When estimated spend crosses this percentage of your credit "
            "limit, the dashboard shows an in-app banner the next time it "
            "polls usage (every ~20s). There's no email/SMS/push delivery "
            "— this only works while the dashboard tab is open. Requires a "
            "credit limit to be set first. Costs nothing — it only reads "
            "numbers Jarvis already tracks."
        ),
    },
    {
        "key": "default_agent",
        "category": "agent_defaults",
        "label": "Default agent for new chats",
        "type": "select",
        "options": [
            "brainstorm",
            "coder",
            "tester",
            "deployer",
            "document",
            "qa",
        ],
        "default": "brainstorm",
        "costs_tokens": False,
        "note": (
            "Which agent is pre-selected when you start a new chat. Purely "
            "a UI convenience — costs nothing, and doesn't call any model "
            "until you actually send a message."
        ),
    },
    {
        "key": "custom_instructions",
        "category": "personalization",
        "label": "Custom instructions",
        "type": "textarea",
        "max_length": 1000,
        "default": "",
        "costs_tokens": True,
        "note": (
            "Free text prepended to every single agent request from now "
            "on — Brainstorm, Coder, Tester, Deployer, Document, and QA "
            "all get it, on every call, permanently until you clear it. "
            "This is the one setting with a genuinely recurring cost: it "
            "isn't a one-time toggle, it's extra input on every future "
            "request. Roughly 4 characters ≈ 1 token, so 400 characters "
            "here adds roughly 100 tokens (and a little compute time) to "
            "every request from every agent, forever. The settings page "
            "shows a live estimate as you type — keep it short and only "
            "as long as it actually needs to be."
        ),
    },
    {
        "key": "rate_limit_per_minute",
        "category": "rate_limiting",
        "label": "Max requests per minute",
        "type": "number",
        "min": 0,
        "default": 0,
        "costs_tokens": False,
        "note": (
            "Rejects agent requests (HTTP 429) once you've made this many "
            "in the trailing 60 seconds, counted from your own task "
            "history — no extra model call needed to enforce it. 0 means "
            "unlimited. This setting only ever *prevents* spend, it never "
            "adds any — it's a safety rail against a runaway loop or a "
            "misclick firing off dozens of requests before you notice."
        ),
    },
    {
        "key": "webhook_url",
        "category": "webhooks",
        "label": "Webhook URL",
        "type": "text",
        "default": "",
        "costs_tokens": False,
        "note": (
            "When set, Jarvis POSTs a JSON summary (task_id, agent_type, "
            "status, cost, output) to this URL after every completed "
            "task — fire-and-forget, it never blocks or fails your actual "
            "response if the URL is down or slow. This fires after the "
            "real Replicate call already happened, using data Jarvis "
            "already has, so it adds no tokens or model calls of its own."
        ),
    },
    {
        "key": "retention_days",
        "category": "data_controls",
        "label": "Auto-purge tasks older than (days)",
        "type": "number",
        "min": 0,
        "default": 0,
        "costs_tokens": False,
        "note": (
            "Sets how old a saved task/output can get before it's eligible "
            "for deletion. 0 means keep everything forever. Important: "
            "Jarvis has no background scheduler running on Vercel, so this "
            'is enforced only when you click "Purge now" below — it is '
            "not automatic yet. Purely a database housekeeping setting; "
            "no Replicate calls involved."
        ),
    },
]

SETTINGS_BY_KEY: Dict[str, Dict[str, Any]] = {
    entry["key"]: entry for entry in SETTINGS_SCHEMA
}

CATEGORIES: List[Dict[str, str]] = [
    {"id": "usage_billing", "label": "Usage & Billing"},
    {"id": "agent_defaults", "label": "Agent Defaults"},
    {"id": "data_controls", "label": "Data Controls"},
    {"id": "appearance", "label": "Appearance"},
    {"id": "system_status", "label": "System Status"},
    {"id": "skills", "label": "Skills"},
    {"id": "connectors", "label": "Connectors / MCP"},
    {"id": "personalization", "label": "Custom Instructions"},
    {"id": "rate_limiting", "label": "Rate Limiting"},
    {"id": "webhooks", "label": "Webhooks"},
    {"id": "danger_zone", "label": "Advanced / Danger Zone"},
]

# Agents whose per-request behavior the "Agent Defaults" matrix can override.
# (agent_type, display label) — order matches the dashboard's own agent list.
AGENT_TYPES: List[Dict[str, str]] = [
    {"id": "brainstorm", "label": "Brainstorm"},
    {"id": "coder", "label": "Coder"},
    {"id": "tester", "label": "Tester"},
    {"id": "deployer", "label": "Deployer"},
    {"id": "document", "label": "Document"},
    {"id": "qa", "label": "QA"},
]

# The one pre-vetted swap-in for "Model override": an official Replicate
# model (no version pinning needed, same shortcut-endpoint pattern already
# used for Llama-3-70B), smaller and cheaper/faster than every agent's
# current default. Deliberately not a free-text field — an unverified
# model or version id would silently break an agent instead of saving
# money, so overrides are limited to this one known-safe alternative.
CHEAPER_MODEL = "meta/meta-llama-3-8b-instruct"

# Each agent's built-in defaults, shown in the Agent Defaults UI as
# placeholders ("leave blank to use the default: ...") so an override
# field starts empty rather than pre-filled with a guess.
AGENT_BUILTIN_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "brainstorm": {"model": "Llama 3 70B", "temperature": 0.7, "max_tokens": 1024},
    "coder": {"model": "DeepSeek-Coder 33B", "temperature": 0.2, "max_tokens": 1024},
    "tester": {"model": "Llama 3 70B", "temperature": 0.2, "max_tokens": 1024},
    "deployer": {"model": "Mistral 7B", "temperature": 0.3, "max_tokens": 512},
    "document": {"model": "Llama 3 70B", "temperature": 0.4, "max_tokens": 1024},
    "qa": {"model": "DeepSeek-Coder 33B", "temperature": 0.2, "max_tokens": 1024},
}


def validate_setting_value(key: str, raw_value: Any) -> str:
    """Validate `raw_value` for `key` against its schema entry.

    Returns the normalized string to persist (settings are always stored
    as text — see DatabaseClient.set_setting), or "" to clear/reset the
    setting to its default. Raises ValueError with a human-readable
    message on anything invalid.
    """
    entry = SETTINGS_BY_KEY.get(key)
    if entry is None:
        raise ValueError(f"Unknown setting: '{key}'")

    if raw_value is None or raw_value == "":
        return ""

    if entry["type"] == "number":
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"'{key}' must be a number")
        if "min" in entry and value < entry["min"]:
            raise ValueError(f"'{key}' must be >= {entry['min']}")
        if "max" in entry and value > entry["max"]:
            raise ValueError(f"'{key}' must be <= {entry['max']}")
        return str(value)

    if entry["type"] == "select":
        if raw_value not in entry["options"]:
            raise ValueError(f"'{key}' must be one of {entry['options']}")
        return str(raw_value)

    if entry["type"] in ("text", "textarea"):
        text = str(raw_value)
        max_length = entry.get("max_length")
        if max_length and len(text) > max_length:
            raise ValueError(f"'{key}' must be {max_length} characters or fewer")
        return text

    raise ValueError(f"Unhandled setting type for '{key}'")


def validate_agent_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validates the full "Agent Defaults" matrix (one entry per agent:
    enabled/model/temperature/max_tokens). Raises ValueError with a
    human-readable message on anything invalid; returns a cleaned dict
    ready to JSON-encode into the `agent_config` setting.
    """
    valid_agent_ids = {a["id"] for a in AGENT_TYPES}
    cleaned: Dict[str, Any] = {}

    for agent_id, cfg in (raw or {}).items():
        if agent_id not in valid_agent_ids:
            raise ValueError(f"Unknown agent: '{agent_id}'")
        if not isinstance(cfg, dict):
            raise ValueError(f"Config for '{agent_id}' must be an object")

        entry: Dict[str, Any] = {}

        if cfg.get("enabled") is not None:
            if not isinstance(cfg["enabled"], bool):
                raise ValueError(f"'{agent_id}.enabled' must be true or false")
            entry["enabled"] = cfg["enabled"]

        if cfg.get("model") is not None:
            if cfg["model"] not in ("cheaper",):
                raise ValueError(f"'{agent_id}.model' must be 'cheaper' or null")
            entry["model"] = cfg["model"]

        if cfg.get("temperature") is not None:
            try:
                temperature = float(cfg["temperature"])
            except (TypeError, ValueError):
                raise ValueError(f"'{agent_id}.temperature' must be a number")
            if not 0 <= temperature <= 2:
                raise ValueError(f"'{agent_id}.temperature' must be between 0 and 2")
            entry["temperature"] = temperature

        if cfg.get("max_tokens") is not None:
            try:
                max_tokens = int(cfg["max_tokens"])
            except (TypeError, ValueError):
                raise ValueError(f"'{agent_id}.max_tokens' must be a whole number")
            if not 1 <= max_tokens <= 4096:
                raise ValueError(f"'{agent_id}.max_tokens' must be between 1 and 4096")
            entry["max_tokens"] = max_tokens

        cleaned[agent_id] = entry

    return cleaned
