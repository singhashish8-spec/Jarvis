# Agents

Every agent inherits from `BaseAgent` ([`src/agents/base_agent.py`](../src/agents/base_agent.py)),
which handles the shared bookkeeping (creating a task, marking it
completed or failed) so each agent only needs to implement its own logic.

## Brainstorm Agent — live in Phase 0

**File**: [`src/agents/brainstorm_agent.py`](../src/agents/brainstorm_agent.py)
**Model**: Llama 70B (via Replicate, starting Phase 1)
**Use it for**: ideas, design options, strategy recommendations.

```bash
curl -X POST http://localhost:5000/api/agents/brainstorm \
  -H "Content-Type: application/json" \
  -d '{"topic": "Warehouse layout for 50,000 sq ft"}'
```

- **Phase 0 (now)**: returns realistic example data. No Replicate API key
  required, no cost. This lets the whole pipeline (API -> agent -> database
  -> storage) be built and tested for free.
- **Phase 1**: the same endpoint starts calling the real model. The prompt
  template is already written in `_build_prompt()`, just not wired up yet.

## Coder Agent — Phase 1

Will take requirements + a tech stack and generate working code
(DeepSeek-Coder 33B via Replicate). Not implemented yet.

## Test Agent — Phase 1

Will generate test cases for code the Coder Agent produces, and loop with
it until tests pass. Not implemented yet.

## Deployer Agent — Phase 1-2

Will push generated code to Vercel/Firebase and manage rollbacks. Not
implemented yet.

## Document / QA Agents — Phase 2

Generate documentation and review code for standards/security. Not
implemented yet.

---

## Adding a new agent (for future reference)

1. Create `src/agents/<name>_agent.py`, subclass `BaseAgent`
2. Implement `process(self, **kwargs)` (required by the abstract base class)
3. Call `self.create_task(...)` at the start, `self.complete_task(...)` or
   `self.fail_task(...)` at the end
4. Add a route in `src/main.py` under `/api/agents/<name>`
5. Add tests in `tests/test_agents.py`
