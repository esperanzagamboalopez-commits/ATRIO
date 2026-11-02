#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m streamlit run app.py --server.address 0.0.0.0 --server.port "${ATRIO_PORT:-8081}" --server.enableCORS true --server.enableXsrfProtection true --browser.gatherUsageStats false
