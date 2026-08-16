#!/bin/bash
# Verify that the credentials in .env actually work, by calling each
# service directly (not just checking the variables are non-empty).
set -e

if [ -d "venv" ]; then
    source venv/bin/activate
fi

if [ ! -f ".env" ]; then
    echo ".env not found. Run ./scripts/setup.sh first."
    exit 1
fi

python3 - <<'PYEOF'
from dotenv import load_dotenv
load_dotenv()

import sys

ok = True

print("Checking Supabase...")
try:
    from src.database.client import DatabaseClient
    db = DatabaseClient()
    if db.health_check():
        print("  OK: Supabase reachable")
    else:
        print("  FAIL: Supabase client created but health check failed")
        ok = False
except Exception as exc:
    print(f"  FAIL: {exc}")
    ok = False

print("Checking Cloudflare R2...")
try:
    from src.storage.r2_client import R2Client
    r2 = R2Client()
    if r2.health_check():
        print("  OK: R2 bucket reachable")
    else:
        print("  FAIL: R2 client created but bucket unreachable")
        ok = False
except Exception as exc:
    print(f"  FAIL: {exc}")
    ok = False

print("Checking Replicate...")
try:
    from src.agents.brainstorm_agent import BrainstormAgent
    agent = BrainstormAgent()
    if agent.verify_api_key():
        print("  OK: REPLICATE_API_KEY is set")
    else:
        print("  FAIL: REPLICATE_API_KEY missing")
        ok = False
except Exception as exc:
    print(f"  FAIL: {exc}")
    ok = False

print("")
if ok:
    print("All credentials verified.")
else:
    print("Some checks failed — see docs/TROUBLESHOOTING.md")
    sys.exit(1)
PYEOF
