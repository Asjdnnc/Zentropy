"""
Unit tests for Phase 1: PQC Backend (ML-DSA key generation & signing).

Run with:
    cd Quantum-Guard/
    python -m pytest pqc_backend/tests/test_phase1.py -v
"""
import json
import tempfile
from pathlib import Path

import oqs
import pytest

from pqc_backend.config import ALGORITHM_SIG, ML_DSA_44_SIZES
from pqc_backend.key_manager import QuantumKeyManager
from pqc_backend.signer import QuantumSigner
from pqc_backend.utils import b64decode, sha256_hex


@pytest.fixture
def tmp_keydir(tmp_path):
    """Provide a temporary directory for key storage."""
    return tmp_path / "test_keys"


@pytest.fixture
def key_manager(tmp_keydir):
    """Provide a QuantumKeyManager using temp storage."""
    return QuantumKeyManager(keydir=tmp_keydir)


@pytest.fixture
def signer(key_manager):
    """Provide a QuantumSigner with a freshly-generated identity."""
    key_manager.generate_identity(label="test")
    return QuantumSigner(key_manager=key_manager)


# ─── Algorithm Availability ─────────────────────────────────────────

class TestAlgorithmAvailability:
    def test_ml_dsa_44_available(self):
        """ML-DSA-44 must be in the enabled signature mechanisms."""
        available = oqs.get_enabled_sig_mechanisms()
        assert ALGORITHM_SIG in available, (
            f"{ALGORITHM_SIG} not found. Available: {available}"
        )

    def test_ml_kem_768_available(self):
        """ML-KEM-768 must be available (needed later for KEM ops)."""
        available = oqs.get_enabled_kem_mechanisms()
        assert "ML-KEM-768" in available


# ─── Key Generation ─────────────────────────────────────────────────

class TestKeyGeneration:
    def test_generate_identity(self, key_manager):
        """Generate a keypair and verify sizes & structure."""
        identity = key_manager.generate_identity(label="alice")

        assert identity["algorithm"] == ALGORITHM_SIG
        assert identity["public_key_size"] > 0
        assert identity["secret_key_size"] > 0
        assert len(identity["pubkey_hash"]) == 64  # SHA-256 hex = 64 chars
        assert identity["created_at"] > 0

    def test_key_persistence(self, key_manager):
        """Keys should survive save/load cycle."""
        identity = key_manager.generate_identity(label="bob")
        loaded = key_manager.load_identity(label="bob")

        assert identity["public_key"] == loaded["public_key"]
        assert identity["secret_key"] == loaded["secret_key"]
        assert identity["pubkey_hash"] == loaded["pubkey_hash"]

    def test_list_wallets(self, key_manager):
        """Should list all created identities."""
        key_manager.generate_identity(label="w1")
        key_manager.generate_identity(label="w2")
        wallets = key_manager.list_wallets()
        labels = [w["label"] for w in wallets]

        assert "w1" in labels
        assert "w2" in labels

    def test_identity_exists(self, key_manager):
        """Existence check should work before and after creation."""
        assert not key_manager.identity_exists("ghost")
        key_manager.generate_identity(label="ghost")
        assert key_manager.identity_exists("ghost")

    def test_missing_identity_raises(self, key_manager):
        """Loading a non-existent identity should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            key_manager.load_identity("nonexistent")


# ─── Signing & Verification ─────────────────────────────────────────

class TestSigning:
    def test_sign_message(self, signer):
        """Sign a message and check output structure."""
        msg = b"Hello, quantum world!"
        result = signer.sign_message(msg, label="test")

        assert result["algorithm"] == ALGORITHM_SIG
        assert result["signature_size"] == ML_DSA_44_SIZES["signature"]
        assert result["message_hash"] == sha256_hex(msg)
        assert len(result["signature"]) > 0

    def test_signature_verifies(self, signer):
        """A valid signature should pass verification."""
        msg = b"Verify me"
        result = signer.sign_message(msg, label="test")

        sig_bytes = b64decode(result["signature"])
        pk_bytes = b64decode(result["public_key"])

        assert QuantumSigner.verify_signature(msg, sig_bytes, pk_bytes) is True

    def test_tampered_message_fails(self, signer):
        """Modifying the message after signing should fail verification."""
        msg = b"Original message"
        result = signer.sign_message(msg, label="test")

        sig_bytes = b64decode(result["signature"])
        pk_bytes = b64decode(result["public_key"])

        # Tamper with message
        tampered = b"Tampered message"
        assert QuantumSigner.verify_signature(tampered, sig_bytes, pk_bytes) is False

    def test_wrong_key_fails(self, signer, key_manager):
        """Verifying with a different key should fail."""
        msg = b"Key mismatch test"
        result = signer.sign_message(msg, label="test")
        sig_bytes = b64decode(result["signature"])

        # Generate a different key
        other_identity = key_manager.generate_identity(label="other")
        other_pk = b64decode(other_identity["public_key"])

        assert QuantumSigner.verify_signature(msg, sig_bytes, other_pk) is False

    def test_sign_transaction(self, signer):
        """Sign a structured transaction payload."""
        tx = {
            "to": "0xdeadbeef",
            "amount": 1.5,
            "nonce": 42,
        }
        result = signer.sign_transaction(tx, label="test")

        assert result["transaction"] == tx
        assert result["signature_size"] == ML_DSA_44_SIZES["signature"]

        # Verify the signature matches the canonical JSON
        canonical = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        sig_bytes = b64decode(result["signature"])
        pk_bytes = b64decode(result["public_key"])
        assert QuantumSigner.verify_signature(
            canonical.encode("utf-8"), sig_bytes, pk_bytes
        ) is True
