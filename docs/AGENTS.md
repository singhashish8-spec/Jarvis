# Agents

Every agent inherits from `BaseAgent` ([`src/agents/base_agent.py`](../src/agents/base_agent.py)),
which handles the shared bookkeeping (creating a task, marking it
completed or failed) so each agent only needs to implement its own logic.

All five agents below are **live** — they call real models on Replicate
and cost a small amount per call (typically a fraction of a rupee to a
few rupees, depending on response length). None are mock data anymore.

The easiest way to try any of them is the dashboard at
`http://localhost:5000` — a ChatGPT-style chat interface with an agent
picker, so you don't need the curl examples below unless you're
scripting or testing the API directly.

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

## Cost estimation

Replicate's API has no endpoint for account balance or spend — only
`/v1/account` (username/type). `ReplicateClient.run()` estimates a cost
per call from what each finished prediction actually reports, in
`prediction["metrics"]`:

- **Llama 3 70B** (Brainstorm, Tester, Document) and other language
  models sometimes report `input_token_count` / `output_token_count`.
  When present, tokens are the accurate figure to track, but Replicate
  doesn't publish a confirmed per-token price for this specific listing,
  so cost still falls back to compute time below.
- **All models** report `predict_time` (compute seconds). Cost is
  estimated as `predict_time * REPLICATE_GPU_RATE_PER_SECOND`, which
  defaults to Replicate's published Nvidia A100 (80GB) rate
  ($0.0014/sec) — override it if your models run on different hardware.

This total rolls into the `usage` table per agent/day (see
[DATABASE.md](DATABASE.md)) and is exposed live via
[`GET /api/usage`](API_SPEC.md#get-apiusage). Treat every dollar figure
as an estimate — [replicate.com/account/billing](https://replicate.com/account/billing)
is the only authoritative source for what you've actually been charged.

---

## How Settings changes what an agent actually does

Every agent request goes through `main.py`'s `_run_agent()`, which calls
`settings.resolve_agent_settings(db_client, agent_type)` once and assigns the
result to `agent.settings` *before* `agent.process(**data)` runs. From
there, each agent applies it the same way:

```python
prompt = self.resolve_prompt(self._build_prompt(...), {"topic": topic, ...})
model, version = resolve_model_and_version(self.settings, MODEL, MODEL_VERSION)
run_result = self.replicate_client.run(
    model,
    {"prompt": prompt, "max_tokens": self.max_tokens_or(1024), "temperature": self.temperature_or(0.7)},
    version=version,
)
```

- **`resolve_prompt()`** (on `BaseAgent`) swaps in an active Skill's
  template if one's set (falling back to the agent's own hardcoded
  `_build_prompt()`), then prepends Custom Instructions if any are saved.
- **`resolve_model_and_version()`** swaps in the Agent Defaults "cheaper"
  model override when set — always dropping the `version` id, since the
  override is always an official model and passing a community model's
  version alongside a different model would silently break the call.
- **`temperature_or()` / `max_tokens_or()`** apply an Agent Defaults
  override when set, otherwise fall back to the agent's own default.

Agents used directly (e.g. in `tests/test_agents.py`, which instantiates
`BrainstormAgent()` with no settings wiring at all) simply see
`self.settings == {}`, so every one of these calls is a no-op and behavior
is identical to before Settings existed — this is what keeps the existing
test suite passing unchanged.

Before `agent.process()` is even called, `_make_agent_route()` checks
`settings.is_agent_enabled()` (rejects with `403` if the agent is disabled)
and Rate Limiting's request count (rejects with `429` if exceeded) — both
free checks against already-known state, no model call involved.

See [SETTINGS.md](SETTINGS.md) for what each of these settings does from
the dashboard's side, and whether it costs tokens.

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
6. If the agent should support Skills, add its template variables to
   `AGENT_TEMPLATE_VARS` in `dashboard.html` and the table in
   [SETTINGS.md#skills](SETTINGS.md#skills); add it to `AGENT_TYPES` in
   `settings_schema.py` to get Agent Defaults support automatically
