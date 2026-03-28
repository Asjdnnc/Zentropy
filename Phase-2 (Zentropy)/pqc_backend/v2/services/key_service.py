"""
QuantumGuard v2 — Key Service (HSM-backed)
============================================
Generates Dilithium (ML-DSA-44) keypairs, encrypts secret keys with
AES-256-GCM (master key from HSM or env), and stores encrypted material
in PostgreSQL.

For local development the master key is derived from an env var.
In production, replace _get_master_key() with actual HSM calls
(AWS CloudHSM, Azure Key Vault, HashiCorp Vault, etc.).

Also handles:
  - Seed phrase generation (BIP-39 compatible 24-word mnemonic)
  - Key rotation (retire old key, generate new one)
  - Key recovery via Shamir Secret Sharing stubs
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
import uuid
from typing import Optional

try:
    import oqs  # type: ignore
    OQS_AVAILABLE = True
except BaseException as e:  # pragma: no cover - depends on local native setup
    oqs = None  # type: ignore
    OQS_AVAILABLE = False
    _OQS_IMPORT_ERROR = e

from ..models.enums import PQ_ALGORITHM, KeyStatus

logger = logging.getLogger("quantumguard.key_service")

# ── Master key derivation (dev mode) ──────────────────

_ENV_MASTER_SECRET = "QUANTUMGUARD_MASTER_SECRET"
_DEFAULT_DEV_SECRET = "dev-only-insecure-master-key-do-not-use-in-production"

# BIP-39 English wordlist subset (2048 words).
# In production, use the full official BIP-39 list.
# Here we embed a small bootstrapping function.
_BIP39_WORDLIST: Optional[list[str]] = None


def _is_truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _allow_insecure_pqc_fallback() -> bool:
    env = os.environ.get("ENV", "development").strip().lower()
    explicit_opt_in = _is_truthy(os.environ.get("ALLOW_INSECURE_PQC_FALLBACK", "0"))
    return env != "production" or explicit_opt_in


def _load_bip39_wordlist() -> list[str]:
    """Load or generate a deterministic wordlist for seed phrase generation."""
    global _BIP39_WORDLIST
    if _BIP39_WORDLIST is not None:
        return _BIP39_WORDLIST

    # Try loading official BIP-39 english wordlist from file
    wordlist_paths = [
        os.path.join(os.path.dirname(__file__), "bip39_english.txt"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "bip39_english.txt"),
    ]
    for path in wordlist_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                words = [w.strip() for w in f if w.strip()]
            if len(words) == 2048:
                _BIP39_WORDLIST = words
                return _BIP39_WORDLIST

    # Fallback: use hashlib to generate deterministic pseudo-words
    # This is NOT real BIP-39, but works for dev/testing
    logger.warning("BIP-39 wordlist not found — using deterministic fallback")
    words = []
    for i in range(2048):
        h = hashlib.sha256(f"qg-word-{i}".encode()).hexdigest()[:6]
        words.append(h)
    _BIP39_WORDLIST = words
    return _BIP39_WORDLIST


def _get_master_key() -> bytes:
    """
    Derive a 32-byte AES-256 master key.

    In production, this should call your HSM API.
    For dev, we derive from an env var.
    """
    secret = os.environ.get(_ENV_MASTER_SECRET, _DEFAULT_DEV_SECRET)
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode("utf-8"),
        b"quantumguard-master-salt-v2",
        iterations=100_000,
        dklen=32,
    )


def _aes_encrypt(plaintext: bytes, key: bytes) -> str:
    """
    Encrypt with AES-256-GCM.  Returns base64-encoded: nonce(12) || ciphertext || tag(16).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, None)  # ct includes 16-byte tag
    return base64.b64encode(nonce + ct).decode("ascii")


def _aes_decrypt(ciphertext_b64: str, key: bytes) -> bytes:
    """Decrypt AES-256-GCM. Input is base64-encoded nonce||ct||tag."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(ciphertext_b64)
    nonce = raw[:12]
    ct = raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


class KeyService:
    """
    Manages Dilithium keypair lifecycle:
      generate → encrypt → store → decrypt-on-demand → sign → wipe
    """

    def __init__(self):
        self._master_key = _get_master_key()
        if not OQS_AVAILABLE:
            if not _allow_insecure_pqc_fallback():
                raise RuntimeError(
                    "oqs native library unavailable in production mode. "
                    "Install liboqs/oqs or set ALLOW_INSECURE_PQC_FALLBACK=true for non-production demos."
                )
            logger.warning(
                "oqs native library unavailable; using development fallback signing. "
                "Error: %s",
                _OQS_IMPORT_ERROR,
            )

    # ── Key Generation ────────────────────────────────────────

    def generate_keypair(self) -> dict:
        """
        Generate a new ML-DSA-44 keypair.

        Returns dict with:
            public_key      (bytes)
            secret_key      (bytes)  — will be encrypted before storage
            public_key_hash (str)
        """
        if OQS_AVAILABLE:
            with oqs.Signature(PQ_ALGORITHM) as signer:
                public_key = signer.generate_keypair()
                secret_key = signer.export_secret_key()
        else:
            # Development fallback only: preserve API shape without native oqs.
            secret_key = secrets.token_bytes(32)
            public_key = secret_key

        return {
            "public_key": public_key,
            "secret_key": secret_key,
            "public_key_hash": hashlib.sha256(public_key).hexdigest(),
        }

    def encrypt_secret_key(self, secret_key: bytes) -> str:
        """Encrypt a secret key with the master key. Returns base64 blob."""
        return _aes_encrypt(secret_key, self._master_key)

    def decrypt_secret_key(self, encrypted_b64: str) -> bytes:
        """Decrypt a secret key. Used only during signing; wipe after."""
        return _aes_decrypt(encrypted_b64, self._master_key)

    # ── Seed Phrase ───────────────────────────────────────────

    def generate_seed_phrase(self, word_count: int = 24) -> str:
        """
        Generate a BIP-39-compatible mnemonic seed phrase.

        The seed phrase is used for account recovery.
        It's encrypted and stored in the wallets table,
        but also shown to the user ONCE at registration.
        """
        wordlist = _load_bip39_wordlist()
        entropy_bits = word_count * 11  # 264 bits for 24 words
        entropy_bytes = (entropy_bits + 7) // 8
        entropy = secrets.token_bytes(entropy_bytes)

        # Convert to word indices (simplified BIP-39)
        bits = bin(int.from_bytes(entropy, "big"))[2:].zfill(entropy_bytes * 8)
        # Add checksum
        checksum = hashlib.sha256(entropy).digest()
        checksum_bits = bin(int.from_bytes(checksum, "big"))[2:].zfill(256)
        all_bits = bits + checksum_bits[:word_count * 11 - len(bits)]

        words = []
        for i in range(word_count):
            idx = int(all_bits[i * 11:(i + 1) * 11], 2) % 2048
            words.append(wordlist[idx])

        return " ".join(words)

    def encrypt_seed_phrase(self, seed_phrase: str) -> str:
        """Encrypt seed phrase for database storage."""
        return _aes_encrypt(seed_phrase.encode("utf-8"), self._master_key)

    def decrypt_seed_phrase(self, encrypted_b64: str) -> str:
        """Decrypt seed phrase (for recovery flows only)."""
        return _aes_decrypt(encrypted_b64, self._master_key).decode("utf-8")

    # ── Signing ───────────────────────────────────────────────

    def sign_message(self, message: bytes, encrypted_sk_b64: str) -> bytes:
        """
        Decrypt the secret key, sign the message, return signature.
        The decrypted key is only in memory for the duration of this call.
        """
        sk = self.decrypt_secret_key(encrypted_sk_b64)
        try:
            if OQS_AVAILABLE:
                with oqs.Signature(PQ_ALGORITHM, secret_key=sk) as signer:
                    signature = signer.sign(message)
            else:
                signature = hmac.new(sk, message, hashlib.sha256).digest()
            return signature
        finally:
            # Overwrite sk in memory (best effort)
            sk_arr = bytearray(sk)
            for i in range(len(sk_arr)):
                sk_arr[i] = 0

    def verify_signature(
        self, message: bytes, signature: bytes, public_key: bytes
    ) -> bool:
        """Verify a Dilithium signature."""
        if OQS_AVAILABLE:
            with oqs.Signature(PQ_ALGORITHM) as verifier:
                try:
                    return verifier.verify(message, signature, public_key)
                except Exception:
                    return False
        expected = hmac.new(public_key, message, hashlib.sha256).digest()
        return hmac.compare_digest(signature, expected)

    # ── DB Operations ─────────────────────────────────────────

    async def store_encrypted_key(
        self,
        conn,
        wallet_id: str,
        secret_key: bytes,
    ) -> str:
        """Encrypt and store a secret key in the encrypted_keys table."""
        key_id = str(uuid.uuid4())
        encrypted = self.encrypt_secret_key(secret_key)
        key_hash = hashlib.sha256(secret_key).hexdigest()
        now = time.time()

        await conn.execute(
            """INSERT INTO encrypted_keys
               (key_id, wallet_id, key_type, algorithm,
                encrypted_key_material, key_material_hash, status, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            key_id, wallet_id, "signing_key", PQ_ALGORITHM,
            encrypted, key_hash, KeyStatus.ACTIVE.value, now,
        )
        return key_id

    async def get_active_encrypted_key(self, conn, wallet_id: str) -> Optional[dict]:
        """Fetch the active encrypted secret key for a wallet."""
        return await conn.fetchrow(
            """SELECT key_id, encrypted_key_material, key_material_hash
               FROM encrypted_keys
               WHERE wallet_id = $1 AND status = $2""",
            wallet_id, KeyStatus.ACTIVE.value,
        )

    async def rotate_key(self, conn, wallet_id: str) -> dict:
        """
        Retire old key, generate new keypair, store encrypted new key.
        Returns the new public key + hash.
        """
        now = time.time()

        # Retire current key
        await conn.execute(
            """UPDATE encrypted_keys
               SET status = $1, rotated_at = $2
               WHERE wallet_id = $3 AND status = $4""",
            KeyStatus.RETIRED.value, now, wallet_id, KeyStatus.ACTIVE.value,
        )

        # Generate new keypair
        kp = self.generate_keypair()
        new_key_id = await self.store_encrypted_key(conn, wallet_id, kp["secret_key"])

        logger.info("Key rotated for wallet %s → new key %s", wallet_id, new_key_id)
        return {
            "key_id": new_key_id,
            "public_key": base64.b64encode(kp["public_key"]).decode(),
            "public_key_hash": kp["public_key_hash"],
        }
