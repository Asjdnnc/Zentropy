"""
QuantumGuard Merkle Audit Trail
================================
Append-only Merkle tree for immutable transaction audit.

Unlike SQLite (mutable, easy to tamper):
  DELETE FROM transactions WHERE tx_id = 123;  -- trivial tampering

Merkle trees provide:
  - Tamper-evident: any modification invalidates the root hash
  - Compact proofs: O(log n) proof that a transaction exists in a batch
  - On-chain anchoring: root hash committed to Starknet for public verification

Architecture:
  1. Transactions accumulate in a batch (in-memory + append-only file)
  2. When batch triggers (N txs OR time interval), compute Merkle tree
  3. Merkle root committed to Starknet
  4. Each transaction gets a proof path: [leaf, sibling1, sibling2, ..., root]

Usage:
    from pqc_backend.merkle_audit import MerkleAuditAccumulator
    acc = MerkleAuditAccumulator()
    acc.add_transaction(tx_dict)
    if acc.should_commit():
        batch = acc.finalize_batch()
        # batch["merkle_root"] → commit to Starknet
"""
import hashlib
import json
import logging
import math
import time
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("quantumguard.merkle")


# =============================================================================
# Merkle Tree Implementation
# =============================================================================

def sha256_hash(data: bytes) -> bytes:
    """Compute SHA-256 digest."""
    return hashlib.sha256(data).digest()


def hash_leaf(tx_data: dict) -> bytes:
    """
    Hash a transaction into a Merkle leaf.
    Uses canonical JSON serialization for deterministic hashing.
    """
    canonical = json.dumps(tx_data, sort_keys=True, separators=(",", ":"))
    return sha256_hash(canonical.encode("utf-8"))


def hash_pair(left: bytes, right: bytes) -> bytes:
    """
    Hash two child nodes into a parent node.
    Always hashes in consistent order (left || right).
    """
    return sha256_hash(left + right)


def build_merkle_tree(leaves: list[bytes]) -> list[list[bytes]]:
    """
    Build a complete Merkle tree from leaf hashes.

    Returns a list of levels, where level[0] = leaves, level[-1] = [root].
    If the number of leaves is odd, the last leaf is duplicated.

    Args:
        leaves: List of 32-byte leaf hashes.

    Returns:
        List of tree levels. levels[0] = leaves, levels[-1] = [root_hash].
    """
    if not leaves:
        return [[sha256_hash(b"empty")]]

    # Ensure even number of leaves (duplicate last if odd)
    current_level = list(leaves)
    if len(current_level) % 2 == 1:
        current_level.append(current_level[-1])

    levels = [current_level]

    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            next_level.append(hash_pair(left, right))

        # Ensure even number at each level (except root)
        if len(next_level) > 1 and len(next_level) % 2 == 1:
            next_level.append(next_level[-1])

        levels.append(next_level)
        current_level = next_level

    return levels


def get_merkle_root(leaves: list[bytes]) -> bytes:
    """Compute the Merkle root from a list of leaf hashes."""
    tree = build_merkle_tree(leaves)
    return tree[-1][0]


def get_merkle_proof(levels: list[list[bytes]], leaf_index: int) -> list[dict]:
    """
    Generate a Merkle proof (authentication path) for a leaf.

    Args:
        levels: Full Merkle tree levels (from build_merkle_tree).
        leaf_index: Index of the leaf to prove.

    Returns:
        List of proof steps: [{"hash": hex, "position": "left"|"right"}, ...]
        Each step is the sibling hash needed to reconstruct the path to root.
    """
    proof = []
    idx = leaf_index

    for level in levels[:-1]:  # Skip root level
        if idx % 2 == 0:
            # We're on the left, sibling is on the right
            sibling_idx = idx + 1
            if sibling_idx < len(level):
                proof.append({
                    "hash": level[sibling_idx].hex(),
                    "position": "right",
                })
        else:
            # We're on the right, sibling is on the left
            sibling_idx = idx - 1
            proof.append({
                "hash": level[sibling_idx].hex(),
                "position": "left",
            })

        idx = idx // 2

    return proof


def verify_merkle_proof(
    leaf_hash: bytes,
    proof: list[dict],
    expected_root: bytes,
) -> bool:
    """
    Verify a Merkle proof: prove that leaf_hash is in the tree with the given root.

    Args:
        leaf_hash: The 32-byte hash of the transaction.
        proof: List of proof steps from get_merkle_proof().
        expected_root: The expected Merkle root.

    Returns:
        True if the proof is valid.
    """
    current = leaf_hash

    for step in proof:
        sibling = bytes.fromhex(step["hash"])
        if step["position"] == "right":
            current = hash_pair(current, sibling)
        else:
            current = hash_pair(sibling, current)

    return current == expected_root


# =============================================================================
# Merkle Audit Accumulator
# =============================================================================

@dataclass
class MerkleBatch:
    """A finalized batch of transactions with Merkle tree."""
    batch_id: str
    merkle_root: str           # Hex-encoded root hash
    tx_count: int
    transactions: list[dict]   # Full transaction data
    leaf_hashes: list[str]     # Hex-encoded leaf hashes
    proofs: dict               # {tx_index: proof_path}
    created_at: float
    committed: bool = False
    starknet_tx_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class MerkleAuditAccumulator:
    """
    Accumulates transactions and produces Merkle batches.

    Batch trigger: hybrid strategy
      - When tx_count >= batch_size (default 1000), OR
      - When time since last batch >= batch_interval (default 300s / 5 min)
      - Whichever comes first

    Thread-safe for concurrent transaction recording.
    """

    def __init__(
        self,
        batch_size: int = 1000,
        batch_interval: float = 300.0,  # 5 minutes
        storage_dir: Optional[Path] = None,
    ):
        self.batch_size = batch_size
        self.batch_interval = batch_interval
        self.storage_dir = Path(
            storage_dir or Path.home() / ".quantum-guard" / "merkle_batches"
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._pending_txs: list[dict] = []
        self._batch_start_time: float = time.time()
        self._batch_counter: int = self._load_batch_counter()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def add_transaction(self, tx_data: dict) -> int:
        """
        Add a transaction to the current accumulating batch.

        Args:
            tx_data: Transaction dict (tx_id, wallet_label, to_addr, amount, etc.)

        Returns:
            Index of the transaction in the current batch.
        """
        with self._lock:
            # Add timestamp if not present
            if "recorded_at" not in tx_data:
                tx_data["recorded_at"] = time.time()

            self._pending_txs.append(tx_data)
            idx = len(self._pending_txs) - 1
            logger.debug(
                f"Merkle accumulator: added tx #{idx} "
                f"(batch size: {len(self._pending_txs)})"
            )
            return idx

    def should_commit(self) -> bool:
        """
        Check if the current batch should be committed.
        Hybrid trigger: batch_size OR batch_interval, whichever first.
        """
        with self._lock:
            if len(self._pending_txs) == 0:
                return False

            # Size trigger
            if len(self._pending_txs) >= self.batch_size:
                return True

            # Time trigger
            elapsed = time.time() - self._batch_start_time
            if elapsed >= self.batch_interval:
                return True

            return False

    def pending_count(self) -> int:
        """Return the number of pending transactions."""
        with self._lock:
            return len(self._pending_txs)

    def finalize_batch(self) -> Optional[MerkleBatch]:
        """
        Finalize the current batch: compute Merkle tree, generate proofs.

        Returns:
            MerkleBatch with root hash and proof paths, or None if empty.
        """
        with self._lock:
            if not self._pending_txs:
                return None

            txs = list(self._pending_txs)
            self._pending_txs = []
            self._batch_start_time = time.time()

        # Compute leaf hashes
        leaf_hashes = [hash_leaf(tx) for tx in txs]

        # Build tree
        tree_levels = build_merkle_tree(leaf_hashes)
        merkle_root = tree_levels[-1][0]

        # Generate proofs for all transactions
        proofs = {}
        for i in range(len(txs)):
            proof_path = get_merkle_proof(tree_levels, i)
            proofs[i] = proof_path

        # Create batch
        self._batch_counter += 1
        batch_id = f"batch_{self._batch_counter:06d}_{int(time.time())}"

        batch = MerkleBatch(
            batch_id=batch_id,
            merkle_root=merkle_root.hex(),
            tx_count=len(txs),
            transactions=txs,
            leaf_hashes=[h.hex() for h in leaf_hashes],
            proofs=proofs,
            created_at=time.time(),
        )

        # Persist batch to disk (append-only)
        self._persist_batch(batch)
        self._save_batch_counter()

        logger.info(
            f"Merkle batch finalized: {batch_id}, "
            f"root={batch.merkle_root[:16]}..., "
            f"txs={batch.tx_count}"
        )

        return batch

    def get_transaction_proof(self, batch_id: str, tx_index: int) -> Optional[dict]:
        """
        Get a Merkle proof for a specific transaction in a specific batch.

        Args:
            batch_id: The batch identifier.
            tx_index: Transaction index within the batch.

        Returns:
            dict with merkle_root, tx_hash, proof_path, or None.
        """
        batch_data = self._load_batch(batch_id)
        if not batch_data:
            return None

        if tx_index >= batch_data["tx_count"]:
            return None

        return {
            "batch_id": batch_id,
            "merkle_root": batch_data["merkle_root"],
            "tx_index": tx_index,
            "tx_hash": batch_data["leaf_hashes"][tx_index],
            "proof_path": batch_data["proofs"].get(str(tx_index), []),
            "batch_tx_count": batch_data["tx_count"],
            "batch_created_at": batch_data["created_at"],
            "committed": batch_data.get("committed", False),
            "starknet_tx_hash": batch_data.get("starknet_tx_hash", ""),
        }

    def list_batches(self, limit: int = 50) -> list[dict]:
        """List recent Merkle batches (metadata only, no full tx data)."""
        batches = []
        batch_files = sorted(
            self.storage_dir.glob("batch_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        for bf in batch_files[:limit]:
            try:
                data = json.loads(bf.read_text())
                batches.append({
                    "batch_id": data["batch_id"],
                    "merkle_root": data["merkle_root"],
                    "tx_count": data["tx_count"],
                    "created_at": data["created_at"],
                    "committed": data.get("committed", False),
                    "starknet_tx_hash": data.get("starknet_tx_hash", ""),
                })
            except Exception:
                continue

        return batches

    def mark_batch_committed(self, batch_id: str, starknet_tx_hash: str):
        """Mark a batch as committed to Starknet."""
        batch_file = self.storage_dir / f"{batch_id}.json"
        if batch_file.exists():
            data = json.loads(batch_file.read_text())
            data["committed"] = True
            data["starknet_tx_hash"] = starknet_tx_hash
            data["committed_at"] = time.time()
            batch_file.write_text(json.dumps(data, indent=2))
            logger.info(f"Batch {batch_id} marked committed: {starknet_tx_hash}")

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------

    def _persist_batch(self, batch: MerkleBatch):
        """Write batch to disk as JSON (append-only storage)."""
        batch_file = self.storage_dir / f"{batch.batch_id}.json"
        # Convert int keys in proofs to string keys for JSON
        serializable = batch.to_dict()
        serializable["proofs"] = {
            str(k): v for k, v in serializable["proofs"].items()
        }
        batch_file.write_text(json.dumps(serializable, indent=2))

    def _load_batch(self, batch_id: str) -> Optional[dict]:
        """Load a batch from disk."""
        batch_file = self.storage_dir / f"{batch_id}.json"
        if batch_file.exists():
            return json.loads(batch_file.read_text())
        return None

    def _load_batch_counter(self) -> int:
        """Load the batch counter from disk."""
        counter_file = self.storage_dir / ".batch_counter"
        if counter_file.exists():
            try:
                return int(counter_file.read_text().strip())
            except (ValueError, OSError):
                pass
        return 0

    def _save_batch_counter(self):
        """Persist the batch counter."""
        counter_file = self.storage_dir / ".batch_counter"
        counter_file.write_text(str(self._batch_counter))
