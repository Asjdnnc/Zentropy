"""
QuantumGuard API Server
=======================
FastAPI orchestrator that connects:
  Phase 1 (Python crypto kernel)  ↔  Phase 2 (Rust prover)  ↔  Phase 3 (Starknet)

Endpoints:
  POST /wallet/create         — Generate new quantum identity (ML-DSA-44 keypair)
  GET  /wallet/info           — Get wallet public key & identity hash
  GET  /wallet/list           — List all stored wallets
  POST /transaction/sign      — Sign a transaction with ML-DSA-44
  POST /transaction/prove     — Send signature to Rust prover, get proof
  POST /transaction/execute   — Full pipeline: sign → prove → (submit to Starknet)
  GET  /health                — Server health check

Run:
  cd Quantum-Guard/
  python -m quantum_wallet_ui.server
"""
import asyncio
import base64
import json
import logging
import subprocess
import sys
import os
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Add parent dir to path so we can import pqc_backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pqc_backend.key_manager import QuantumKeyManager
from pqc_backend.signer import QuantumSigner
from pqc_backend.contract_manager import StarknetContractManager
from pqc_backend.balance_provider import StarknetBalanceProvider
from pqc_backend.transfer_handler import StarknetTransferHandler
from pqc_backend.drand_integration import fetch_drand_beacon
from pqc_backend.merkle_audit import MerkleAuditAccumulator
from pqc_backend.batch_committer import BatchCommitter
from pqc_backend.config import (
    PROVER_BINARY, API_HOST, API_PORT, STARKNET_RPC,
    CORS_ORIGINS, RATE_LIMIT_RPM, LOG_LEVEL,
    MERKLE_BATCH_SIZE, MERKLE_BATCH_INTERVAL, MERKLE_STORAGE_DIR,
    MERKLE_COMMITTER_POLL,
)
from pqc_backend.utils import b64encode, b64decode, sha256_hex, truncate_display
from pqc_backend.persistence import TransactionStore

# Logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("quantumguard")

# =============================================================================
# App setup
# =============================================================================

app = FastAPI(
    title="QuantumGuard Wallet API",
    description="Quantum-resistant wallet infrastructure on Starknet",
    version="0.1.0",
)

# CORS — configured via .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rate limiting middleware ────────────────────────────────────
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple in-memory rate limiter (per-IP, sliding window)."""
    if RATE_LIMIT_RPM <= 0:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60.0

    # Clean old entries
    _rate_limit_store[client_ip] = [
        t for t in _rate_limit_store[client_ip] if now - t < window
    ]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_RPM:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
        )

    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


key_manager = QuantumKeyManager()
signer = QuantumSigner(key_manager=key_manager)
tx_store = TransactionStore()
contract_manager = StarknetContractManager(key_manager=key_manager, tx_store=tx_store)
balance_provider = StarknetBalanceProvider(tx_store=tx_store)

# Merkle audit accumulator
merkle_accumulator = MerkleAuditAccumulator(
    batch_size=MERKLE_BATCH_SIZE,
    batch_interval=MERKLE_BATCH_INTERVAL,
    storage_dir=MERKLE_STORAGE_DIR,
)

transfer_handler = StarknetTransferHandler(
    key_manager=key_manager,
    signer=signer,
    tx_store=tx_store,
    merkle_accumulator=merkle_accumulator,
)

# Batch committer (started on app startup)
batch_committer = BatchCommitter(
    accumulator=merkle_accumulator,
    tx_store=tx_store,
    poll_interval=MERKLE_COMMITTER_POLL,
)

# Contract deployment config — persisted in ~/.quantum-guard/contract.json
_CONTRACT_CONFIG_FILE = Path.home() / ".quantum-guard" / "contract.json"


def _load_contract_config() -> dict:
    """Load stored contract deployment info."""
    if _CONTRACT_CONFIG_FILE.exists():
        return json.loads(_CONTRACT_CONFIG_FILE.read_text())
    return {"deployed": False}


def _save_contract_config(config: dict):
    """Persist contract deployment info."""
    _CONTRACT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONTRACT_CONFIG_FILE.write_text(json.dumps(config, indent=2))


# =============================================================================
# App lifecycle: start/stop batch committer
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Start the Merkle batch committer background task."""
    asyncio.create_task(batch_committer.run())
    logger.info("Merkle batch committer started")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the batch committer gracefully."""
    batch_committer.stop()
    # Force-commit any pending transactions
    if merkle_accumulator.pending_count() > 0:
        logger.info("Flushing pending Merkle transactions on shutdown...")
        await batch_committer.force_commit()
    logger.info("Batch committer stopped")


# =============================================================================
# Request / Response models
# =============================================================================

class CreateWalletRequest(BaseModel):
    label: str = Field(default="default", description="Wallet label/name")
    camera_photo: str = Field(default="", description="Base64-encoded camera photo for entropy")


class TransactionRequest(BaseModel):
    to: str = Field(description="Recipient address (hex)")
    amount: float = Field(description="Amount to send")
    nonce: int | None = Field(default=None, description="Transaction nonce (auto if None)")
    data: str = Field(default="", description="Optional calldata")
    label: str = Field(default="default", description="Wallet identity to sign with")


class ProveRequest(BaseModel):
    message: str = Field(description="Base64-encoded message")
    signature: str = Field(description="Base64-encoded ML-DSA signature")
    public_key: str = Field(description="Base64-encoded ML-DSA public key")


class TransferRequest(BaseModel):
    label: str = Field(default="default", description="Wallet identity to use")
    to_address: str = Field(description="Recipient Starknet address (0x...)")
    amount_strk: float = Field(description="Amount in STRK to send")


# =============================================================================
# Health
# =============================================================================

@app.get("/health")
async def health():
    """Server health check + dependency status."""
    prover_ready = PROVER_BINARY.exists() if PROVER_BINARY else False
    return {
        "status": "healthy",
        "version": "0.2.0",
        "prover_binary": str(PROVER_BINARY),
        "prover_ready": prover_ready,
        "starknet_rpc": STARKNET_RPC,
        "merkle_pending": merkle_accumulator.pending_count(),
        "batch_committer": batch_committer.stats,
    }


# =============================================================================
# Wallet management
# =============================================================================

@app.post("/wallet/create")
async def create_wallet(req: CreateWalletRequest):
    """
    Generate a new quantum identity (ML-DSA-44 keypair) using hybrid seed
    from camera entropy + drand beacon, then auto-deploy a
    QuantumGuardAccount contract to Starknet Sepolia.

    The frontend sends a camera photo (base64). The backend:
      1. Decodes the photo → raw pixel bytes (local entropy)
      2. Fetches a fresh drand beacon (public verifiable randomness)
      3. Combines both → hybrid seed for key generation
      4. No seed/entropy/drand details are returned to the frontend
    """
    try:
        if key_manager.identity_exists(req.label):
            raise HTTPException(
                status_code=409,
                detail=f"Wallet '{req.label}' already exists. Choose a different label.",
            )

        # Determine seed source based on whether camera photo was provided
        if req.camera_photo:
            # Hybrid seed: camera entropy + drand beacon
            try:
                # Decode base64 camera photo to raw bytes
                # Strip data URL prefix if present (e.g., "data:image/jpeg;base64,")
                photo_data = req.camera_photo
                if "," in photo_data:
                    photo_data = photo_data.split(",", 1)[1]
                camera_bytes = base64.b64decode(photo_data)

                if len(camera_bytes) < 1024:
                    raise ValueError("Camera photo too small for sufficient entropy")

                # Fetch drand beacon (real-time from public network)
                drand_beacon = fetch_drand_beacon()

                # Generate identity with hybrid seed
                identity = key_manager.generate_identity_from_seed(
                    camera_entropy=camera_bytes,
                    drand_randomness=drand_beacon.randomness_bytes,
                    drand_round=drand_beacon.round,
                    label=req.label,
                )
                logger.info(
                    f"Identity created for wallet '{req.label}' "
                    f"(hybrid seed: camera+drand round {drand_beacon.round})"
                )

            except Exception as seed_err:
                # If hybrid seed fails, fall back to system PRNG
                logger.warning(
                    f"Hybrid seed generation failed: {seed_err}. "
                    "Falling back to system PRNG."
                )
                identity = key_manager.generate_identity(label=req.label)
        else:
            # No camera photo — use system PRNG
            identity = key_manager.generate_identity(label=req.label)
            logger.info(f"Identity created for wallet '{req.label}' (system PRNG)")

        # Build response — NO seed/entropy/drand technical details exposed
        result = {
            "status": "created",
            "label": req.label,
            "algorithm": identity["algorithm"],
            "pubkey_hash": identity["pubkey_hash"],
            "public_key_size": identity["public_key_size"],
            "secret_key_size": identity["secret_key_size"],
            "contract_address": None,
            "deployment_status": "pending",
            "seed_verified": identity.get("seed_source") == "camera+drand",
        }

        # Step 2: Auto-deploy contract to Starknet
        try:
            deploy_result = await contract_manager.deploy_wallet_contract(req.label)
            result["contract_address"] = deploy_result.get("contract_address")
            result["deployment_status"] = deploy_result.get("status", "deployed")
            result["class_hash"] = deploy_result.get("class_hash")
            result["explorer_url"] = (
                f"https://sepolia.starkscan.co/contract/{result['contract_address']}"
                if result["contract_address"] else None
            )
            logger.info(f"Contract auto-deployed for wallet '{req.label}': {result['contract_address']}")
        except Exception as deploy_err:
            # Wallet created but deployment failed — user can retry
            result["deployment_status"] = "failed"
            result["deployment_error"] = str(deploy_err)
            logger.warning(f"Auto-deploy failed for wallet '{req.label}': {deploy_err}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/wallet/info")
async def wallet_info(label: str = "default"):
    """Get wallet information including contract address and deployment status."""
    try:
        identity = key_manager.load_identity(label)
        contract_address = identity.get("contract_address")
        return {
            "status": "ok",
            "label": identity.get("label", label),
            "algorithm": identity["algorithm"],
            "pubkey_hash": identity["pubkey_hash"],
            "public_key_preview": truncate_display(identity["public_key"], 48),
            "public_key_size": identity["public_key_size"],
            "contract_address": contract_address,
            "deployment_status": identity.get("deployment_status", "pending"),
            "class_hash": identity.get("class_hash"),
            "explorer_url": (
                f"https://sepolia.starkscan.co/contract/{contract_address}"
                if contract_address else None
            ),
            "created_at": identity.get("created_at"),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/wallet/list")
async def list_wallets():
    """List all stored wallet identities."""
    wallets = key_manager.list_wallets()
    return {"status": "ok", "count": len(wallets), "wallets": wallets}


# =============================================================================
# Transaction signing
# =============================================================================

@app.post("/transaction/sign")
async def sign_transaction(tx: TransactionRequest):
    """Sign a transaction with ML-DSA-44."""
    try:
        tx_payload = {
            "to": tx.to,
            "amount": tx.amount,
            "nonce": tx.nonce or 0,
            "data": tx.data,
        }

        result = signer.sign_transaction(tx_payload, label=tx.label)

        # Record in persistence
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"
        tx_store.record_transaction(
            tx_id=tx_id,
            wallet_label=tx.label,
            to_addr=tx.to,
            amount=tx.amount,
            nonce=tx.nonce or 0,
            data=tx.data,
            message_hash=result["message_hash"],
            pubkey_hash=result["pubkey_hash"],
            signature_size=result["signature_size"],
            status="signed",
        )
        logger.info(f"Transaction {tx_id} signed with wallet '{tx.label}'")

        return {
            "status": "signed",
            "tx_id": tx_id,
            "message": result["message"],
            "signature": result["signature"],
            "public_key": result["public_key"],
            "signature_size": result["signature_size"],
            "message_hash": result["message_hash"],
            "pubkey_hash": result["pubkey_hash"],
            "transaction": result["transaction"],
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Proof generation (calls Rust prover)
# =============================================================================

@app.post("/transaction/prove")
async def prove_signature(req: ProveRequest):
    """
    Send a signed message to the Rust prover for off-chain verification.
    Returns a compact proof commitment (32 bytes) instead of the full
    2420-byte signature.
    """
    try:
        proof = await _call_prover(req.message, req.signature, req.public_key)
        return {
            "status": "proved",
            **proof,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transaction/execute")
async def execute_transaction(tx: TransactionRequest):
    """
    Full pipeline: sign → prove → submit to Starknet.

    Steps:
      1. Sign the transaction with ML-DSA-44
      2. Send signature to Rust prover for verification
      3. Receive proof commitment
      4. Submit proof commitment to Starknet smart contract (if deployed)
    """
    tx_id = f"tx_{uuid.uuid4().hex[:12]}"

    try:
        # Step 1: Sign
        tx_payload = {
            "to": tx.to,
            "amount": tx.amount,
            "nonce": tx.nonce or 0,
            "data": tx.data,
        }
        sig_result = signer.sign_transaction(tx_payload, label=tx.label)

        # Record the signed transaction
        tx_store.record_transaction(
            tx_id=tx_id,
            wallet_label=tx.label,
            to_addr=tx.to,
            amount=tx.amount,
            nonce=tx.nonce or 0,
            data=tx.data,
            message_hash=sig_result["message_hash"],
            pubkey_hash=sig_result["pubkey_hash"],
            signature_size=sig_result["signature_size"],
            status="signed",
        )
        logger.info(f"Transaction {tx_id} signed")

        # Step 2: Prove
        proof = await _call_prover(
            sig_result["message"],
            sig_result["signature"],
            sig_result["public_key"],
        )

        # Update with proof result
        tx_store.update_transaction_proof(
            tx_id=tx_id,
            proof_commitment=proof.get("proof_commitment", ""),
            proof_valid=proof.get("valid", False),
        )

        # Cache the proof
        tx_store.cache_proof(
            proof_commitment=proof.get("proof_commitment", ""),
            message_hash=sig_result["message_hash"],
            pubkey_hash=sig_result["pubkey_hash"],
            valid=proof.get("valid", False),
            signature_hash=proof.get("signature_hash", ""),
            signature_size=sig_result["signature_size"],
            prover=proof.get("prover", "rust"),
        )
        logger.info(f"Transaction {tx_id} proved: valid={proof.get('valid')}")

        # Record in Merkle audit trail (immutable)
        if proof.get("valid"):
            merkle_tx = {
                "tx_id": tx_id,
                "wallet_label": tx.label,
                "to_addr": tx.to,
                "amount": tx.amount,
                "message_hash": sig_result["message_hash"],
                "pubkey_hash": sig_result["pubkey_hash"],
                "proof_commitment": proof.get("proof_commitment", ""),
                "proof_valid": True,
                "timestamp": time.time(),
            }
            merkle_accumulator.add_transaction(merkle_tx)
            logger.debug(f"Transaction {tx_id} added to Merkle accumulator")

        # Step 3: Build result
        result = {
            "status": "executed" if proof.get("valid") else "proof_failed",
            "tx_id": tx_id,
            "transaction": tx_payload,
            "signature_size": sig_result["signature_size"],
            "proof_commitment": proof.get("proof_commitment"),
            "proof_valid": proof.get("valid"),
            "message_hash": sig_result["message_hash"],
            "pubkey_hash": sig_result["pubkey_hash"],
        }

        # Step 4: Submit to Starknet if contract is deployed
        if proof.get("valid"):
            contract_config = _load_contract_config()
            if contract_config.get("deployed") and contract_config.get("contract_address"):
                try:
                    starknet_result = await _submit_to_starknet(
                        contract_config["contract_address"],
                        proof.get("proof_commitment", ""),
                        sig_result["pubkey_hash"],
                        tx_payload,
                    )
                    result["starknet_status"] = "submitted"
                    result["starknet_tx_hash"] = starknet_result.get("tx_hash")
                    tx_store.update_transaction_starknet(
                        tx_id=tx_id,
                        starknet_tx_hash=starknet_result.get("tx_hash", ""),
                        starknet_status="submitted",
                    )
                    logger.info(f"Transaction {tx_id} submitted to Starknet: {starknet_result.get('tx_hash')}")
                except Exception as e:
                    result["starknet_status"] = "submission_failed"
                    result["starknet_error"] = str(e)
                    tx_store.update_transaction_starknet(
                        tx_id=tx_id,
                        starknet_tx_hash="",
                        starknet_status="submission_failed",
                        error=str(e),
                    )
                    logger.warning(f"Transaction {tx_id} Starknet submission failed: {e}")
            else:
                result["starknet_status"] = "contract_not_deployed"
                result["note"] = (
                    "Proof valid. Deploy the contract first via POST /contract/deploy "
                    "or 'make deploy-contract' to enable on-chain submission."
                )

        return result

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        tx_store.update_transaction_status(tx_id, "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Transaction history & status
# =============================================================================

@app.get("/transaction/history")
async def transaction_history(
    label: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    Get transaction history with optional filters.

    Query params:
      label  — filter by wallet label
      status — filter by status (signed, proved, submitted, error, etc.)
      limit  — max results (default 50)
      offset — pagination offset
    """
    transactions = tx_store.list_transactions(
        wallet_label=label, status=status, limit=limit, offset=offset,
    )
    total = tx_store.count_transactions(wallet_label=label)
    return {
        "status": "ok",
        "total": total,
        "count": len(transactions),
        "offset": offset,
        "transactions": transactions,
    }


@app.get("/transaction/{tx_id}")
async def get_transaction(tx_id: str):
    """Get a single transaction by its internal ID."""
    tx = tx_store.get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction '{tx_id}' not found")
    return {"status": "ok", **tx}


@app.get("/transaction/starknet/{starknet_tx_hash}")
async def get_transaction_by_starknet_hash(starknet_tx_hash: str):
    """Get a transaction by its Starknet transaction hash."""
    tx = tx_store.get_transaction_by_starknet_hash(starknet_tx_hash)
    if not tx:
        raise HTTPException(
            status_code=404,
            detail=f"No transaction found with Starknet hash '{starknet_tx_hash}'",
        )
    return {"status": "ok", **tx}


@app.get("/transaction/{tx_id}/status")
async def get_transaction_status(tx_id: str):
    """
    Get the current status of a transaction.
    If it has a Starknet tx hash, optionally query the chain for confirmation.
    """
    tx = tx_store.get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction '{tx_id}' not found")

    result = {
        "tx_id": tx_id,
        "status": tx["status"],
        "starknet_status": tx.get("starknet_status", "none"),
        "starknet_tx_hash": tx.get("starknet_tx_hash"),
        "proof_valid": bool(tx.get("proof_valid")),
        "proof_commitment": tx.get("proof_commitment"),
        "updated_at": tx.get("updated_at"),
    }

    # If submitted to Starknet, try to check receipt via starkli
    if tx.get("starknet_tx_hash") and tx.get("starknet_status") == "submitted":
        try:
            receipt_result = subprocess.run(
                [
                    "starkli", "receipt",
                    tx["starknet_tx_hash"],
                    "--rpc", STARKNET_RPC,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if receipt_result.returncode == 0:
                result["starknet_receipt"] = receipt_result.stdout.strip()
                if "ACCEPTED" in receipt_result.stdout.upper():
                    result["starknet_status"] = "confirmed"
                    tx_store.update_transaction_starknet(
                        tx_id, tx["starknet_tx_hash"], "confirmed"
                    )
                elif "REJECTED" in receipt_result.stdout.upper():
                    result["starknet_status"] = "rejected"
                    tx_store.update_transaction_starknet(
                        tx_id, tx["starknet_tx_hash"], "rejected"
                    )
        except Exception:
            pass  # Non-critical, keep existing status

    return result


@app.get("/proofs")
async def list_proofs(limit: int = 50):
    """List cached proof commitments for audit trail."""
    proofs = tx_store.list_proofs(limit=limit)
    return {"status": "ok", "count": len(proofs), "proofs": proofs}


# =============================================================================
# Merkle Audit Trail
# =============================================================================

@app.get("/audit/batches")
async def list_merkle_batches(limit: int = 50, committed_only: bool = False):
    """
    List Merkle audit batches.
    Each batch contains the root hash of a group of transactions.
    Committed batches have their root anchored on Starknet.
    """
    batches = tx_store.list_merkle_batches(limit=limit, committed_only=committed_only)
    return {
        "status": "ok",
        "count": len(batches),
        "pending_txs": merkle_accumulator.pending_count(),
        "committer_stats": batch_committer.stats,
        "batches": batches,
    }


@app.get("/audit/batch/{batch_id}")
async def get_merkle_batch(batch_id: str):
    """Get details of a specific Merkle batch."""
    batch = tx_store.get_merkle_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")

    leaves = tx_store.get_leaves_for_batch(batch_id)
    return {
        "status": "ok",
        **batch,
        "leaves": leaves,
    }


@app.get("/audit/proof/{tx_id}")
async def get_transaction_merkle_proof(tx_id: str):
    """
    Get the Merkle proof for a specific transaction.
    This proves the transaction is included in a committed batch,
    anchored on Starknet.
    """
    proof = tx_store.get_merkle_proof_for_tx(tx_id)
    if not proof:
        raise HTTPException(
            status_code=404,
            detail=f"No Merkle proof found for transaction '{tx_id}'. "
                   "Transaction may be in a pending batch.",
        )
    return {"status": "ok", **proof}


@app.post("/audit/force-commit")
async def force_commit_batch():
    """
    Force-commit the current pending batch immediately,
    regardless of batch size or time interval.
    """
    if merkle_accumulator.pending_count() == 0:
        return {"status": "empty", "message": "No pending transactions to commit"}

    result = await batch_committer.force_commit()
    if result:
        return {"status": "committed", **result}
    return {"status": "error", "message": "Failed to commit batch"}


# =============================================================================
# Starknet contract management
# =============================================================================

class DeployRequest(BaseModel):
    label: str = Field(default="default", description="Wallet identity to use as contract owner")


@app.get("/contract/status")
async def contract_status():
    """Get the deployed contract status and address."""
    config = _load_contract_config()
    return {
        "deployed": config.get("deployed", False),
        "contract_address": config.get("contract_address"),
        "network": config.get("network", "starknet-sepolia"),
        "owner_pubkey_hash": config.get("owner_pubkey_hash"),
        "deployed_at": config.get("deployed_at"),
    }


@app.post("/contract/deploy")
async def deploy_contract(req: DeployRequest):
    """
    Deploy the QuantumGuard smart contract to Starknet Sepolia.

    Requires environment variables:
      - STARKNET_PRIVATE_KEY: Deployer account private key
      - STARKNET_ACCOUNT_ADDRESS: Deployer account address

    Uses starkli CLI under the hood for declare + deploy.
    """
    try:
        # Load the owner identity
        identity = key_manager.load_identity(req.label)
        owner_hash = identity["pubkey_hash"]

        # Check if already deployed
        config = _load_contract_config()
        if config.get("deployed"):
            return {
                "status": "already_deployed",
                "contract_address": config["contract_address"],
                "network": config.get("network"),
            }

        # Check for required env vars
        private_key = os.environ.get("STARKNET_PRIVATE_KEY")
        account_addr = os.environ.get("STARKNET_ACCOUNT_ADDRESS")

        if not private_key or not account_addr:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Set STARKNET_PRIVATE_KEY and STARKNET_ACCOUNT_ADDRESS "
                    "environment variables before deploying. "
                    "Get testnet ETH from https://faucet.starknet.io"
                ),
            )

        # Check for compiled contract
        contract_dir = Path(__file__).resolve().parent.parent / "starknet_contracts"
        sierra_file = contract_dir / "target" / "dev" / "quantum_guard_contract_QuantumGuardAccount.contract_class.json"

        if not sierra_file.exists():
            # Try building first
            build_result = subprocess.run(
                ["scarb", "build"],
                cwd=str(contract_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if build_result.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"Contract build failed: {build_result.stderr}",
                )

        if not sierra_file.exists():
            raise HTTPException(
                status_code=500,
                detail="Contract Sierra file not found after build. Check scarb build output.",
            )

        # Truncate owner_hash to fit felt252 (31 bytes = 62 hex chars)
        owner_hash_felt = "0x" + owner_hash[:62]

        # Step 1: Declare the contract class
        declare_result = subprocess.run(
            [
                "starkli", "declare",
                str(sierra_file),
                "--rpc", STARKNET_RPC,
                "--private-key", private_key,
                "--account", account_addr,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Extract class hash (starkli prints it on success)
        class_hash = None
        for line in (declare_result.stdout + declare_result.stderr).splitlines():
            if line.strip().startswith("0x") and len(line.strip()) >= 60:
                class_hash = line.strip()
                break

        if not class_hash:
            # May already be declared
            if "already declared" in declare_result.stderr.lower():
                # Extract from error message
                for line in declare_result.stderr.splitlines():
                    if "0x" in line:
                        parts = line.split("0x")
                        if len(parts) > 1:
                            class_hash = "0x" + parts[-1].strip().rstrip(".")
                            break

        if not class_hash:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to declare contract: {declare_result.stderr}",
            )

        # Step 2: Deploy the contract
        deploy_result = subprocess.run(
            [
                "starkli", "deploy",
                class_hash,
                owner_hash_felt,   # constructor arg: owner_pubkey_hash
                account_addr,      # constructor arg: initial_prover
                "--rpc", STARKNET_RPC,
                "--private-key", private_key,
                "--account", account_addr,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Extract contract address
        contract_address = None
        for line in (deploy_result.stdout + deploy_result.stderr).splitlines():
            if line.strip().startswith("0x") and len(line.strip()) >= 60:
                contract_address = line.strip()
                break

        if not contract_address:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to deploy contract: {deploy_result.stderr}",
            )

        # Save deployment info
        deploy_config = {
            "deployed": True,
            "contract_address": contract_address,
            "class_hash": class_hash,
            "network": "starknet-sepolia",
            "rpc": STARKNET_RPC,
            "owner_pubkey_hash": owner_hash,
            "owner_label": req.label,
            "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        _save_contract_config(deploy_config)

        # Also record in persistence
        tx_store.record_deployment(
            contract_address=contract_address,
            class_hash=class_hash,
            owner_pubkey_hash=owner_hash,
            owner_label=req.label,
            network="starknet-sepolia",
            rpc=STARKNET_RPC,
            deployed_at=deploy_config["deployed_at"],
        )
        logger.info(f"Contract deployed at {contract_address}")

        return {
            "status": "deployed",
            **deploy_config,
        }

    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Wallet balance
# =============================================================================

@app.get("/wallet/{label}/balance")
async def get_wallet_balance(label: str, force_refresh: bool = False):
    """
    Get the STRK token balance for a wallet's deployed contract.
    Queries Starknet Sepolia RPC directly and caches the result.
    """
    try:
        identity = key_manager.load_identity(label)
        contract_address = identity.get("contract_address")
        if not contract_address:
            return {
                "status": "no_contract",
                "label": label,
                "balance_wei": "0",
                "balance_strk": "0.000000",
                "balance_display": "0 STRK",
                "error": "No contract deployed for this wallet",
            }

        balance = await balance_provider.get_balance(
            contract_address, force_refresh=force_refresh
        )
        balance["label"] = label
        balance["status"] = "ok"
        return balance

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Manual deployment (fallback if auto-deploy failed)
# =============================================================================

@app.post("/wallet/{label}/deploy")
async def deploy_wallet_contract(label: str):
    """
    Manually deploy a QuantumGuardAccount contract for a wallet.
    Use this if the auto-deploy during wallet creation failed.
    """
    try:
        result = await contract_manager.deploy_wallet_contract(label)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Token transfers (via execute_with_proof)
# =============================================================================

@app.post("/transfer/create")
async def create_transfer(req: TransferRequest):
    """
    Prepare a STRK transfer (without executing).
    Returns estimated tx data for user review.
    """
    try:
        result = await transfer_handler.create_transfer(
            label=req.label,
            to_address=req.to_address,
            amount_strk=req.amount_strk,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transfer/execute")
async def execute_transfer(req: TransferRequest):
    """
    Full STRK transfer pipeline: sign → prove → submit to Starknet.

    Uses the quantum signature (ML-DSA-44) and execute_with_proof
    on the wallet's QuantumGuardAccount contract.
    """
    try:
        result = await transfer_handler.execute_transfer(
            label=req.label,
            to_address=req.to_address,
            amount_strk=req.amount_strk,
            call_prover_fn=_call_prover,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/transfer/{starknet_tx_hash}/status")
async def get_transfer_status(starknet_tx_hash: str):
    """Check the status of a submitted Starknet transfer."""
    try:
        result = await transfer_handler.get_transfer_status(starknet_tx_hash)
        return {"starknet_tx_hash": starknet_tx_hash, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Internal: Submit to Starknet (legacy — used by /transaction/execute)
# =============================================================================

async def _submit_to_starknet(
    contract_address: str,
    proof_commitment: str,
    pubkey_hash: str,
    tx_payload: dict,
) -> dict:
    """
    Submit a proved transaction to the on-chain QuantumGuard contract
    via starkli invoke.
    """
    private_key = os.environ.get("STARKNET_PRIVATE_KEY", "")
    account_addr = os.environ.get("STARKNET_ACCOUNT_ADDRESS", "")

    if not private_key or not account_addr:
        raise RuntimeError(
            "STARKNET_PRIVATE_KEY and STARKNET_ACCOUNT_ADDRESS required for submission"
        )

    # Truncate hashes to felt252-compatible hex
    proof_felt = "0x" + proof_commitment[:62]
    pubkey_felt = "0x" + pubkey_hash[:62]
    nonce_str = str(tx_payload.get("nonce", 0))

    # Call execute_with_proof on the contract
    invoke_result = subprocess.run(
        [
            "starkli", "invoke",
            contract_address,
            "execute_with_proof",
            account_addr,     # to (target address)
            "0x0",            # selector
            "0",              # calldata length
            proof_felt,       # proof_commitment
            pubkey_felt,      # pubkey_hash
            nonce_str,        # nonce
            "--rpc", STARKNET_RPC,
            "--private-key", private_key,
            "--account", account_addr,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if invoke_result.returncode != 0:
        raise RuntimeError(f"Starknet invoke failed: {invoke_result.stderr}")

    # Extract tx hash
    tx_hash = None
    for line in (invoke_result.stdout + invoke_result.stderr).splitlines():
        if "0x" in line and len(line.strip()) > 10:
            tx_hash = line.strip()
            break

    return {"tx_hash": tx_hash, "status": "submitted"}


# =============================================================================
# Internal: Call Rust prover
# =============================================================================

async def _call_prover(message_b64: str, signature_b64: str, pubkey_b64: str) -> dict:
    """
    Call the Rust prover binary via subprocess (stdin JSON → stdout JSON).
    Falls back to Python-native verification if the binary isn't built yet.
    """
    request_json = json.dumps({
        "message": message_b64,
        "signature": signature_b64,
        "public_key": pubkey_b64,
    })

    prover_path = PROVER_BINARY

    # Try Rust prover first
    if prover_path and prover_path.exists():
        try:
            result = subprocess.run(
                [str(prover_path), "verify"],
                input=request_json,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                print(f"[Prover] Binary failed: {result.stderr}")
        except Exception as e:
            print(f"[Prover] Binary error: {e}")

    # Fallback: Python-native verification
    print("[Prover] Using Python fallback verification")
    msg_bytes = b64decode(message_b64)
    sig_bytes = b64decode(signature_b64)
    pk_bytes = b64decode(pubkey_b64)

    valid = QuantumSigner.verify_signature(msg_bytes, sig_bytes, pk_bytes)

    return {
        "valid": valid,
        "message_hash": sha256_hex(msg_bytes),
        "signature_hash": sha256_hex(sig_bytes),
        "pubkey_hash": sha256_hex(pk_bytes),
        "proof_commitment": sha256_hex(
            f"{valid}:{sha256_hex(msg_bytes)}:{sha256_hex(sig_bytes)}:{sha256_hex(pk_bytes)}".encode()
        ),
        "signature_size": len(sig_bytes),
        "prover": "python_fallback",
    }


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    print("🔐 QuantumGuard Wallet API")
    print(f"   Swagger UI: http://localhost:{API_PORT}/docs")
    print(f"   Prover:     {PROVER_BINARY}")
    print(f"   Starknet:   {STARKNET_RPC}")
    print()
    uvicorn.run(app, host=API_HOST, port=API_PORT)
