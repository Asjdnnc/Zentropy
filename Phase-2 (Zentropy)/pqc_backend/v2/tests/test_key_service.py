"""
Tests for KeyService — PQC key generation, encryption, signing.
"""

import pytest


@pytest.mark.asyncio
class TestKeyGeneration:
    """Test ML-DSA-44 key pair generation."""

    async def test_generate_keypair(self, key_service):
        """Should produce valid public/secret key pair."""
        kp = key_service.generate_keypair()
        assert kp["public_key"] is not None
        assert kp["secret_key"] is not None
        assert len(kp["public_key"]) > 0
        assert len(kp["secret_key"]) > 0
        # ML-DSA-44 public key is 1312 bytes
        assert len(kp["public_key"]) == 1312, f"Expected 1312-byte PK, got {len(kp['public_key'])}"
        # public_key_hash should be a hex string
        assert len(kp["public_key_hash"]) == 64  # sha256 hex

    async def test_keypairs_are_unique(self, key_service):
        """Two key generations should produce different keys."""
        kp1 = key_service.generate_keypair()
        kp2 = key_service.generate_keypair()
        assert kp1["public_key"] != kp2["public_key"], "Public keys should be unique"
        assert kp1["secret_key"] != kp2["secret_key"], "Secret keys should be unique"


@pytest.mark.asyncio
class TestKeyEncryption:
    """Test AES-256-GCM key encryption/decryption."""

    async def test_encrypt_decrypt_roundtrip(self, key_service):
        """Encrypted key should decrypt back to the original."""
        kp = key_service.generate_keypair()
        encrypted = key_service.encrypt_secret_key(kp["secret_key"])
        decrypted = key_service.decrypt_secret_key(encrypted)
        assert decrypted == kp["secret_key"], "Decrypted key should match original"

    async def test_encrypted_differs_from_plaintext(self, key_service):
        """Encrypted bytes should not match the plaintext."""
        kp = key_service.generate_keypair()
        encrypted = key_service.encrypt_secret_key(kp["secret_key"])
        # encrypted is base64 string, sk is bytes — they can't equal
        assert encrypted != kp["secret_key"]

    async def test_different_encryptions_differ(self, key_service):
        """Same plaintext encrypted twice should produce different ciphertexts (random nonce)."""
        kp = key_service.generate_keypair()
        enc1 = key_service.encrypt_secret_key(kp["secret_key"])
        enc2 = key_service.encrypt_secret_key(kp["secret_key"])
        assert enc1 != enc2, "AES-GCM with random nonce should produce different ciphertexts"


@pytest.mark.asyncio
class TestSeedPhrase:
    """Test BIP-39 seed phrase generation."""

    async def test_generate_seed_phrase(self, key_service):
        """Should produce a 24-word mnemonic."""
        phrase = key_service.generate_seed_phrase()
        words = phrase.split()
        assert len(words) == 24, f"Expected 24 words, got {len(words)}"

    async def test_seed_phrases_are_unique(self, key_service):
        """Two seed phrases should differ."""
        p1 = key_service.generate_seed_phrase()
        p2 = key_service.generate_seed_phrase()
        assert p1 != p2, "Seed phrases should be unique"

    async def test_encrypt_decrypt_seed_phrase(self, key_service):
        """Seed phrase should survive encrypt/decrypt roundtrip."""
        phrase = key_service.generate_seed_phrase()
        encrypted = key_service.encrypt_seed_phrase(phrase)
        decrypted = key_service.decrypt_seed_phrase(encrypted)
        assert decrypted == phrase


@pytest.mark.asyncio
class TestSigning:
    """Test ML-DSA-44 sign/verify cycle."""

    async def test_sign_and_verify(self, key_service):
        """Message signed with SK should verify with PK."""
        kp = key_service.generate_keypair()
        encrypted_sk = key_service.encrypt_secret_key(kp["secret_key"])

        message = b"Hello QuantumGuard"
        signature = key_service.sign_message(message, encrypted_sk)
        assert signature is not None
        assert len(signature) > 0

        is_valid = key_service.verify_signature(message, signature, kp["public_key"])
        assert is_valid, "Signature should verify"

    async def test_verify_rejects_wrong_message(self, key_service):
        """Signature should not verify with a different message."""
        kp = key_service.generate_keypair()
        encrypted_sk = key_service.encrypt_secret_key(kp["secret_key"])

        signature = key_service.sign_message(b"original", encrypted_sk)
        is_valid = key_service.verify_signature(b"tampered", signature, kp["public_key"])
        assert not is_valid, "Should reject wrong message"

    async def test_verify_rejects_wrong_key(self, key_service):
        """Signature should not verify with a different public key."""
        kp1 = key_service.generate_keypair()
        kp2 = key_service.generate_keypair()
        encrypted_sk1 = key_service.encrypt_secret_key(kp1["secret_key"])

        signature = key_service.sign_message(b"test", encrypted_sk1)
        is_valid = key_service.verify_signature(b"test", signature, kp2["public_key"])
        assert not is_valid, "Should reject wrong PK"


@pytest.mark.asyncio
class TestKeyDBOperations:
    """Test key storage and retrieval in the database."""

    async def test_store_and_retrieve_key(self, key_service, conn):
        """Stored key should be retrievable."""
        import uuid, time

        # Create prerequisite org + user + wallet
        org_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        wallet_id = str(uuid.uuid4())
        now = time.time()

        await conn.execute(
            "INSERT INTO organizations (org_id, org_name, api_key, created_at, updated_at) VALUES ($1,$2,$3,$4,$5)",
            org_id, "KeyDB Org", "key_test_api_key", now, now,
        )
        await conn.execute(
            "INSERT INTO users (user_id, org_id, email, kyc_status, is_active, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            user_id, org_id, "key@test.com", "pending", 1, now, now,
        )
        await conn.execute(
            "INSERT INTO wallets (wallet_id, user_id, seed_phrase_encrypted, seed_phrase_hash, status, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            wallet_id, user_id, "enc_seed", "hash", "active", now, now,
        )

        kp = key_service.generate_keypair()
        key_id = await key_service.store_encrypted_key(conn, wallet_id, kp["secret_key"])
        assert key_id is not None

        active = await key_service.get_active_encrypted_key(conn, wallet_id)
        assert active is not None
        assert active["key_id"] == key_id
