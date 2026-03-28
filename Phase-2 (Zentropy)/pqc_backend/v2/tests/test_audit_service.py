"""
Tests for AuditService — hash-chained tamper-evident logging.
"""

import pytest


@pytest.mark.asyncio
class TestAuditLogging:
    """Test audit log creation and querying."""

    async def test_log_creates_entry(self, audit_service, conn, test_org):
        """Should create an audit log entry in the database."""
        org_id = test_org["org_id"]

        await audit_service.log(
            conn,
            org_id=org_id,
            user_id=None,
            entity_type="user",
            entity_id="test-user-123",
            action="USER_CREATED",
            details={"note": "Test user created"},
        )
        # Query back
        logs = await audit_service.get_log(conn, org_id=org_id, entity_type="user")
        assert len(logs) >= 1
        entry = logs[0]
        assert entry["action"] == "USER_CREATED"
        assert entry["entity_id"] == "test-user-123"

    async def test_log_entries_are_hash_chained(self, audit_service, conn, test_org):
        """Each log entry's prev_hash should reference the previous entry."""
        org_id = test_org["org_id"]

        await audit_service.log(
            conn, org_id, None, "test", "chain-test", "ACTION_1",
        )
        await audit_service.log(
            conn, org_id, None, "test", "chain-test", "ACTION_2",
        )
        logs = await audit_service.get_log(conn, org_id=org_id, entity_type="test")
        assert len(logs) >= 2

        # The second entry should have a non-genesis prev_hash
        has_prev = any(
            log.get("previous_log_hash") and log["previous_log_hash"] != "genesis"
            for log in logs
        )
        assert has_prev, "At least one entry should chain to a previous hash"


@pytest.mark.asyncio
class TestAuditChainIntegrity:
    """Test hash chain verification."""

    async def test_verify_intact_chain(self, audit_service, conn, test_org):
        """A chain with no tampering should verify successfully."""
        org_id = test_org["org_id"]

        await audit_service.log(conn, org_id, None, "integrity", "verify-test", "STEP_1")
        await audit_service.log(conn, org_id, None, "integrity", "verify-test", "STEP_2")
        await audit_service.log(conn, org_id, None, "integrity", "verify-test", "STEP_3")

        result = await audit_service.verify_chain_integrity(conn, org_id)
        assert result["valid"], f"Chain should be valid, got: {result}"
        assert result["checked"] >= 3
