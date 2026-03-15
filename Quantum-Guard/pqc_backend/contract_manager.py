"""
QuantumGuard Contract Manager
==============================
Handles automated deployment of QuantumGuardAccount contracts to Starknet Sepolia.
Each wallet (ML-DSA identity) gets its own contract instance (1:1 mapping).

Usage:
    from pqc_backend.contract_manager import StarknetContractManager
    mgr = StarknetContractManager(key_manager, tx_store)
    result = await mgr.deploy_wallet_contract("my-wallet")
"""
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from .config import (
    STARKNET_RPC,
    CONTRACT_DIR,
    SIERRA_FILE,
    DEPLOY_SCRIPT_PATH,
)
from .key_manager import QuantumKeyManager
from .persistence import TransactionStore

logger = logging.getLogger("quantumguard.contract")


class StarknetContractManager:
    """Manages deployment & querying of QuantumGuardAccount contracts."""

    def __init__(
        self,
        key_manager: QuantumKeyManager,
        tx_store: TransactionStore,
    ):
        self.key_manager = key_manager
        self.tx_store = tx_store

    def _get_starknet_credentials(self) -> tuple[str, str]:
        """Get Starknet private key and account address from env."""
        private_key = os.environ.get("STARKNET_PRIVATE_KEY", "")
        account_addr = os.environ.get("STARKNET_ACCOUNT_ADDRESS", "")
        if not private_key or not account_addr:
            raise RuntimeError(
                "STARKNET_PRIVATE_KEY and STARKNET_ACCOUNT_ADDRESS must be set. "
                "Get testnet STRK from https://faucet.starknet.io"
            )
        return private_key, account_addr

    def _ensure_contract_built(self):
        """Build the Cairo contract if Sierra file doesn't exist."""
        if SIERRA_FILE.exists():
            return

        logger.info("Building Cairo contract with scarb...")
        result = subprocess.run(
            ["scarb", "build"],
            cwd=str(CONTRACT_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Contract build failed: {result.stderr}")

        if not SIERRA_FILE.exists():
            raise RuntimeError(
                "Sierra file not found after build. "
                "Check scarb configuration and build output."
            )

    def _extract_hex_address(self, output: str) -> Optional[str]:
        """Extract a long hex address (0x...) from CLI output."""
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("0x") and len(stripped) >= 60:
                return stripped
            # Also search within lines
            parts = stripped.split()
            for part in parts:
                clean = part.strip(".,;:\"'()")
                if clean.startswith("0x") and len(clean) >= 60:
                    return clean
        return None

    def _declare_contract(self, private_key: str, account_addr: str) -> str:
        """Declare the contract class on Starknet. Returns class_hash."""
        self._ensure_contract_built()

        declare_result = subprocess.run(
            [
                "starkli", "declare",
                str(SIERRA_FILE),
                "--rpc", STARKNET_RPC,
                "--private-key", private_key,
                "--account", account_addr,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        combined = declare_result.stdout + "\n" + declare_result.stderr
        class_hash = self._extract_hex_address(combined)

        if not class_hash:
            # May already be declared
            if "already declared" in declare_result.stderr.lower():
                # Try extracting from the error message
                import re
                match = re.search(r'0x[0-9a-fA-F]{50,}', declare_result.stderr)
                if match:
                    class_hash = match.group(0)

        if not class_hash:
            raise RuntimeError(f"Failed to declare contract: {declare_result.stderr}")

        logger.info(f"Contract class declared: {class_hash[:20]}...")
        return class_hash

    def _deploy_instance(
        self,
        class_hash: str,
        owner_hash_felt: str,
        private_key: str,
        account_addr: str,
    ) -> str:
        """Deploy a new contract instance. Returns contract address."""
        deploy_result = subprocess.run(
            [
                "starkli", "deploy",
                class_hash,
                owner_hash_felt,    # constructor arg: owner_pubkey_hash
                account_addr,       # constructor arg: initial_prover
                "--rpc", STARKNET_RPC,
                "--private-key", private_key,
                "--account", account_addr,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        combined = deploy_result.stdout + "\n" + deploy_result.stderr
        contract_address = self._extract_hex_address(combined)

        if not contract_address:
            raise RuntimeError(f"Failed to deploy contract: {deploy_result.stderr}")

        logger.info(f"Contract deployed at: {contract_address}")
        return contract_address

    async def deploy_wallet_contract(self, label: str) -> dict:
        """
        Deploy a QuantumGuardAccount contract for a wallet identity.

        Steps:
          1. Load the wallet's pubkey_hash
          2. Declare the contract class (if not already declared)
          3. Deploy a new instance with pubkey_hash as constructor arg
          4. Store contract address in identity file + database

        Returns:
            dict with contract_address, class_hash, deployment status
        """
        # Check if wallet exists
        identity = self.key_manager.load_identity(label)
        owner_hash = identity["pubkey_hash"]

        # Check if already deployed
        existing_addr = identity.get("contract_address")
        if existing_addr:
            return {
                "status": "already_deployed",
                "contract_address": existing_addr,
                "class_hash": identity.get("class_hash", ""),
                "label": label,
            }

        # Mark as deploying
        self.key_manager.set_deployment_status(label, "deploying")
        self.tx_store.record_wallet(
            label=label,
            pubkey_hash=owner_hash,
            deployment_status="deploying",
        )

        try:
            private_key, account_addr = self._get_starknet_credentials()

            # Truncate to felt252 (31 bytes = 62 hex chars)
            owner_hash_felt = "0x" + owner_hash[:62]

            # Step 1: Declare
            class_hash = self._declare_contract(private_key, account_addr)

            # Step 2: Deploy
            contract_address = self._deploy_instance(
                class_hash, owner_hash_felt, private_key, account_addr
            )

            # Step 3: Persist in identity file
            self.key_manager.set_contract_address(label, contract_address, class_hash)

            # Step 4: Persist in database
            self.tx_store.update_wallet_deployment(
                label=label,
                contract_address=contract_address,
                class_hash=class_hash,
                deployment_status="deployed",
            )

            # Also record in deployments table
            self.tx_store.record_deployment(
                contract_address=contract_address,
                class_hash=class_hash,
                owner_pubkey_hash=owner_hash,
                owner_label=label,
                network="starknet-sepolia",
                rpc=STARKNET_RPC,
                deployed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

            logger.info(f"Wallet '{label}' contract deployed at {contract_address}")

            return {
                "status": "deployed",
                "contract_address": contract_address,
                "class_hash": class_hash,
                "label": label,
                "network": "starknet-sepolia",
                "owner_pubkey_hash": owner_hash,
            }

        except Exception as e:
            # Mark as failed
            self.key_manager.set_deployment_status(label, "failed")
            self.tx_store.update_wallet_status(label, "failed")
            logger.error(f"Deployment failed for wallet '{label}': {e}")
            raise

    def get_contract_address(self, label: str) -> Optional[str]:
        """Get the deployed contract address for a wallet."""
        return self.key_manager.get_contract_address(label)

    def get_deployment_status(self, label: str) -> dict:
        """Get deployment status for a wallet."""
        try:
            identity = self.key_manager.load_identity(label)
            return {
                "label": label,
                "contract_address": identity.get("contract_address"),
                "class_hash": identity.get("class_hash"),
                "deployment_status": identity.get("deployment_status", "pending"),
                "deployed_at": identity.get("deployed_at"),
            }
        except FileNotFoundError:
            return {"label": label, "deployment_status": "not_found"}
