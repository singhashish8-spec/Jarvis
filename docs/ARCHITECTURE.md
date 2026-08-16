# Architecture

## The big picture

```
                    Your request (curl, dashboard, Antigravity, ...)
                                    |
                                    v
                      +---------------------------+
                      |   Flask API (src/main.py) |
                      |   /health  /status         |
                      |   /api/agents/brainstorm   |
                      +-------------+---------------+
                                    |
                                    v
                      +---------------------------+
                      |  BrainstormAgent            |
                      |  (src/agents/)               |
                      |  Phase 0: mock data          |
                      |  Phase 1: calls Replicate     |
                      +------+----------------+------+
                             |                  |
                             v                  v
                +----------------------+  +----------------------+
                |  DatabaseClient       |  |  R2Client             |
                |  (Supabase)           |  |  (Cloudflare R2)       |
                |  saves task records   |  |  backs up task output |
                +----------------------+  +----------------------+
```

## Why it's structured this way

- **`src/main.py`** is the only file that talks HTTP. It validates the
  request, calls an agent, and returns JSON. It doesn't know anything about
  how an agent works internally — that's the agent's job.

- **`src/agents/`** — `BaseAgent` defines the shared lifecycle (create a
  task, mark it complete/failed) so every future agent (Coder, Tester,
  Deployer) tracks its work the same way. `BrainstormAgent` is the first
  concrete agent; in Phase 0 it returns realistic example data so the rest
  of the system (API, database, storage) can be built and tested without
  spending anything on the Replicate API. Phase 1 flips one method
  (`brainstorm()`) to call the real model instead.

- **`src/database/`** wraps Supabase so the rest of the app calls
  `db_client.save_task(...)` instead of writing raw Supabase queries
  everywhere. If the backend ever changed, only this file would need to.

- **`src/storage/`** wraps Cloudflare R2 (which speaks the S3 API) the same
  way, for backing up task outputs independent of the database.

- **Persistence is best-effort.** If Supabase or R2 is briefly unreachable,
  `/api/agents/brainstorm` still returns a result to the caller — it logs
  the failure instead of blocking the response. A brainstorm result you
  can't save is still more useful than an error.

## Request flow: a brainstorm call

1. `POST /api/agents/brainstorm` with `{"topic": "..."}`
2. `main.py` validates the body, calls `brainstorm_agent.brainstorm(...)`
3. The agent creates a task record (in-memory), generates ideas (mock in
   Phase 0, real Llama 70B call in Phase 1), and marks the task complete
4. `main.py` saves the task to Supabase and backs up the output to R2
   (both best-effort)
5. The API returns `{task_id, ideas, reasoning, status, timestamp}`

## Deployment

- **Local dev**: `make dev` runs the Flask dev server directly.
- **CI**: GitHub Actions runs the test suite on every push/PR
  (`.github/workflows/test.yml`) and checks formatting
  (`format.yml`).
- **Production**: pushing to `main` triggers `deploy.yml`, which runs tests
  and then deploys to Vercel via `vercel.json` — once `VERCEL_TOKEN` /
  `VERCEL_PROJECT_ID` / `VERCEL_ORG_ID` are added as GitHub Secrets. Until
  then, the deploy step is skipped rather than failing the build.

## What changes in later phases

- **Phase 1**: `BrainstormAgent` calls Replicate for real; `CoderAgent` and
  `TestAgent` are added following the same `BaseAgent` pattern.
- **Phase 4**: agents gain a local-first mode — call a home server running
  Ollama first, fall back to Replicate if it's unreachable.

See [../ROADMAP.md](../ROADMAP.md) for the full phase-by-phase plan.
