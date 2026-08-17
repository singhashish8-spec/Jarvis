# API Specification

Base URL (local): `http://localhost:5000`

All responses are JSON. Every agent endpoint calls a real model on
Replicate and costs a small amount per call — see [AGENTS.md](AGENTS.md)
for which model each one uses.

---

## `GET /health`

Liveness check — is the process running at all.

**Response `200`**
```json
{
  "status": "healthy",
  "service": "Jarvis API",
  "timestamp": "2026-08-20T10:30:00+00:00",
  "version": "0.1.0"
}
```

---

## `GET /status`

Readiness check — is everything the API depends on actually reachable.

**Response `200`** (all components healthy)
```json
{
  "status": "operational",
  "timestamp": "2026-08-20T10:30:00+00:00",
  "components": {
    "database": "healthy",
    "replicate": "healthy",
    "storage": "healthy"
  }
}
```

**Response `503`** (one or more components unavailable — e.g. credentials
not filled in yet)
```json
{
  "status": "degraded",
  "timestamp": "2026-08-20T10:30:00+00:00",
  "components": {
    "database": "unavailable",
    "replicate": "healthy",
    "storage": "unavailable"
  }
}
```

---

## `GET /api/usage`

Live token usage and estimated spend, for the sidebar's usage popover and
Settings > Usage & Billing. **Replicate has no API for real account
balance/credit** — `/v1/account` only returns username/type, nothing
financial (confirmed against Replicate's own docs). Every number here is
derived from what each prediction actually reports (token counts when the
model provides them, compute time otherwise — see
[AGENTS.md](AGENTS.md#cost-estimation)), and `credit_limit_usd` is a budget
you set yourself (Settings > Usage & Billing, or `REPLICATE_CREDIT_LIMIT_USD`
as a fallback) to match what you've loaded on
[replicate.com/account/billing](https://replicate.com/account/billing) —
that page remains the authoritative source for your real balance.

**Response `200`**
```json
{
  "tokens_used_today": 4210,
  "tokens_used_total": 128430,
  "estimated_cost_usd_today": 0.0842,
  "estimated_cost_usd_total": 1.9031,
  "credit_limit_usd": 10.0,
  "credit_remaining_usd": 8.0969,
  "cost_note": "Estimated from Replicate's own per-prediction metrics (tokens or compute time) — Replicate's API does not expose real account balance. See replicate.com/account/billing for the authoritative figure.",
  "budget_alert": {"threshold_pct": 80.0, "current_pct": 19.0, "triggered": false},
  "by_agent": [{"agent_type": "brainstorm", "tokens_used": 2000, "cost": 0.05}],
  "rate_limit": {"limit_per_minute": 20, "current": 4}
}
```

`credit_limit_usd` and `credit_remaining_usd` are `null` when no budget
has been saved (dashboard or env var) — the sidebar just shows tokens and
estimated spend with no budget bar in that case. `by_agent` is today's
`usage` rows (one per agent that's run at least once today) — the
sidebar popover renders it as a segmented bar. `rate_limit.limit_per_minute`
is `null` when Rate Limiting is unset.

---

## `GET /api/storage`

R2 (file backups) and Supabase (row counts) storage usage, for the
sidebar's usage popover. Both sides are best-effort — a failure on either
degrades to zeros rather than breaking the whole response. Postgres disk
size isn't included: that requires a raw SQL connection or a pre-created
RPC function, neither of which this REST-only client has — row counts are
the closest available signal.

**Response `200`**
```json
{
  "r2": {"total_bytes": 18400000, "object_count": 42, "truncated": false},
  "supabase_tables": {"tasks": 42, "usage": 6, "skills": 3}
}
```

`r2.truncated` is `true` if the bucket has more than 5000 objects (the
listing stops there rather than paging through an unbounded bucket on
every popover open); `total_bytes`/`object_count` reflect only what was
counted in that case, not the true total.

---

## Connectors — Dropbox

The one real connector (Drive/Slack/GitHub are still placeholders, no
endpoints). Requires `DROPBOX_APP_KEY`/`DROPBOX_APP_SECRET` — see
`.env.example` for setup. Auth state (a refresh token) lives in the
`settings` table under keys not part of `SETTINGS_SCHEMA`, so it never
appears in `GET /api/settings`.

### `GET /api/connectors/dropbox/status`

```json
{"configured": true, "connected": true, "account_email": "you@example.com"}
```
`configured` reflects whether the env vars are set; `connected` whether a
refresh token is stored; `account_email` is `null` until connected.

### `GET /api/connectors/dropbox/authorize`

`302` redirect into Dropbox's OAuth consent screen. `400` if not
configured. Not meant to be fetched via `fetch()` — the dashboard
navigates the whole page here (`window.location.href = ...`).

### `GET /api/connectors/dropbox/callback`

Dropbox redirects here after consent. Exchanges the one-time code for a
refresh token, stores it, and redirects to `/?connector=dropbox&status=connected`
(or `status=error` if the code/exchange failed) — the dashboard reads that
query param on load to show a toast and clears it from the URL.

### `POST /api/connectors/dropbox/disconnect`

Clears the stored refresh token. `{"disconnected": true}`.

### `GET /api/connectors/dropbox/files?path=<path>`

Lists one folder's immediate children (`path=""` is the account root).
`400` if not connected; `502` if Dropbox itself errors.
```json
{"path": "/Projects", "entries": [{"name": "notes.txt", "path": "/Projects/notes.txt", "is_folder": false, "size": 812}]}
```

### `POST /api/connectors/dropbox/pull`

Body: `{"path": "/Projects/notes.txt"}`. Downloads that file's text
content, capped at ~200KB (~50k tokens) so one click can't blow up a
prompt. `400` if `path` is missing or Dropbox isn't connected; `502` on a
Dropbox-side failure.
```json
{"path": "/Projects/notes.txt", "content": "..."}
```
Pulling a file costs nothing by itself — it's copied to your clipboard,
not injected into any prompt. Only pasting it into a message counts as
input tokens, same as pasting anything else by hand.

---

## `POST /api/settings/credit-limit`

Saves the budget `GET /api/usage` tracks spend against, persisted in the
database's `settings` table. Kept as a dedicated endpoint for backward
compatibility — Settings > Usage & Billing's credit-limit field now
saves through the generic `POST /api/settings` instead, with identical
validation. Either way, setting a budget doesn't require touching Vercel
env vars or `.env`, and a saved value takes precedence over
`REPLICATE_CREDIT_LIMIT_USD`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `credit_limit_usd` | number or `null` | yes | Non-negative. `null` clears the saved override, falling back to `REPLICATE_CREDIT_LIMIT_USD` if set. |

```bash
curl -X POST http://localhost:5000/api/settings/credit-limit \
  -H "Content-Type: application/json" \
  -d '{"credit_limit_usd": 10.0}'
```

**Response `200`**
```json
{"credit_limit_usd": 10.0}
```

**Response `400`** — `credit_limit_usd` missing, negative, or not a number.

**Response `500`** — couldn't save, most likely because the `settings`
table doesn't exist yet in your Supabase project (see
[DATABASE.md](DATABASE.md)).

---

## Settings endpoints

See [SETTINGS.md](SETTINGS.md) for what each setting does, whether it costs
tokens, and how it takes effect — this section is just the request/response
shapes.

### `GET /api/settings`

Every generic scalar setting (Usage & Billing's credit limit/GPU rate/budget
alert, Custom Instructions, Rate Limiting, Webhooks, Data Controls' retention
days, Agent Defaults' default-agent) plus the metadata the dashboard renders
itself from — label, input type, whether it costs tokens, and the (i)-tooltip
note. [`settings_schema.py`](../src/settings_schema.py) is the single source
of truth for all of it.

**Response `200`**
```json
{
  "categories": [{"id": "usage_billing", "label": "Usage & Billing"}, "..."],
  "settings": [
    {
      "key": "credit_limit_usd", "category": "usage_billing", "label": "Credit limit",
      "type": "number", "min": 0, "unit": "$", "default": null, "costs_tokens": false,
      "note": "A budget you set yourself...", "value": 10.0
    }
  ]
}
```

### `POST /api/settings`

Bulk-updates one or more generic settings: `{"key": value, ...}`. Every key is
validated against `settings_schema.py` before anything is saved, so one bad
value in the batch doesn't partially apply the rest. `null` clears a setting
back to its default/env-var fallback.

```bash
curl -X POST http://localhost:5000/api/settings \
  -H "Content-Type: application/json" \
  -d '{"rate_limit_per_minute": 20, "webhook_url": "https://example.com/hook"}'
```

**Response `200`**: `{"saved": ["rate_limit_per_minute", "webhook_url"]}`
**Response `400`**: an unknown key, or a value that fails its schema's type/range check.

### `POST /api/settings/reset`

Advanced / Danger Zone. Reverts every setting to its default/env-var
fallback, including Agent Defaults overrides and active Skill selections.
Does not delete Skills themselves or any chat/task history.

**Response `200`**: `{"reset": true}`

### `GET /api/settings/agent-config`

The full Agent Defaults matrix: every agent's built-in defaults, the one
available model override, and any saved overrides.

**Response `200`**
```json
{
  "agents": [{"id": "brainstorm", "label": "Brainstorm"}, "..."],
  "defaults": {"brainstorm": {"model": "Llama 3 70B", "temperature": 0.7, "max_tokens": 1024}, "..."},
  "cheaper_model": "meta/meta-llama-3-8b-instruct",
  "config": {"coder": {"enabled": false, "model": "cheaper", "temperature": 0.5, "max_tokens": 300}}
}
```

### `POST /api/settings/agent-config`

Saves the full matrix in one call (not a per-agent patch — always send the
whole object). Each agent's entry accepts `enabled` (bool), `model`
(`"cheaper"` or `null`), `temperature` (0–2), `max_tokens` (1–4096); omit a
key to leave that agent using its built-in default.

**Response `200`**: `{"config": {...}}` (the cleaned, saved matrix)
**Response `400`**: unknown agent id, wrong type, or an out-of-range value.

### `GET /api/tasks`

Recent tasks for Data Controls' task browser. `?agent_type=` filters;
`?limit=` defaults to 50, capped at 200.

**Response `200`**: `{"tasks": [{"id": "...", "agent_type": "coder", "input": {...}, "created_at": "...", "cost": 0.002}, "..."]}`

### `DELETE /api/tasks/<task_id>`

Deletes one saved task. **Response `200`**: `{"deleted": "<task_id>"}`

### `POST /api/data/purge`

Manual trigger behind Data Controls' "Auto-purge tasks older than" setting —
deletes tasks older than the given (or saved) number of days. Named "purge
now" deliberately: there's no scheduler wired up on Vercel, so nothing is
ever deleted unless this is called.

```bash
curl -X POST http://localhost:5000/api/data/purge \
  -H "Content-Type: application/json" -d '{"older_than_days": 30}'
```

**Response `200`**: `{"deleted_count": 12}`
**Response `400`**: no `older_than_days` given and no `retention_days` setting saved.

### `POST /api/usage/reset`

Advanced / Danger Zone. Wipes all `usage` table rollups (e.g. to start a
fresh spend count for a new month). Does not touch task history.

**Response `200`**: `{"reset": true}`

---

## Skills endpoints

See [SETTINGS.md#skills](SETTINGS.md#skills) for the per-agent template
variables and what activating a skill actually changes.

### `GET /api/skills`

`?agent_type=` filters to one agent's skills.

**Response `200`**
```json
{
  "skills": [{"id": "...", "agent_type": "coder", "skill_name": "Terse code", "template": "...", "version": "1.0", "is_active": true}],
  "active_by_agent": {"brainstorm": null, "coder": "skill-id-here", "...": null},
  "agents": [{"id": "brainstorm", "label": "Brainstorm"}, "..."]
}
```

### `POST /api/skills`

Creates a skill (doesn't activate it — that's a separate call, so a draft
doesn't immediately take over an agent's real requests).

| Field | Type | Required |
|---|---|---|
| `agent_type` | string, one of the 6 agent ids | yes |
| `skill_name` | string | yes |
| `template` | string (`$variable` placeholders) | yes |
| `description` | string | no |
| `version` | string | no (defaults to `"1.0"`) |

**Response `201`**: `{"id": "<new skill id>"}`
**Response `400`**: missing/invalid `agent_type`, or missing `skill_name`/`template`.
**Response `500`**: likely the `skills` table is missing its `template` column — see [DATABASE.md](DATABASE.md).

### `PUT /api/skills/<skill_id>`

Edits `skill_name`, `description`, `template`, `version`, and/or `is_active`
— any other field is ignored. **Response `200`**: `{"updated": "<skill_id>"}`

### `DELETE /api/skills/<skill_id>`

**Response `200`**: `{"deleted": "<skill_id>"}`

### `POST /api/skills/<skill_id>/activate`

Makes this skill the one used for its agent's future requests, replacing
that agent's built-in prompt.

**Response `200`**: `{"active_skill": "<skill_id>", "agent_type": "coder"}`
**Response `404`**: skill not found.

### `POST /api/skills/deactivate`

Reverts an agent back to its built-in prompt. Body: `{"agent_type": "coder"}`

**Response `200`**: `{"agent_type": "coder", "active_skill": null}`

### `POST /api/settings/test-webhook`

Sends one real test payload to the saved `webhook_url` so you can confirm
it's reachable before relying on it. Costs nothing — plain HTTP POST with
fake data, no Replicate call involved.

**Response `200`** (even on delivery failure — the failure itself isn't a
Jarvis-side error):
```json
{"delivered": true, "status_code": 200}
```
or
```json
{"delivered": false, "error": "Connection refused"}
```
**Response `400`**: no `webhook_url` is currently set.

---

## Agent endpoints

Every agent endpoint now also respects Agent Defaults (Settings): a disabled
agent rejects the request outright, and Rate Limiting can reject it too.

**Response `403`** (agent disabled in Settings > Agent Defaults)
```json
{"error": "APIError", "message": "The coder agent is disabled in Settings > Agent Defaults.", "status": 403}
```

**Response `429`** (Rate Limiting's "max requests per minute" exceeded)
```json
{"error": "RateLimitError", "message": "Rate limit exceeded: max 20 requests/minute. Adjust this in Settings > Rate Limiting.", "status": 429}
```

All five follow the same shape: a JSON body with one required field
(plus optional extras), and a response with `task_id` + `output` (the
model's raw text response).

**Common response `200`**
```json
{
  "task_id": "676a369b-43d0-4fe5-be71-7b03f3a9e9dc",
  "output": "<the model's response>",
  "status": "completed",
  "timestamp": "2026-08-20T10:30:00+00:00"
}
```

**Common response `400`** (missing the required field)
```json
{
  "error": "APIError",
  "message": "Missing required field: '<field>'",
  "status": 400
}
```

### `POST /api/agents/brainstorm`

| Field | Type | Required | Notes |
|---|---|---|---|
| `topic` | string | yes | What to brainstorm about |
| `context` | string | no | Extra background/constraints |
| `style` | string | no | `detailed` (default), `concise`, or `bullet_points` |

```bash
curl -X POST http://localhost:5000/api/agents/brainstorm \
  -H "Content-Type: application/json" \
  -d '{"topic":"Design a mobile app for architects","style":"concise"}'
```

### `POST /api/agents/code`

| Field | Type | Required | Notes |
|---|---|---|---|
| `requirements` | string | yes | What the code should do |
| `tech_stack` | string | no | Defaults to `Python` |
| `style` | string | no | Any extra style guidance |
| `context` | string | no | Prior conversation, for follow-ups like "now add error handling to that" |

```bash
curl -X POST http://localhost:5000/api/agents/code \
  -H "Content-Type: application/json" \
  -d '{"requirements":"a function that checks if a number is prime"}'
```

### `POST /api/agents/test`

| Field | Type | Required | Notes |
|---|---|---|---|
| `code` | string | yes | The code to write tests for |
| `description` | string | no | Extra context |
| `framework` | string | no | Defaults to `pytest` |

```bash
curl -X POST http://localhost:5000/api/agents/test \
  -H "Content-Type: application/json" \
  -d '{"code":"def add(a, b): return a + b"}'
```

### `POST /api/agents/deploy`

| Field | Type | Required | Notes |
|---|---|---|---|
| `change_summary` | string | yes | What's being deployed |
| `target` | string | no | Defaults to `Vercel` |
| `context` | string | no | Prior conversation, for follow-up requests |

Drafts a deployment checklist — does not execute a real deployment.

```bash
curl -X POST http://localhost:5000/api/agents/deploy \
  -H "Content-Type: application/json" \
  -d '{"change_summary":"Add login page"}'
```

### `POST /api/agents/document`

| Field | Type | Required | Notes |
|---|---|---|---|
| `subject` | string | yes | What to document |
| `content` | string | no | Source material/context |
| `doc_type` | string | no | Defaults to `README section` |

```bash
curl -X POST http://localhost:5000/api/agents/document \
  -H "Content-Type: application/json" \
  -d '{"subject":"the is_prime function","doc_type":"docstring"}'
```

### `POST /api/agents/qa`

| Field | Type | Required | Notes |
|---|---|---|---|
| `code` | string | yes | The code to review |
| `context` | string | no | Extra context |

```bash
curl -X POST http://localhost:5000/api/agents/qa \
  -H "Content-Type: application/json" \
  -d '{"code":"def add(a, b): return a + b"}'
```

---

## Error format

Every error response follows the same shape:

```json
{
  "error": "<ExceptionClassName>",
  "message": "<human-readable explanation>",
  "status": <http status code>
}
```

## A note on response time

Llama 3 70B (Brainstorm, Tester, Document) responds in a few seconds.
The community-hosted models (Coder/QA's DeepSeek-Coder, Deployer's
Mistral) spin down after a couple of minutes idle and can take
60-90+ seconds on their first call after a gap — this is normal, not
a bug. Subsequent calls within a minute or two are fast.
