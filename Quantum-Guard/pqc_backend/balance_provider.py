"""
QuantumGuard Balance Provider
==============================
Fetches STRK token balances from Starknet Sepolia RPC.
Uses JSON-RPC calls to query balanceOf on the STRK token contract.

The balance is cached locally with a configurable TTL to avoid
hammering the RPC endpoint.

Usage:
    from pqc_backend.balance_provider import StarknetBalanceProvider
    provider = StarknetBalanceProvider(tx_store)
    balance = await provider.get_balance("0x123...")
"""
import json
import logging
import time
from typing import Optional

import httpx

from .config import STARKNET_RPC, STRK_TOKEN_ADDRESS, BALANCE_CACHE_TTL
from .persistence import TransactionStore

logger = logging.getLogger("quantumguard.balance")

# STRK has 18 decimals
STRK_DECIMALS = 18


class StarknetBalanceProvider:
    """Fetches and caches STRK token balances from Starknet RPC."""

    def __init__(self, tx_store: TransactionStore):
        self.tx_store = tx_store
        self.rpc_url = STARKNET_RPC
        self.strk_address = STRK_TOKEN_ADDRESS
        self.cache_ttl = BALANCE_CACHE_TTL

    async def get_balance(
        self,
        contract_address: str,
        token_address: Optional[str] = None,
        force_refresh: bool = False,
    ) -> dict:
        """
        Get the STRK token balance for a contract address.

        Args:
            contract_address: The deployed QuantumGuardAccount address
            token_address: Token contract address (defaults to STRK)
            force_refresh: Skip cache and query Starknet directly

        Returns:
            dict with balance_wei, balance_strk, contract_address
        """
        token = token_address or self.strk_address

        # Check cache first
        if not force_refresh:
            cached = self.tx_store.get_cached_balance(
                contract_address, token, self.cache_ttl
            )
            if cached is not None:
                return self._format_balance(cached, contract_address)

        # Query Starknet RPC
        try:
            balance_wei = await self._query_balance(contract_address, token)
        except Exception as e:
            logger.warning(f"Failed to fetch balance for {contract_address[:16]}...: {e}")
            # Return cached value even if expired, or 0
            cached = self.tx_store.get_cached_balance(
                contract_address, token, ttl=float("inf")
            )
            balance_wei = cached if cached is not None else "0"
            return self._format_balance(balance_wei, contract_address, stale=True)

        # Update cache
        self.tx_store.cache_balance(contract_address, balance_wei, token)
        return self._format_balance(balance_wei, contract_address)

    async def _query_balance(self, contract_address: str, token_address: str) -> str:
        """
        Query balanceOf(contract_address) on the STRK token contract
        via starknet_call JSON-RPC.
        """
        # Starknet uses felt252 for addresses — ensure 0x prefix
        if not contract_address.startswith("0x"):
            contract_address = "0x" + contract_address

        # balanceOf selector: sn_keccak("balanceOf") truncated to felt252
        # Standard ERC20 selector for balanceOf
        balance_of_selector = "0x02e4263afad30923c891518314c3c95dbe830a16874e8abc5777a9a20b54c76e"

        payload = {
            "jsonrpc": "2.0",
            "method": "starknet_call",
            "params": [
                {
                    "contract_address": token_address,
                    "entry_point_selector": balance_of_selector,
                    "calldata": [contract_address],
                },
                "latest",
            ],
            "id": 1,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self.rpc_url, json=payload)
            response.raise_for_status()
            data = response.json()

        if "error" in data:
            error_msg = data["error"].get("message", str(data["error"]))
            raise RuntimeError(f"Starknet RPC error: {error_msg}")

        result = data.get("result", [])
        if not result:
            return "0"

        # STRK balance is Uint256 (two felt252: low, high)
        # For most balances, high will be 0
        low = int(result[0], 16) if result[0] else 0
        high = int(result[1], 16) if len(result) > 1 and result[1] else 0
        balance_wei = str(low + (high << 128))

        logger.debug(f"Balance for {contract_address[:16]}...: {balance_wei} wei")
        return balance_wei

    def _format_balance(
        self,
        balance_wei: str,
        contract_address: str,
        stale: bool = False,
    ) -> dict:
        """Format balance as both wei and human-readable STRK."""
        wei = int(balance_wei)
        strk = wei / (10 ** STRK_DECIMALS)

        return {
            "contract_address": contract_address,
            "balance_wei": balance_wei,
            "balance_strk": f"{strk:.6f}",
            "balance_display": self._display_balance(strk),
            "decimals": STRK_DECIMALS,
            "token": "STRK",
            "stale": stale,
        }

    @staticmethod
    def _display_balance(strk: float) -> str:
        """Human-friendly balance display."""
        if strk == 0:
            return "0 STRK"
        if strk < 0.000001:
            return f"<0.000001 STRK"
        if strk < 1:
            return f"{strk:.6f} STRK"
        if strk < 1000:
            return f"{strk:.4f} STRK"
        return f"{strk:,.2f} STRK"
