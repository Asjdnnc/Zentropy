"""
QuantumGuard v2 — Database Migrations
=======================================
Creates all tables for the multi-user custodial wallet system.

Supports both PostgreSQL and SQLite (for local dev).
Run once at startup via `await run_migrations()`.
"""

from __future__ import annotations

import logging

from .connection import get_db

logger = logging.getLogger("quantumguard.db.migrations")


# ──────────────────────────────────────────────
#  DDL — Compatible with both Postgres and SQLite
# ──────────────────────────────────────────────

_SCHEMA_SQL = """
-- 1. ORGANIZATIONS
CREATE TABLE IF NOT EXISTS organizations (
    org_id          TEXT PRIMARY KEY,
    org_name        TEXT NOT NULL,
    api_key         TEXT NOT NULL UNIQUE,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

-- 2. USERS
CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL REFERENCES organizations(org_id),
    email           TEXT NOT NULL,
    username        TEXT,
    kyc_status      TEXT NOT NULL DEFAULT 'pending',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    UNIQUE(org_id, email)
);
CREATE INDEX IF NOT EXISTS idx_user_org ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_user_email ON users(email);

-- 3. WALLETS (one per user)
CREATE TABLE IF NOT EXISTS wallets (
    wallet_id               TEXT PRIMARY KEY,
    user_id                 TEXT NOT NULL UNIQUE REFERENCES users(user_id),
    wallet_name             TEXT NOT NULL DEFAULT 'Default Wallet',
    seed_phrase_encrypted   TEXT NOT NULL,
    seed_phrase_hash        TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'active',
    pq_algorithm            TEXT NOT NULL DEFAULT 'ML-DSA-44',
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    last_activity           REAL
);
CREATE INDEX IF NOT EXISTS idx_wallet_user ON wallets(user_id);
CREATE INDEX IF NOT EXISTS idx_wallet_status ON wallets(status);

-- 4. ACCOUNTS (per-user Starknet contract)
CREATE TABLE IF NOT EXISTS accounts (
    account_id          TEXT PRIMARY KEY,
    wallet_id           TEXT NOT NULL REFERENCES wallets(wallet_id),
    blockchain          TEXT NOT NULL DEFAULT 'STARKNET',
    account_address     TEXT NOT NULL,
    public_key_pq       TEXT NOT NULL,
    public_key_pq_hash  TEXT NOT NULL,
    contract_class_hash TEXT,
    deployment_status   TEXT NOT NULL DEFAULT 'counterfactual',
    deployment_tx_hash  TEXT,
    deployed_at         REAL,
    nonce               INTEGER NOT NULL DEFAULT 0,
    balance_wei         TEXT NOT NULL DEFAULT '0',
    balance_updated_at  REAL,
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL,
    UNIQUE(account_address, blockchain)
);
CREATE INDEX IF NOT EXISTS idx_account_wallet ON accounts(wallet_id);
CREATE INDEX IF NOT EXISTS idx_account_address ON accounts(account_address);

-- 5. ENCRYPTED KEYS
CREATE TABLE IF NOT EXISTS encrypted_keys (
    key_id                  TEXT PRIMARY KEY,
    wallet_id               TEXT NOT NULL REFERENCES wallets(wallet_id),
    key_type                TEXT NOT NULL DEFAULT 'signing_key',
    algorithm               TEXT NOT NULL DEFAULT 'ML-DSA-44',
    encrypted_key_material  TEXT NOT NULL,
    key_material_hash       TEXT NOT NULL,
    status                  TEXT NOT NULL DEFAULT 'active',
    created_at              REAL NOT NULL,
    rotated_at              REAL
);
CREATE INDEX IF NOT EXISTS idx_key_wallet ON encrypted_keys(wallet_id);
CREATE INDEX IF NOT EXISTS idx_key_status ON encrypted_keys(status);

-- 6. KEY RECOVERY SHARES (Shamir Secret Sharing)
CREATE TABLE IF NOT EXISTS key_recovery_shares (
    share_id        TEXT PRIMARY KEY,
    wallet_id       TEXT NOT NULL REFERENCES wallets(wallet_id),
    share_index     INTEGER NOT NULL,
    encrypted_share TEXT NOT NULL,
    threshold       INTEGER NOT NULL DEFAULT 3,
    custodian_name  TEXT,
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_share_wallet ON key_recovery_shares(wallet_id);

-- 7. TRANSACTIONS
CREATE TABLE IF NOT EXISTS transactions (
    tx_id               TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(account_id),
    to_address          TEXT NOT NULL,
    amount_wei          TEXT NOT NULL,
    token_address       TEXT NOT NULL DEFAULT 'STARKNET_NATIVE',
    message_hash        TEXT,
    signature_size      INTEGER,
    nonce               INTEGER NOT NULL,
    proof_commitment    TEXT,
    proof_valid         INTEGER,
    tx_hash             TEXT,
    status              TEXT NOT NULL DEFAULT 'signed',
    starknet_status     TEXT,
    error_message       TEXT,
    created_at          REAL NOT NULL,
    confirmed_at        REAL
);
CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_tx_nonce ON transactions(account_id, nonce);
CREATE INDEX IF NOT EXISTS idx_tx_hash ON transactions(tx_hash);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created_at);

-- 8. MERKLE BATCHES
CREATE TABLE IF NOT EXISTS merkle_batches (
    batch_id            TEXT PRIMARY KEY,
    org_id              TEXT NOT NULL REFERENCES organizations(org_id),
    batch_number        INTEGER NOT NULL UNIQUE,
    transaction_count   INTEGER NOT NULL,
    merkle_root         TEXT NOT NULL,
    starknet_tx_hash    TEXT,
    starknet_confirmed  INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL,
    committed_at        REAL
);
CREATE INDEX IF NOT EXISTS idx_batch_root ON merkle_batches(merkle_root);
CREATE INDEX IF NOT EXISTS idx_batch_org ON merkle_batches(org_id);
CREATE INDEX IF NOT EXISTS idx_batch_created ON merkle_batches(created_at);

-- 9. MERKLE LEAVES (individual tx proofs)
CREATE TABLE IF NOT EXISTS merkle_leaves (
    leaf_id         TEXT PRIMARY KEY,
    batch_id        TEXT NOT NULL REFERENCES merkle_batches(batch_id),
    tx_id           TEXT NOT NULL REFERENCES transactions(tx_id),
    leaf_index      INTEGER NOT NULL,
    leaf_hash       TEXT NOT NULL,
    proof_path      TEXT NOT NULL DEFAULT '[]',
    created_at      REAL NOT NULL,
    UNIQUE(batch_id, tx_id)
);
CREATE INDEX IF NOT EXISTS idx_leaf_tx ON merkle_leaves(tx_id);
CREATE INDEX IF NOT EXISTS idx_leaf_batch ON merkle_leaves(batch_id);

-- 10. AUDIT LOG (immutable chain)
CREATE TABLE IF NOT EXISTS audit_log (
    log_id              INTEGER PRIMARY KEY,
    org_id              TEXT NOT NULL REFERENCES organizations(org_id),
    user_id             TEXT REFERENCES users(user_id),
    entity_type         TEXT NOT NULL,
    entity_id           TEXT NOT NULL,
    action              TEXT NOT NULL,
    details             TEXT,
    ip_address          TEXT,
    user_agent          TEXT,
    previous_log_hash   TEXT,
    log_hash            TEXT,
    merkle_batch_id     TEXT REFERENCES merkle_batches(batch_id),
    created_at          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_org ON audit_log(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);

-- 11. BALANCE CACHE
CREATE TABLE IF NOT EXISTS balance_cache (
    contract_address    TEXT NOT NULL,
    token_address       TEXT NOT NULL DEFAULT 'native',
    balance_wei         TEXT NOT NULL DEFAULT '0',
    updated_at          REAL NOT NULL,
    UNIQUE(contract_address, token_address)
);
CREATE INDEX IF NOT EXISTS idx_balance_addr ON balance_cache(contract_address);
"""


async def run_migrations():
    """Execute schema DDL. Safe to run repeatedly (IF NOT EXISTS)."""
    logger.info("Running database migrations …")

    async with get_db() as conn:
        # Split by statement and execute individually for SQLite compat
        stmts = [s.strip() for s in _SCHEMA_SQL.split(";") if s.strip()]
        for stmt in stmts:
            try:
                await conn.execute(stmt)
            except Exception as e:
                # Skip "already exists" errors gracefully
                err_str = str(e).lower()
                if "already exists" in err_str or "duplicate" in err_str:
                    continue
                logger.error("Migration statement failed: %s\n  Error: %s", stmt[:80], e)
                raise

    logger.info("Database migrations complete — all tables ready")
