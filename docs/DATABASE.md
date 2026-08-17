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
Not used yet — will back the skills-versioning work described in the
roadmap's later phases.

### `usage`
One row per `(date, agent_type)`, upserted by `DatabaseClient.record_usage()`
after every completed task: `calls_count`, `tokens_used`, and an estimated
`cost` in USD. Backs the dashboard's live usage widget and the
[`GET /api/usage`](API_SPEC.md#get-apiusage) endpoint.

### Upgrading an existing database
Tables created before this change used `decimal(10,2)` and defaulted to
`INR`. `CREATE TABLE IF NOT EXISTS` won't retroactively fix that, so if
your `tasks`/`usage` tables already exist, run once in the Supabase SQL
editor:
```sql
ALTER TABLE tasks ALTER COLUMN cost TYPE decimal(10, 4);
ALTER TABLE tasks ALTER COLUMN cost_currency SET DEFAULT 'USD';
ALTER TABLE usage ALTER COLUMN cost TYPE decimal(10, 4);
ALTER TABLE usage ALTER COLUMN cost_currency SET DEFAULT 'USD';
```
(`decimal(10,2)` rounds any cost under $0.005 to zero — real per-call
costs are usually a fraction of a cent, so the wider precision matters.)

## How the app talks to these tables

All access goes through [`src/database/client.py`](../src/database/client.py)
(`DatabaseClient`) — nothing else in the codebase should import the
Supabase SDK directly. That keeps the query logic in one place and makes
`health_check()` / `save_task()` / `list_tasks()` reusable and testable.
