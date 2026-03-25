#!/usr/bin/env bash
set -euo pipefail

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-${PORT:-8000}}"
PROVER_PORT="${PROVER_PORT:-8001}"

echo "[entrypoint] Starting Rust prover on port ${PROVER_PORT}..."
prover serve --port "${PROVER_PORT}" &
PROVER_PID=$!

cleanup() {
  echo "[entrypoint] Shutting down services..."
  kill "${PROVER_PID}" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

echo "[entrypoint] Starting QuantumGuard v2 API on ${API_HOST}:${API_PORT}..."
exec uvicorn pqc_backend.v2.app:app --host "${API_HOST}" --port "${API_PORT}" --proxy-headers
