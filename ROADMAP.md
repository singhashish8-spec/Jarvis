# Jarvis Roadmap

This is a condensed version of the full 12-month plan. It exists so anyone
opening the repo can see where Phase 0 fits without digging through the
original planning doc.

## Phases

| Phase | Timeframe | Goal | Monthly cost (approx) |
|---|---|---|---|
| **0 — Foundation** *(this repo)* | Week 1-2 | Flask API skeleton, DB/storage wired up, Brainstorm agent (mock data) | ₹0 |
| **1 — MVP** | Month 1-3 | Brainstorm agent goes live (real Llama 70B calls), Coder + Test agents, dashboard | ₹1,000-2,000 |
| **2 — Scaling** | Month 4-6 | More agents (Deployer, Document, QA), fine-tuning pipeline, cost optimization | ₹5,000-8,000 |
| **3 — Hardware** | Month 7-9 | Buy + assemble a home GPU server, install Ollama + Llama 70B locally | one-time ~₹1,30,000 |
| **4 — Migration** | Month 10-12 | Gradually shift traffic from Replicate (cloud) to the home server | ₹0 (backup only) |
| **5-6 — Production & self-improvement** | Year 2+ | More agents, mobile app, monthly fine-tunes | ₹1,000-3,100 |

## Why the home server?

Cloud API costs (Replicate) run ~₹9,240/month at Phase 2 usage. A one-time
~₹1.3L hardware purchase (Month 7-9) drops that to ~₹1,000/month
(electricity only) once migration completes — payback in about 6 months,
with 5-year savings of roughly ₹2.6L versus staying cloud-only.

## Your role at each phase

- **Phase 0-1**: review generated code, run `make setup` / `make dev`, approve.
- **Phase 2-3**: plan and buy hardware (a few hours of shopping/research).
- **Phase 4**: oversee the cloud-to-local switchover (mostly automated).
- **Phase 5+**: set direction — ~15 hours/month total across all phases.

## Full detail

The complete week-by-week plan, cost tables, risk analysis, and success
criteria for every phase live in the original planning document shared
alongside this repo (`JARVIS_COMPLETE_ROADMAP.md`). This file is the
in-repo summary; that document is the source of truth for phase details.
