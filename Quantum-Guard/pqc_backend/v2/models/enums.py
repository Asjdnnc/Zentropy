"""
QuantumGuard v2 — Enums & Constants
====================================
Centralised status values and constants used across the full system.
"""

from enum import Enum


class KYCStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class WalletStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPROMISED = "compromised"


class DeploymentStatus(str, Enum):
    COUNTERFACTUAL = "counterfactual"
    PENDING = "pending"
    DEPLOYED = "deployed"
    FAILED = "failed"


class TransactionStatus(str, Enum):
    SIGNED = "signed"
    PROVED = "proved"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class KeyStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"
    COMPROMISED = "compromised"


class AuditAction(str, Enum):
    USER_CREATED = "user_created"
    WALLET_CREATED = "wallet_created"
    ACCOUNT_DEPLOYED = "account_deployed"
    TRANSACTION_SIGNED = "transaction_signed"
    TRANSACTION_PROVED = "transaction_proved"
    TRANSACTION_SUBMITTED = "transaction_submitted"
    TRANSACTION_CONFIRMED = "transaction_confirmed"
    KEY_ROTATED = "key_rotated"
    KEY_COMPROMISED = "key_compromised"
    BATCH_COMMITTED = "batch_committed"
    PROVER_ADDED = "prover_added"
    PROVER_REMOVED = "prover_removed"


class AuditEntityType(str, Enum):
    USER = "user"
    WALLET = "wallet"
    ACCOUNT = "account"
    TRANSACTION = "transaction"
    BATCH = "batch"
    KEY = "key"


# Algorithm defaults
PQ_ALGORITHM = "ML-DSA-44"
PQ_PUBLIC_KEY_SIZE = 1312
PQ_SECRET_KEY_SIZE = 2560
PQ_SIGNATURE_SIZE = 2420
STRK_DECIMALS = 18
