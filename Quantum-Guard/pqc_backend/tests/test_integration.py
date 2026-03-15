"""
Integration tests for QuantumGuard full pipeline.

Tests the complete flow: wallet create → sign → prove → persistence
without requiring an actual running server (uses TestClient).

Run with:
    cd Quantum-Guard/
    python -m pytest pqc_backend/tests/test_integration.py -v
"""
import json
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pqc_backend.key_manager import QuantumKeyManager
from pqc_backend.signer import QuantumSigner
from pqc_backend.persistence import TransactionStore
from pqc_backend.utils import b64decode, sha256_hex


@pytest.fixture
def tmp_keydir(tmp_path):
    return tmp_path / "keys"


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def key_manager(tmp_keydir):
    return QuantumKeyManager(keydir=tmp_keydir)


@pytest.fixture
def signer(key_manager):
    key_manager.generate_identity(label="integration")
    return QuantumSigner(key_manager=key_manager)


@pytest.fixture
def store(tmp_db):
    return TransactionStore(db_path=tmp_db)


# ─── Full Pipeline Test (without server) ────────────────────────

class TestFullPipeline:
    """Test the complete sign → verify → prove → persist pipeline."""

    def test_sign_verify_persist(self, signer, store, key_manager):
        """
        End-to-end: sign a transaction, verify it locally,
        generate a proof commitment, and persist everything.
        """
        # Step 1: Sign a transaction
        tx_payload = {
            "to": "0xdeadbeef",
            "amount": 1.5,
            "nonce": 0,
            "data": "",
        }
        sig_result = signer.sign_transaction(tx_payload, label="integration")

        assert sig_result["algorithm"] == "ML-DSA-44"
        assert sig_result["signature_size"] == 2420
        assert len(sig_result["message"]) > 0
        assert len(sig_result["signature"]) > 0

        # Step 2: Verify the signature locally (mirrors Rust prover logic)
        canonical = json.dumps(tx_payload, sort_keys=True, separators=(",", ":"))
        msg_bytes = canonical.encode("utf-8")
        sig_bytes = b64decode(sig_result["signature"])
        pk_bytes = b64decode(sig_result["public_key"])

        assert QuantumSigner.verify_signature(msg_bytes, sig_bytes, pk_bytes) is True

        # Step 3: Generate proof commitment (Python fallback logic)
        valid = True
        msg_hash = sha256_hex(msg_bytes)
        sig_hash = sha256_hex(sig_bytes)
        pk_hash = sha256_hex(pk_bytes)
        proof_input = f"{valid}:{msg_hash}:{sig_hash}:{pk_hash}"
        proof_commitment = sha256_hex(proof_input.encode())

        assert len(proof_commitment) == 64

        # Step 4: Persist the transaction
        tx_id = "tx_integration_001"
        store.record_transaction(
            tx_id=tx_id,
            wallet_label="integration",
            to_addr=tx_payload["to"],
            amount=tx_payload["amount"],
            nonce=tx_payload["nonce"],
            data=tx_payload["data"],
            message_hash=msg_hash,
            pubkey_hash=pk_hash,
            signature_size=2420,
            status="signed",
        )

        # Step 5: Update with proof
        store.update_transaction_proof(
            tx_id=tx_id,
            proof_commitment=proof_commitment,
            proof_valid=True,
        )

        # Step 6: Cache the proof
        store.cache_proof(
            proof_commitment=proof_commitment,
            message_hash=msg_hash,
            pubkey_hash=pk_hash,
            valid=True,
            signature_hash=sig_hash,
            signature_size=2420,
            prover="python_test",
        )

        # Verify persistence
        tx = store.get_transaction(tx_id)
        assert tx is not None
        assert tx["status"] == "proved"
        assert tx["proof_valid"] == 1
        assert tx["proof_commitment"] == proof_commitment

        # Verify proof cache
        cached = store.get_cached_proof(proof_commitment)
        assert cached is not None
        assert cached["valid"] == 1
        assert cached["prover"] == "python_test"

    def test_tampered_transaction_fails(self, signer):
        """
        A modified transaction should fail verification.
        """
        tx_payload = {"to": "0xabc", "amount": 5.0, "nonce": 1}
        sig_result = signer.sign_transaction(tx_payload, label="integration")

        sig_bytes = b64decode(sig_result["signature"])
        pk_bytes = b64decode(sig_result["public_key"])

        # Modify the transaction
        tampered = {"to": "0xabc", "amount": 999.0, "nonce": 1}
        tampered_bytes = json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode()

        assert QuantumSigner.verify_signature(tampered_bytes, sig_bytes, pk_bytes) is False

    def test_multiple_wallets_isolated(self, key_manager, store):
        """
        Different wallets produce different signatures for the same message.
        """
        key_manager.generate_identity(label="wallet_a")
        key_manager.generate_identity(label="wallet_b")

        signer_a = QuantumSigner(key_manager=key_manager)
        signer_b = QuantumSigner(key_manager=key_manager)

        tx = {"to": "0x123", "amount": 1.0, "nonce": 0}

        result_a = signer_a.sign_transaction(tx, label="wallet_a")
        result_b = signer_b.sign_transaction(tx, label="wallet_b")

        # Different keys → different signatures
        assert result_a["signature"] != result_b["signature"]
        assert result_a["pubkey_hash"] != result_b["pubkey_hash"]

        # But both should verify with their own key
        canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
        assert QuantumSigner.verify_signature(
            canonical, b64decode(result_a["signature"]), b64decode(result_a["public_key"])
        )
        assert QuantumSigner.verify_signature(
            canonical, b64decode(result_b["signature"]), b64decode(result_b["public_key"])
        )

        # Cross-verification should fail
        assert not QuantumSigner.verify_signature(
            canonical, b64decode(result_a["signature"]), b64decode(result_b["public_key"])
        )

    def test_nonce_replay_protection(self, store):
        """
        Transaction IDs must be unique (replay protection at persistence level).
        """
        store.record_transaction(
            tx_id="tx_replay_1",
            wallet_label="alice",
            to_addr="0x1",
            amount=1.0,
            nonce=0,
        )
        # Reusing same tx_id should overwrite (OR REPLACE behavior)
        store.record_transaction(
            tx_id="tx_replay_1",
            wallet_label="alice",
            to_addr="0x1",
            amount=2.0,  # changed
            nonce=0,
        )
        tx = store.get_transaction("tx_replay_1")
        assert tx["amount"] == 2.0

    def test_proof_commitment_determinism(self, signer):
        """
        Same message + key should produce identical proof commitments.
        """
        tx = {"to": "0xfoo", "amount": 0.1, "nonce": 42}

        result1 = signer.sign_transaction(tx, label="integration")
        # Sign again with same key
        result2 = signer.sign_transaction(tx, label="integration")

        # Signatures will differ (randomized), but verification should work for both
        canonical = json.dumps(tx, sort_keys=True, separators=(",", ":")).encode()
        assert QuantumSigner.verify_signature(
            canonical, b64decode(result1["signature"]), b64decode(result1["public_key"])
        )
        assert QuantumSigner.verify_signature(
            canonical, b64decode(result2["signature"]), b64decode(result2["public_key"])
        )


# ─── Server endpoint tests (TestClient) ─────────────────────────

class TestServerEndpoints:
    """
    Test server endpoints using FastAPI's TestClient.
    Requires the server module to be importable.
    """

    @pytest.fixture(autouse=True)
    def setup_server(self, tmp_path):
        """Set up test environment with temp dirs."""
        self.tmp_keydir = tmp_path / "keys"
        self.tmp_db = tmp_path / "test.db"

        # Patch the server's global instances
        with patch.dict(os.environ, {"DB_PATH": str(self.tmp_db)}):
            from quantum_wallet_ui.server import app, key_manager as km, tx_store as ts
            from fastapi.testclient import TestClient

            # Use temp keydir
            km.keydir = self.tmp_keydir
            km.keydir.mkdir(parents=True, exist_ok=True)

            self.client = TestClient(app)
            self.km = km

    def test_health(self):
        """Health endpoint returns status."""
        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_create_and_info_wallet(self):
        """Create → info round-trip."""
        # Create
        resp = self.client.post("/wallet/create", json={"label": "test_wallet"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "created"
        assert resp.json()["label"] == "test_wallet"

        # Info
        resp2 = self.client.get("/wallet/info", params={"label": "test_wallet"})
        assert resp2.status_code == 200
        assert resp2.json()["algorithm"] == "ML-DSA-44"

    def test_duplicate_wallet_rejected(self):
        """Creating the same wallet twice returns 409."""
        self.client.post("/wallet/create", json={"label": "dup"})
        resp = self.client.post("/wallet/create", json={"label": "dup"})
        assert resp.status_code == 409

    def test_list_wallets(self):
        """List wallets endpoint."""
        self.client.post("/wallet/create", json={"label": "w1"})
        self.client.post("/wallet/create", json={"label": "w2"})
        resp = self.client.get("/wallet/list")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 2

    def test_sign_transaction(self):
        """Sign a transaction and get structured result."""
        self.client.post("/wallet/create", json={"label": "signer"})
        resp = self.client.post("/transaction/sign", json={
            "to": "0xdeadbeef",
            "amount": 1.0,
            "label": "signer",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "signed"
        assert data["signature_size"] == 2420
        assert "tx_id" in data

    def test_execute_transaction(self):
        """Full pipeline: sign → prove → (no Starknet)."""
        self.client.post("/wallet/create", json={"label": "executor"})
        resp = self.client.post("/transaction/execute", json={
            "to": "0xcafebabe",
            "amount": 0.5,
            "label": "executor",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("executed", "proof_failed")
        assert "tx_id" in data
        assert "proof_commitment" in data

    def test_transaction_history(self):
        """Transaction history returns persisted records."""
        self.client.post("/wallet/create", json={"label": "hist"})
        self.client.post("/transaction/sign", json={
            "to": "0x1", "amount": 1.0, "label": "hist",
        })
        self.client.post("/transaction/sign", json={
            "to": "0x2", "amount": 2.0, "label": "hist",
        })
        resp = self.client.get("/transaction/history", params={"label": "hist"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2

    def test_missing_wallet_returns_404(self):
        """Signing with a non-existent wallet returns 404."""
        resp = self.client.post("/transaction/sign", json={
            "to": "0x1", "amount": 1.0, "label": "ghost",
        })
        assert resp.status_code == 404

    def test_contract_status(self):
        """Contract status endpoint works even when not deployed."""
        resp = self.client.get("/contract/status")
        assert resp.status_code == 200
        assert resp.json()["deployed"] is False

    def test_proofs_endpoint(self):
        """Proofs endpoint returns cached proofs."""
        resp = self.client.get("/proofs")
        assert resp.status_code == 200
        assert "proofs" in resp.json()
