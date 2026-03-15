"""
Tests for MerkleService — SHA-256 Merkle tree batching and proofs.
"""

import hashlib
import pytest

from pqc_backend.v2.services.merkle_service import (
    _sha256,
    _hash_pair,
    _build_tree,
    _get_proof,
    verify_merkle_proof,
)


@pytest.mark.asyncio
class TestMerklePrimitives:
    """Test low-level Merkle tree operations (module-level functions)."""

    async def test_build_tree_single_leaf(self):
        """A single-leaf tree should have a single-element root level."""
        leaf = _sha256(b"leaf0")
        tree = _build_tree([leaf])
        # Tree is list of levels; the last level is the root level
        root = tree[-1][0]
        # Single leaf (padded to 2): root = H(leaf || leaf)
        expected = _hash_pair(leaf, leaf)
        assert root == expected

    async def test_build_tree_two_leaves(self):
        """Two leaves should produce root = H(leaf0 || leaf1)."""
        leaf0 = _sha256(b"leaf0")
        leaf1 = _sha256(b"leaf1")

        tree = _build_tree([leaf0, leaf1])
        root = tree[-1][0]
        expected = _hash_pair(leaf0, leaf1)
        assert root == expected

    async def test_build_tree_four_leaves(self):
        """Four leaves should produce a balanced 3-level tree."""
        leaves = [_sha256(f"leaf{i}".encode()) for i in range(4)]
        tree = _build_tree(leaves)

        # Layer 1
        h01 = _hash_pair(leaves[0], leaves[1])
        h23 = _hash_pair(leaves[2], leaves[3])
        expected_root = _hash_pair(h01, h23)
        assert tree[-1][0] == expected_root

    async def test_verify_merkle_proof(self):
        """A valid proof should verify successfully."""
        leaves = [_sha256(f"tx{i}".encode()) for i in range(4)]
        tree = _build_tree(leaves)
        root = tree[-1][0]

        # Get proof for leaf at index 0
        proof = _get_proof(tree, 0)
        is_valid = verify_merkle_proof(leaves[0], proof, root)
        assert is_valid, "Valid proof should verify"

    async def test_verify_proof_all_indices(self):
        """Every leaf index should produce a valid proof."""
        leaves = [_sha256(f"item{i}".encode()) for i in range(8)]
        tree = _build_tree(leaves)
        root = tree[-1][0]

        for idx in range(len(leaves)):
            proof = _get_proof(tree, idx)
            assert verify_merkle_proof(
                leaves[idx], proof, root
            ), f"Proof for index {idx} should verify"

    async def test_invalid_proof_rejects(self):
        """A tampered proof should fail verification."""
        leaves = [_sha256(f"tx{i}".encode()) for i in range(4)]
        tree = _build_tree(leaves)
        root = tree[-1][0]

        proof = _get_proof(tree, 0)
        # Tamper with the proof
        if proof:
            tampered = list(proof)
            tampered[0] = {**tampered[0], "hash": "deadbeef" * 8}
            assert not verify_merkle_proof(leaves[0], tampered, root), "Tampered proof should reject"

    async def test_wrong_leaf_rejects(self):
        """Verifying with the wrong leaf hash should fail."""
        leaves = [_sha256(f"tx{i}".encode()) for i in range(4)]
        tree = _build_tree(leaves)
        root = tree[-1][0]

        proof = _get_proof(tree, 0)
        fake_leaf = _sha256(b"fake")
        assert not verify_merkle_proof(fake_leaf, proof, root), "Wrong leaf should reject"


@pytest.mark.asyncio
class TestMerkleBatching:
    """Test batch accumulation and finalization."""

    async def _create_test_transaction(self, conn, wallet_service, test_org, email_suffix):
        """Helper: create a user with wallet + insert a fake transaction record."""
        import uuid, time, hashlib

        reg = await wallet_service.register_user(
            conn, org_id=test_org["org_id"], email=f"merkle_{email_suffix}@test.com",
        )
        # Get the account
        account = await conn.fetchrow(
            "SELECT account_id FROM accounts WHERE wallet_id = $1", reg["wallet_id"]
        )
        account_id = account["account_id"]

        tx_id = f"mtx-{email_suffix}-{uuid.uuid4().hex[:8]}"
        now = time.time()
        await conn.execute(
            """INSERT INTO transactions
               (tx_id, account_id, to_address, amount_wei, nonce, status, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            tx_id, account_id, "0xdeadbeef", "1000", 0, "signed", now,
        )
        return tx_id

    async def test_add_transaction_to_batch(self, merkle_service, conn, test_org, wallet_service):
        """Adding a transaction should succeed without finalization."""
        org_id = test_org["org_id"]
        tx_id = await self._create_test_transaction(conn, wallet_service, test_org, "add1")
        tx_hash = hashlib.sha256(b"test_tx_1").hexdigest()

        result = await merkle_service.add_transaction_to_batch(
            conn, org_id, tx_id, tx_hash, "proof_commit_1"
        )
        # Returns batch_id if auto-finalized, else None
        assert result is None or isinstance(result, str)

    async def test_force_finalize(self, merkle_service, conn, test_org, wallet_service):
        """Force finalizing should create a batch record."""
        org_id = test_org["org_id"]

        # Add pending entries with real transaction records
        tx_ids = []
        for i in range(3):
            tx_id = await self._create_test_transaction(conn, wallet_service, test_org, f"fin{i}")
            tx_hash = hashlib.sha256(f"finalize_tx_{i}".encode()).hexdigest()
            await merkle_service.add_transaction_to_batch(
                conn, org_id, tx_id, tx_hash, f"proof_{i}"
            )
            tx_ids.append(tx_id)

        # Force finalize
        batch_id = await merkle_service.force_finalize(conn, org_id)
        assert batch_id is not None
        assert batch_id.startswith("batch_")

        # Verify batch is in DB
        batch = await merkle_service.get_batch(conn, batch_id)
        assert batch is not None
        assert batch["transaction_count"] == 3
        assert batch["merkle_root"] is not None
