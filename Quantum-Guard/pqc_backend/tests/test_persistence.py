"""
Unit tests for the persistence layer (TransactionStore).

Run with:
    cd Quantum-Guard/
    python -m pytest pqc_backend/tests/test_persistence.py -v
"""
import tempfile
import time
from pathlib import Path

import pytest

from pqc_backend.persistence import TransactionStore


@pytest.fixture
def store(tmp_path):
    """Provide a TransactionStore backed by a temporary SQLite database."""
    db_path = tmp_path / "test.db"
    return TransactionStore(db_path=db_path)


# ─── Transaction CRUD ────────────────────────────────────────────

class TestTransactionCRUD:
    def test_record_transaction(self, store):
        """Basic insert and retrieve."""
        result = store.record_transaction(
            tx_id="tx_abc123",
            wallet_label="default",
            to_addr="0xdeadbeef",
            amount=1.5,
            nonce=0,
            message_hash="abc",
            pubkey_hash="def",
            signature_size=2420,
            status="signed",
        )
        assert result["tx_id"] == "tx_abc123"
        assert result["status"] == "signed"

    def test_get_transaction(self, store):
        """Retrieve a recorded transaction."""
        store.record_transaction(
            tx_id="tx_get1",
            wallet_label="alice",
            to_addr="0x123",
            amount=2.0,
        )
        tx = store.get_transaction("tx_get1")
        assert tx is not None
        assert tx["wallet_label"] == "alice"
        assert tx["amount"] == 2.0

    def test_get_nonexistent(self, store):
        """Missing transactions return None."""
        assert store.get_transaction("tx_nonexistent") is None

    def test_update_proof(self, store):
        """Proof update changes status to 'proved'."""
        store.record_transaction(
            tx_id="tx_proof1",
            wallet_label="bob",
            to_addr="0x456",
            amount=1.0,
        )
        store.update_transaction_proof(
            tx_id="tx_proof1",
            proof_commitment="0xaabbccdd",
            proof_valid=True,
        )
        tx = store.get_transaction("tx_proof1")
        assert tx["status"] == "proved"
        assert tx["proof_valid"] == 1
        assert tx["proof_commitment"] == "0xaabbccdd"

    def test_update_starknet(self, store):
        """Starknet submission updates status."""
        store.record_transaction(
            tx_id="tx_stk1",
            wallet_label="carol",
            to_addr="0x789",
            amount=0.5,
        )
        store.update_transaction_starknet(
            tx_id="tx_stk1",
            starknet_tx_hash="0xstarknet123",
            starknet_status="submitted",
        )
        tx = store.get_transaction("tx_stk1")
        assert tx["status"] == "submitted"
        assert tx["starknet_tx_hash"] == "0xstarknet123"

    def test_update_generic_status(self, store):
        """Generic status update."""
        store.record_transaction(
            tx_id="tx_gen1",
            wallet_label="dave",
            to_addr="0xabc",
            amount=3.0,
        )
        store.update_transaction_status("tx_gen1", "error", "Something went wrong")
        tx = store.get_transaction("tx_gen1")
        assert tx["status"] == "error"
        assert tx["error"] == "Something went wrong"


# ─── Listing & Filtering ─────────────────────────────────────────

class TestTransactionListing:
    def test_list_all(self, store):
        """List all transactions."""
        for i in range(5):
            store.record_transaction(
                tx_id=f"tx_list_{i}",
                wallet_label="default",
                to_addr=f"0x{i}",
                amount=float(i),
            )
        txs = store.list_transactions()
        assert len(txs) == 5

    def test_filter_by_wallet(self, store):
        """Filter by wallet label."""
        store.record_transaction(tx_id="tx_w1", wallet_label="alice", to_addr="0x1", amount=1.0)
        store.record_transaction(tx_id="tx_w2", wallet_label="bob", to_addr="0x2", amount=2.0)
        store.record_transaction(tx_id="tx_w3", wallet_label="alice", to_addr="0x3", amount=3.0)

        alice_txs = store.list_transactions(wallet_label="alice")
        assert len(alice_txs) == 2

    def test_filter_by_status(self, store):
        """Filter by status."""
        store.record_transaction(tx_id="tx_s1", wallet_label="x", to_addr="0x1", amount=1.0, status="signed")
        store.record_transaction(tx_id="tx_s2", wallet_label="x", to_addr="0x2", amount=2.0, status="signed")
        store.update_transaction_proof("tx_s2", "proof", True)

        signed = store.list_transactions(status="signed")
        assert len(signed) == 1

        proved = store.list_transactions(status="proved")
        assert len(proved) == 1

    def test_pagination(self, store):
        """Pagination with limit and offset."""
        for i in range(10):
            store.record_transaction(
                tx_id=f"tx_page_{i}",
                wallet_label="default",
                to_addr=f"0x{i}",
                amount=float(i),
            )
        page1 = store.list_transactions(limit=3, offset=0)
        page2 = store.list_transactions(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0]["tx_id"] != page2[0]["tx_id"]

    def test_count(self, store):
        """Count transactions."""
        assert store.count_transactions() == 0
        store.record_transaction(tx_id="tx_c1", wallet_label="a", to_addr="0x1", amount=1.0)
        store.record_transaction(tx_id="tx_c2", wallet_label="b", to_addr="0x2", amount=2.0)
        assert store.count_transactions() == 2
        assert store.count_transactions(wallet_label="a") == 1

    def test_get_by_starknet_hash(self, store):
        """Find by Starknet tx hash."""
        store.record_transaction(tx_id="tx_sh1", wallet_label="x", to_addr="0x1", amount=1.0)
        store.update_transaction_starknet("tx_sh1", "0xstark_abc", "submitted")
        tx = store.get_transaction_by_starknet_hash("0xstark_abc")
        assert tx is not None
        assert tx["tx_id"] == "tx_sh1"


# ─── Proof Cache ─────────────────────────────────────────────────

class TestProofCache:
    def test_cache_and_retrieve(self, store):
        """Cache a proof and retrieve it."""
        store.cache_proof(
            proof_commitment="0xproof_abc",
            message_hash="0xmsg",
            pubkey_hash="0xpk",
            valid=True,
            signature_hash="0xsig",
            signature_size=2420,
            prover="rust",
        )
        proof = store.get_cached_proof("0xproof_abc")
        assert proof is not None
        assert proof["valid"] == 1
        assert proof["prover"] == "rust"

    def test_duplicate_proof_ignored(self, store):
        """Inserting same proof_commitment twice is ignored (no error)."""
        store.cache_proof(proof_commitment="dup", message_hash="m", pubkey_hash="p", valid=True)
        store.cache_proof(proof_commitment="dup", message_hash="m2", pubkey_hash="p2", valid=False)
        # First insert wins
        proof = store.get_cached_proof("dup")
        assert proof["valid"] == 1

    def test_list_proofs(self, store):
        """List cached proofs."""
        for i in range(3):
            store.cache_proof(
                proof_commitment=f"proof_{i}",
                message_hash=f"msg_{i}",
                pubkey_hash=f"pk_{i}",
                valid=True,
            )
        proofs = store.list_proofs(limit=10)
        assert len(proofs) == 3


# ─── Deployments ─────────────────────────────────────────────────

class TestDeployments:
    def test_record_deployment(self, store):
        """Record and retrieve a deployment."""
        store.record_deployment(
            contract_address="0xcontract_123",
            class_hash="0xclass_456",
            owner_pubkey_hash="0xowner_789",
            owner_label="default",
            network="starknet-sepolia",
        )
        dep = store.get_deployment("0xcontract_123")
        assert dep is not None
        assert dep["class_hash"] == "0xclass_456"

    def test_list_deployments(self, store):
        """List all deployments."""
        store.record_deployment(
            contract_address="0xc1",
            class_hash="0xh1",
            owner_pubkey_hash="0xo1",
        )
        store.record_deployment(
            contract_address="0xc2",
            class_hash="0xh2",
            owner_pubkey_hash="0xo2",
        )
        deps = store.list_deployments()
        assert len(deps) == 2


# ─── Thread Safety ───────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_writes(self, store):
        """Multiple threads writing concurrently should not corrupt data."""
        import threading

        def write_tx(thread_id):
            for i in range(10):
                store.record_transaction(
                    tx_id=f"tx_t{thread_id}_{i}",
                    wallet_label=f"thread_{thread_id}",
                    to_addr=f"0x{thread_id}{i}",
                    amount=float(i),
                )

        threads = [threading.Thread(target=write_tx, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total = store.count_transactions()
        assert total == 40
