# Jarvis — AI Agent Orchestration System

> Automate your work with a team of AI agents. Run on your laptop, control in the cloud, improve every month.

---

## What is Jarvis?

Jarvis is a team of AI agents that work together on your behalf:

- **Brainstorm Agent** — ideas and strategy *(Phase 0: skeleton, live now)*
- **Coder Agent** — writes code *(Phase 1)*
- **Test Agent** — finds bugs *(Phase 1)*
- **Deployer Agent** — pushes to production *(Phase 1)*

You give them a task, they execute, you review. Think of yourself as the architect: Jarvis is your team of contractors.

This repo is **Phase 0** — the foundation. It's a working skeleton: a real Flask API, a real (mocked-for-now) Brainstorm agent, a real database and storage layer, tests, and CI. Phase 1 replaces the mock data with real AI calls.

Full plan: see [ROADMAP.md](ROADMAP.md).

---

## Quick Start (5 minutes)

**Prerequisites**: Python 3.11+, Git.

```bash
git clone <this-repo-url>
cd Jarvis
make setup      # creates venv, installs deps, walks you through .env
make dev        # starts the API on http://localhost:5000
```

In another terminal:

```bash
curl http://localhost:5000/health
```

Full walkthrough (including creating your Replicate/Supabase/R2 accounts): [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

---

## Project Status

**Phase 0 (this repo, now)**
- Flask API with health/status/brainstorm endpoints
- Supabase database wrapper, Cloudflare R2 storage wrapper
- Brainstorm agent (returns example data — no API cost yet)
- Tests, CI (GitHub Actions), one-command setup

**Phase 1 (next, ~3 months)** — Brainstorm agent calls real Llama 70B via Replicate, Coder + Test agents added, dashboard.

**Phase 2+** — more agents, fine-tuning, optional home-server migration (cost drops ~93%).

See [ROADMAP.md](ROADMAP.md) for the full 12-month plan and cost breakdown.

---

## Architecture (at a glance)

```
Your request
    -> Jarvis API (Flask)
    -> Agent Router
         - Brainstorm Agent (Llama 70B, via Replicate)
         - [Phase 1+] Coder / Test / Deploy agents
    -> Result saved to Supabase (database) + R2 (backup)
    -> Returned to you
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Documentation

- [Getting Started](docs/GETTING_STARTED.md) — step-by-step setup
- [API Spec](docs/API_SPEC.md) — endpoints, requests, responses
- [Architecture](docs/ARCHITECTURE.md) — how the system fits together
- [Database](docs/DATABASE.md) — Supabase schema
- [Agents](docs/AGENTS.md) — what each agent does, phase by phase
- [Troubleshooting](docs/TROUBLESHOOTING.md) — common problems and fixes
- [Roadmap](ROADMAP.md) — the full 12-month plan

---

## For Non-Coders

This project is built for an architect, not a programmer. You're not expected to write code — just review, run `make` commands, and approve. Every file that matters has a comment explaining *why* it exists, not just what it does.

---

## Development

```bash
make setup     # first-time setup
make dev       # start the dev server
make test      # run tests
make verify    # check your API credentials actually work
make format    # auto-format code
make help      # see every command
```

---

## License

MIT — see [LICENSE](LICENSE).
