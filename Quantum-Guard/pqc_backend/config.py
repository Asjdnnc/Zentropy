"""
Configuration for QuantumGuard PQC Backend.

All algorithm parameters, key sizes, and paths are defined here.
Environment variables are loaded from .env via python-dotenv.
Change PATH_TO_LIBOQS if your compiled liboqs is in a different location.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# =============================================================================
# Load .env from project root (Quantum-Guard/.env)
# =============================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_env_path = PROJECT_ROOT / ".env"
load_dotenv(_env_path, override=False)

# =============================================================================
# Algorithm Selection (NIST FIPS 204 / FIPS 203)
# =============================================================================
ALGORITHM_SIG = "ML-DSA-44"       # Dilithium - NIST Level 2 signatures
ALGORITHM_KEM = "ML-KEM-768"      # Kyber     - NIST Level 3 key encapsulation

# =============================================================================
# Key & Signature Sizes (bytes) - from NIST FIPS 204
# =============================================================================
ML_DSA_44_SIZES = {
    "public_key":  1312,   # FIPS 204 ML-DSA-44
    "secret_key":  2560,
    "signature":   2420,
}

ML_KEM_768_SIZES = {
    "public_key":     1184,
    "secret_key":     2400,
    "ciphertext":     1088,
    "shared_secret":  32,
}

# =============================================================================
# Paths
# =============================================================================
# liboqs shared library — already compiled in the sibling liboqs directory
# Resolve: Quantum-Guard/../liboqs/build/lib/liboqs.so
_LIBOQS_DIR = PROJECT_ROOT.parent / "liboqs" / "build" / "lib"

if os.name == "nt":
    # Windows
    PATH_TO_LIBOQS = str(_LIBOQS_DIR / "oqs.dll")
elif os.uname().sysname == "Darwin":
    # macOS
    PATH_TO_LIBOQS = str(_LIBOQS_DIR / "liboqs.dylib")
else:
    # Linux / WSL2
    PATH_TO_LIBOQS = str(_LIBOQS_DIR / "liboqs.so")

# Wallet key storage
KEYS_DIR = Path.home() / ".quantum-guard" / "keys"
IDENTITY_FILE = "identity.json"
WALLET_DB_FILE = "wallets.json"

# =============================================================================
# Database (persistence layer)
# =============================================================================
DB_PATH = Path(os.environ.get("DB_PATH", str(Path.home() / ".quantum-guard" / "quantumguard.db")))

# =============================================================================
# Server Configuration
# =============================================================================
API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

_prover_env = os.environ.get("PROVER_BINARY", "")
PROVER_BINARY = Path(_prover_env) if _prover_env else (PROJECT_ROOT / "zk_prover" / "target" / "release" / "prover")
PROVER_PORT = int(os.environ.get("PROVER_PORT", "8001"))

# =============================================================================
# Starknet Configuration
# =============================================================================
STARKNET_RPC = os.environ.get(
    "STARKNET_RPC", "https://free-rpc.nethermind.io/sepolia-juno/v0_7"
)
STARKNET_CHAIN_ID = os.environ.get("STARKNET_CHAIN_ID", "SN_SEPOLIA")

# STRK token contract on Sepolia
STRK_TOKEN_ADDRESS = os.environ.get(
    "STRK_TOKEN_ADDRESS",
    "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
)

# Contract deployment
DEPLOY_SCRIPT_PATH = PROJECT_ROOT / "starknet_contracts" / "deploy.sh"
CONTRACT_DIR = PROJECT_ROOT / "starknet_contracts"
SIERRA_FILE = CONTRACT_DIR / "target" / "dev" / "quantum_guard_contract_QuantumGuardAccount.contract_class.json"

# Balance cache TTL (seconds)
BALANCE_CACHE_TTL = int(os.environ.get("BALANCE_CACHE_TTL", "30"))

# Starknet TX polling
STARKNET_TX_POLL_INTERVAL = int(os.environ.get("STARKNET_TX_POLL_INTERVAL", "2"))
STARKNET_TX_MAX_POLLS = int(os.environ.get("STARKNET_TX_MAX_POLLS", "30"))

# =============================================================================
# Security
# =============================================================================
RATE_LIMIT_RPM = int(os.environ.get("RATE_LIMIT_RPM", "60"))
CORS_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# =============================================================================
# Merkle Audit Trail
# =============================================================================
MERKLE_BATCH_SIZE = int(os.environ.get("MERKLE_BATCH_SIZE", "1000"))
MERKLE_BATCH_INTERVAL = float(os.environ.get("MERKLE_BATCH_INTERVAL", "300"))  # seconds
MERKLE_STORAGE_DIR = Path(
    os.environ.get("MERKLE_STORAGE_DIR", str(Path.home() / ".quantum-guard" / "merkle_batches"))
)
MERKLE_COMMITTER_POLL = float(os.environ.get("MERKLE_COMMITTER_POLL", "10"))  # seconds

# =============================================================================
# Drand Configuration
# =============================================================================
DRAND_CHAIN_HASH = os.environ.get(
    "DRAND_CHAIN_HASH",
    "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971",
)
DRAND_TIMEOUT = int(os.environ.get("DRAND_TIMEOUT", "10"))
