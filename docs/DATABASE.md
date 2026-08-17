# Database Schema

Jarvis uses Supabase (hosted Postgres). Table definitions live in
[`src/database/models.py`](../src/database/models.py) as the source of truth.

## Setting up the tables

Run the SQL once, in the Supabase SQL editor (Project -> SQL Editor -> New query):

```bash
python3 -c "from src.database.models import get_init_sql; print(get_init_sql())"
```

Paste the output in and run it. `scripts/verify.sh` will confirm the
`tasks` table is reachable afterward.

## Tables

### `tasks`
One row per agent execution (a single brainstorm call, a single code
generation, etc.).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | primary key |
| `agent_type` | varchar(50) | e.g. `brainstorm` |
| `status` | varchar(20) | `running`, `completed`, or `failed` |
| `input` | jsonb | the request body |
| `output` | jsonb | the agent's result |
| `error` | text | populated if `status = failed` |
| `created_at` / `updated_at` / `completed_at` | timestamptz | |
| `cost` | decimal(10,4) | USD estimate — see [AGENTS.md#cost-estimation](AGENTS.md#cost-estimation) |
| `cost_currency` | varchar(3) | default `USD` |

### `projects`
Groups tasks under a named project. Not used by the API yet (Phase 0);
reserved for when Jarvis manages multiple concurrent projects.

### `skills`
Registry of versioned agent skills/prompts (e.g. `brainstorm-skill-v1.0`).
Backs the Settings > Skills feature — see
[SETTINGS.md#skills](SETTINGS.md#skills). `is_active` marks a skill as not
archived; which skill (if any) is the one actually *used* per agent is a
separate `active_skill:<agent_type>` row in `settings`, not a column here.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | primary key |
| `agent_type` | varchar(50) | e.g. `coder` |
| `skill_name` | varchar(255) | |
| `description` | text | |
| `template` | text | the actual prompt template, `$variable` placeholders |
| `version` | varchar(20) | |
| `is_active` | boolean | default `true` — not archived (separate from "currently in use") |
| `created_at` / `updated_at` | timestamptz | |

### `usage`
One row per `(date, agent_type)`, upserted by `DatabaseClient.record_usage()`
after every completed task: `calls_count`, `tokens_used`, and an estimated
`cost` in USD. Backs the dashboard's live usage widget and the
[`GET /api/usage`](API_SPEC.md#get-apiusage) endpoint.

### `settings`
Generic key/value store for every user-configurable setting saved from the
dashboard itself rather than an env var — Usage & Billing's credit
limit/GPU rate/budget alert, Agent Defaults' matrix (`agent_config`, one
JSON blob covering all 6 agents), Custom Instructions, Rate Limiting,
Webhooks, Data Controls' retention days, and each agent's active Skill
(`active_skill:<agent_type>`). See [SETTINGS.md](SETTINGS.md) for what each
one does.

| Column | Type | Notes |
|---|---|---|
| `key` | varchar(50) | primary key, e.g. `credit_limit_usd`, `agent_config`, `active_skill:coder` |
| `value` | text | stored as text regardless of the setting's real type (JSON-encoded for `agent_config`) |
| `updated_at` | timestamptz | |

### Upgrading an existing database
Tables created before this change used `decimal(10,2)` and defaulted to
`INR`, didn't have a `settings` table, and `skills` didn't have a `template`
column. `CREATE TABLE IF NOT EXISTS` won't retroactively fix any of that, so
if your tables already exist, run once in the Supabase SQL editor:
```sql
ALTER TABLE tasks ALTER COLUMN cost TYPE decimal(10, 4);
ALTER TABLE tasks ALTER COLUMN cost_currency SET DEFAULT 'USD';
ALTER TABLE usage ALTER COLUMN cost TYPE decimal(10, 4);
ALTER TABLE usage ALTER COLUMN cost_currency SET DEFAULT 'USD';

CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(50) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE skills ADD COLUMN IF NOT EXISTS template TEXT;
```
(`decimal(10,2)` rounds any cost under $0.005 to zero — real per-call
costs are usually a fraction of a cent, so the wider precision matters.
Without the `settings` table, every Settings save returns a clear `500`
rather than failing silently; without `skills.template`, so does
`POST /api/skills`.)

## How the app talks to these tables

All access goes through [`src/database/client.py`](../src/database/client.py)
(`DatabaseClient`) — nothing else in the codebase should import the
Supabase SDK directly. That keeps the query logic in one place and makes
`health_check()` / `save_task()` / `list_tasks()` reusable and testable.
