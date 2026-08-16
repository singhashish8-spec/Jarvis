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

**`ValueError: SUPABASE_URL and SUPABASE_KEY are required`**
Your `.env` is missing (or still has placeholder values for) the Supabase
credentials. See [GETTING_STARTED.md](GETTING_STARTED.md) Step 1B.

**`/status` shows `"database": "unavailable"` or `"storage": "unavailable"`**
The app started fine, but a credential is wrong (not just missing — a
malformed URL or an invalid key). Run `make verify` for a clearer,
per-service error message than `/status` gives.

**`/status` shows `"replicate": "unavailable"`**
`REPLICATE_API_KEY` isn't set in `.env`. This only matters starting Phase 1
— Phase 0's brainstorm endpoint works fine without it.

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
