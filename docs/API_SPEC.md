# API Specification

Base URL (local): `http://localhost:5000`

All responses are JSON.

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

## `POST /api/agents/brainstorm`

Generate ideas for a topic.

**Phase 0**: returns realistic example data (no API cost).
**Phase 1**: will call Llama 70B via Replicate for real ideas.

**Request body**
```json
{
  "topic": "What should a warehouse design include?",
  "context": "Industrial building, 50,000 sq ft",
  "style": "detailed"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `topic` | string | yes | What to brainstorm about |
| `context` | string | no | Extra background/constraints |
| `style` | string | no | `detailed` (default), `concise`, or `bullet_points` |

**Response `200`**
```json
{
  "task_id": "676a369b-43d0-4fe5-be71-7b03f3a9e9dc",
  "ideas": ["...", "...", "..."],
  "reasoning": "...",
  "status": "completed",
  "timestamp": "2026-08-20T10:30:00+00:00"
}
```

**Response `400`** (missing `topic`)
```json
{
  "error": "APIError",
  "message": "Missing required field: 'topic'",
  "status": 400
}
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

## Example: full curl session

```bash
curl http://localhost:5000/health

curl -X POST http://localhost:5000/api/agents/brainstorm \
  -H "Content-Type: application/json" \
  -d '{"topic":"Design a mobile app for architects","style":"concise"}'
```
