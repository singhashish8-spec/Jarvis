# API Specification

Base URL (local): `http://localhost:5000`

All responses are JSON. Every agent endpoint calls a real model on
Replicate and costs a small amount per call — see [AGENTS.md](AGENTS.md)
for which model each one uses.

---

## `GET /health`

Liveness check — is the process running at all.

**Response `200`**
```json
{
  "status": "healthy",
  "service": "Jarvis API",
  "timestamp": "2026-08-20T10:30:00+00:00",
  "version": "0.1.0"
}
```

---

## `GET /status`

Readiness check — is everything the API depends on actually reachable.

**Response `200`** (all components healthy)
```json
{
  "status": "operational",
  "timestamp": "2026-08-20T10:30:00+00:00",
  "components": {
    "database": "healthy",
    "replicate": "healthy",
    "storage": "healthy"
  }
}
```

**Response `503`** (one or more components unavailable — e.g. credentials
not filled in yet)
```json
{
  "status": "degraded",
  "timestamp": "2026-08-20T10:30:00+00:00",
  "components": {
    "database": "unavailable",
    "replicate": "healthy",
    "storage": "unavailable"
  }
}
```

---

## Agent endpoints

All five follow the same shape: a JSON body with one required field
(plus optional extras), and a response with `task_id` + `output` (the
model's raw text response).

**Common response `200`**
```json
{
  "task_id": "676a369b-43d0-4fe5-be71-7b03f3a9e9dc",
  "output": "<the model's response>",
  "status": "completed",
  "timestamp": "2026-08-20T10:30:00+00:00"
}
```

**Common response `400`** (missing the required field)
```json
{
  "error": "APIError",
  "message": "Missing required field: '<field>'",
  "status": 400
}
```

### `POST /api/agents/brainstorm`

| Field | Type | Required | Notes |
|---|---|---|---|
| `topic` | string | yes | What to brainstorm about |
| `context` | string | no | Extra background/constraints |
| `style` | string | no | `detailed` (default), `concise`, or `bullet_points` |

```bash
curl -X POST http://localhost:5000/api/agents/brainstorm \
  -H "Content-Type: application/json" \
  -d '{"topic":"Design a mobile app for architects","style":"concise"}'
```

### `POST /api/agents/code`

| Field | Type | Required | Notes |
|---|---|---|---|
| `requirements` | string | yes | What the code should do |
| `tech_stack` | string | no | Defaults to `Python` |
| `style` | string | no | Any extra style guidance |

```bash
curl -X POST http://localhost:5000/api/agents/code \
  -H "Content-Type: application/json" \
  -d '{"requirements":"a function that checks if a number is prime"}'
```

### `POST /api/agents/test`

| Field | Type | Required | Notes |
|---|---|---|---|
| `code` | string | yes | The code to write tests for |
| `description` | string | no | Extra context |
| `framework` | string | no | Defaults to `pytest` |

```bash
curl -X POST http://localhost:5000/api/agents/test \
  -H "Content-Type: application/json" \
  -d '{"code":"def add(a, b): return a + b"}'
```

### `POST /api/agents/deploy`

| Field | Type | Required | Notes |
|---|---|---|---|
| `change_summary` | string | yes | What's being deployed |
| `target` | string | no | Defaults to `Vercel` |

Drafts a deployment checklist — does not execute a real deployment.

```bash
curl -X POST http://localhost:5000/api/agents/deploy \
  -H "Content-Type: application/json" \
  -d '{"change_summary":"Add login page"}'
```

### `POST /api/agents/document`

| Field | Type | Required | Notes |
|---|---|---|---|
| `subject` | string | yes | What to document |
| `content` | string | no | Source material/context |
| `doc_type` | string | no | Defaults to `README section` |

```bash
curl -X POST http://localhost:5000/api/agents/document \
  -H "Content-Type: application/json" \
  -d '{"subject":"the is_prime function","doc_type":"docstring"}'
```

### `POST /api/agents/qa`

| Field | Type | Required | Notes |
|---|---|---|---|
| `code` | string | yes | The code to review |
| `context` | string | no | Extra context |

```bash
curl -X POST http://localhost:5000/api/agents/qa \
  -H "Content-Type: application/json" \
  -d '{"code":"def add(a, b): return a + b"}'
```

---

## Error format

Every error response follows the same shape:

```json
{
  "error": "<ExceptionClassName>",
  "message": "<human-readable explanation>",
  "status": <http status code>
}
```

## A note on response time

Llama 3 70B (Brainstorm, Tester, Document) responds in a few seconds.
The community-hosted models (Coder/QA's DeepSeek-Coder, Deployer's
Mistral) spin down after a couple of minutes idle and can take
60-90+ seconds on their first call after a gap — this is normal, not
a bug. Subsequent calls within a minute or two are fast.
