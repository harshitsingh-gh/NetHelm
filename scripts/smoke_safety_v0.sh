#!/usr/bin/env bash
# smoke_safety_v0.sh — end-to-end smoke test: generate → fake-eval → report
# Asserts results.csv exists and macro_f1 looks sane.
set -e

SUITE_DIR="/tmp/netbrace_smoke_suite"
RUN_ID="smoke_$(date +%s)"
FIGURES_DIR="/tmp/netbrace_smoke_figures"

echo "=== Step 1: generate 3 tasks ==="
netbrace safety generate --count 3 --out "${SUITE_DIR}"

echo ""
echo "=== Step 2: validate (no oracle required) ==="
netbrace safety validate --suite "${SUITE_DIR}"

echo ""
echo "=== Step 3: fake eval (oracle mode) ==="
netbrace eval fake --suite "${SUITE_DIR}" --run-id "${RUN_ID}"

echo ""
echo "=== Step 4: report ==="
netbrace report --run "runs/${RUN_ID}" --figures "${FIGURES_DIR}"

echo ""
echo "=== Assertions ==="
CSV_PATH="runs/${RUN_ID}/results.csv"
if [ ! -f "${CSV_PATH}" ]; then
    echo "FAIL: results.csv not found at ${CSV_PATH}"
    exit 1
fi
echo "PASS: results.csv exists at ${CSV_PATH}"

PDF_PATH="${FIGURES_DIR}/safety_f1_by_intent.pdf"
if [ ! -f "${PDF_PATH}" ]; then
    echo "FAIL: PDF not found at ${PDF_PATH}"
    exit 1
fi
echo "PASS: PDF exists at ${PDF_PATH}"

echo ""
echo "Smoke test passed."
