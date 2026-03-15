"""
QuantumGuard Persistence Layer
==============================
SQLite-backed storage for transaction history, proof cache, and audit trail.

Tables:
  transactions  — signed + proved transactions with status
  proofs        — cached proof commitments
  deployments   — contract deployment records

Usage:
    from pqc_backend.persistence import TransactionStore
    store = TransactionStore()
    store.record_transaction(...)
"""
import json
import sqlite3
import time
import threading
from pathlib import Path
from typing import Optional

from .config import DB_PATH


class TransactionStore:
    """Thread-safe SQLite store for transaction history and proof cache."""

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path or DB_PATH).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self):
        """Create tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id       TEXT UNIQUE NOT NULL,
                wallet_label TEXT NOT NULL,
                to_addr     TEXT NOT NULL,
                amount      REAL NOT NULL,
                nonce       INTEGER NOT NULL DEFAULT 0,
                data        TEXT DEFAULT '',
                message_hash TEXT,
                pubkey_hash  TEXT,
                signature_size INTEGER,
                proof_commitment TEXT,
                proof_valid   INTEGER DEFAULT 0,
                starknet_tx_hash TEXT,
                starknet_status  TEXT DEFAULT 'pending',
                contract_address TEXT,
                status       TEXT DEFAULT 'signed',
                error        TEXT,
                created_at   REAL NOT NULL,
                updated_at   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS proofs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                proof_commitment TEXT UNIQUE NOT NULL,
                message_hash     TEXT NOT NULL,
                signature_hash   TEXT,
                pubkey_hash      TEXT NOT NULL,
                valid            INTEGER NOT NULL DEFAULT 0,
                signature_size   INTEGER,
                prover           TEXT DEFAULT 'unknown',
                created_at       REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deployments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_address TEXT UNIQUE NOT NULL,
                class_hash       TEXT,
                network          TEXT DEFAULT 'starknet-sepolia',
                owner_pubkey_hash TEXT NOT NULL,
                owner_label      TEXT,
                rpc              TEXT,
                deployed_at      TEXT,
                created_at       REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wallets (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                label            TEXT UNIQUE NOT NULL,
                pubkey_hash      TEXT NOT NULL,
                contract_address TEXT,
                class_hash       TEXT,
                deployment_status TEXT DEFAULT 'pending',
                network          TEXT DEFAULT 'starknet-sepolia',
                deployed_at      REAL,
                created_at       REAL NOT NULL,
                updated_at       REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS balance_cache (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_address TEXT NOT NULL,
                token_address    TEXT NOT NULL DEFAULT 'native',
                balance_wei      TEXT NOT NULL DEFAULT '0',
                updated_at       REAL NOT NULL,
                UNIQUE(contract_address, token_address)
            );

            CREATE INDEX IF NOT EXISTS idx_tx_wallet
                ON transactions(wallet_label);
            CREATE INDEX IF NOT EXISTS idx_tx_status
                ON transactions(status);
            CREATE INDEX IF NOT EXISTS idx_tx_starknet
                ON transactions(starknet_tx_hash);
            CREATE INDEX IF NOT EXISTS idx_proof_commitment
                ON proofs(proof_commitment);
            CREATE INDEX IF NOT EXISTS idx_wallet_label
                ON wallets(label);
            CREATE INDEX IF NOT EXISTS idx_wallet_contract
                ON wallets(contract_address);
            CREATE INDEX IF NOT EXISTS idx_balance_contract
                ON balance_cache(contract_address);

            -- ──────────────────────────────────────────────────
            -- Merkle Audit Trail (immutable batch anchoring)
            -- ──────────────────────────────────────────────────

            CREATE TABLE IF NOT EXISTS merkle_batches (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id        TEXT UNIQUE NOT NULL,
                merkle_root     TEXT NOT NULL,
                tx_count        INTEGER NOT NULL DEFAULT 0,
                committed       INTEGER NOT NULL DEFAULT 0,
                starknet_tx_hash TEXT DEFAULT '',
                committed_at    REAL,
                created_at      REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS merkle_leaves (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id        TEXT NOT NULL,
                tx_index        INTEGER NOT NULL,
                tx_id           TEXT NOT NULL,
                tx_hash         TEXT NOT NULL,
                merkle_proof    TEXT DEFAULT '[]',
                created_at      REAL NOT NULL,
                FOREIGN KEY (batch_id) REFERENCES merkle_batches(batch_id),
                UNIQUE(batch_id, tx_index)
            );

            CREATE INDEX IF NOT EXISTS idx_merkle_batch_root
                ON merkle_batches(merkle_root);
            CREATE INDEX IF NOT EXISTS idx_merkle_batch_committed
                ON merkle_batches(committed);
            CREATE INDEX IF NOT EXISTS idx_merkle_leaf_batch
                ON merkle_leaves(batch_id);
            CREATE INDEX IF NOT EXISTS idx_merkle_leaf_tx
                ON merkle_leaves(tx_id);
        """)
        self._conn.commit()

    # ─── Transactions ────────────────────────────────────────────

    def record_transaction(
        self,
        tx_id: str,
        wallet_label: str,
        to_addr: str,
        amount: float,
        nonce: int = 0,
        data: str = "",
        message_hash: str = "",
        pubkey_hash: str = "",
        signature_size: int = 0,
        status: str = "signed",
    ) -> dict:
        """Record a new signed transaction."""
        now = time.time()
        self._conn.execute(
            """INSERT OR REPLACE INTO transactions
               (tx_id, wallet_label, to_addr, amount, nonce, data,
                message_hash, pubkey_hash, signature_size, status,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tx_id, wallet_label, to_addr, amount, nonce, data,
             message_hash, pubkey_hash, signature_size, status,
             now, now),
        )
        self._conn.commit()
        return {"tx_id": tx_id, "status": status}

    def update_transaction_proof(
        self,
        tx_id: str,
        proof_commitment: str,
        proof_valid: bool,
    ):
        """Update a transaction with proof results."""
        now = time.time()
        self._conn.execute(
            """UPDATE transactions
               SET proof_commitment = ?, proof_valid = ?, status = ?, updated_at = ?
               WHERE tx_id = ?""",
            (proof_commitment, int(proof_valid),
             "proved" if proof_valid else "proof_failed", now, tx_id),
        )
        self._conn.commit()

    def update_transaction_starknet(
        self,
        tx_id: str,
        starknet_tx_hash: str,
        starknet_status: str = "submitted",
        error: Optional[str] = None,
    ):
        """Update a transaction with Starknet submission result."""
        now = time.time()
        new_status = "submitted" if starknet_status == "submitted" else "submission_failed"
        self._conn.execute(
            """UPDATE transactions
               SET starknet_tx_hash = ?, starknet_status = ?,
                   status = ?, error = ?, updated_at = ?
               WHERE tx_id = ?""",
            (starknet_tx_hash, starknet_status, new_status, error, now, tx_id),
        )
        self._conn.commit()

    def update_transaction_status(self, tx_id: str, status: str, error: Optional[str] = None):
        """Generic status update."""
        now = time.time()
        self._conn.execute(
            "UPDATE transactions SET status = ?, error = ?, updated_at = ? WHERE tx_id = ?",
            (status, error, now, tx_id),
        )
        self._conn.commit()

    def get_transaction(self, tx_id: str) -> Optional[dict]:
        """Get a single transaction by ID."""
        row = self._conn.execute(
            "SELECT * FROM transactions WHERE tx_id = ?", (tx_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_transaction_by_starknet_hash(self, starknet_tx_hash: str) -> Optional[dict]:
        """Get a transaction by its Starknet tx hash."""
        row = self._conn.execute(
            "SELECT * FROM transactions WHERE starknet_tx_hash = ?",
            (starknet_tx_hash,),
        ).fetchone()
        return dict(row) if row else None

    def list_transactions(
        self,
        wallet_label: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List transactions with optional filters."""
        query = "SELECT * FROM transactions WHERE 1=1"
        params: list = []
        if wallet_label:
            query += " AND wallet_label = ?"
            params.append(wallet_label)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def count_transactions(self, wallet_label: Optional[str] = None) -> int:
        """Count transactions."""
        if wallet_label:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE wallet_label = ?",
                (wallet_label,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
        return row[0] if row else 0

    # ─── Proofs ──────────────────────────────────────────────────

    def cache_proof(
        self,
        proof_commitment: str,
        message_hash: str,
        pubkey_hash: str,
        valid: bool,
        signature_hash: str = "",
        signature_size: int = 0,
        prover: str = "unknown",
    ):
        """Cache a proof commitment for audit/reuse."""
        now = time.time()
        self._conn.execute(
            """INSERT OR IGNORE INTO proofs
               (proof_commitment, message_hash, signature_hash, pubkey_hash,
                valid, signature_size, prover, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (proof_commitment, message_hash, signature_hash, pubkey_hash,
             int(valid), signature_size, prover, now),
        )
        self._conn.commit()

    def get_cached_proof(self, proof_commitment: str) -> Optional[dict]:
        """Check if a proof commitment is already cached."""
        row = self._conn.execute(
            "SELECT * FROM proofs WHERE proof_commitment = ?",
            (proof_commitment,),
        ).fetchone()
        return dict(row) if row else None

    def list_proofs(self, limit: int = 50) -> list[dict]:
        """List recent proofs."""
        rows = self._conn.execute(
            "SELECT * FROM proofs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Deployments ─────────────────────────────────────────────

    def record_deployment(
        self,
        contract_address: str,
        class_hash: str,
        owner_pubkey_hash: str,
        owner_label: str = "default",
        network: str = "starknet-sepolia",
        rpc: str = "",
        deployed_at: str = "",
    ):
        """Record a contract deployment."""
        now = time.time()
        self._conn.execute(
            """INSERT OR REPLACE INTO deployments
               (contract_address, class_hash, network, owner_pubkey_hash,
                owner_label, rpc, deployed_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (contract_address, class_hash, network, owner_pubkey_hash,
             owner_label, rpc, deployed_at, now),
        )
        self._conn.commit()

    def get_deployment(self, contract_address: str) -> Optional[dict]:
        """Get deployment info by contract address."""
        row = self._conn.execute(
            "SELECT * FROM deployments WHERE contract_address = ?",
            (contract_address,),
        ).fetchone()
        return dict(row) if row else None

    def list_deployments(self) -> list[dict]:
        """List all recorded deployments."""
        rows = self._conn.execute(
            "SELECT * FROM deployments ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Cleanup ─────────────────────────────────────────────────

    def close(self):
        """Close the thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    # ─── Wallets ─────────────────────────────────────────────────

    def record_wallet(
        self,
        label: str,
        pubkey_hash: str,
        contract_address: Optional[str] = None,
        class_hash: Optional[str] = None,
        deployment_status: str = "pending",
        network: str = "starknet-sepolia",
    ) -> dict:
        """Record a new wallet with its deployment status."""
        now = time.time()
        self._conn.execute(
            """INSERT OR REPLACE INTO wallets
               (label, pubkey_hash, contract_address, class_hash,
                deployment_status, network, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (label, pubkey_hash, contract_address, class_hash,
             deployment_status, network, now, now),
        )
        self._conn.commit()
        return {"label": label, "pubkey_hash": pubkey_hash, "deployment_status": deployment_status}

    def update_wallet_deployment(
        self,
        label: str,
        contract_address: str,
        class_hash: str = "",
        deployment_status: str = "deployed",
    ):
        """Update a wallet with its deployment result."""
        now = time.time()
        self._conn.execute(
            """UPDATE wallets
               SET contract_address = ?, class_hash = ?,
                   deployment_status = ?, deployed_at = ?, updated_at = ?
               WHERE label = ?""",
            (contract_address, class_hash, deployment_status, now, now, label),
        )
        self._conn.commit()

    def update_wallet_status(self, label: str, deployment_status: str, error: Optional[str] = None):
        """Update wallet deployment status."""
        now = time.time()
        self._conn.execute(
            "UPDATE wallets SET deployment_status = ?, updated_at = ? WHERE label = ?",
            (deployment_status, now, label),
        )
        self._conn.commit()

    def get_wallet(self, label: str) -> Optional[dict]:
        """Get wallet info by label."""
        row = self._conn.execute(
            "SELECT * FROM wallets WHERE label = ?", (label,)
        ).fetchone()
        return dict(row) if row else None

    def get_wallet_by_contract(self, contract_address: str) -> Optional[dict]:
        """Get wallet info by contract address."""
        row = self._conn.execute(
            "SELECT * FROM wallets WHERE contract_address = ?",
            (contract_address,),
        ).fetchone()
        return dict(row) if row else None

    def list_all_wallets(self) -> list[dict]:
        """List all wallets with deployment info."""
        rows = self._conn.execute(
            "SELECT * FROM wallets ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Balance Cache ───────────────────────────────────────────

    def cache_balance(
        self,
        contract_address: str,
        balance_wei: str,
        token_address: str = "native",
    ):
        """Cache a balance value."""
        now = time.time()
        self._conn.execute(
            """INSERT OR REPLACE INTO balance_cache
               (contract_address, token_address, balance_wei, updated_at)
               VALUES (?, ?, ?, ?)""",
            (contract_address, token_address, balance_wei, now),
        )
        self._conn.commit()

    def get_cached_balance(
        self,
        contract_address: str,
        token_address: str = "native",
        ttl: float = 30.0,
    ) -> Optional[str]:
        """Get cached balance if still valid (within TTL)."""
        now = time.time()
        row = self._conn.execute(
            """SELECT balance_wei, updated_at FROM balance_cache
               WHERE contract_address = ? AND token_address = ?""",
            (contract_address, token_address),
        ).fetchone()
        if row and (now - row["updated_at"]) < ttl:
            return row["balance_wei"]
        return None

    # ─── Merkle Audit Trail ──────────────────────────────────────

    def record_merkle_batch(
        self,
        batch_id: str,
        merkle_root: str,
        tx_count: int,
    ) -> dict:
        """Record a finalized Merkle batch."""
        now = time.time()
        self._conn.execute(
            """INSERT OR REPLACE INTO merkle_batches
               (batch_id, merkle_root, tx_count, committed, created_at)
               VALUES (?, ?, ?, 0, ?)""",
            (batch_id, merkle_root, tx_count, now),
        )
        self._conn.commit()
        return {"batch_id": batch_id, "merkle_root": merkle_root}

    def record_merkle_leaf(
        self,
        batch_id: str,
        tx_index: int,
        tx_id: str,
        tx_hash: str,
        merkle_proof: str = "[]",
    ):
        """Record a leaf (transaction) in a Merkle batch."""
        now = time.time()
        self._conn.execute(
            """INSERT OR REPLACE INTO merkle_leaves
               (batch_id, tx_index, tx_id, tx_hash, merkle_proof, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (batch_id, tx_index, tx_id, tx_hash, merkle_proof, now),
        )
        self._conn.commit()

    def mark_batch_committed(
        self,
        batch_id: str,
        starknet_tx_hash: str,
    ):
        """Mark a Merkle batch as committed to Starknet."""
        now = time.time()
        self._conn.execute(
            """UPDATE merkle_batches
               SET committed = 1, starknet_tx_hash = ?, committed_at = ?
               WHERE batch_id = ?""",
            (starknet_tx_hash, now, batch_id),
        )
        self._conn.commit()

    def get_merkle_batch(self, batch_id: str) -> Optional[dict]:
        """Get a Merkle batch by ID."""
        row = self._conn.execute(
            "SELECT * FROM merkle_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_merkle_batch_by_root(self, merkle_root: str) -> Optional[dict]:
        """Get a Merkle batch by its root hash."""
        row = self._conn.execute(
            "SELECT * FROM merkle_batches WHERE merkle_root = ?", (merkle_root,)
        ).fetchone()
        return dict(row) if row else None

    def list_merkle_batches(self, limit: int = 50, committed_only: bool = False) -> list[dict]:
        """List Merkle batches."""
        query = "SELECT * FROM merkle_batches"
        params: list = []
        if committed_only:
            query += " WHERE committed = 1"
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_merkle_proof_for_tx(self, tx_id: str) -> Optional[dict]:
        """Get the Merkle proof for a specific transaction."""
        row = self._conn.execute(
            """SELECT ml.*, mb.merkle_root, mb.committed, mb.starknet_tx_hash
               FROM merkle_leaves ml
               JOIN merkle_batches mb ON ml.batch_id = mb.batch_id
               WHERE ml.tx_id = ?""",
            (tx_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_leaves_for_batch(self, batch_id: str) -> list[dict]:
        """Get all leaves (transactions) in a Merkle batch."""
        rows = self._conn.execute(
            """SELECT * FROM merkle_leaves
               WHERE batch_id = ?
               ORDER BY tx_index""",
            (batch_id,),
        ).fetchall()
        return [dict(r) for r in rows]
