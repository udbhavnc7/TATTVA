#!/usr/bin/env bash
# test-all.sh — Run the full test suite (backend + frontend) in CI.
# Usage: bash scripts/test-all.sh
# Exits with a non-zero status if any step fails.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKEND_FAILED=0
FRONTEND_FAILED=0

echo "=============================="
echo "  Running backend tests (pytest + hypothesis)"
echo "=============================="
cd "${ROOT_DIR}/backend"
poetry run pytest tests/ --tb=short -q || BACKEND_FAILED=1

echo ""
echo "=============================="
echo "  Running frontend tests (Vitest)"
echo "=============================="
cd "${ROOT_DIR}/frontend"
npm run test || FRONTEND_FAILED=1

echo ""
echo "=============================="
echo "  Test summary"
echo "=============================="
if [ "${BACKEND_FAILED}" -eq 1 ]; then
  echo "FAILED: backend tests"
fi
if [ "${FRONTEND_FAILED}" -eq 1 ]; then
  echo "FAILED: frontend tests"
fi

if [ "${BACKEND_FAILED}" -eq 1 ] || [ "${FRONTEND_FAILED}" -eq 1 ]; then
  echo ""
  echo "One or more test suites failed."
  exit 1
fi

echo "All tests passed."
exit 0
