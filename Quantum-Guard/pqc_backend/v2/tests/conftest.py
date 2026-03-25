"""
Shared fixtures for v2 tests.
Sets up a temp SQLite database and service instances.

All service methods take `conn` as first argument.
The `conn` fixture provides a DB connection from the pool.
"""

import asyncio
import os
import tempfile
import pytest
import pytest_asyncio

# ── Force test environment BEFORE any imports ─────────────
_TMPDIR = tempfile.mkdtemp(prefix="qg_test_")
_TEST_DB_PATH = os.path.join(_TMPDIR, "test.db")

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["QUANTUMGUARD_MASTER_SECRET"] = "test_master_secret_for_unit_tests_only_not_production"
os.environ["BOOTSTRAP_SECRET"] = "test_bootstrap_secret"
os.environ["ENV"] = "test"
os.environ["ALLOW_INSECURE_PQC_FALLBACK"] = "1"
os.environ.setdefault("STARKNET_RPC", "https://test-rpc.example.com")
os.environ.setdefault("STARKNET_PRIVATE_KEY", "0xTEST")
os.environ.setdefault("STARKNET_ACCOUNT_ADDRESS", "0xTEST")


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def _init_db():
    """One-time DB init: create pool and run migrations."""
    from pqc_backend.v2.db.connection import get_pool, close_pool
    from pqc_backend.v2.db.migrations import run_migrations

    pool = await get_pool()
    await run_migrations()
    yield pool
    await close_pool()
    # Cleanup temp DB
    try:
        os.unlink(_TEST_DB_PATH)
        os.rmdir(_TMPDIR)
    except OSError:
        pass


@pytest_asyncio.fixture
async def conn(_init_db):
    """Get a database connection from the pool."""
    async with _init_db.acquire() as c:
        yield c


@pytest_asyncio.fixture
def key_service():
    """KeyService instance."""
    from pqc_backend.v2.services.key_service import KeyService
    return KeyService()


@pytest_asyncio.fixture
def audit_service():
    """AuditService instance (stateless, takes conn per call)."""
    from pqc_backend.v2.services.audit_service import AuditService
    return AuditService()


@pytest_asyncio.fixture
def wallet_service(key_service, audit_service):
    """WalletService instance with dependencies."""
    from pqc_backend.v2.services.wallet_service import WalletService
    return WalletService(key_service=key_service, audit_service=audit_service)


@pytest_asyncio.fixture
def merkle_service(audit_service):
    """MerkleService instance with temp storage."""
    from pqc_backend.v2.services.merkle_service import MerkleService
    return MerkleService(storage_dir=os.path.join(_TMPDIR, "merkle"), audit_service=audit_service)


@pytest_asyncio.fixture
def transaction_service(key_service, audit_service, merkle_service):
    """TransactionService instance with dependencies."""
    from pqc_backend.v2.services.transaction_service import TransactionService
    return TransactionService(
        key_service=key_service,
        audit_service=audit_service,
        merkle_service=merkle_service,
    )


@pytest_asyncio.fixture
async def test_org(conn, wallet_service):
    """Create a test organization and return its dict."""
    result = await wallet_service.create_organization(conn, "Test Org", "test-org@example.com")
    return result
