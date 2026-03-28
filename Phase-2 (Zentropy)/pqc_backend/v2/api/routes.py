"""
QuantumGuard v2 — FastAPI Router
==================================
Multi-user custodial wallet REST API.

All endpoints require an `Authorization: Bearer <api_key>` header
that maps to an organization.

Endpoints:
  POST   /api/v2/users/register         — Create user + wallet + keys
  GET    /api/v2/users/{user_id}/wallet  — Get wallet info + balance
  GET    /api/v2/users                   — List all users in org
  POST   /api/v2/transactions/transfer   — Sign → Prove → Batch → Submit
  GET    /api/v2/transactions/{tx_id}    — Get transaction detail
  GET    /api/v2/users/{user_id}/transactions — Transaction history
  GET    /api/v2/batches                 — List Merkle batches
  GET    /api/v2/batches/{batch_id}      — Batch detail + leaves
  GET    /api/v2/proof/{tx_id}           — Merkle proof for a transaction
  POST   /api/v2/batches/force-finalize  — Force-finalize current batch
  GET    /api/v2/audit/{user_id}         — Audit log for user
  GET    /api/v2/audit/verify-chain      — Verify audit chain integrity
  GET    /api/v2/health                  — Service health
  POST   /api/v2/org/create              — Create organization (bootstrap)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request, Query, Path
from pydantic import BaseModel, Field, EmailStr

from ..db.connection import get_db
from ..models.schemas import (
    UserCreate, WalletRegistrationOut, TransferRequest,
    TransactionDetailOut, TransferResultOut,
    MerkleBatchOut, MerkleBatchDetailOut, MerkleProofOut,
    AuditLogOut, HealthOut, OrganizationCreate, OrganizationOut, SenderProfileUpdate,
    SetMpinRequest, VerifyMpinRequest,
)
from ..models.enums import STRK_DECIMALS
from ..services.key_service import KeyService
from ..services.wallet_service import WalletService
from ..services.transaction_service import TransactionService
from ..services.merkle_service import MerkleService
from ..services.audit_service import AuditService
from ..services.deployment_service import DeploymentService

logger = logging.getLogger("quantumguard.api")

router = APIRouter(prefix="/api/v2", tags=["QuantumGuard v2"])

# ── Service singletons (initialized once) ────────────────

_key_svc = KeyService()
_audit_svc = AuditService()
_wallet_svc = WalletService(key_service=_key_svc, audit_service=_audit_svc)
_merkle_svc = MerkleService(audit_service=_audit_svc)
_tx_svc = TransactionService(
    key_service=_key_svc, audit_service=_audit_svc, merkle_service=_merkle_svc
)
_deploy_svc = DeploymentService(audit_service=_audit_svc)


def _resolve_prover_endpoint() -> Optional[str]:
    configured = (os.environ.get("PROVER_URL", "") or "").strip()
    if configured:
        return configured

    port = (os.environ.get("PROVER_PORT", "") or "").strip()
    if not port:
        return None

    host = (os.environ.get("PROVER_HOST", "127.0.0.1") or "127.0.0.1").strip()
    return f"http://{host}:{port}"


async def _auto_deploy_account_task(account_id: str, org_id: str, user_id: str) -> None:
    """Background wrapper to deploy account without blocking registration."""
    try:
        await _deploy_svc.deploy_account_via_new_connection(account_id, org_id, user_id)
    except Exception as e:
        logger.error("Auto deployment task crashed for account %s: %s", account_id, e)


# ── Auth Dependency ───────────────────────────────────────

async def _get_org_id(authorization: str = Header(...)) -> str:
    """Extract org_id from Bearer token (API key)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid Authorization header")
    api_key = authorization[7:]
    async with get_db() as conn:
        org = await _wallet_svc.get_organization_by_api_key(conn, api_key)
    if not org:
        raise HTTPException(401, "Invalid API key")
    return dict(org)["org_id"]


# ── Bootstrap: Create Organization ────────────────────────

class OrgCreateRequest(BaseModel):
    org_name: str = Field(..., min_length=1, max_length=255)
    admin_email: EmailStr
    bootstrap_secret: str = Field(..., description="Admin secret for bootstrapping")


@router.post("/org/create")
async def create_organization(req: OrgCreateRequest):
    """
    Create a new organization. Requires bootstrap secret.
    Returns the API key for all subsequent requests.
    """
    expected = os.environ.get("BOOTSTRAP_SECRET", "").strip()
    if not expected:
        raise HTTPException(500, "Server misconfigured: BOOTSTRAP_SECRET is not set")
    if req.bootstrap_secret != expected:
        raise HTTPException(403, "Invalid bootstrap secret")

    async with get_db() as conn:
        result = await _wallet_svc.create_organization(conn, req.org_name, str(req.admin_email))
    return result

@router.get("/org")
async def get_current_organization(authorization: str = Header(...)):
    """Get the current organization details based on the API key."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid Authorization header")
    api_key = authorization[7:]
    async with get_db() as conn:
        org = await _wallet_svc.get_organization_by_api_key(conn, api_key)
    if not org:
        raise HTTPException(404, "Organization not found")
    
    return {
        "org_id": org["org_id"],
        "org_name": org["org_name"],
        "admin_email": org["admin_email"]
    }


# ── User Registration ─────────────────────────────────────

@router.post("/users/register", response_model=WalletRegistrationOut)
async def register_user(
    req: UserCreate,
    request: Request,
    authorization: str = Header(...),
):
    """
    Register a new user: creates wallet + Dilithium keys + counterfactual address.
    Returns seed phrase (SHOWN ONCE).
    """
    org_id = await _get_org_id(authorization)
    ip = request.client.host if request.client else None

    async with get_db() as conn:
        result = await _wallet_svc.register_user(
            conn, org_id, req.email, req.username, ip_address=ip
        )

        if _deploy_svc.auto_deploy_enabled():
            await conn.execute(
                """UPDATE accounts
                   SET deployment_status = $1, deployment_error_message = NULL, updated_at = $2
                   WHERE account_id = $3""",
                "pending",
                time.time(),
                result["account_id"],
            )
            asyncio.create_task(
                _auto_deploy_account_task(result["account_id"], org_id, result["user_id"])
            )
            result["deployment_status"] = "pending"
        else:
            result["deployment_status"] = "counterfactual"

    return WalletRegistrationOut(
        user_id=result["user_id"],
        wallet_id=result["wallet_id"],
        contract_address=result["contract_address"],
        public_key=result["public_key"],
        public_key_hash=result["public_key_hash"],
        seed_phrase=result["seed_phrase"],
        sender_model=result.get("sender_model", "relayer"),
        submitter_address=result.get("submitter_address"),
        deployment_status=result.get("deployment_status", "counterfactual"),
        deployment_tx_hash=result.get("deployment_tx_hash"),
        deployment_error_message=result.get("deployment_error_message"),
    )


@router.get("/users/{user_id}/deployment-status")
async def get_user_deployment_status(user_id: str, authorization: str = Header(...)):
    """Return deployment lifecycle state for a user's account."""
    org_id = await _get_org_id(authorization)

    async with get_db() as conn:
        user = await _wallet_svc.get_user(conn, user_id)
        if not user or dict(user).get("org_id") != org_id:
            raise HTTPException(404, "User not found")
        data = await _wallet_svc.get_full_user_wallet(conn, user_id)

    if not data:
        raise HTTPException(404, "User not found")

    account = data.get("account") or {}
    return {
        "user_id": user_id,
        "wallet_id": data["wallet"]["wallet_id"],
        "deployment_status": account.get("deployment_status", "unknown"),
        "deployment_tx_hash": account.get("deployment_tx_hash"),
        "deployment_error_message": account.get("deployment_error_message"),
        "deployment_attempts": account.get("deployment_attempts", 0),
        "last_deployment_attempt": account.get("last_deployment_attempt"),
        "deployed_at": account.get("deployed_at"),
        "contract_address": account.get("account_address"),
        "sender_model": account.get("sender_model", "relayer"),
        "submitter_address": account.get("submitter_address"),
        "submitter_account_config": account.get("submitter_account_config"),
        "private_key_configured": bool(account.get("submitter_private_key_encrypted")),
    }


@router.post("/users/{user_id}/sender-profile")
async def update_user_sender_profile(
    user_id: str,
    req: SenderProfileUpdate,
    authorization: str = Header(...),
):
    """Configure per-user sender profile for relayer or user-account submission."""
    org_id = await _get_org_id(authorization)

    async with get_db() as conn:
        user = await _wallet_svc.get_user(conn, user_id)
        if not user or dict(user).get("org_id") != org_id:
            raise HTTPException(404, "User not found")
        try:
            result = await _wallet_svc.update_sender_profile(
                conn,
                user_id=user_id,
                sender_model=req.sender_model,
                submitter_address=req.submitter_address,
                submitter_account_config=req.submitter_account_config,
                submitter_private_key=req.submitter_private_key,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

    return result


@router.post("/users/{user_id}/mpin")
async def set_mpin(
    user_id: str,
    req: SetMpinRequest,
    authorization: str = Header(...),
):
    """Set or update the MPIN for a user's wallet."""
    org_id = await _get_org_id(authorization)

    async with get_db() as conn:
        user = await _wallet_svc.get_user(conn, user_id)
        if not user or dict(user).get("org_id") != org_id:
            raise HTTPException(404, "User not found")
            
        wallet = await _wallet_svc.get_wallet_by_user(conn, user_id)
        if not wallet:
            raise HTTPException(404, "Wallet not found")

        wallet_id = dict(wallet)["wallet_id"]
        await _wallet_svc.set_mpin(conn, wallet_id, req.mpin)

    return {"status": "success", "message": "MPIN configured securely."}


@router.post("/users/{user_id}/mpin/verify")
async def verify_mpin(
    user_id: str,
    req: VerifyMpinRequest,
    authorization: str = Header(...),
):
    """Verify the MPIN for a user's wallet without executing a transaction."""
    org_id = await _get_org_id(authorization)

    async with get_db() as conn:
        user = await _wallet_svc.get_user(conn, user_id)
        if not user or dict(user).get("org_id") != org_id:
            raise HTTPException(404, "User not found")
            
        wallet = await _wallet_svc.get_wallet_by_user(conn, user_id)
        if not wallet:
            raise HTTPException(404, "Wallet not found")

        wallet_id = dict(wallet)["wallet_id"]
        is_valid = await _wallet_svc.verify_mpin(conn, wallet_id, req.mpin)

    if not is_valid:
        raise HTTPException(401, "Invalid MPIN")

    return {"status": "success", "valid": True}


@router.post("/users/{user_id}/deployment/retry")
async def retry_user_deployment(
    user_id: str = Path(..., min_length=1),
    authorization: str = Header(...),
):
    """Force a deployment retry for a user's account and return queued status."""
    org_id = await _get_org_id(authorization)

    async with get_db() as conn:
        data = await _wallet_svc.get_full_user_wallet(conn, user_id)
        if not data:
            raise HTTPException(404, "User not found")

        account = data.get("account") or {}
        account_id = account.get("account_id")
        if not account_id:
            raise HTTPException(400, "No account found for user")

        now = time.time()
        await conn.execute(
            """UPDATE accounts
               SET deployment_status = $1,
                   deployment_error_message = NULL,
                   updated_at = $2
               WHERE account_id = $3""",
            "pending",
            now,
            account_id,
        )

        asyncio.create_task(_auto_deploy_account_task(account_id, org_id, user_id))

    return {
        "user_id": user_id,
        "account_id": account_id,
        "deployment_status": "pending",
        "message": "Deployment retry queued",
    }


# ── Wallet Info ───────────────────────────────────────────

@router.get("/users/{user_id}/wallet")
async def get_user_wallet(user_id: str, authorization: str = Header(...)):
    """Get user's wallet details including balance and deployment status."""
    org_id = await _get_org_id(authorization)

    async with get_db() as conn:
        user = await _wallet_svc.get_user(conn, user_id)
        if not user or dict(user).get("org_id") != org_id:
            raise HTTPException(404, "User not found")

        data = await _wallet_svc.get_full_user_wallet(conn, user_id)

        if data and data.get("account"):
            account = data["account"]
            deployment_status = (account.get("deployment_status") or "").strip().lower()
            refreshed_balance = await _wallet_svc.refresh_account_balance_from_chain(
                conn,
                account.get("account_address", ""),
                deployed=deployment_status == "deployed",
            )
            if refreshed_balance is not None:
                account["balance_wei"] = refreshed_balance

    if not data:
        raise HTTPException(404, "User not found")

    account = data["account"] or {}
    balance_wei = account.get("balance_wei", "0")
    balance_strk = int(balance_wei) / (10 ** STRK_DECIMALS) if balance_wei else 0

    return {
        "user_id": user_id,
        "wallet_id": data["wallet"]["wallet_id"],
        "wallet_name": data["wallet"]["wallet_name"],
        "contract_address": account.get("account_address", ""),
        "sender_model": account.get("sender_model", "relayer"),
        "submitter_address": account.get("submitter_address"),
        "public_key_hash": account.get("public_key_pq_hash", ""),
        "deployment_status": account.get("deployment_status", "unknown"),
        "nonce": account.get("nonce", 0),
        "balance_strk": f"{balance_strk:.6f}",
        "balance_wei": balance_wei,
        "status": data["wallet"]["status"],
        "has_mpin": data["wallet"].get("has_mpin", False),
    }


@router.get("/users")
async def list_users(
    authorization: str = Header(...),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List all users in organization."""
    org_id = await _get_org_id(authorization)
    async with get_db() as conn:
        users = await _wallet_svc.list_users(conn, org_id, limit, offset)
    return {"total": len(users), "users": users}


# ── Transfers ─────────────────────────────────────────────

class TransferBody(BaseModel):
    user_id: str
    to_address: str = Field(..., min_length=3)
    amount_strk: float = Field(..., gt=0)
    mpin: str = Field(..., min_length=4, max_length=6, pattern="^[0-9]+$")


@router.post("/transactions/transfer")
async def transfer(
    req: TransferBody,
    request: Request,
    authorization: str = Header(...),
):
    """
    Execute a full transfer: Sign → Prove → Batch → Submit to Starknet.
    """
    org_id = await _get_org_id(authorization)
    ip = request.client.host if request.client else None

    async with get_db() as conn:
        result = await _tx_svc.execute_transfer(
            conn, req.user_id, org_id,
            req.to_address, req.amount_strk,
            req.mpin,
            ip_address=ip,
        )

    return result


# ── Transaction Queries ───────────────────────────────────

@router.get("/transactions/{tx_id}")
async def get_transaction(tx_id: str, authorization: str = Header(...)):
    """Get transaction detail."""
    org_id = await _get_org_id(authorization)
    async with get_db() as conn:
        owner_org = await conn.fetchval(
            """SELECT u.org_id
               FROM transactions t
               JOIN accounts a ON t.account_id = a.account_id
               JOIN wallets w ON a.wallet_id = w.wallet_id
               JOIN users u ON w.user_id = u.user_id
               WHERE t.tx_id = $1""",
            tx_id,
        )
        if not owner_org or owner_org != org_id:
            raise HTTPException(404, "Transaction not found")

        tx = await _tx_svc.get_transaction(conn, tx_id)
        if tx and tx.get("tx_hash") and tx.get("status") in {"submitted", "pending"}:
            chain = await _tx_svc.get_transaction_status_from_starknet(
                tx["tx_hash"],
                expected_from_address=tx.get("sender_account_address"),
                expected_to_address=tx.get("to_address"),
                expected_amount_wei=tx.get("amount_wei"),
            )
            chain_status = (chain or {}).get("status")
            if chain_status == "confirmed":
                now = time.time()
                await conn.execute(
                    """UPDATE transactions
                       SET status = $1, starknet_status = $2, confirmed_at = $3
                       WHERE tx_id = $4""",
                    "confirmed",
                    "confirmed",
                    now,
                    tx_id,
                )
                tx["status"] = "confirmed"
                tx["starknet_status"] = "confirmed"
                tx["confirmed_at"] = now
            elif chain_status == "rejected":
                await conn.execute(
                    """UPDATE transactions
                       SET status = $1, starknet_status = $2
                       WHERE tx_id = $3""",
                    "rejected",
                    "rejected",
                    tx_id,
                )
                tx["status"] = "rejected"
                tx["starknet_status"] = "rejected"
            elif chain_status == "pending":
                await conn.execute(
                    """UPDATE transactions
                       SET starknet_status = $1
                       WHERE tx_id = $2""",
                    "pending",
                    tx_id,
                )
                tx["starknet_status"] = "pending"
            elif chain_status == "failed":
                err = (chain or {}).get("error") or "Transaction confirmed without STRK transfer"
                await conn.execute(
                    """UPDATE transactions
                       SET status = $1, starknet_status = $2, error_message = $3
                       WHERE tx_id = $4""",
                    "failed",
                    (chain or {}).get("starknet_status") or "failed",
                    str(err),
                    tx_id,
                )
                tx["status"] = "failed"
                tx["starknet_status"] = (chain or {}).get("starknet_status") or "failed"
                tx["error_message"] = str(err)
    if not tx:
        raise HTTPException(404, "Transaction not found")

    amount_wei = tx.get("amount_wei", "0")
    strk = int(amount_wei) / (10 ** STRK_DECIMALS) if amount_wei else 0
    explorer = f"https://sepolia.voyager.online/tx/{tx['tx_hash']}" if tx.get("tx_hash") else None

    return {
        **tx,
        "amount_strk": f"{strk:.6f}",
        "explorer_url": explorer,
    }


@router.get("/users/{user_id}/transactions")
async def list_user_transactions(
    user_id: str = Path(..., min_length=1),
    authorization: str = Header(...),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List all transactions for a user."""
    org_id = await _get_org_id(authorization)

    async with get_db() as conn:
        user = await _wallet_svc.get_user(conn, user_id)
        if not user or dict(user).get("org_id") != org_id:
            raise HTTPException(404, "User wallet not found")

        wallet = await _wallet_svc.get_wallet_by_user(conn, user_id)
        if not wallet:
            raise HTTPException(404, "User wallet not found")
        wallet_dict = dict(wallet)
        account = await _wallet_svc.get_account_by_wallet(conn, wallet_dict["wallet_id"])
        if not account:
            raise HTTPException(404, "Account not found")
        account_dict = dict(account)

        account_addr = account_dict.get("account_address")
        txs = await _tx_svc.list_transactions(
            conn, account_dict["account_id"], limit, offset, account_addr
        )
        total = await _tx_svc.count_transactions(conn, account_dict["account_id"], account_addr)

        for tx in txs:
            status = (tx.get("status") or "").lower()
            tx_hash = tx.get("tx_hash")
            if not tx_hash or status not in {"submitted", "pending"}:
                continue

            chain = await _tx_svc.get_transaction_status_from_starknet(
                tx_hash,
                expected_from_address=tx.get("sender_account_address"),
                expected_to_address=tx.get("to_address"),
                expected_amount_wei=tx.get("amount_wei"),
            )
            chain_status = (chain or {}).get("status")
            if chain_status == "confirmed":
                now = time.time()
                await conn.execute(
                    """UPDATE transactions
                       SET status = $1, starknet_status = $2, confirmed_at = $3
                       WHERE tx_id = $4""",
                    "confirmed",
                    "confirmed",
                    now,
                    tx["tx_id"],
                )
                tx["status"] = "confirmed"
                tx["starknet_status"] = "confirmed"
                tx["confirmed_at"] = now
            elif chain_status == "rejected":
                await conn.execute(
                    """UPDATE transactions
                       SET status = $1, starknet_status = $2
                       WHERE tx_id = $3""",
                    "rejected",
                    "rejected",
                    tx["tx_id"],
                )
                tx["status"] = "rejected"
                tx["starknet_status"] = "rejected"
            elif chain_status == "pending":
                await conn.execute(
                    """UPDATE transactions
                       SET starknet_status = $1
                       WHERE tx_id = $2""",
                    "pending",
                    tx["tx_id"],
                )
                tx["starknet_status"] = "pending"
            elif chain_status == "failed":
                err = (chain or {}).get("error") or "Transaction confirmed without STRK transfer"
                await conn.execute(
                    """UPDATE transactions
                       SET status = $1, starknet_status = $2, error_message = $3
                       WHERE tx_id = $4""",
                    "failed",
                    (chain or {}).get("starknet_status") or "failed",
                    str(err),
                    tx["tx_id"],
                )
                tx["status"] = "failed"
                tx["starknet_status"] = (chain or {}).get("starknet_status") or "failed"
                tx["error_message"] = str(err)

    # Format amounts and directions
    for tx in txs:
        wei = int(tx.get("amount_wei", "0"))
        tx["amount_strk"] = f"{wei / (10 ** STRK_DECIMALS):.6f}"
        
        is_receive = False
        to_addr = tx.get("to_address", "")
        if account_addr and to_addr:
            norm_to = _tx_svc._normalize_starknet_address(to_addr).lower()
            norm_acc = _tx_svc._normalize_starknet_address(account_addr).lower()
            if norm_to and norm_acc and norm_to == norm_acc:
                is_receive = True
            elif to_addr.lower() == account_addr.lower():
                is_receive = True
        tx["type"] = "receive" if is_receive else "send"

    return {"total": total, "limit": limit, "offset": offset, "transactions": txs}


# ── Merkle Batches ────────────────────────────────────────

@router.get("/batches")
async def list_batches(
    authorization: str = Header(...),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List all Merkle batches for this organization."""
    org_id = await _get_org_id(authorization)
    async with get_db() as conn:
        batches = await _merkle_svc.list_batches(conn, org_id, limit, offset)
    return {"batches": batches}


@router.get("/batches/{batch_id}")
async def get_batch_detail(batch_id: str, authorization: str = Header(...)):
    """Get Merkle batch with all leaves."""
    await _get_org_id(authorization)
    async with get_db() as conn:
        batch = await _merkle_svc.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, "Batch not found")
        leaves = await _merkle_svc.get_batch_leaves(conn, batch_id)
    batch_dict = dict(batch)
    for leaf in leaves:
        if isinstance(leaf.get("proof_path"), str):
            try:
                leaf["proof_path"] = json.loads(leaf["proof_path"])
            except (json.JSONDecodeError, TypeError):
                pass
    return {**batch_dict, "leaves": leaves}


@router.get("/proof/{tx_id}")
async def get_merkle_proof(tx_id: str, authorization: str = Header(...)):
    """Get the Merkle proof for a specific transaction."""
    await _get_org_id(authorization)
    async with get_db() as conn:
        proof = await _merkle_svc.get_proof_for_tx(conn, tx_id)
    if not proof:
        raise HTTPException(404, "No Merkle proof found for this transaction")

    if isinstance(proof.get("proof_path"), str):
        try:
            proof["proof_path"] = json.loads(proof["proof_path"])
        except (json.JSONDecodeError, TypeError):
            pass

    return proof


@router.post("/batches/force-finalize")
async def force_finalize_batch(authorization: str = Header(...)):
    """Force-finalize the current pending batch."""
    org_id = await _get_org_id(authorization)
    async with get_db() as conn:
        batch_id = await _merkle_svc.force_finalize(conn, org_id)
    if not batch_id:
        return {"status": "no_pending_transactions"}
    return {"status": "finalized", "batch_id": batch_id}


# ── Audit Log ─────────────────────────────────────────────

@router.get("/audit/verify-chain")
async def verify_audit_chain(authorization: str = Header(...)):
    """Verify the integrity of the full audit chain."""
    org_id = await _get_org_id(authorization)
    async with get_db() as conn:
        result = await _audit_svc.verify_chain_integrity(conn, org_id)
    return result


@router.get("/audit/{user_id}")
async def get_user_audit_log(
    user_id: str,
    authorization: str = Header(...),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Get immutable audit trail for a user."""
    org_id = await _get_org_id(authorization)
    async with get_db() as conn:
        logs = await _audit_svc.get_log(conn, org_id, user_id=user_id, limit=limit, offset=offset)
    return {"user_id": user_id, "audit_logs": logs}


# ── Health ────────────────────────────────────────────────

@router.get("/health", response_model=HealthOut)
async def health():
    """Service health check."""
    db_status = "disconnected"
    starknet_rpc = os.environ.get("STARKNET_RPC", "unset")
    prover_status = "not_configured"
    prover_ready = False
    prover_mode = "python_fallback"
    prover_backend = "python_fallback"
    prover_binary = "python_internal"
    prover_endpoint = None
    try:
        async with get_db() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception:
        pass

    prover_url = _resolve_prover_endpoint()
    if prover_url:
        prover_endpoint = prover_url
        prover_binary = prover_url
        import httpx

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{prover_url.rstrip('/')}/health")
            if res.status_code == 200:
                prover_status = "connected"
                prover_ready = True
                prover_mode = "rust_http"
                prover_backend = "rust_http"
            else:
                prover_status = "degraded"
                prover_mode = "fallback"
        except Exception:
            prover_status = "disconnected"
            prover_mode = "fallback"
    else:
        prover_status = "not_configured"

    return HealthOut(
        status="ok" if db_status == "connected" else "degraded",
        database=db_status,
        starknet_rpc=starknet_rpc,
        prover=prover_status,
        prover_ready=prover_ready,
        prover_mode=prover_mode,
        prover_backend=prover_backend,
        prover_binary=prover_binary,
        prover_endpoint=prover_endpoint,
    )
