# Settings

The dashboard has a Settings panel (gear icon at the bottom of the sidebar) with eleven
categories. Every field in it has an (i) icon — click it for a note on what the setting does,
how it takes effect, and whether it costs Replicate tokens/compute.

This doc is the same information in one place, plus the API endpoints behind each category
(see [API_SPEC.md](API_SPEC.md) for full request/response shapes) and what's needed for each
to actually persist (some require the `settings` and `skills.template` schema additions — see
[DATABASE.md](DATABASE.md)).

**The one thing every category shares**: Replicate has no API for real account balance,
usage, or spend — confirmed against their own API reference and billing docs, `/v1/account`
returns only your username and account type. Every cost figure anywhere in Jarvis is an
*estimate*, computed locally from what each prediction actually reports (token counts when a
model provides them, compute time otherwise — see [AGENTS.md#cost-estimation](AGENTS.md#cost-estimation)).
[replicate.com/account/billing](https://replicate.com/account/billing) remains the only
authoritative source for what you've actually been charged.

## Usage & Billing

| Setting | Costs tokens? | What it does |
|---|---|---|
| Credit limit | No | A budget you set yourself to compare estimated spend against. Backed by `POST /api/settings/credit-limit` (or the generic `POST /api/settings`) — both validate and store the same `credit_limit_usd` setting. |
| GPU rate override | No | Overrides the $/sec rate used to estimate cost for models Replicate bills by compute time rather than tokens. Defaults to Replicate's published Nvidia A100 rate. |
| Budget alert threshold | No | Shows an in-app banner once estimated spend crosses this % of your credit limit. No email/SMS — the dashboard tab has to be open. |

Also shows live totals (tokens today/total, estimated spend) pulled from `GET /api/usage`.

### Sidebar usage popover

Clicking the sidebar's usage readout (below the chat list) opens a quick-glance
popover instead of jumping straight into Settings — a "Manage in Settings →"
link at the bottom does that. It shows:

- **Today's spend by agent** — a segmented bar + legend from `by_agent` in
  `GET /api/usage`, one segment per agent that's actually run today.
- **Credit limit** and, when Rate Limiting has a value set, a **requests
  (last 60s)** bar — the same rolling-window count `_check_rate_limit()`
  enforces, just displayed rather than acted on.
- **Storage** — R2 file-backup size/count and Supabase row counts, from
  `GET /api/storage`. See that endpoint's docs in
  [API_SPEC.md](API_SPEC.md#get-apistorage) for what's (and isn't) counted.

Clicking the DB/Replicate/Storage status row below it opens System Status
directly, the same "click a readout, land on what manages it" pattern.

## Agent Defaults

Per-agent matrix — enable/disable, model override, temperature, max tokens — via
`GET`/`POST /api/settings/agent-config`. **Disabling an agent is free**: the request is
rejected with `403` before any model is called. **The model override is the one control here
that actually reduces spend** — it swaps in `meta/meta-llama-3-8b-instruct` (an official
Replicate model, no version-pinning risk) in place of an agent's default. It's deliberately not
a free-text field: an unverified model or version id would silently break an agent instead of
saving money. Temperature doesn't affect cost; a higher max-tokens value costs nothing to set
but produces longer, more expensive replies on every future call.

## Data Controls

- **Auto-purge tasks older than (N days)** — a preference, not automatic. Vercel has no
  background scheduler wired up, so nothing is ever deleted unless you click **Purge now**
  (`POST /api/data/purge`).
- **Export chats as JSON** / **Clear local history** — pure client-side. Chat history lives
  only in the browser's `localStorage`; Jarvis's server never stores it beyond the single
  request/response used to generate each reply.
- **Recent tasks** — a browser for what *is* saved server-side (`GET /api/tasks`,
  `DELETE /api/tasks/<id>`), separate from the chat history above.

None of this touches Replicate — it's all local storage or database housekeeping.

## Appearance

One real control today: **Compact messages** (tightens spacing, saved in `localStorage`). A
full light theme is planned but not built — see the note on the toggle. The dashboard stays
dark-mode only for now.

## System Status

A fuller view of the same health checks behind the sidebar's DB/Replicate/Storage dots
(`GET /status`). "Replicate: healthy" only confirms an API key is configured — it never fires
a real prediction, so checking status costs nothing.

## Skills

A Skill is a saved, versioned prompt template for one agent (`GET`/`POST /api/skills`,
`PUT`/`DELETE /api/skills/<id>`, `POST /api/skills/<id>/activate`,
`POST /api/skills/deactivate`). Activating one replaces that agent's built-in hardcoded prompt
on every future request, until deactivated. Templates use `$variable`-style placeholders (Python's
`string.Template`, via `safe_substitute` — an unknown placeholder degrades to literal text
instead of raising):

| Agent | Available variables |
|---|---|
| Brainstorm | `$topic`, `$context`, `$style` |
| Coder | `$requirements`, `$tech_stack`, `$style`, `$context` |
| Tester | `$code`, `$description`, `$framework` |
| Deployer | `$change_summary`, `$target`, `$context` |
| Document | `$subject`, `$content`, `$doc_type` |
| QA | `$code`, `$context` |

Creating, editing, or activating a skill costs nothing by itself — it only changes the prompt
sent the next time that agent actually runs, the same cost as any other call to it.

**Requires a schema change**: the `skills` table needs a `template` column that didn't exist
before this feature. See [DATABASE.md](DATABASE.md) for the upgrade SQL — without it,
`POST /api/skills` returns a clear `500` explaining exactly this rather than failing silently.

## Connectors / MCP

Placeholders only — nothing here is wired up yet. Google Drive, Slack, and GitHub would each
be a cloud-to-cloud OAuth connector (Jarvis's server talking directly to that service's API, no
local software needed). **PyRevit / Local PC & Home Server is different in kind, not just
unbuilt**: Jarvis runs on Vercel, which has no way to reach your PC directly, and PyRevit is
local desktop software with no cloud API of its own. Making that one real needs either a small
bridge/onboard app running on your machine that Jarvis's cloud side can talk to, or running
Jarvis itself locally on your laptop/home server once you've procured your own hardware (see
[ROADMAP.md](../ROADMAP.md), Phase 3 — hardware). It's marked "Needs local bridge app" in the
UI rather than "Coming soon" for exactly this reason, and is worth its own design discussion
once that migration is closer.

None of the four connectors can consume tokens on their own — pulling in outside data is free;
only what actually gets stuffed into a prompt afterward counts as input tokens, the same as
pasting it in by hand.

## Custom Instructions

The one setting with a genuinely **recurring** cost. Whatever you save here gets prepended to
every single agent request — Brainstorm, Coder, Tester, Deployer, Document, and QA all get it,
on every call, permanently until cleared. Roughly 4 characters ≈ 1 token, so 400 characters
adds roughly 100 tokens (and a little compute time) to every future request from every agent.
The settings page shows a live estimate as you type. Capped at 1000 characters
(`custom_instructions` in [settings_schema.py](../src/settings_schema.py)).

## Rate Limiting

**Max requests per minute** — rejects agent requests (`429`) once you've made this many in the
trailing 60 seconds, counted from real task history (`tasks.created_at`) rather than in-memory
state, since Vercel's serverless functions don't reliably keep process memory between requests.
0 means unlimited. This setting only ever *prevents* spend — a safety rail against a runaway
loop or a misclick firing off dozens of requests before you notice.

## Webhooks

**Webhook URL** — Jarvis POSTs a JSON summary (`task_id`, `agent_type`, `status`, `cost`,
`output`) to this URL after every completed task, fire-and-forget: it never blocks or fails
your actual response if the URL is down or slow (5s timeout, logged and swallowed on failure).
Fires after the real Replicate call already happened, using data Jarvis already has, so it adds
no tokens or model calls of its own. **Send test** (`POST /api/settings/test-webhook`) delivers
one real test payload so you can confirm the URL is reachable before relying on it.

## Advanced / Danger Zone

- **Reset all settings** (`POST /api/settings/reset`) — reverts every setting above back to its
  default/env-var fallback, including Agent Defaults overrides and active Skill selections (all
  stored in the same `settings` table). Does not delete Skills themselves or any chat/task
  history.
- **Reset usage stats** (`POST /api/usage/reset`) — wipes the tokens/cost totals shown in the
  sidebar and Usage & Billing, e.g. to start a fresh count for a new month. Does not touch saved
  task history.

Both are destructive and irreversible; the dashboard confirms before calling either.

## Where everything lives

- [`src/settings_schema.py`](../src/settings_schema.py) — the single source of truth for every
  generic setting (label, type, validation rule, and the (i)-tooltip text) and the Agent
  Defaults matrix's validation.
- [`src/settings.py`](../src/settings.py) — resolves those settings into what a single agent
  request actually uses (`resolve_agent_settings`), called once per request from `main.py`.
- [`src/database/client.py`](../src/database/client.py) — generic `get_setting`/`set_setting`
  plus the Skills/task-browser/danger-zone specific methods.
- [`src/static/dashboard.html`](../src/static/dashboard.html) — the Settings panel itself (CSS
  under `/* ---------- Settings ---------- */`, JS under `SETTINGS`).
