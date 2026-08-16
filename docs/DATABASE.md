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
| `cost` | decimal(10,2) | INR, Phase 1+ |
| `cost_currency` | varchar(3) | default `INR` |

### `projects`
Groups tasks under a named project. Not used by the API yet (Phase 0);
reserved for when Jarvis manages multiple concurrent projects.

### `skills`
Registry of versioned agent skills/prompts (e.g. `brainstorm-skill-v1.0`).
Not used yet — will back the skills-versioning work described in the
roadmap's later phases.

### `usage`
Daily cost/usage rollups per agent, for the cost dashboard planned in
Phase 1-2.

## How the app talks to these tables

All access goes through [`src/database/client.py`](../src/database/client.py)
(`DatabaseClient`) — nothing else in the codebase should import the
Supabase SDK directly. That keeps the query logic in one place and makes
`health_check()` / `save_task()` / `list_tasks()` reusable and testable.
