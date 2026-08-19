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
                      |  Brainstorm / Coder / Tester |
                      |  Deployer / Document / QA    |
                      |  (src/agents/) — all live,    |
                      |  calling real Replicate models|
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
  task, mark it complete/failed) so all six agents (Brainstorm, Coder,
  Tester, Deployer, Document, QA) track their work the same way. Each is a
  thin subclass that calls a specific Replicate model — see
  [AGENTS.md](AGENTS.md) for which model each one uses and why.

- **`src/database/`** wraps Supabase so the rest of the app calls
  `db_client.save_task(...)` instead of writing raw Supabase queries
  everywhere. If the backend ever changed, only this file would need to.

- **`src/storage/`** wraps Cloudflare R2 (which speaks the S3 API) the same
  way, for backing up task outputs independent of the database.

- **Persistence is best-effort.** If Supabase or R2 is briefly unreachable,
  `/api/agents/brainstorm` still returns a result to the caller — it logs
  the failure instead of blocking the response. A brainstorm result you
  can't save is still more useful than an error.

- **Startup never crashes the process, even with missing/bad credentials.**
  `main.py` builds every client/agent through a small `_init_client()`
  helper that catches a constructor failure and returns `None` instead of
  letting it propagate — logging which service failed and why. Both
  `DatabaseClient` and `R2Client` additionally degrade *internally*
  (`self.client = None` when required env vars are missing, or when the
  underlying SDK construction itself raises), which is what lets their
  existing per-method `try/except` blocks (already written to survive a
  transient outage) handle "never configured" for free, with no extra
  guard needed at each of the ~50 call sites in `main.py` that use them.
  The one place this matters most is Vercel: a serverless function that
  raises at *import* time takes down every route in the deployment,
  including routes that don't need the failed client (like the static
  dashboard) — not just the request that would have used it. `/status`
  (see [API_SPEC.md](API_SPEC.md#get-status)) is how you find out a
  client failed to init; the app itself stays up either way.

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

- **Phase 1** (done): all six agents call Replicate for real.
- **Phase 2+**: Connectors/MCP beyond Dropbox and GitHub (Google Drive,
  Slack), fine-tuning.
- **Phase 4**: agents gain a local-first mode — call a home server running
  Ollama first, fall back to Replicate if it's unreachable.

See [../ROADMAP.md](../ROADMAP.md) for the full phase-by-phase plan.
