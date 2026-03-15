"""
QuantumGuard Signer
===================
Create and verify ML-DSA-44 (Dilithium) detached signatures.

A "detached signature" means the signature is separate from the message.
This is what gets sent to the Rust prover for off-chain verification,
then a compact proof is submitted on-chain.

Signature size: ~2420 bytes (vs ECDSA's 64 bytes).
"""
import json
import time

import oqs

from .config import ALGORITHM_SIG
from .key_manager import QuantumKeyManager
from .utils import b64encode, b64decode, sha256_hex, truncate_display


class QuantumSigner:
    """Create and verify ML-DSA-44 detached signatures."""

    def __init__(self, key_manager: QuantumKeyManager | None = None):
        self.key_manager = key_manager or QuantumKeyManager()

    def sign_message(self, message: bytes, label: str = "default") -> dict:
        """
        Sign an arbitrary message with the stored ML-DSA-44 secret key.

        Args:
            message: Raw bytes of the message/transaction to sign.
            label:   Which wallet identity to use.

        Returns:
            dict containing base64-encoded message, signature, public key,
            and metadata needed by the Rust prover.
        """
        secret_key = self.key_manager.get_secret_key(label)
        public_key = self.key_manager.get_public_key(label)

        with oqs.Signature(ALGORITHM_SIG, secret_key=secret_key) as signer:
            signature = signer.sign(message)

        result = {
            "message":        b64encode(message),
            "signature":      b64encode(signature),
            "public_key":     b64encode(public_key),
            "algorithm":      ALGORITHM_SIG,
            "signature_size": len(signature),
            "message_hash":   sha256_hex(message),
            "pubkey_hash":    sha256_hex(public_key),
            "timestamp":      int(time.time()),
        }

        print(f"[Signer] Signed message ({len(message)} bytes)")
        print(f"  Signature size : {len(signature)} bytes")
        print(f"  Message hash   : {result['message_hash'][:16]}...")
        print(f"  PK hash        : {result['pubkey_hash'][:16]}...")

        return result

    def sign_transaction(self, tx_payload: dict, label: str = "default") -> dict:
        """
        Sign a structured transaction payload.

        The transaction dict is serialized to canonical JSON bytes before signing.
        This ensures deterministic encoding across platforms.

        Args:
            tx_payload: dict with keys like 'to', 'amount', 'nonce', etc.
            label:      Which wallet identity to use.

        Returns:
            Signed transaction bundle ready for the prover.
        """
        # Canonical JSON serialization (sorted keys, no whitespace)
        canonical = json.dumps(tx_payload, sort_keys=True, separators=(",", ":"))
        message_bytes = canonical.encode("utf-8")

        sig_result = self.sign_message(message_bytes, label)
        sig_result["transaction"] = tx_payload
        return sig_result

    @staticmethod
    def verify_signature(
        message: bytes,
        signature: bytes,
        public_key: bytes,
    ) -> bool:
        """
        Verify an ML-DSA-44 signature.

        This is the SAME operation the Rust prover will perform.
        Having it in Python lets us unit-test locally before involving Rust.

        Args:
            message:    Raw message bytes.
            signature:  Raw signature bytes.
            public_key: Raw public key bytes.

        Returns:
            True if verification passes, False otherwise.
        """
        with oqs.Signature(ALGORITHM_SIG) as verifier:
            try:
                is_valid = verifier.verify(message, signature, public_key)
                return is_valid
            except Exception:
                return False
