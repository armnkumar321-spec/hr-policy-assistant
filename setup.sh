#!/bin/bash
# Recreates ONLY this project's .venv with Python 3.12 and installs requirements.
set -euo pipefail
cd "$(dirname "$0")"
PY312="$(command -v python3.12 || true)"
[ -z "$PY312" ] && [ -x /opt/homebrew/bin/python3.12 ] && PY312=/opt/homebrew/bin/python3.12
[ -z "$PY312" ] && { echo "python3.12 not found. Install with: brew install python@3.12"; exit 1; }
echo "Using $PY312 ($("$PY312" --version))"
if [ -x .venv/bin/python ] && .venv/bin/python --version 2>/dev/null | grep -q " 3\.12\." && [ "$(ls .venv/lib)" = "python3.12" ]; then
  echo ".venv already uses Python 3.12"
else
  echo "Recreating .venv with Python 3.12"
  rm -rf ./.venv
  "$PY312" -m venv .venv
fi
.venv/bin/python --version
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env — add your GEMINI_API_KEY there."; }
.venv/bin/python -c "import langchain_core, langchain_chroma, langchain_google_genai, chromadb, pypdf, streamlit, dotenv; print('All imports OK')"
.venv/bin/python -m pytest -q
[ -f data/hr_manual.pdf ] && .venv/bin/python ingest.py || echo "NOTE: put hr_manual.pdf at $(pwd)/data/hr_manual.pdf, then run the 'Ingest PDF' task."
echo "Setup complete."
