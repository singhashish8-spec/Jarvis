#!/bin/bash
# Start the Jarvis API in development mode.
set -e

if [ ! -d "venv" ]; then
    echo "No venv found. Run ./scripts/setup.sh first."
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "No .env found. Run ./scripts/setup.sh first."
    exit 1
fi

source venv/bin/activate
export ENV=development
export DEBUG=True
python3 -m src.main
