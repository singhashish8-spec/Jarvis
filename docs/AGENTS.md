# Agents

Every agent inherits from `BaseAgent` ([`src/agents/base_agent.py`](../src/agents/base_agent.py)),
which handles the shared bookkeeping (creating a task, marking it
completed or failed) so each agent only needs to implement its own logic.

All five agents below are **live** — they call real models on Replicate
and cost a small amount per call (typically a fraction of a rupee to a
few rupees, depending on response length). None are mock data anymore.

## Model choices

| Agent | Model | Why this one |
|---|---|---|
| Brainstorm | Llama 3 70B | strong general reasoning for ideation |
| Tester | Llama 3 70B | writing tests that catch real bugs needs real reasoning, not just speed |
| Coder | DeepSeek-Coder 33B (community GGUF build) | code-specialized model; the official `deepseek-ai` hosted version is currently broken on Replicate (`cannot pickle 'async_generator' object`) |
| QA | DeepSeek-Coder 33B (same as Coder) | code review is itself a code-specialized task |
| Deployer | Mistral 7B, OpenOrca fine-tune | official `mistralai/mistral-7b-instruct-v0.1` is archived with no runnable version; this is a verified-working substitute |
| Document | Llama 3 70B | not specified in the original planning docs; picked for writing quality |

**A note on cold starts**: community-hosted models (DeepSeek-Coder, Mistral)
spin down after a couple of minutes of no requests and take 60-90+ seconds
to spin back up on the next call. Llama 3 70B, an "official" Replicate
model, responds in a few seconds either way. `ReplicateClient.run()`
polls for up to 180 seconds to accommodate this — a slow first response
is expected behavior, not a bug.

## Brainstorm Agent

**File**: [`src/agents/brainstorm_agent.py`](../src/agents/brainstorm_agent.py)
**Endpoint**: `POST /api/agents/brainstorm`
**Use it for**: ideas, design options, strategy recommendations.

```bash
curl -X POST http://localhost:5000/api/agents/brainstorm \
  -H "Content-Type: application/json" \
  -d '{"topic": "Warehouse layout for 50,000 sq ft"}'
```

## Coder Agent

**File**: [`src/agents/coder_agent.py`](../src/agents/coder_agent.py)
**Endpoint**: `POST /api/agents/code`
**Use it for**: generating working code from a plain-language requirement.

```bash
curl -X POST http://localhost:5000/api/agents/code \
  -H "Content-Type: application/json" \
  -d '{"requirements": "a function that checks if a number is prime", "tech_stack": "Python"}'
```

## Tester Agent

**File**: [`src/agents/tester_agent.py`](../src/agents/tester_agent.py)
**Endpoint**: `POST /api/agents/test`
**Use it for**: generating test cases for a piece of code.

```bash
curl -X POST http://localhost:5000/api/agents/test \
  -H "Content-Type: application/json" \
  -d '{"code": "def add(a, b): return a + b", "framework": "pytest"}'
```

## Deployer Agent

**File**: [`src/agents/deployer_agent.py`](../src/agents/deployer_agent.py)
**Endpoint**: `POST /api/agents/deploy`
**Use it for**: drafting a deployment checklist (pre-deploy checks, steps,
rollback plan) for a change.

This agent **does not execute real deployments**. Pushing to production
is a hard-to-reverse action that belongs behind a human decision point,
not something an agent runs on its own — it drafts the plan, you (or a
future, explicitly-approved automation step) carry it out.

```bash
curl -X POST http://localhost:5000/api/agents/deploy \
  -H "Content-Type: application/json" \
  -d '{"change_summary": "Add login page", "target": "Vercel"}'
```

## Document Agent

**File**: [`src/agents/document_agent.py`](../src/agents/document_agent.py)
**Endpoint**: `POST /api/agents/document`
**Use it for**: generating documentation, docstrings, or explanations.

```bash
curl -X POST http://localhost:5000/api/agents/document \
  -H "Content-Type: application/json" \
  -d '{"subject": "the is_prime function", "doc_type": "docstring"}'
```

## QA Agent

**File**: [`src/agents/qa_agent.py`](../src/agents/qa_agent.py)
**Endpoint**: `POST /api/agents/qa`
**Use it for**: reviewing code for bugs, style issues, and security concerns.

```bash
curl -X POST http://localhost:5000/api/agents/qa \
  -H "Content-Type: application/json" \
  -d '{"code": "def add(a, b): return a + b"}'
```

---

## Adding a new agent

1. Create `src/agents/<name>_agent.py`, subclass `BaseAgent`
2. Implement `process(self, **kwargs)` (required by the abstract base class)
   — it should just delegate to your agent's main method, since
   `main.py` calls every agent through `process(**request_json)`
3. Call `self.create_task(...)` at the start, `self.complete_task(...)` or
   `self.fail_task(...)` at the end
4. Register a route with `_make_agent_route(...)` in `src/main.py`
   (see the existing routes near the bottom of the file for the pattern)
5. Add tests in `tests/test_agents.py` and `tests/test_api.py`, mocking
   `agent.replicate_client.run` so tests stay offline and free
