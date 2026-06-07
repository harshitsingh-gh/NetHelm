#!/usr/bin/env bash
# check_env.sh — verify the netbrace environment is ready
set -e

echo "=== Python version ==="
python --version

echo ""
echo "=== Package import ==="
python -c "import netbrace; print('netbrace imported OK')"

echo ""
echo "=== Batfish port check ==="
BATFISH_HOST="${BATFISH_HOST:-127.0.0.1}"
if timeout 2 bash -c "echo >/dev/tcp/${BATFISH_HOST}/9997" 2>/dev/null; then
    echo "Batfish port 9997 is open on ${BATFISH_HOST}"
else
    echo "WARNING: Batfish port 9997 not reachable on ${BATFISH_HOST} (expected if not on lab host)"
fi

echo ""
echo "=== CLI smoke ==="
netbrace --help > /dev/null && echo "netbrace CLI OK"

echo ""
echo "All checks passed."
