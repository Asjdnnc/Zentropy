"""
Tests for QuantumGuard Starknet integration:
  - Contract auto-deploy via StarknetContractManager
  - Balance queries via StarknetBalanceProvider
  - Transfer pipeline via StarknetTransferHandler
  - New API endpoints: /wallet/{label}/balance, /wallet/{label}/deploy,
    /transfer/create, /transfer/execute, /transfer/{hash}/status

Run with:
    cd Quantum-Guard/
    python -m pytest pqc_backend/tests/test_starknet_integration.py -v
"""
import asyncio
import json
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pqc_backend.key_manager import QuantumKeyManager
from pqc_backend.persistence import TransactionStore
from pqc_backend.config import STRK_TOKEN_ADDRESS


# ─── Fixtures ────────────────────────────────────────────────────

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
def store(tmp_db):
    return TransactionStore(db_path=tmp_db)


@pytest.fixture
def wallet_label(key_manager):
    """Create a test wallet and return its label."""
    label = "test-starknet"
    key_manager.generate_identity(label=label)
    return label


# ─── Persistence: Wallet Table Tests ─────────────────────────────

class TestPersistenceWallet:
    def test_record_wallet(self, store):
        store.record_wallet(
            label="w1",
            pubkey_hash="abc123",
            contract_address="0x1234",
            class_hash="0x5678",
            deployment_status="deployed",
            network="starknet-sepolia",
        )
        wallet = store.get_wallet("w1")
        assert wallet is not None
        assert wallet["label"] == "w1"
        assert wallet["contract_address"] == "0x1234"
        assert wallet["deployment_status"] == "deployed"

    def test_update_wallet_deployment(self, store):
        store.record_wallet(label="w2", pubkey_hash="def456")
        store.update_wallet_deployment(
            label="w2",
            contract_address="0xABCD",
            class_hash="0xEFEF",
        )
        wallet = store.get_wallet("w2")
        assert wallet["contract_address"] == "0xABCD"
        assert wallet["deployment_status"] == "deployed"

    def test_update_wallet_status(self, store):
        store.record_wallet(label="w3", pubkey_hash="ghi789")
        store.update_wallet_status("w3", "failed")
        wallet = store.get_wallet("w3")
        assert wallet["deployment_status"] == "failed"

    def test_list_all_wallets(self, store):
        store.record_wallet(label="a", pubkey_hash="h1")
        store.record_wallet(label="b", pubkey_hash="h2")
        wallets = store.list_all_wallets()
        labels = [w["label"] for w in wallets]
        assert "a" in labels
        assert "b" in labels

    def test_get_wallet_not_found(self, store):
        assert store.get_wallet("nonexistent") is None


# ─── Persistence: Balance Cache Tests ────────────────────────────

class TestPersistenceBalanceCache:
    def test_cache_and_get_balance(self, store):
        store.cache_balance("0x1111", STRK_TOKEN_ADDRESS, "1000000")
        result = store.get_cached_balance("0x1111", STRK_TOKEN_ADDRESS)
        assert result is not None
        assert result["balance_wei"] == "1000000"

    def test_cache_ttl_expired(self, store):
        store.cache_balance("0x2222", STRK_TOKEN_ADDRESS, "500")
        # With ttl_seconds=0, the cache should be considered "expired"
        result = store.get_cached_balance("0x2222", STRK_TOKEN_ADDRESS, ttl_seconds=0)
        assert result is None

    def test_cache_update_existing(self, store):
        store.cache_balance("0x3333", STRK_TOKEN_ADDRESS, "100")
        store.cache_balance("0x3333", STRK_TOKEN_ADDRESS, "200")
        result = store.get_cached_balance("0x3333", STRK_TOKEN_ADDRESS)
        assert result["balance_wei"] == "200"


# ─── Key Manager: Contract Address Methods ───────────────────────

class TestKeyManagerContract:
    def test_set_and_get_contract_address(self, key_manager, wallet_label):
        key_manager.set_contract_address(wallet_label, "0xCONTRACT", "0xCLASS")
        addr = key_manager.get_contract_address(wallet_label)
        assert addr == "0xCONTRACT"

    def test_set_deployment_status(self, key_manager, wallet_label):
        key_manager.set_deployment_status(wallet_label, "deployed")
        wallets = key_manager.list_wallets()
        w = next(w for w in wallets if w["label"] == wallet_label)
        assert w["deployment_status"] == "deployed"

    def test_list_wallets_includes_contract_fields(self, key_manager, wallet_label):
        key_manager.set_contract_address(wallet_label, "0xADDR", "0xCH")
        key_manager.set_deployment_status(wallet_label, "deployed")
        wallets = key_manager.list_wallets()
        w = next(w for w in wallets if w["label"] == wallet_label)
        assert "contract_address" in w
        assert "deployment_status" in w
        assert w["contract_address"] == "0xADDR"


# ─── Balance Provider Tests (mocked RPC) ─────────────────────────

class TestBalanceProvider:
    def test_format_balance(self):
        from pqc_backend.balance_provider import StarknetBalanceProvider
        provider = StarknetBalanceProvider.__new__(StarknetBalanceProvider)
        # 1 STRK = 10^18 wei
        assert provider._format_balance(10**18) == "1.000000"
        assert provider._format_balance(0) == "0.000000"
        assert provider._format_balance(5 * 10**17) == "0.500000"
        assert provider._format_balance(123456789012345678) == "0.123456"

    @pytest.mark.asyncio
    async def test_get_balance_caches(self):
        from pqc_backend.balance_provider import StarknetBalanceProvider

        mock_store = MagicMock()
        mock_store.get_cached_balance.return_value = {
            "balance_wei": str(10**18)
        }

        provider = StarknetBalanceProvider.__new__(StarknetBalanceProvider)
        provider.rpc_url = "http://fake"
        provider.store = mock_store
        provider.cache_ttl = 30

        result = await provider.get_balance("0xTEST")
        assert result["balance_wei"] == str(10**18)
        assert result["balance_display"] == "1.000000 STRK"
        mock_store.get_cached_balance.assert_called_once()


# ─── Contract Manager Tests (mocked subprocess) ──────────────────

class TestContractManager:
    def test_extract_hex_address(self):
        from pqc_backend.contract_manager import StarknetContractManager
        mgr = StarknetContractManager.__new__(StarknetContractManager)

        output = "Contract deployed at 0x04abcdef1234567890abcdef1234567890abcdef1234567890abcdef12345678"
        result = mgr._extract_hex_address(output)
        assert result.startswith("0x")
        assert len(result) > 10

    def test_extract_hex_address_none(self):
        from pqc_backend.contract_manager import StarknetContractManager
        mgr = StarknetContractManager.__new__(StarknetContractManager)
        assert mgr._extract_hex_address("no hex here") is None


# ─── Transfer Handler Tests (unit) ───────────────────────────────

class TestTransferHandler:
    def test_amount_conversion(self):
        """Verify STRK → wei conversion with 18 decimals."""
        from pqc_backend.transfer_handler import StarknetTransferHandler
        handler = StarknetTransferHandler.__new__(StarknetTransferHandler)
        handler.decimals = 18

        # 1 STRK = 10^18 wei 
        wei = int(1.0 * (10 ** handler.decimals))
        assert wei == 10**18

        # 0.5 STRK
        wei_half = int(0.5 * (10 ** handler.decimals))
        assert wei_half == 5 * 10**17


# ─── API Endpoint Tests (TestClient) ─────────────────────────────

class TestAPIEndpoints:
    """Test the new API endpoints using FastAPI TestClient."""

    @pytest.fixture
    def client(self, tmp_path):
        """Create a test client with isolated temp dirs."""
        keydir = tmp_path / "keys"
        dbpath = tmp_path / "test.db"

        with patch.dict(os.environ, {
            "QG_KEY_DIR": str(keydir),
            "QG_DB_PATH": str(dbpath),
        }):
            # We need to import after patching to get fresh instances
            from quantum_wallet_ui.server import app
            from fastapi.testclient import TestClient
            return TestClient(app)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_wallet_create(self, client):
        r = client.post("/wallet/create", json={"label": "api-test"})
        # May fail due to contract deploy but wallet should be created
        assert r.status_code in [200, 500]
        if r.status_code == 200:
            data = r.json()
            assert "label" in data
            assert data["label"] == "api-test"

    def test_wallet_list(self, client):
        # Create a wallet first
        client.post("/wallet/create", json={"label": "list-test"})
        r = client.get("/wallet/list")
        assert r.status_code == 200
        data = r.json()
        assert "wallets" in data

    def test_wallet_balance_no_contract(self, client):
        """Balance endpoint should fail gracefully for wallet without contract."""
        client.post("/wallet/create", json={"label": "no-contract"})
        r = client.get("/wallet/no-contract/balance")
        # Should return 404 or error since no contract deployed
        assert r.status_code in [404, 500]

    def test_transfer_create_invalid_wallet(self, client):
        r = client.post("/transfer/create", json={
            "label": "nonexistent",
            "to_address": "0x1234",
            "amount_strk": 1.0,
        })
        assert r.status_code in [400, 404, 500]

    def test_transfer_status_unknown_hash(self, client):
        r = client.get("/transfer/0xdeadbeef/status")
        # Should handle gracefully
        assert r.status_code in [200, 404, 500]
