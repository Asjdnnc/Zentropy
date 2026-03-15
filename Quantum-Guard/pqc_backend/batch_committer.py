"""
QuantumGuard Batch Committer
============================
Background service that monitors the Merkle accumulator and commits
finalized batches to Starknet.

The committer runs as an async background task alongside the FastAPI server.
It periodically checks if a batch should be committed (hybrid trigger:
batch_size >= N OR elapsed_time >= T, whichever comes first).

When a batch is ready:
  1. Finalize the Merkle tree (compute root + proof paths)
  2. Record batch metadata in persistence layer
  3. Submit merkle_root to Starknet (on-chain audit anchor)
  4. Mark batch as committed

Usage:
    from pqc_backend.batch_committer import BatchCommitter
    committer = BatchCommitter(accumulator, tx_store)
    asyncio.create_task(committer.run())  # Start in background
"""
import asyncio
import json
import logging
import subprocess
import os
import time
from typing import Optional

from .merkle_audit import MerkleAuditAccumulator, MerkleBatch
from .persistence import TransactionStore
from .config import STARKNET_RPC

logger = logging.getLogger("quantumguard.committer")

# How often the committer checks if a batch should be committed
POLL_INTERVAL = 10  # seconds


class BatchCommitter:
    """
    Background service that commits Merkle batches to Starknet.

    Lifecycle:
        1. Poll accumulator.should_commit() every POLL_INTERVAL seconds
        2. If True → finalize batch → record in DB → submit to Starknet
        3. Mark batch as committed with Starknet tx hash
    """

    def __init__(
        self,
        accumulator: MerkleAuditAccumulator,
        tx_store: TransactionStore,
        poll_interval: float = POLL_INTERVAL,
    ):
        self.accumulator = accumulator
        self.tx_store = tx_store
        self.poll_interval = poll_interval
        self._running = False
        self._committed_count = 0

    async def run(self):
        """Run the committer loop (call as asyncio task)."""
        self._running = True
        logger.info("Batch committer started (poll interval: %.0fs)", self.poll_interval)

        while self._running:
            try:
                if self.accumulator.should_commit():
                    await self._commit_batch()
            except Exception as e:
                logger.error(f"Batch committer error: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    def stop(self):
        """Signal the committer to stop."""
        self._running = False
        logger.info("Batch committer stopping...")

    async def force_commit(self) -> Optional[dict]:
        """
        Force an immediate batch commit (regardless of trigger conditions).
        Used by the API for manual batch finalization.
        """
        if self.accumulator.pending_count() == 0:
            return None
        return await self._commit_batch()

    async def _commit_batch(self) -> Optional[dict]:
        """
        Finalize and commit the current batch.

        Steps:
            1. Finalize Merkle tree in accumulator
            2. Record batch + leaves in persistence DB
            3. Submit merkle_root to Starknet
            4. Mark committed
        """
        batch = self.accumulator.finalize_batch()
        if not batch:
            return None

        logger.info(
            f"Committing batch {batch.batch_id}: "
            f"{batch.tx_count} txs, root={batch.merkle_root[:16]}..."
        )

        # Step 1: Record batch in persistence layer
        self.tx_store.record_merkle_batch(
            batch_id=batch.batch_id,
            merkle_root=batch.merkle_root,
            tx_count=batch.tx_count,
        )

        # Step 2: Record individual leaves with proofs
        for i, tx in enumerate(batch.transactions):
            tx_id = tx.get("tx_id", f"unknown_{i}")
            self.tx_store.record_merkle_leaf(
                batch_id=batch.batch_id,
                tx_index=i,
                tx_id=tx_id,
                tx_hash=batch.leaf_hashes[i],
                merkle_proof=json.dumps(batch.proofs.get(i, [])),
            )

        # Step 3: Submit to Starknet (if credentials available)
        starknet_tx_hash = ""
        try:
            starknet_tx_hash = await self._submit_merkle_root(
                batch.merkle_root, batch.tx_count
            )
            if starknet_tx_hash:
                logger.info(
                    f"Batch {batch.batch_id} committed to Starknet: {starknet_tx_hash}"
                )
        except Exception as e:
            logger.warning(
                f"Starknet submission failed for batch {batch.batch_id}: {e}. "
                "Batch recorded locally — can be resubmitted."
            )

        # Step 4: Mark committed
        if starknet_tx_hash:
            self.tx_store.mark_batch_committed(batch.batch_id, starknet_tx_hash)
            self.accumulator.mark_batch_committed(batch.batch_id, starknet_tx_hash)

        self._committed_count += 1

        return {
            "batch_id": batch.batch_id,
            "merkle_root": batch.merkle_root,
            "tx_count": batch.tx_count,
            "starknet_tx_hash": starknet_tx_hash,
            "committed": bool(starknet_tx_hash),
        }

    async def _submit_merkle_root(self, merkle_root: str, batch_size: int) -> str:
        """
        Submit a merkle_root to the Starknet QuantumGuardAccount contract.

        Calls commit_merkle_batch(merkle_root, batch_size, timestamp) on-chain.

        Returns:
            Starknet transaction hash, or empty string if not configured.
        """
        private_key = os.environ.get("STARKNET_PRIVATE_KEY", "")
        account_addr = os.environ.get("STARKNET_ACCOUNT_ADDRESS", "")
        contract_addr = os.environ.get("QUANTUM_GUARD_CONTRACT", "")

        if not all([private_key, account_addr, contract_addr]):
            logger.debug("Starknet credentials not configured — skipping on-chain commit")
            return ""

        # Truncate merkle_root to felt252 (31 bytes = 62 hex chars)
        root_felt = "0x" + merkle_root[:62]
        timestamp = str(int(time.time()))

        try:
            result = subprocess.run(
                [
                    "starkli", "invoke",
                    contract_addr,
                    "commit_merkle_batch",
                    root_felt,              # merkle_root
                    str(batch_size),        # batch_size
                    timestamp,              # timestamp
                    "--rpc", STARKNET_RPC,
                    "--private-key", private_key,
                    "--account", account_addr,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(f"starkli invoke failed: {result.stderr}")

            # Extract tx hash
            for line in (result.stdout + result.stderr).splitlines():
                stripped = line.strip()
                if stripped.startswith("0x") and len(stripped) > 10:
                    return stripped

            return ""

        except subprocess.TimeoutExpired:
            raise RuntimeError("Starknet submission timed out")

    @property
    def stats(self) -> dict:
        """Return committer statistics."""
        return {
            "running": self._running,
            "committed_batches": self._committed_count,
            "pending_transactions": self.accumulator.pending_count(),
            "poll_interval": self.poll_interval,
            "batch_size": self.accumulator.batch_size,
            "batch_interval": self.accumulator.batch_interval,
        }
