#!/bin/bash
# Run the test suite with coverage.
set -e

if [ -d "venv" ]; then
    source venv/bin/activate
fi

pytest tests/ -v --cov=src --cov-report=term-missing
