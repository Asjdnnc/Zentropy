"""
QuantumGuard Transfer Handler
==============================
Handles the full STRK token transfer pipeline:
  1. Build transfer transaction data
  2. Sign with ML-DSA-44
  3. Send to Rust prover for verification
  4. Submit execute_with_proof to Starknet via starkli

Each transfer goes through the quantum signature verification pipeline
before being submitted on-chain.

Usage:
    from pqc_backend.transfer_handler import StarknetTransferHandler
    handler = StarknetTransferHandler(key_manager, signer, tx_store, balance_provider)
    result = await handler.execute_transfer("my-wallet", "0xrecipient", "1000000000000000000")
"""
import json
import logging
import os
import subprocess
import time
import uuid
from typing import Optional

from .config import (
    STARKNET_RPC,
    STRK_TOKEN_ADDRESS,
    STARKNET_TX_POLL_INTERVAL,
    STARKNET_TX_MAX_POLLS,
    PROVER_BINARY,
    ALGORITHM_SIG,
)
from .key_manager import QuantumKeyManager
from .signer import QuantumSigner
from .persistence import TransactionStore
from .merkle_audit import MerkleAuditAccumulator
from .utils import b64encode, b64decode, sha256_hex

logger = logging.getLogger("quantumguard.transfer")

# STRK decimals
STRK_DECIMALS = 18


class StarknetTransferHandler:
    """Handles full transfer pipeline: sign → prove → submit to Starknet."""

    def __init__(
        self,
        key_manager: QuantumKeyManager,
        signer: QuantumSigner,
        tx_store: TransactionStore,
        merkle_accumulator: Optional[MerkleAuditAccumulator] = None,
    ):
        self.key_manager = key_manager
        self.signer = signer
        self.tx_store = tx_store
        self.merkle_accumulator = merkle_accumulator

    def _get_starknet_credentials(self) -> tuple[str, str]:
        """Get Starknet private key and account address from env."""
        private_key = os.environ.get("STARKNET_PRIVATE_KEY", "")
        account_addr = os.environ.get("STARKNET_ACCOUNT_ADDRESS", "")
        if not private_key or not account_addr:
            raise RuntimeError(
                "STARKNET_PRIVATE_KEY and STARKNET_ACCOUNT_ADDRESS required"
            )
        return private_key, account_addr

    def strk_to_wei(self, amount_strk: float) -> str:
        """Convert STRK amount to wei string."""
        wei = int(amount_strk * (10 ** STRK_DECIMALS))
        return str(wei)

    def wei_to_strk(self, amount_wei: str) -> float:
        """Convert wei string to STRK float."""
        return int(amount_wei) / (10 ** STRK_DECIMALS)

    async def create_transfer(
        self,
        label: str,
        to_address: str,
        amount_strk: float,
    ) -> dict:
        """
        Prepare a transfer transaction (without executing).

        Returns:
            dict with tx_data, amount_wei, nonce, gas estimate
        """
        # Validate wallet exists and has contract
        identity = self.key_manager.load_identity(label)
        contract_address = identity.get("contract_address")
        if not contract_address:
            raise RuntimeError(
                f"Wallet '{label}' does not have a deployed contract. "
                "Deploy first via wallet creation."
            )

        amount_wei = self.strk_to_wei(amount_strk)

        # Build the transaction payload
        tx_data = {
            "from_contract": contract_address,
            "to": to_address,
            "amount_strk": amount_strk,
            "amount_wei": amount_wei,
            "token": STRK_TOKEN_ADDRESS,
            "label": label,
            "pubkey_hash": identity["pubkey_hash"],
        }

        return {
            "status": "prepared",
            "tx_data": tx_data,
            "amount_wei": amount_wei,
            "amount_strk": f"{amount_strk:.6f}",
            "from_contract": contract_address,
            "to_address": to_address,
        }

    async def execute_transfer(
        self,
        label: str,
        to_address: str,
        amount_strk: float,
        call_prover_fn=None,
    ) -> dict:
        """
        Full transfer pipeline:
          1. Sign the transfer with ML-DSA-44
          2. Prove the signature (Rust prover or Python fallback)
          3. Submit execute_with_proof to Starknet
          4. Poll for confirmation

        Args:
            label: Wallet identity label
            to_address: Recipient Starknet address
            amount_strk: Amount in STRK
            call_prover_fn: Optional async callable for proof generation

        Returns:
            dict with tx_id, status, starknet_tx_hash, etc.
        """
        tx_id = f"tx_{uuid.uuid4().hex[:12]}"

        # Validate inputs
        identity = self.key_manager.load_identity(label)
        contract_address = identity.get("contract_address")
        if not contract_address:
            raise RuntimeError(
                f"Wallet '{label}' has no deployed contract. Deploy first."
            )

        amount_wei = self.strk_to_wei(amount_strk)
        pubkey_hash = identity["pubkey_hash"]

        # Determine nonce from contract nonce (query or use local tx count)
        nonce = self._get_next_nonce(label)

        # Step 1: Build and sign the transaction
        tx_payload = {
            "type": "transfer",
            "from": contract_address,
            "to": to_address,
            "amount_wei": amount_wei,
            "token": STRK_TOKEN_ADDRESS,
            "nonce": nonce,
        }

        sig_result = self.signer.sign_transaction(tx_payload, label=label)

        # Record the signed transaction
        self.tx_store.record_transaction(
            tx_id=tx_id,
            wallet_label=label,
            to_addr=to_address,
            amount=amount_strk,
            nonce=nonce,
            data=json.dumps({"type": "transfer", "token": "STRK"}),
            message_hash=sig_result["message_hash"],
            pubkey_hash=pubkey_hash,
            signature_size=sig_result["signature_size"],
            status="signed",
        )
        logger.info(f"Transfer {tx_id}: signed ({amount_strk} STRK → {to_address[:16]}...)")

        # Step 2: Prove the signature
        if call_prover_fn:
            proof = await call_prover_fn(
                sig_result["message"],
                sig_result["signature"],
                sig_result["public_key"],
            )
        else:
            proof = self._python_fallback_prove(sig_result)

        proof_valid = proof.get("valid", False)
        proof_commitment = proof.get("proof_commitment", "")

        self.tx_store.update_transaction_proof(
            tx_id=tx_id,
            proof_commitment=proof_commitment,
            proof_valid=proof_valid,
        )

        if not proof_valid:
            logger.error(f"Transfer {tx_id}: proof verification FAILED")
            return {
                "status": "proof_failed",
                "tx_id": tx_id,
                "proof_valid": False,
                "error": "Proof verification failed",
            }

        logger.info(f"Transfer {tx_id}: proof verified")

        # Record in Merkle audit trail (immutable, tamper-evident)
        if self.merkle_accumulator:
            merkle_tx = {
                "tx_id": tx_id,
                "wallet_label": label,
                "to_addr": to_address,
                "amount_strk": amount_strk,
                "amount_wei": amount_wei,
                "message_hash": sig_result["message_hash"],
                "pubkey_hash": pubkey_hash,
                "proof_commitment": proof_commitment,
                "proof_valid": proof_valid,
                "timestamp": time.time(),
            }
            self.merkle_accumulator.add_transaction(merkle_tx)
            logger.info(f"Transfer {tx_id}: added to Merkle accumulator")

        # Step 3: Submit to Starknet via starkli invoke
        try:
            starknet_result = await self._submit_transfer(
                contract_address=contract_address,
                to_address=to_address,
                amount_wei=amount_wei,
                proof_commitment=proof_commitment,
                pubkey_hash=pubkey_hash,
                nonce=nonce,
            )

            starknet_tx_hash = starknet_result.get("tx_hash", "")

            self.tx_store.update_transaction_starknet(
                tx_id=tx_id,
                starknet_tx_hash=starknet_tx_hash,
                starknet_status="submitted",
            )

            logger.info(f"Transfer {tx_id}: submitted to Starknet ({starknet_tx_hash})")

            return {
                "status": "submitted",
                "tx_id": tx_id,
                "starknet_tx_hash": starknet_tx_hash,
                "proof_valid": True,
                "proof_commitment": proof_commitment,
                "amount_strk": f"{amount_strk:.6f}",
                "amount_wei": amount_wei,
                "from_contract": contract_address,
                "to_address": to_address,
                "nonce": nonce,
                "explorer_url": f"https://sepolia.starkscan.co/tx/{starknet_tx_hash}",
            }

        except Exception as e:
            self.tx_store.update_transaction_starknet(
                tx_id=tx_id,
                starknet_tx_hash="",
                starknet_status="submission_failed",
                error=str(e),
            )
            logger.error(f"Transfer {tx_id}: Starknet submission failed: {e}")
            return {
                "status": "submission_failed",
                "tx_id": tx_id,
                "proof_valid": True,
                "proof_commitment": proof_commitment,
                "error": str(e),
            }

    async def _submit_transfer(
        self,
        contract_address: str,
        to_address: str,
        amount_wei: str,
        proof_commitment: str,
        pubkey_hash: str,
        nonce: int,
    ) -> dict:
        """Submit the transfer via starkli invoke on execute_with_proof."""
        private_key, account_addr = self._get_starknet_credentials()

        # Truncate to felt252
        proof_felt = "0x" + proof_commitment[:62]
        pubkey_felt = "0x" + pubkey_hash[:62]

        # Build calldata for STRK transfer
        # The execute_with_proof function calls the target with selector+calldata
        # For ERC20 transfer: transfer(recipient, amount_low, amount_high)
        transfer_selector = "0x0083afd3f4caedc6eebf44246fe54e38c95e3179a5ec9ea81740eca5b482d12e"  # transfer

        # Amount as Uint256 (low, high)
        amount_int = int(amount_wei)
        amount_low = hex(amount_int & ((1 << 128) - 1))
        amount_high = hex(amount_int >> 128)

        invoke_result = subprocess.run(
            [
                "starkli", "invoke",
                contract_address,
                "execute_with_proof",
                STRK_TOKEN_ADDRESS,     # to: token contract
                transfer_selector,       # selector: transfer
                "3",                     # calldata length
                to_address,              # calldata[0]: recipient
                amount_low,              # calldata[1]: amount low
                amount_high,             # calldata[2]: amount high
                proof_felt,              # proof_commitment
                pubkey_felt,             # pubkey_hash
                str(nonce),              # nonce
                "--rpc", STARKNET_RPC,
                "--private-key", private_key,
                "--account", account_addr,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if invoke_result.returncode != 0:
            raise RuntimeError(f"Starknet invoke failed: {invoke_result.stderr}")

        # Extract tx hash
        tx_hash = None
        combined = invoke_result.stdout + "\n" + invoke_result.stderr
        for line in combined.splitlines():
            stripped = line.strip()
            if stripped.startswith("0x") and len(stripped) > 10:
                tx_hash = stripped
                break

        return {"tx_hash": tx_hash or "", "status": "submitted"}

    async def get_transfer_status(self, starknet_tx_hash: str) -> dict:
        """Poll Starknet for transaction receipt status."""
        try:
            result = subprocess.run(
                [
                    "starkli", "receipt",
                    starknet_tx_hash,
                    "--rpc", STARKNET_RPC,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0:
                output = result.stdout.upper()
                if "ACCEPTED" in output:
                    return {"status": "confirmed", "receipt": result.stdout.strip()}
                elif "REJECTED" in output:
                    return {"status": "rejected", "receipt": result.stdout.strip()}
                else:
                    return {"status": "pending", "receipt": result.stdout.strip()}
            else:
                return {"status": "pending", "error": result.stderr}

        except Exception as e:
            return {"status": "unknown", "error": str(e)}

    def _get_next_nonce(self, label: str) -> int:
        """
        Get the next nonce for a wallet.
        Uses local transaction count as a simple nonce tracker.
        """
        txs = self.tx_store.list_transactions(wallet_label=label, limit=1000)
        # Count only successfully submitted transactions
        submitted = [t for t in txs if t.get("status") in ("submitted", "confirmed")]
        return len(submitted)

    def _python_fallback_prove(self, sig_result: dict) -> dict:
        """Python-native ML-DSA verification as prover fallback."""
        msg_bytes = b64decode(sig_result["message"])
        sig_bytes = b64decode(sig_result["signature"])
        pk_bytes = b64decode(sig_result["public_key"])

        valid = QuantumSigner.verify_signature(msg_bytes, sig_bytes, pk_bytes)

        return {
            "valid": valid,
            "message_hash": sha256_hex(msg_bytes),
            "signature_hash": sha256_hex(sig_bytes),
            "pubkey_hash": sha256_hex(pk_bytes),
            "proof_commitment": sha256_hex(
                f"{valid}:{sha256_hex(msg_bytes)}:{sha256_hex(sig_bytes)}:{sha256_hex(pk_bytes)}".encode()
            ),
            "prover": "python_fallback",
        }
