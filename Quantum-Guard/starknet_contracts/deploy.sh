#!/bin/bash
# ================================================================
# QuantumGuard — Deploy Cairo Contract to Starknet Sepolia
# ================================================================
#
# Prerequisites:
#   1. scarb installed (cairo build tool)
#   2. starkli installed (starknet CLI)
#   3. Contract compiled: cd starknet_contracts && scarb build
#   4. Environment variables set:
#        export STARKNET_PRIVATE_KEY="0x..."
#        export STARKNET_ACCOUNT_ADDRESS="0x..."
#   5. Testnet ETH in the account (get from https://faucet.starknet.io)
#
# Usage:
#   ./deploy.sh [--owner-hash HASH] [--rpc URL]
#
# ================================================================

set -e

# ─── Config ──────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTRACT_DIR="${SCRIPT_DIR}"
TARGET_DIR="${CONTRACT_DIR}/target/dev"
SIERRA_FILE="${TARGET_DIR}/quantum_guard_contract_QuantumGuardAccount.contract_class.json"
CONFIG_FILE="${HOME}/.quantum-guard/contract.json"

# Load .env from parent directory (Quantum-Guard root)
ENV_FILE="${CONTRACT_DIR}/../.env"
if [ -f "${ENV_FILE}" ]; then
    set -a
    source "${ENV_FILE}"
    set +a
fi

RPC_URL="${STARKNET_RPC:-https://free-rpc.nethermind.io/sepolia-juno/v0_7}"

# Starkli account paths
ACCOUNT_FILE="${HOME}/.starkli/accounts/quantum-guard.json"
KEYSTORE_FILE="${HOME}/.starkli/signers/quantum-guard"

# Parse CLI args
OWNER_HASH=""
JSON_OUTPUT=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --owner-hash)  OWNER_HASH="$2"; shift 2 ;;
        --rpc)         RPC_URL="$2"; shift 2 ;;
        --json-output) JSON_OUTPUT=true; shift ;;
        *)             echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Helper: output JSON result and exit
json_result() {
    local status="$1" class_hash="$2" contract_address="$3" error="$4"
    if [ "${JSON_OUTPUT}" = true ]; then
        cat <<JSONEOF
{"status":"${status}","class_hash":"${class_hash}","contract_address":"${contract_address}","error":"${error}","network":"starknet-sepolia","rpc":"${RPC_URL}"}
JSONEOF
    fi
}

json_error() {
    local msg="$1"
    if [ "${JSON_OUTPUT}" = true ]; then
        echo "{\"status\":\"error\",\"error\":\"${msg}\"}"
        exit 1
    else
        echo "✗ ${msg}"
        exit 1
    fi
}

# ─── Checks ─────────────────────────────────────────────────────

echo "=== QuantumGuard Contract Deployment ==="
echo ""

# Check tools
command -v scarb >/dev/null 2>&1 || { echo "✗ scarb not found. Install: curl -sSf https://docs.swmansion.com/scarb/install.sh | sh"; exit 1; }
command -v starkli >/dev/null 2>&1 || { echo "✗ starkli not found. Install: curl https://get.starkli.sh | sh && starkliup"; exit 1; }

echo "✓ scarb  : $(scarb --version | head -1)"
echo "✓ starkli: $(starkli --version)"
echo "  RPC    : ${RPC_URL}"
echo ""

# Check env vars
if [ -z "${STARKNET_PRIVATE_KEY}" ]; then
    json_error "STARKNET_PRIVATE_KEY not set"
    echo "✗ STARKNET_PRIVATE_KEY not set."
    echo "  export STARKNET_PRIVATE_KEY=\"0x...\""
    exit 1
fi

if [ -z "${STARKNET_ACCOUNT_ADDRESS}" ]; then
    json_error "STARKNET_ACCOUNT_ADDRESS not set"
    echo "✗ STARKNET_ACCOUNT_ADDRESS not set."
    echo "  export STARKNET_ACCOUNT_ADDRESS=\"0x...\""
    exit 1
fi

echo "✓ Deployer account: ${STARKNET_ACCOUNT_ADDRESS:0:16}..."

# ─── Build ───────────────────────────────────────────────────────

echo ""
echo "Step 1/3: Building contract..."
cd "${CONTRACT_DIR}"
scarb build
echo "✓ Contract compiled"

if [ ! -f "${SIERRA_FILE}" ]; then
    echo "✗ Sierra file not found at: ${SIERRA_FILE}"
    echo "  Check scarb build output. Available files:"
    ls -la "${TARGET_DIR}/" 2>/dev/null || echo "  (target/dev/ does not exist)"
    exit 1
fi

echo "  Sierra: ${SIERRA_FILE}"

# ─── Owner Hash ──────────────────────────────────────────────────

if [ -z "${OWNER_HASH}" ]; then
    # Try to get from default wallet
    WALLET_FILE="${HOME}/.quantum-guard/keys/default/identity.json"
    if [ -f "${WALLET_FILE}" ]; then
        OWNER_HASH=$(python3 -c "import json; print('0x' + json.load(open('${WALLET_FILE}'))['pubkey_hash'][:62])" 2>/dev/null || echo "")
    fi

    if [ -z "${OWNER_HASH}" ]; then
        echo "✗ No owner hash provided and no default wallet found."
        echo "  Create a wallet first: make cli ARGS='wallet create'"
        echo "  Or pass: ./deploy.sh --owner-hash 0x..."
        exit 1
    fi
fi

echo "  Owner : ${OWNER_HASH:0:16}..."

# ─── Declare ─────────────────────────────────────────────────────

echo ""
echo "Step 2/3: Declaring contract class..."

# Use starkli account file if it exists, otherwise use private-key directly
if [ -f "${ACCOUNT_FILE}" ]; then
    # Use the starkli account (recommended)
    DECLARE_OUTPUT=$(starkli declare \
        "${SIERRA_FILE}" \
        --rpc "${RPC_URL}" \
        --account "${ACCOUNT_FILE}" \
        --keystore "${KEYSTORE_FILE}" \
        2>&1) || true
else
    # Fallback to raw private key (less secure)
    DECLARE_OUTPUT=$(starkli declare \
        "${SIERRA_FILE}" \
        --rpc "${RPC_URL}" \
        --private-key "${STARKNET_PRIVATE_KEY}" \
        --account "${STARKNET_ACCOUNT_ADDRESS}" \
        2>&1) || true
fi

# Extract class hash
CLASS_HASH=""
while IFS= read -r line; do
    if [[ "${line}" =~ 0x[0-9a-fA-F]{50,} ]]; then
        CLASS_HASH=$(echo "${line}" | grep -oP '0x[0-9a-fA-F]+' | head -1)
        break
    fi
done <<< "${DECLARE_OUTPUT}"

if [ -z "${CLASS_HASH}" ]; then
    if echo "${DECLARE_OUTPUT}" | grep -qi "already declared"; then
        CLASS_HASH=$(echo "${DECLARE_OUTPUT}" | grep -oP '0x[0-9a-fA-F]{50,}' | head -1)
        echo "  Contract class already declared: ${CLASS_HASH:0:16}..."
    else
        echo "✗ Failed to declare contract:"
        echo "${DECLARE_OUTPUT}"
        exit 1
    fi
else
    echo "✓ Declared class: ${CLASS_HASH:0:16}..."
fi

# ─── Deploy ──────────────────────────────────────────────────────

echo ""
echo "Step 3/3: Deploying contract instance..."

if [ -f "${ACCOUNT_FILE}" ]; then
    # Use the starkli account (recommended)
    DEPLOY_OUTPUT=$(starkli deploy \
        "${CLASS_HASH}" \
        "${OWNER_HASH}" \
        "${STARKNET_ACCOUNT_ADDRESS}" \
        --rpc "${RPC_URL}" \
        --account "${ACCOUNT_FILE}" \
        --keystore "${KEYSTORE_FILE}" \
        2>&1) || true
else
    # Fallback to raw private key (less secure)
    DEPLOY_OUTPUT=$(starkli deploy \
        "${CLASS_HASH}" \
        "${OWNER_HASH}" \
        "${STARKNET_ACCOUNT_ADDRESS}" \
        --rpc "${RPC_URL}" \
        --private-key "${STARKNET_PRIVATE_KEY}" \
        --account "${STARKNET_ACCOUNT_ADDRESS}" \
        2>&1) || true
fi

# Extract contract address
CONTRACT_ADDRESS=""
while IFS= read -r line; do
    if [[ "${line}" =~ 0x[0-9a-fA-F]{50,} ]]; then
        CONTRACT_ADDRESS=$(echo "${line}" | grep -oP '0x[0-9a-fA-F]+' | head -1)
        break
    fi
done <<< "${DEPLOY_OUTPUT}"

if [ -z "${CONTRACT_ADDRESS}" ]; then
    json_error "Failed to deploy contract: ${DEPLOY_OUTPUT}"
    echo "✗ Failed to deploy contract:"
    echo "${DEPLOY_OUTPUT}"
    exit 1
fi

echo "✓ Contract deployed!"
echo "  Address: ${CONTRACT_ADDRESS}"

# ─── Save Config ─────────────────────────────────────────────────

mkdir -p "$(dirname "${CONFIG_FILE}")"
cat > "${CONFIG_FILE}" << EOF
{
  "deployed": true,
  "contract_address": "${CONTRACT_ADDRESS}",
  "class_hash": "${CLASS_HASH}",
  "network": "starknet-sepolia",
  "rpc": "${RPC_URL}",
  "owner_pubkey_hash": "${OWNER_HASH}",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo ""
echo "✓ Config saved to: ${CONFIG_FILE}"

# JSON output mode for programmatic callers
if [ "${JSON_OUTPUT}" = true ]; then
    json_result "success" "${CLASS_HASH}" "${CONTRACT_ADDRESS}" ""
fi

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "  Contract : ${CONTRACT_ADDRESS}"
echo "  Class    : ${CLASS_HASH}"
echo "  Network  : Starknet Sepolia"
echo "  Explorer : https://sepolia.starkscan.co/contract/${CONTRACT_ADDRESS}"
echo ""
echo "Next steps:"
echo "  make run-api    # Start API server"
echo "  make run-prover # Start Rust prover"
echo "  Then use: POST /transaction/execute to sign+prove+submit on-chain"
