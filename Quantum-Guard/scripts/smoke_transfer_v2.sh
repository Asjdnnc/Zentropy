#!/usr/bin/env bash
set -euo pipefail

# QuantumGuard v2 smoke test:
# 1) create org
# 2) create sender + receiver
# 3) submit transfer
# 4) print history + summary

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/api/v2}"
ENV_FILE="${ENV_FILE:-.env}"
AMOUNT_STRK="${AMOUNT_STRK:-0.25}"
DEPLOY_WAIT_SECONDS="${DEPLOY_WAIT_SECONDS:-180}"
DEPLOY_POLL_SECONDS="${DEPLOY_POLL_SECONDS:-3}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: missing required command: $1" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd jq
require_cmd tr
require_cmd grep

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

BOOTSTRAP_SECRET="${BOOTSTRAP_SECRET:-}"
if [[ -z "$BOOTSTRAP_SECRET" ]]; then
  BOOTSTRAP_SECRET="$(grep '^BOOTSTRAP_SECRET=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r')"
fi

if [[ -z "$BOOTSTRAP_SECRET" ]]; then
  echo "ERROR: BOOTSTRAP_SECRET is empty (set env var or $ENV_FILE)" >&2
  exit 1
fi

if [[ -n "${STARKNET_ACCOUNT_CONFIG:-}" ]]; then
  if [[ ! -f "$STARKNET_ACCOUNT_CONFIG" ]]; then
    echo "ERROR: STARKNET_ACCOUNT_CONFIG does not exist: $STARKNET_ACCOUNT_CONFIG" >&2
    exit 1
  fi
fi

echo "== Health =="
curl -s "$BASE_URL/health" | jq .

echo "== Create Organization =="
ORG_NAME="TxnTestOrg$(date +%s)"
ORG_ADMIN_EMAIL="ops+${ORG_NAME,,}@example.com"
ORG_JSON=$(printf '{"org_name":"%s","admin_email":"%s","bootstrap_secret":"%s"}' "$ORG_NAME" "$ORG_ADMIN_EMAIL" "$BOOTSTRAP_SECRET" | curl -s -X POST "$BASE_URL/org/create" -H "Content-Type: application/json" -d @-)
echo "$ORG_JSON" | jq .

ORG_ID="$(echo "$ORG_JSON" | jq -r '.org_id // empty')"
API_KEY="$(echo "$ORG_JSON" | jq -r '.api_key // empty')"
if [[ -z "$ORG_ID" || -z "$API_KEY" ]]; then
  echo "ERROR: org creation failed" >&2
  exit 1
fi

echo "== Register Sender =="
SENDER_EMAIL="sender$(date +%s)@test.com"
SENDER_JSON=$(printf '{"email":"%s","username":"sender"}' "$SENDER_EMAIL" | curl -s -X POST "$BASE_URL/users/register" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d @-)
echo "$SENDER_JSON" | jq .
SENDER_ID="$(echo "$SENDER_JSON" | jq -r '.user_id // empty')"
if [[ -z "$SENDER_ID" ]]; then
  echo "ERROR: sender registration failed" >&2
  exit 1
fi

echo "== Wait Sender Deployment =="
deadline=$(( $(date +%s) + DEPLOY_WAIT_SECONDS ))
while true; do
  DEPLOY_JSON=$(curl -s "$BASE_URL/users/$SENDER_ID/deployment-status" -H "Authorization: Bearer $API_KEY")
  DEPLOY_STATUS="$(echo "$DEPLOY_JSON" | jq -r '.deployment_status // empty')"

  if [[ "$DEPLOY_STATUS" == "deployed" ]]; then
    echo "$DEPLOY_JSON" | jq .
    break
  fi

  if [[ "$DEPLOY_STATUS" == "failed" ]]; then
    echo "$DEPLOY_JSON" | jq .
    echo "ERROR: automatic deployment failed" >&2
    exit 1
  fi

  now=$(date +%s)
  if (( now >= deadline )); then
    echo "$DEPLOY_JSON" | jq .
    echo "ERROR: deployment timed out after ${DEPLOY_WAIT_SECONDS}s" >&2
    exit 1
  fi

  sleep "$DEPLOY_POLL_SECONDS"
done

echo "== Register Receiver =="
RECV_EMAIL="recv$(date +%s)@test.com"
RECV_JSON=$(printf '{"email":"%s","username":"receiver"}' "$RECV_EMAIL" | curl -s -X POST "$BASE_URL/users/register" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d @-)
echo "$RECV_JSON" | jq .
RECV_ID="$(echo "$RECV_JSON" | jq -r '.user_id // empty')"
if [[ -z "$RECV_ID" ]]; then
  echo "ERROR: receiver registration failed" >&2
  exit 1
fi

echo "== Wait Receiver Deployment =="
deadline=$(( $(date +%s) + DEPLOY_WAIT_SECONDS ))
while true; do
  DEPLOY_JSON=$(curl -s "$BASE_URL/users/$RECV_ID/deployment-status" -H "Authorization: Bearer $API_KEY")
  DEPLOY_STATUS="$(echo "$DEPLOY_JSON" | jq -r '.deployment_status // empty')"

  if [[ "$DEPLOY_STATUS" == "deployed" ]]; then
    echo "$DEPLOY_JSON" | jq .
    RECV_ADDR="$(echo "$DEPLOY_JSON" | jq -r '.contract_address // empty')"
    if [[ -z "$RECV_ADDR" ]]; then
      echo "ERROR: receiver deployment status missing contract address" >&2
      exit 1
    fi
    break
  fi

  if [[ "$DEPLOY_STATUS" == "failed" ]]; then
    echo "$DEPLOY_JSON" | jq .
    echo "ERROR: receiver automatic deployment failed" >&2
    exit 1
  fi

  now=$(date +%s)
  if (( now >= deadline )); then
    echo "$DEPLOY_JSON" | jq .
    echo "ERROR: receiver deployment timed out after ${DEPLOY_WAIT_SECONDS}s" >&2
    exit 1
  fi

  sleep "$DEPLOY_POLL_SECONDS"
done

echo "== Transfer =="
TX_JSON=$(printf '{"user_id":"%s","to_address":"%s","amount_strk":%s}' "$SENDER_ID" "$RECV_ADDR" "$AMOUNT_STRK" | curl -s -X POST "$BASE_URL/transactions/transfer" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d @-)
echo "$TX_JSON" | jq .

STATUS="$(echo "$TX_JSON" | jq -r '.status // empty')"
TX_ID="$(echo "$TX_JSON" | jq -r '.tx_id // empty')"
TX_HASH="$(echo "$TX_JSON" | jq -r '.starknet_tx_hash // empty')"

if [[ -z "$STATUS" ]]; then
  echo "ERROR: transfer did not return status" >&2
  exit 1
fi

echo "== Sender History =="
curl -s "$BASE_URL/users/$SENDER_ID/transactions?limit=10&offset=0" -H "Authorization: Bearer $API_KEY" | jq .

echo "== Summary =="
echo "ORG_ID=$ORG_ID"
echo "API_KEY=$API_KEY"
echo "SENDER_ID=$SENDER_ID"
echo "RECV_ADDR=$RECV_ADDR"
echo "TX_ID=$TX_ID"
echo "STATUS=$STATUS"
echo "STARKNET_TX_HASH=$TX_HASH"

if [[ "$STATUS" != "submitted" ]]; then
  if [[ "$STATUS" == "account_not_deployed" ]]; then
    echo "Hint: wait for deployment to complete and then retry transfer." >&2
    echo "Deployment status:" >&2
    curl -s "$BASE_URL/users/$SENDER_ID/deployment-status" -H "Authorization: Bearer $API_KEY" | jq . >&2
  fi
  echo "Transfer was not submitted. Check backend logs for details." >&2
  exit 2
fi

echo "Smoke transfer completed successfully."
