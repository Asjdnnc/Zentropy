"""
QuantumGuard v2 — Pydantic Schemas
====================================
Request/response models for the API layer and inter-service communication.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, EmailStr

from .enums import (
    KYCStatus, WalletStatus, DeploymentStatus, TransactionStatus,
    KeyStatus, AuditAction, AuditEntityType, PQ_ALGORITHM,
)


# ──────────────────────────────────────────────
#  Organization
# ──────────────────────────────────────────────

class OrganizationCreate(BaseModel):
    org_name: str = Field(..., min_length=1, max_length=255)
    admin_email: EmailStr


class OrganizationOut(BaseModel):
    org_id: str
    org_name: str
    admin_email: EmailStr
    api_key: str
    created_at: datetime


# ──────────────────────────────────────────────
#  User
# ──────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: Optional[str] = Field(None, max_length=127)


class UserOut(BaseModel):
    user_id: str
    org_id: str
    email: str
    username: Optional[str] = None
    kyc_status: KYCStatus = KYCStatus.PENDING
    is_active: bool = True
    created_at: datetime


# ──────────────────────────────────────────────
#  Wallet
# ──────────────────────────────────────────────

class WalletCreate(BaseModel):
    wallet_name: str = Field("Default Wallet", max_length=255)


class SenderProfileUpdate(BaseModel):
    sender_model: str = Field("relayer", min_length=3, max_length=32)
    submitter_address: Optional[str] = Field(None, min_length=3, max_length=255)
    submitter_account_config: Optional[str] = Field(None, min_length=3, max_length=1024)
    submitter_private_key: Optional[str] = Field(None, min_length=3, max_length=255)


class SetMpinRequest(BaseModel):
    mpin: str = Field(..., min_length=4, max_length=6, pattern="^[0-9]+$")


class VerifyMpinRequest(BaseModel):
    mpin: str = Field(..., min_length=4, max_length=6, pattern="^[0-9]+$")


class WalletOut(BaseModel):
    wallet_id: str
    user_id: str
    wallet_name: str
    status: WalletStatus = WalletStatus.ACTIVE
    pq_algorithm: str = PQ_ALGORITHM
    has_mpin: bool = False
    created_at: datetime
    last_activity: Optional[datetime] = None


class WalletRegistrationOut(BaseModel):
    """Returned only at account creation — includes seed phrase."""
    user_id: str
    wallet_id: str
    contract_address: str
    sender_model: str = "relayer"
    submitter_address: Optional[str] = None
    public_key: str
    public_key_hash: str
    seed_phrase: str  # shown once
    deployment_status: str = DeploymentStatus.COUNTERFACTUAL.value
    deployment_tx_hash: Optional[str] = None
    deployment_error_message: Optional[str] = None
    status: str = "created"
    message: str = "SAVE YOUR SEED PHRASE — it will not be shown again"


# ──────────────────────────────────────────────
#  Account (Blockchain)
# ──────────────────────────────────────────────

class AccountOut(BaseModel):
    account_id: str
    wallet_id: str
    blockchain: str = "STARKNET"
    account_address: str
    sender_model: str = "relayer"
    submitter_address: Optional[str] = None
    public_key_pq_hash: str
    deployment_status: DeploymentStatus = DeploymentStatus.COUNTERFACTUAL
    nonce: int = 0
    balance_strk: str = "0.000000"
    created_at: datetime


# ──────────────────────────────────────────────
#  Transaction
# ──────────────────────────────────────────────

class TransferRequest(BaseModel):
    to_address: str = Field(..., min_length=3, max_length=255)
    amount_strk: float = Field(..., gt=0)
    mpin: str = Field(..., min_length=4, max_length=6, pattern="^[0-9]+$")


class TransactionOut(BaseModel):
    tx_id: str
    account_id: str
    to_address: str
    amount_strk: str
    status: TransactionStatus
    sender_account_address: Optional[str] = None
    submitted_by_address: Optional[str] = None
    submission_mode: Optional[str] = None
    prover_backend: Optional[str] = None
    proof_commitment: Optional[str] = None
    tx_hash: Optional[str] = None
    created_at: datetime
    confirmed_at: Optional[datetime] = None


class TransactionDetailOut(TransactionOut):
    message_hash: Optional[str] = None
    signature_size: Optional[int] = None
    nonce: int = 0
    proof_valid: Optional[bool] = None
    prover_fallback_reason: Optional[str] = None
    starknet_status: Optional[str] = None
    error_message: Optional[str] = None
    explorer_url: Optional[str] = None


class TransferResultOut(BaseModel):
    tx_id: str
    starknet_tx_hash: Optional[str] = None
    status: str
    proof_valid: bool = False
    prover_backend: Optional[str] = None
    proof_commitment: Optional[str] = None
    batch_id: Optional[str] = None
    merkle_root_committed: Optional[str] = None
    sender_account_address: Optional[str] = None
    submitted_by_address: Optional[str] = None
    submission_mode: Optional[str] = None
    amount_strk: str = "0.000000"
    explorer_url: Optional[str] = None
    error: Optional[str] = None


# ──────────────────────────────────────────────
#  Merkle Batch
# ──────────────────────────────────────────────

class MerkleBatchOut(BaseModel):
    batch_id: str
    batch_number: int
    transaction_count: int
    merkle_root: str
    starknet_tx_hash: Optional[str] = None
    starknet_confirmed: bool = False
    created_at: datetime
    committed_at: Optional[datetime] = None


class MerkleLeafOut(BaseModel):
    tx_id: str
    leaf_index: int
    leaf_hash: str
    proof_path: Any  # JSON list of {hash, position}


class MerkleBatchDetailOut(MerkleBatchOut):
    leaves: list[MerkleLeafOut] = []


class MerkleProofOut(BaseModel):
    tx_id: str
    batch_id: str
    merkle_root: str
    leaf_hash: str
    leaf_index: int
    proof_path: Any
    starknet_confirmed: bool = False
    starknet_tx_hash: Optional[str] = None


# ──────────────────────────────────────────────
#  Audit Log
# ──────────────────────────────────────────────

class AuditLogOut(BaseModel):
    log_id: int
    org_id: str
    user_id: Optional[str] = None
    entity_type: str
    entity_id: str
    action: str
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    log_hash: Optional[str] = None
    previous_log_hash: Optional[str] = None
    created_at: datetime


# ──────────────────────────────────────────────
#  Health / Misc
# ──────────────────────────────────────────────

class HealthOut(BaseModel):
    status: str = "ok"
    service: str = "quantum-guard-custodial"
    version: str = "2.0.0"
    database: str = "connected"
    starknet_rpc: str = "connected"
    prover: str = "unknown"
    prover_ready: bool = False
    prover_mode: str = "python_fallback"
    prover_backend: str = "python_fallback"
    prover_binary: str = "python_internal"
    prover_endpoint: Optional[str] = None


class PaginatedResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Any]
