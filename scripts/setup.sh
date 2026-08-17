#!/bin/bash
# ============================================
# JARVIS SETUP SCRIPT
# ============================================
# One command to set up everything.
# Usage: ./scripts/setup.sh   (or: make setup)
# ============================================

set -e

echo "JARVIS SETUP"
echo "============================================"
echo ""

# --- 1. Prerequisites ---
echo "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Please install Python 3.11+"
    exit 1
fi
echo "Python found: $(python3 --version)"

if ! command -v git &> /dev/null; then
    echo "Git not found. Please install git"
    exit 1
fi
echo "Git found"

# --- 2. Virtual environment ---
echo ""
echo "Creating virtual environment..."

if [ -d "venv" ]; then
    echo "   venv/ already exists, reusing it"
else
    python3 -m venv venv
    echo "Virtual environment created"
fi

source venv/bin/activate
echo "Virtual environment activated"

# --- 3. Dependencies ---
echo ""
echo "Installing Python dependencies..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
pip install -r requirements.txt
echo "Dependencies installed"

# --- 4. .env file ---
echo ""
echo "Setting up environment variables..."

if [ -f ".env" ]; then
    echo "   .env already exists, leaving it as-is (delete it to reconfigure)"
else
    cp .env.example .env
    echo "Created .env from .env.example"
    echo ""
    echo "Enter your API credentials (leave blank to fill in .env by hand later):"
    echo ""

    read -p "Replicate API Key: " REPLICATE_API_KEY
    read -p "Supabase URL: " SUPABASE_URL
    read -p "Supabase Key: " SUPABASE_KEY
    read -p "R2 Account ID: " R2_ACCOUNT_ID
    read -p "R2 Access Key: " R2_ACCESS_KEY
    read -p "R2 Secret Key: " R2_SECRET_KEY

    [ -n "$REPLICATE_API_KEY" ] && sed -i.bak "s|your_replicate_api_key_here|$REPLICATE_API_KEY|" .env
    [ -n "$SUPABASE_URL" ] && sed -i.bak "s|https://xxxxx.supabase.co|$SUPABASE_URL|" .env
    [ -n "$SUPABASE_KEY" ] && sed -i.bak "s|your_supabase_service_role_key_here|$SUPABASE_KEY|" .env
    [ -n "$R2_ACCOUNT_ID" ] && sed -i.bak "s|your_cloudflare_account_id|$R2_ACCOUNT_ID|" .env
    [ -n "$R2_ACCESS_KEY" ] && sed -i.bak "s|your_r2_access_key|$R2_ACCESS_KEY|" .env
    [ -n "$R2_SECRET_KEY" ] && sed -i.bak "s|your_r2_secret_key|$R2_SECRET_KEY|" .env
    rm -f .env.bak

    # Generate a real random SECRET_KEY instead of leaving the placeholder.
    GENERATED_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i.bak "s|change_this_to_a_random_string|$GENERATED_SECRET|" .env
    rm -f .env.bak

    echo "Credentials saved to .env"
fi

# --- 5. Verify ---
echo ""
echo "Verifying setup..."

[ -f ".env" ] && echo ".env file exists" || { echo ".env file missing"; exit 1; }
[ -f "venv/bin/activate" ] && echo "Virtual environment ready" || { echo "venv missing"; exit 1; }

python3 -c "import flask, supabase, boto3" 2>/dev/null && echo "Core dependencies importable" || echo "Some dependencies failed to import — check pip install output above"

# --- 6. Next steps ---
echo ""
echo "============================================"
echo "SETUP COMPLETE"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Review docs/GETTING_STARTED.md"
echo "  2. make dev      -> start the API on http://localhost:5000"
echo "  3. make test     -> run the test suite"
echo "  4. make verify   -> check your credentials actually work"
echo ""
