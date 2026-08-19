# Troubleshooting

## Setup

**"Python 3 not found"**
Install Python 3.11+ from https://python.org, then confirm with `python3 --version`.

**"venv/bin/activate: No such file or directory"**
Run `make setup` first (or `./scripts/setup.sh` directly) to create the
virtual environment.

**`make setup` doesn't ask for credentials**
That means `.env` already exists — setup only prompts on first run.
Delete `.env` and run `make setup` again to reconfigure.

## Running the server

**`ModuleNotFoundError: No module named 'src'`**
Run commands from the repo root (not from inside `src/`), and make sure the
virtualenv is activated: `source venv/bin/activate`.

**`/status` shows `"database": "unavailable"` or `"storage": "unavailable"`**
Either a credential is missing from `.env` (see
[GETTING_STARTED.md](GETTING_STARTED.md) Step 1B), or it's set but wrong —
a malformed URL or an invalid key. The app itself still starts and every
other route still works either way: `DatabaseClient` and `R2Client` log
the failure and degrade to a client that reports unhealthy instead of
raising, so one bad credential can't take down the whole process (this
matters most on Vercel, where a construction-time exception used to crash
every route, including static ones, not just the ones that needed that
client). Run `make verify` for a clearer, per-service error message than
`/status` gives.

**`/status` shows `"replicate": "unavailable"`**
`REPLICATE_API_KEY` isn't set in `.env`.

**An agent endpoint returns 402 "Insufficient credit"**
Your Replicate account needs credit added before it'll run any model —
see https://replicate.com/account/billing#billing. If your account is an
**organization** account, adding a card isn't enough by itself; you need
to explicitly **purchase credit** there. Wait a few minutes after
purchasing before retrying.

**An agent endpoint is slow (60-90+ seconds) on its first call**
Expected for the community-hosted models (Coder/QA's DeepSeek-Coder,
Deployer's Mistral) — they spin down after a couple of minutes idle and
cold-start on the next request. Llama 3 70B (Brainstorm/Tester/Document)
doesn't have this issue. Subsequent calls within a minute or two are fast.

**An agent endpoint returns 404 from Replicate**
If you've changed a `MODEL_VERSION` constant in one of the `src/agents/*.py`
files: community models require an exact version id, and that id changes
whenever the model's owner pushes a new version. Look up the current one
with the `latest_version` field at
`https://api.replicate.com/v1/models/<owner>/<name>` (needs your API key
in the `Authorization: Bearer` header) and update the constant.

## Tests

**`make test` fails with a Supabase/R2 connection error**
Tests are designed to run fully offline — they should never hit real
services. If you see a real network error, check you didn't delete
`tests/conftest.py`'s fixture stubs, or that a new test forgot to use the
`client` fixture (which stubs external calls).

## Deployment

**GitHub Actions "Deploy" step is skipped**
Expected until you add `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, and
`VERCEL_ORG_ID` under the repo's Settings -> Secrets and variables ->
Actions. The test job still runs and must pass either way.

**Formatting check fails in CI**
Run `make format` locally (Black + isort) and push again.

## Still stuck?

Check the relevant module's docstring in `src/` — every client
(`DatabaseClient`, `R2Client`, `BrainstormAgent`) explains what it expects
in its class docstring. If that doesn't answer it, open a GitHub issue
using the bug report template.
