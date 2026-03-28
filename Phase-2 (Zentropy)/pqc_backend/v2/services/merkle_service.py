"""
QuantumGuard v2 — Merkle Service
==================================
Manages per-organization Merkle batch trees.

Flow:
  1. Transactions are added to the "current batch" via add_transaction_to_batch()
  2. When batch reaches threshold (count or time), finalize_batch() is called
  3. Finalization: build tree, compute root + proof paths, persist to DB + disk
  4. Root is committed to Starknet via external commit call
  5. Each transaction gets an individual Merkle proof

Reuses the existing SHA-256 Merkle primitives from pqc_backend.merkle_audit
but adds multi-user, database-backed persistence.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import threading
import uuid
from pathlib import Path
from typing import Optional

from ..models.enums import AuditAction, AuditEntityType
from .audit_service import AuditService

logger = logging.getLogger("quantumguard.merkle_service")

# ── Merkle Primitives (reused from v1, pure functions) ────


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _hash_pair(left: bytes, right: bytes) -> bytes:
    return _sha256(left + right)


def _build_tree(leaves: list[bytes]) -> list[list[bytes]]:
    """Build full Merkle tree from leaf hashes. Returns list of levels."""
    if not leaves:
        return [[_sha256(b"empty")]]

    current = list(leaves)
    if len(current) % 2 == 1:
        current.append(current[-1])

    levels = [current]
    while len(current) > 1:
        nxt = []
        for i in range(0, len(current), 2):
            l = current[i]
            r = current[i + 1] if i + 1 < len(current) else l
            nxt.append(_hash_pair(l, r))
        if len(nxt) > 1 and len(nxt) % 2 == 1:
            nxt.append(nxt[-1])
        levels.append(nxt)
        current = nxt
    return levels


def _get_proof(levels: list[list[bytes]], leaf_index: int) -> list[dict]:
    """Compute authentication path for a leaf."""
    proof = []
    idx = leaf_index
    for level in levels[:-1]:
        if idx % 2 == 0:
            sib = idx + 1
            if sib < len(level):
                proof.append({"hash": level[sib].hex(), "position": "right"})
        else:
            sib = idx - 1
            proof.append({"hash": level[sib].hex(), "position": "left"})
        idx //= 2
    return proof


def verify_merkle_proof(leaf_hash: bytes, proof: list[dict], root: bytes) -> bool:
    """Verify a Merkle proof against an expected root."""
    current = leaf_hash
    for step in proof:
        sibling = bytes.fromhex(step["hash"])
        if step["position"] == "right":
            current = _hash_pair(current, sibling)
        else:
            current = _hash_pair(sibling, current)
    return current == root


# ── Batch State (in-memory, per org) ─────────────────────

class _PendingBatch:
    """Lightweight in-memory accumulator for a single batch."""

    def __init__(self, org_id: str, max_size: int = 100, max_interval: float = 300.0):
        self.org_id = org_id
        self.max_size = max_size
        self.max_interval = max_interval
        self.entries: list[dict] = []
        self.started_at = time.time()

    def add(self, entry: dict):
        self.entries.append(entry)

    @property
    def full(self) -> bool:
        return len(self.entries) >= self.max_size

    @property
    def expired(self) -> bool:
        return (time.time() - self.started_at) >= self.max_interval

    @property
    def should_finalize(self) -> bool:
        return len(self.entries) > 0 and (self.full or self.expired)


class MerkleService:
    """
    Multi-org Merkle batch manager.
    Maintains one pending batch per organization in memory.
    """

    def __init__(
        self,
        batch_size: int = 100,
        batch_interval: float = 300.0,
        storage_dir: Optional[str] = None,
        audit_service: Optional[AuditService] = None,
    ):
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.storage_dir = Path(
            storage_dir or str(Path.home() / ".quantum-guard" / "v2_merkle_batches")
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.audit_svc = audit_service or AuditService()

        self._lock = threading.Lock()
        self._pending: dict[str, _PendingBatch] = {}  # org_id → batch
        self._batch_counter = self._load_counter()

    # ── Add Transaction ───────────────────────────────────────

    async def add_transaction_to_batch(
        self,
        conn,
        org_id: str,
        tx_id: str,
        message_hash: str,
        proof_commitment: str,
    ) -> Optional[str]:
        """
        Add a transaction to the current pending batch for this org.
        If the batch is full or expired, finalize it first.
        Returns batch_id if finalized, else None.
        """
        finalized_batch_id = None

        with self._lock:
            if org_id not in self._pending:
                self._pending[org_id] = _PendingBatch(
                    org_id, self.batch_size, self.batch_interval
                )

            batch = self._pending[org_id]

            # Check if we need to finalize current batch first
            if batch.should_finalize:
                finalized_batch_id = await self._finalize_batch_locked(conn, batch)
                self._pending[org_id] = _PendingBatch(
                    org_id, self.batch_size, self.batch_interval
                )
                batch = self._pending[org_id]

            # Add entry
            entry = {
                "tx_id": tx_id,
                "message_hash": message_hash,
                "proof_commitment": proof_commitment,
                "timestamp": time.time(),
            }
            batch.add(entry)

        return finalized_batch_id

    # ── Force Finalize ────────────────────────────────────────

    async def force_finalize(self, conn, org_id: str) -> Optional[str]:
        """Force-finalize the current pending batch for an org."""
        with self._lock:
            batch = self._pending.get(org_id)
            if not batch or not batch.entries:
                return None
            batch_id = await self._finalize_batch_locked(conn, batch)
            self._pending[org_id] = _PendingBatch(
                org_id, self.batch_size, self.batch_interval
            )
            return batch_id

    # ── Batch Finalization ────────────────────────────────────

    async def _finalize_batch_locked(self, conn, batch: _PendingBatch) -> str:
        """
        Build Merkle tree, persist to DB + disk.
        Caller must hold self._lock.
        """
        self._batch_counter += 1
        batch_id = f"batch_{self._batch_counter:06d}_{int(time.time())}"
        now = time.time()

        entries = list(batch.entries)

        # Compute leaf hashes
        leaf_hashes = []
        for e in entries:
            canonical = json.dumps(e, sort_keys=True, separators=(",", ":"))
            leaf_hashes.append(_sha256(canonical.encode()))

        # Build tree
        tree = _build_tree(leaf_hashes)
        root = tree[-1][0].hex()

        # Get batch_number
        batch_number = self._batch_counter

        # Persist batch metadata
        await conn.execute(
            """INSERT INTO merkle_batches
               (batch_id, org_id, batch_number, transaction_count,
                merkle_root, created_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            batch_id, batch.org_id, batch_number, len(entries), root, now,
        )

        # Persist leaves with proofs
        for i, entry in enumerate(entries):
            leaf_id = str(uuid.uuid4())
            proof_path = _get_proof(tree, i)

            await conn.execute(
                """INSERT INTO merkle_leaves
                   (leaf_id, batch_id, tx_id, leaf_index, leaf_hash,
                    proof_path, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                leaf_id, batch_id, entry["tx_id"], i,
                leaf_hashes[i].hex(), json.dumps(proof_path), now,
            )

        # Save to disk (append-only)
        self._save_batch_file(batch_id, root, entries, leaf_hashes, tree)
        self._save_counter()

        # Audit
        await self.audit_svc.log(
            conn, batch.org_id, None,
            AuditEntityType.BATCH.value, batch_id,
            AuditAction.BATCH_COMMITTED.value,
            details={"merkle_root": root, "tx_count": len(entries)},
        )

        logger.info(
            "Batch finalized: %s root=%s txs=%d",
            batch_id, root[:16], len(entries),
        )
        return batch_id

    # ── On-Chain Commit ───────────────────────────────────────

    async def mark_batch_committed(
        self, conn, batch_id: str, starknet_tx_hash: str
    ):
        """Update batch after successful Starknet commitment."""
        now = time.time()
        await conn.execute(
            """UPDATE merkle_batches
               SET starknet_tx_hash = $1, starknet_confirmed = 1, committed_at = $2
               WHERE batch_id = $3""",
            starknet_tx_hash, now, batch_id,
        )

    # ── Queries ───────────────────────────────────────────────

    async def get_batch(self, conn, batch_id: str) -> Optional[dict]:
        return await conn.fetchrow(
            "SELECT * FROM merkle_batches WHERE batch_id = $1", batch_id
        )

    async def get_batch_leaves(self, conn, batch_id: str) -> list[dict]:
        rows = await conn.fetch(
            """SELECT leaf_id, tx_id, leaf_index, leaf_hash, proof_path
               FROM merkle_leaves
               WHERE batch_id = $1
               ORDER BY leaf_index""",
            batch_id,
        )
        return [dict(r) for r in rows]

    async def get_proof_for_tx(self, conn, tx_id: str) -> Optional[dict]:
        row = await conn.fetchrow(
            """SELECT ml.leaf_id, ml.batch_id, ml.leaf_index, ml.leaf_hash,
                      ml.proof_path,
                      mb.merkle_root, mb.starknet_confirmed, mb.starknet_tx_hash
               FROM merkle_leaves ml
               JOIN merkle_batches mb ON ml.batch_id = mb.batch_id
               WHERE ml.tx_id = $1""",
            tx_id,
        )
        return dict(row) if row else None

    async def list_batches(
        self,
        conn,
        org_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        rows = await conn.fetch(
            """SELECT batch_id, batch_number, transaction_count,
                      merkle_root, starknet_tx_hash, starknet_confirmed,
                      created_at, committed_at
               FROM merkle_batches
               WHERE org_id = $1
               ORDER BY batch_number DESC
               LIMIT $2 OFFSET $3""",
            org_id, limit, offset,
        )
        return [dict(r) for r in rows]

    def get_pending_count(self, org_id: str) -> int:
        with self._lock:
            batch = self._pending.get(org_id)
            return len(batch.entries) if batch else 0

    # ── Disk Persistence ──────────────────────────────────────

    def _save_batch_file(
        self,
        batch_id: str,
        root: str,
        entries: list[dict],
        leaf_hashes: list[bytes],
        tree: list[list[bytes]],
    ):
        """Save batch as append-only JSON file."""
        batch_file = self.storage_dir / f"{batch_id}.json"
        data = {
            "batch_id": batch_id,
            "merkle_root": root,
            "tx_count": len(entries),
            "entries": entries,
            "leaf_hashes": [h.hex() for h in leaf_hashes],
            "created_at": time.time(),
        }
        batch_file.write_text(json.dumps(data, indent=2, default=str))

    def _load_counter(self) -> int:
        counter_file = self.storage_dir / ".batch_counter"
        if counter_file.exists():
            try:
                return int(counter_file.read_text().strip())
            except (ValueError, OSError):
                pass
        return 0

    def _save_counter(self):
        counter_file = self.storage_dir / ".batch_counter"
        counter_file.write_text(str(self._batch_counter))
