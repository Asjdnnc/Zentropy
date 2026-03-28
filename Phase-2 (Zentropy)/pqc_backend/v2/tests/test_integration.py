"""
Integration test — full QuantumGuard v2 flow.

Exercises the complete pipeline:
  1. Create organization
  2. Register user (generates PQC keypair + wallet + seed phrase)
  3. Verify wallet retrieval
  4. Verify audit chain integrity
  5. Multi-user isolation checks
"""

import pytest


@pytest.mark.asyncio
class TestFullPipeline:
    """End-to-end integration test through all v2 services."""

    async def test_full_custodial_flow(
        self,
        wallet_service,
        merkle_service,
        audit_service,
        key_service,
        conn,
    ):
        """
        Complete flow: org → user → wallet verify → audit verify.
        """
        # ── Step 1: Create organization ──────────────────────────
        org = await wallet_service.create_organization(conn, "Integration Test Corp", "integration@example.com")
        assert org["org_id"]
        assert org["api_key"]
        org_id = org["org_id"]

        # ── Step 2: Register a user ──────────────────────────────
        user = await wallet_service.register_user(
            conn,
            org_id=org_id,
            email="integration@test.com",
        )
        assert user["user_id"]
        assert user["wallet_id"]
        assert len(user["seed_phrase"].split()) == 24
        user_id = user["user_id"]

        # ── Step 3: Verify wallet was created ────────────────────
        wallet_info = await wallet_service.get_full_user_wallet(conn, user_id)
        assert wallet_info is not None
        assert wallet_info["user"]["email"] == "integration@test.com"
        assert wallet_info["wallet"]["status"] == "active"
        assert wallet_info["account"] is not None
        assert wallet_info["account"]["account_address"].startswith("0x")

        # ── Step 4: Verify encrypted key exists ──────────────────
        enc_key = await key_service.get_active_encrypted_key(conn, user["wallet_id"])
        assert enc_key is not None
        assert enc_key["encrypted_key_material"] is not None

        # ── Step 5: Sign something with the stored key ───────────
        message = b"test-integration-message"
        signature = key_service.sign_message(message, enc_key["encrypted_key_material"])
        assert signature is not None and len(signature) > 0

        # Verify the signature using public key from account
        import base64
        pk_bytes = base64.b64decode(wallet_info["account"]["public_key_pq"])
        assert key_service.verify_signature(message, signature, pk_bytes)

        # ── Step 6: Verify audit chain ───────────────────────────
        chain_result = await audit_service.verify_chain_integrity(conn, org_id)
        assert chain_result["valid"], f"Audit chain broken: {chain_result}"
        assert chain_result["checked"] >= 2  # At least user + wallet create

        # ── Step 7: Check audit log has entries ──────────────────
        logs = await audit_service.get_log(conn, org_id=org_id)
        assert len(logs) >= 2, "Should have audit entries for user + wallet creation"


@pytest.mark.asyncio
class TestMultiUserIsolation:
    """Test that multiple users in the same org are properly isolated."""

    async def test_users_have_different_keys(self, wallet_service, conn):
        """Each user should get a unique keypair."""
        org = await wallet_service.create_organization(conn, "Multi User Org", "multi-user@example.com")
        org_id = org["org_id"]

        user1 = await wallet_service.register_user(conn, org_id, "user1@test.com")
        user2 = await wallet_service.register_user(conn, org_id, "user2@test.com")

        wallet1 = await wallet_service.get_full_user_wallet(conn, user1["user_id"])
        wallet2 = await wallet_service.get_full_user_wallet(conn, user2["user_id"])

        assert (
            wallet1["account"]["public_key_pq"]
            != wallet2["account"]["public_key_pq"]
        ), "Users should have different public keys"

        assert (
            wallet1["account"]["account_address"]
            != wallet2["account"]["account_address"]
        ), "Users should have different Starknet addresses"

        assert user1["seed_phrase"] != user2["seed_phrase"], \
            "Users should have different seed phrases"

    async def test_users_have_different_wallets(self, wallet_service, conn):
        """Each user should have a separate wallet record."""
        org = await wallet_service.create_organization(conn, "Wallet Isolation Org", "isolation@example.com")
        org_id = org["org_id"]

        u1 = await wallet_service.register_user(conn, org_id, "a@test.com")
        u2 = await wallet_service.register_user(conn, org_id, "b@test.com")

        assert u1["wallet_id"] != u2["wallet_id"]


@pytest.mark.asyncio
class TestKeyRotation:
    """Test PQC key rotation for a user."""

    async def test_key_rotation(self, wallet_service, key_service, conn, test_org):
        """After rotation, the active key should be the new one."""
        reg = await wallet_service.register_user(
            conn, org_id=test_org["org_id"], email="rotate@test.com",
        )

        old_key = await key_service.get_active_encrypted_key(conn, reg["wallet_id"])
        assert old_key is not None

        # Rotate key
        new_key_info = await key_service.rotate_key(conn, reg["wallet_id"])
        assert new_key_info is not None
        assert "key_id" in new_key_info
        assert new_key_info["key_id"] != old_key["key_id"]

        # Verify new key is active
        active = await key_service.get_active_encrypted_key(conn, reg["wallet_id"])
        assert active is not None
        assert active["key_id"] == new_key_info["key_id"]
