#!/usr/bin/env bash
# scripts/repro_setup.sh — one-command reproducible environment setup for NetBrace
#
# Idempotent: safe to re-run; skips steps already done.
# Creates (if absent) harness/venvs/nethelm/, installs all package extras, and
# prints next-step instructions.
#
# Usage:
#   bash scripts/repro_setup.sh
#
# Requirements:
#   - python3 (>=3.10) on PATH
#   - pip (comes with python3)
#   - internet access for first install (PyPI packages)
#
# Docker / Batfish (oracle paths only):
#   The unit test suite (tests/unit/) runs with NO Docker and NO Batfish.
#   Oracle-backed paths (netbrace oracle, eval run, extended scenario runner) need
#   Batfish running locally:
#     docker pull batfish/allinone:nethelm@sha256:09817554db90...  # see CLAUDE.md
#     docker run -d --name batfish -p 9996:9996 -p 9997:9997 \
#         batfish/allinone:nethelm@sha256:09817554db90...
#   Then set BATFISH_HOST=127.0.0.1 (default).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$REPO_ROOT/harness/venvs/nethelm"

echo "==> NetBrace reproducible environment setup"
echo "    Repo: $REPO_ROOT"
echo "    Venv: $VENV_DIR"

# --- Step 1: ensure the venv directory parent exists ---
mkdir -p "$REPO_ROOT/harness/venvs"

# --- Step 2: create venv if absent ---
if [ -x "$VENV_DIR/bin/python" ]; then
    echo "==> [skip] venv already exists at $VENV_DIR"
else
    echo "==> Creating venv with $(python3 --version) ..."
    python3 -m venv "$VENV_DIR"
    echo "==> [done] venv created"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# --- Step 3: upgrade pip (silent) ---
"$VENV_PIP" install --quiet --upgrade pip

# --- Step 4: install all extras ---
# oracle   = pybatfish + pandas      (Batfish oracle paths; needs Docker)
# knowledge= sentence-transformers + faiss-cpu + requests (./kb queries)
# eval     = inspect-ai              (model eval harness)
# report   = matplotlib + pandas     (figure generation)
# dev      = pytest + ruff           (unit tests + lint)
echo "==> Installing netbrace[oracle,knowledge,eval,report,dev] ..."
"$VENV_PIP" install --quiet -e "$REPO_ROOT[oracle,knowledge,eval,report,dev]"
echo "==> [done] packages installed"

echo ""
echo "================================================================"
echo " Setup complete.  Next steps:"
echo ""
echo "  1. Run the unit suite (no Docker needed):"
echo "       $VENV_PY -m pytest tests/unit -q"
echo "     Expected: 887 passed, 5 skipped"
echo ""
echo "  2. Query the knowledge base:"
echo "       $REPO_ROOT/kb \"blast radius\""
echo ""
echo "  3. Oracle / run paths need Batfish on 127.0.0.1:9996/9997."
echo "     Pull and start the pinned image (see CLAUDE.md for full digest):"
echo "       docker run -d --name batfish -p 9996:9996 -p 9997:9997 \\"
echo "           batfish/allinone:nethelm"
echo ""
echo "  4. API keys for model-under-test runs:"
echo "       export ANTHROPIC_API_KEY=..."
echo "       export OPENAI_API_KEY=..."
echo "================================================================"
