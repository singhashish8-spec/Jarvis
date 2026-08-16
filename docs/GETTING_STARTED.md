# Getting Started

This walks you through running Jarvis locally, start to finish, in about 30 minutes.

## Prerequisites

- Python 3.11 or higher
- Git
- Internet connection

## Step 1: Create your API accounts (~15 minutes)

You need three free accounts before Jarvis can do anything real. Phase 0 works
without them (it uses example data), but you'll want them for Phase 1.

**A. Replicate** (runs the AI models)
1. Visit https://replicate.com and sign up
2. Settings -> API tokens -> copy your key

**B. Supabase** (database)
1. Visit https://supabase.com -> create a project (any region near you)
2. Settings -> API -> copy the **Project URL** and the **service_role key**

**C. Cloudflare R2** (file storage)
1. Visit https://www.cloudflare.com/products/r2/ -> create a bucket named `jarvis-data`
2. R2 -> Manage API tokens -> create a token with Object Read & Write
3. Copy the Access Key, Secret Key, and your Account ID

## Step 2: Clone and set up

```bash
git clone <this-repo-url>
cd Jarvis
make setup
```

`make setup` will:
1. Create a Python virtual environment
2. Install dependencies
3. Copy `.env.example` to `.env`
4. Prompt you to paste in the credentials from Step 1 (or press Enter to skip and edit `.env` by hand later)

## Step 3: Start the server

```bash
make dev
```

You should see:
```
Starting Jarvis API...
URL: http://localhost:5000
```

## Step 4: Verify it works

In another terminal:

```bash
curl http://localhost:5000/health
```

Expected:
```json
{"status": "healthy", "service": "Jarvis API", "version": "0.1.0", ...}
```

Then check that your credentials are actually working:

```bash
curl http://localhost:5000/status
```

If `database`, `replicate`, and `storage` all say `"healthy"`, you're fully
set up. If some say `"unavailable"`, that's fine for Phase 0 — it just
means that credential isn't filled in correctly yet (see Troubleshooting).

Finally, try the brainstorm endpoint:

```bash
curl -X POST http://localhost:5000/api/agents/brainstorm \
  -H "Content-Type: application/json" \
  -d '{"topic":"Design a mobile app for architects"}'
```

You'll get back example ideas (Phase 0 uses mock data — no API cost). In
Phase 1, this same endpoint starts calling the real Llama 70B model.

## Step 5: Run the tests

```bash
make test
```

All tests run offline (no real credentials needed) and should pass.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues.

## Next steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand how the pieces fit together
- Read [API_SPEC.md](API_SPEC.md) for the full endpoint reference
- Read [ROADMAP.md](../ROADMAP.md) for what comes after Phase 0
