# Settings

The dashboard has a Settings panel (gear icon at the bottom of the sidebar) with eleven
categories. Every field in it has an (i) icon — click it for a note on what the setting does,
how it takes effect, and whether it costs Replicate tokens/compute.

**Look**: the whole app (not just Settings) runs on a neutral, brand-agnostic design system —
plain solid surfaces, no OS-specific chrome, a single user-chosen accent hue driving every
highlight — defined as CSS custom properties on `:root`/`:root[data-theme]` in
[dashboard.html](../src/static/dashboard.html) (search for `Design tokens (Calm Neutral)`). Two
pieces worth knowing about:

- **Jump to a setting** — the search bar under the header title (`Ctrl`/`Cmd`+`K` while Settings
  is open focuses it) filters the current category's fields, connector cards, status rows,
  skills, and tasks by matching visible text. It's a local DOM filter, not a search index — it
  only searches what's already rendered in the category you're on.
- **App theme** (Appearance category) — a Dark/Light toggle that switches the *entire app* —
  chat, sidebar, and Settings alike — by setting `data-theme` on `<html>`, saved in
  `localStorage` (`jarvisSettingsTheme`). Unlike the old per-modal toggle this used to be, chat
  and the sidebar now follow it too.

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

### Presets

Two buttons above the matrix — **Frugal** and **Max Quality** — that bundle a one-click change
across every agent instead of six manual edits, via `GET /api/settings/presets` +
`POST /api/settings/presets/<id>/apply`:

- **Frugal** sets every agent's model to the cheaper override and halves its max-tokens ceiling
  (floored at 256) — the two controls that actually affect spend.
- **Max Quality** clears every agent's model and max-tokens override back to its built-in
  default.

Both leave `temperature` and `enabled`/disabled alone on purpose — temperature doesn't affect
cost, and disabling an agent is a separate "I don't use this" choice a preset shouldn't silently
override. Applying a preset merges onto whatever's already saved rather than replacing the whole
matrix, so an existing `enabled: false` or custom temperature survives. Presets are fixed and
built-in for now (`PRESETS` in `settings_schema.py`) — not user-editable, same reasoning as the
model override being limited to one vetted option rather than free text. Applying one costs
nothing by itself; it only changes what future requests use.

### Cost simulator

Editing a **max tokens** field in the matrix shows a live line under the table: how that change
projects against your own real usage, via `GET /api/settings/cost-simulator`. It's honest about
what it can and can't tell you:

- It projects from **your actual task history** for that agent (real `cost`/`created_at` rows
  over the trailing 30 days) — average $/call and calls/week — never a fabricated number. If an
  agent has no history yet, it says so instead of showing a fake $0.00.
- It scales that average proportionally to the max-tokens change (halve the ceiling, the
  projection roughly halves) — a real simplification (output length doesn't scale perfectly
  linearly with the ceiling), stated as such in the hint text, not hidden.
- **Model changes aren't simulated** — the `usage` table rolls up a whole day per agent, so a
  day where you tried both the default and cheaper model blends into one row; there's no clean
  per-model cost split to project from. Changing the Model dropdown shows a plain note instead
  of guessing a savings percentage Jarvis can't back up.

Running the simulation costs nothing itself — it only reads history that's already there.

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

- **App theme** — Dark/Light toggle for the whole app (see above). Saved in `localStorage`
  (`jarvisSettingsTheme`), applied via `applySettingsTheme()`, which sets `data-theme` on
  `<html>` and re-derives the accent below for the new theme's contrast.
- **Accent color** — a single hue slider (0-360). Saturation and lightness are fixed by Jarvis
  per theme so any pick stays legible, and the text color drawn on top of the accent (e.g. the
  primary button's label) is chosen automatically via a WCAG contrast check
  (`textOnAccent()` in dashboard.html) rather than being fixed to always-white or always-black.
  Drives every accent throughout the app — primary buttons, the active-chat highlight, focus
  rings — computed once in `applyAccent()` and written out as CSS custom properties (`--accent`,
  `--accent-strong`, `--accent-text-on`, `--active-bg`). Saved in `localStorage`
  (`jarvisAccentHue`).
- **Ambient wash** — a second slider (0-100%) controlling a faint accent-tinted radial gradient
  behind the whole page, purely decorative. `0` turns it off entirely. Saved in `localStorage`
  (`jarvisWashPct`).
- **Compact messages** — tightens spacing between chat messages, saved in `localStorage`
  (`jarvisCompactMode`).

All four are client-side only (`localStorage`), cost nothing, and apply instantly without a
page reload — including to the whole app now, not just the Settings modal.

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

### Dropbox — the one real connector

Connect once, browse your Dropbox, and pull a file's text content in instead of copying it by
hand. Real OAuth 2.0, not a placeholder:

- **Setup** (one-time, outside the dashboard): create an app at
  [dropbox.com/developers/apps](https://www.dropbox.com/developers/apps) — scoped access,
  access type **App folder** (Jarvis only ever sees a dedicated folder, not your whole
  Dropbox), permissions `files.metadata.read` + `files.content.read`. Register a redirect URI
  for every place Jarvis runs (`.../api/connectors/dropbox/callback`), then set
  `DROPBOX_APP_KEY` / `DROPBOX_APP_SECRET` as environment variables — see `.env.example` for
  the exact steps. Until both are set, the card shows "Needs setup" instead of a broken button.
- **Connect** (`GET /api/connectors/dropbox/authorize`) redirects into Dropbox's own consent
  screen; approving sends you back to `.../callback`, which exchanges the one-time code for a
  refresh token and redirects to `/?connector=dropbox&status=connected`. That refresh token is
  the only thing persisted — in the `settings` table, under a key deliberately left out of
  `SETTINGS_SCHEMA` so it can never surface through `GET /api/settings`.
- **Browse** (`GET /api/connectors/dropbox/files?path=...`) lists one folder at a time — no
  local caching, no recursive crawl.
- **Copy** (`POST /api/connectors/dropbox/pull`) downloads one file (capped at ~200KB / ~50k
  tokens of text — the response's `truncated` flag is set and the toast says so when a file
  hit the cap) and copies it to your clipboard — paste it into your message same as any
  pasted text. Nothing gets fed into a prompt automatically.
- **Disconnect** (`POST /api/connectors/dropbox/disconnect`) clears the stored refresh token.

Every real API call first exchanges the stored refresh token for a fresh access token rather
than caching one — Vercel's serverless functions don't reliably keep process memory between
requests, the same reasoning behind the rate limiter's DB-backed count.

### GitHub — the second real connector

Same idea as Dropbox, one level deeper: connect once, pick a repo, browse it, pull a file's
text content in.

- **Setup** (one-time, outside the dashboard): create a **classic OAuth App** at
  [github.com/settings/developers](https://github.com/settings/developers) — GitHub OAuth Apps
  only allow one callback URL each, so register a separate app per place Jarvis runs (local dev
  vs. production get different apps, not one app with two URLs). Set `GITHUB_OAUTH_CLIENT_ID` /
  `GITHUB_OAUTH_CLIENT_SECRET` — see `.env.example` for the exact steps. Until both are set, the
  card shows "Needs setup".
- **Connect** (`GET /api/connectors/github/authorize`, scope `repo` — covers private repos too,
  since most real project repos aren't public) redirects into GitHub's consent screen; approving
  sends you back to `.../callback`, which exchanges the code for an access token and redirects
  to `/?connector=github&status=connected`. Classic OAuth App tokens don't expire, so unlike
  Dropbox there's no refresh step — the token from the exchange is stored and reused as-is (same
  `settings`-table-key-outside-`SETTINGS_SCHEMA` pattern as Dropbox's refresh token).
- **Browse** (`GET /api/connectors/github/repos` to list your repos, then
  `GET /api/connectors/github/files?repo=...&path=...` to browse one) — repos first, then files
  within the one you pick, same "up one level" pattern as Dropbox but with an extra level back
  to the repo list.
- **Copy** (`POST /api/connectors/github/pull`) — same ~200KB cap and clipboard-copy behavior as
  Dropbox.
- **Disconnect** (`POST /api/connectors/github/disconnect`) clears the stored token.

### The rest — still placeholders

Google Drive and Slack would each be a cloud-to-cloud OAuth connector, same shape as Dropbox/
GitHub above — nothing wired up yet. **PyRevit / Local PC & Home Server is different in kind,
not just unbuilt**: Jarvis runs on Vercel, which has no way to reach your PC directly, and
PyRevit is local desktop software with no cloud API of its own. Making that one real needs
either a small bridge/onboard app running on your machine that Jarvis's cloud side can talk to,
or running Jarvis itself locally on your laptop/home server once you've procured your own
hardware (see [ROADMAP.md](../ROADMAP.md), Phase 3 — hardware). It's marked "Needs local bridge
app" in the UI rather than "Coming soon" for exactly this reason.

None of the connectors can consume tokens on their own — pulling in outside data is free; only
what actually gets stuffed into a prompt afterward counts as input tokens, the same as pasting
it in by hand.

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
- [`src/connectors/dropbox_client.py`](../src/connectors/dropbox_client.py) and
  [`src/connectors/github_client.py`](../src/connectors/github_client.py) — the OAuth handshake
  and REST calls behind each real connector; routes live in `main.py` under
  `/api/connectors/{dropbox,github}/*`.
- [`src/static/dashboard.html`](../src/static/dashboard.html) — the Settings panel itself (CSS
  under `/* ---------- Settings (Command Deck) ---------- */`, JS under `SETTINGS`).
