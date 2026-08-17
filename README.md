# Jarvis — AI Agent Orchestration System

> Automate your work with a team of AI agents. Run on your laptop, control in the cloud, improve every month.

---

## What is Jarvis?

Jarvis is a team of AI agents that work together on your behalf — all five below are **live**, calling real models on Replicate:

- **Brainstorm Agent** — ideas and strategy (Llama 3 70B)
- **Coder Agent** — writes code (DeepSeek-Coder 33B)
- **Tester Agent** — writes tests that catch real bugs (Llama 3 70B)
- **Deployer Agent** — drafts deployment plans (Mistral 7B)
- **Document / QA Agents** — writes docs, reviews code (Llama 3 70B / DeepSeek-Coder 33B)

You give them a task, they execute, you review. Think of yourself as the architect: Jarvis is your team of contractors.

This repo has a working Flask API, a real database and storage layer, tests, and CI — plus five working agents making real AI calls. See [docs/AGENTS.md](docs/AGENTS.md) for exactly which model each one uses and why.

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

Visit **http://localhost:5000** for the dashboard — a ChatGPT-style chat
interface: pick an agent from the model-style picker, type a message, get
a reply. No curl required (though it still works, see below).

Full walkthrough (including creating your Replicate/Supabase/R2 accounts): [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

---

## Project Status

**Live now**
- Flask API with health/status + 5 agent endpoints
- Supabase database wrapper, Cloudflare R2 storage wrapper
- Brainstorm, Coder, Tester, Deployer, Document, and QA agents — all calling real Replicate models
- Tests (offline, mocked), CI (GitHub Actions), one-command setup

**Next (Phase 1 remainder)** — a dashboard so you're not stuck using curl, and Google Antigravity integration.

**Phase 2+** — fine-tuning, optional home-server migration (cost drops ~93%).

See [ROADMAP.md](ROADMAP.md) for the full 12-month plan and cost breakdown.

---

## Architecture (at a glance)

```
Your request
    -> Jarvis API (Flask)
    -> Agent Router
         - Brainstorm / Tester / Document Agent (Llama 3 70B)
         - Coder / QA Agent (DeepSeek-Coder 33B)
         - Deployer Agent (Mistral 7B)
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
