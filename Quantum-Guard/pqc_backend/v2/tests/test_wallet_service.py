"""
Tests for WalletService — user registration, wallet creation, key storage.
"""

import pytest


@pytest.mark.asyncio
class TestOrganizationCreation:
    """Test organization (custodian) setup."""

    async def test_create_organization(self, wallet_service, conn):
        """Should create an org and return an API key."""
        result = await wallet_service.create_organization(conn, "Acme Corp", "acme@example.com")
        assert result is not None
        assert "org_id" in result
        assert result["admin_email"] == "acme@example.com"
        assert "api_key" in result

    async def test_org_ids_are_unique(self, wallet_service, conn):
        """Creating two orgs should produce unique IDs."""
        r1 = await wallet_service.create_organization(conn, "Org One", "one@example.com")
        r2 = await wallet_service.create_organization(conn, "Org Two", "two@example.com")
        assert r1["org_id"] != r2["org_id"]

    async def test_get_org_by_api_key(self, wallet_service, conn):
        """Should find an org by its API key."""
        created = await wallet_service.create_organization(conn, "Lookup Test Corp", "lookup@example.com")
        org = await wallet_service.get_organization_by_api_key(conn, created["api_key"])
        assert org is not None
        assert org["org_id"] == created["org_id"]

    async def test_invalid_api_key_returns_none(self, wallet_service, conn):
        """A bogus API key should return None."""
        org = await wallet_service.get_organization_by_api_key(conn, "invalid_key_12345678")
        assert org is None


@pytest.mark.asyncio
class TestUserRegistration:
    """Test end-to-end user registration flow."""

    async def test_register_user(self, wallet_service, conn, test_org):
        """Should create user + wallet + keypair + seed phrase."""
        result = await wallet_service.register_user(
            conn,
            org_id=test_org["org_id"],
            email="alice@example.com",
        )
        assert result is not None
        assert "user_id" in result
        assert "wallet_id" in result
        assert "seed_phrase" in result
        assert "contract_address" in result

        # Seed phrase should be 24 words
        words = result["seed_phrase"].split()
        assert len(words) == 24, f"Expected 24 words, got {len(words)}"

        # Address should start with 0x
        assert result["contract_address"].startswith("0x")

    async def test_duplicate_email_rejected(self, wallet_service, conn, test_org):
        """Registering the same email twice in the same org should fail."""
        await wallet_service.register_user(
            conn, org_id=test_org["org_id"], email="dup@example.com",
        )
        with pytest.raises(ValueError, match="already exists"):
            await wallet_service.register_user(
                conn, org_id=test_org["org_id"], email="dup@example.com",
            )

    async def test_register_creates_encrypted_key(self, wallet_service, conn, test_org):
        """Registration should store an encrypted key in the DB."""
        result = await wallet_service.register_user(
            conn, org_id=test_org["org_id"], email="bob@example.com",
        )
        # Check encrypted_keys table
        row = await conn.fetchrow(
            "SELECT * FROM encrypted_keys WHERE wallet_id = $1",
            result["wallet_id"],
        )
        assert row is not None
        assert row["status"] == "active"
        assert row["algorithm"] == "ML-DSA-44"

    async def test_get_user_wallet(self, wallet_service, conn, test_org):
        """Should retrieve full wallet info for a registered user."""
        reg = await wallet_service.register_user(
            conn, org_id=test_org["org_id"], email="carol@example.com",
        )
        wallet_info = await wallet_service.get_full_user_wallet(conn, reg["user_id"])
        assert wallet_info is not None
        assert wallet_info["user"]["email"] == "carol@example.com"
        assert wallet_info["wallet"]["status"] == "active"
        assert wallet_info["account"] is not None

    async def test_list_users(self, wallet_service, conn, test_org):
        """Should list all users for an organization."""
        await wallet_service.register_user(
            conn, org_id=test_org["org_id"], email="user1@example.com",
        )
        await wallet_service.register_user(
            conn, org_id=test_org["org_id"], email="user2@example.com",
        )
        users = await wallet_service.list_users(conn, test_org["org_id"])
        assert len(users) >= 2
