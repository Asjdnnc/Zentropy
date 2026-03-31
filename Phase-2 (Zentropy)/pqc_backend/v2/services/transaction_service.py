"""
QuantumGuard v2 — Transaction Service
========================================
Full transfer pipeline for a custodial multi-user system:

  1. Validate user & wallet ownership
  2. Build canonical transaction payload
  3. Sign with Dilithium (via encrypted key from DB)
  4. Generate proof commitment (Rust prover or Python fallback)
  5. Record in DB
  6. Add to Merkle batch
  7. Submit to Starknet via starkli
  8. Update status + audit log

Each step is atomic with respect to the database transaction.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from collections import deque
from typing import Any, Callable, Optional

import httpx

from ..models.enums import (
    TransactionStatus, AuditAction, AuditEntityType, STRK_DECIMALS,
)
from .key_service import KeyService
from .starknet_felt_utils import pubkey_hash_to_felt
from .audit_service import AuditService

logger = logging.getLogger("quantumguard.tx_service")

ERC20_TRANSFER_EVENT_SELECTOR = (
    "0x0099cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"
)

# Global in-memory log buffer for the Live Prover Telemetry UI
prover_telemetry_logs = deque(maxlen=20)

def push_telemetry(msg: str, level: str = "INFO"):
    from datetime import datetime
    colors = {
        "INFO": "blue",
        "WARN": "yellow",
        "SUCCESS": "green",
        "MERKLE": "purple",
        "ERROR": "red"
    }
    color = colors.get(level, "gray")
    ts = datetime.utcnow().strftime("%H:%M:%S")
    formatted = f"<span class='text-gray-500 mr-3'>[{ts}]</span><span class='text-{color}-400'>[{level}]</span> {msg}"
    prover_telemetry_logs.append(formatted)


class TransactionService:
    """Orchestrates the full sign → prove → submit pipeline."""

    def __init__(
        self,
        key_service: Optional[KeyService] = None,
        audit_service: Optional[AuditService] = None,
        merkle_service=None,
    ):
        self.key_svc = key_service or KeyService()
        self.audit_svc = audit_service or AuditService()
        self.merkle_svc = merkle_service  # Set after init to avoid circular import

    # ── Transfer Execution ────────────────────────────────────

    async def execute_transfer(
        self,
        conn,
        user_id: str,
        org_id: str,
        to_address: str,
        amount_strk: float,
        mpin: str,
        call_prover_fn: Optional[Callable] = None,
        ip_address: Optional[str] = None,
    ) -> dict:
        """
        Full transfer pipeline.
        Returns a result dict with tx_id, status, proof info, etc.
        """
        tx_id = f"tx_{uuid.uuid4().hex[:16]}"

        # 1. FETCH USER WALLET + ACCOUNT
        user_wallet = await self._get_user_wallet_or_fail(conn, user_id, org_id)
        wallet = user_wallet["wallet"]
        account = user_wallet["account"]
        wallet_id = wallet["wallet_id"]
        account_id = account["account_id"]
        contract_address = account["account_address"]

        # Validate MPIN
        mpin_hash = wallet.get("mpin_hash")
        if not mpin_hash:
            return {
                "tx_id": tx_id,
                "status": "unauthorized",
                "proof_valid": False,
                "error": "MPIN is not configured for this wallet. Please set an MPIN first.",
            }
        
        salt = wallet_id.encode('utf-8')
        expected_hash = hashlib.pbkdf2_hmac('sha256', mpin.encode('utf-8'), salt, 100000).hex()
        if expected_hash != mpin_hash:
            return {
                "tx_id": tx_id,
                "status": "unauthorized",
                "proof_valid": False,
                "error": "Invalid MPIN provided.",
            }

        deployment_status = (account.get("deployment_status") or "").strip().lower()
        if deployment_status != "deployed":
            return {
                "tx_id": tx_id,
                "status": "account_not_deployed",
                "proof_valid": False,
                "error": "Sender wallet is not deployed on Starknet yet. Wait for deployment to complete.",
            }

        # CRITICAL VALIDATION: Reject if using factory address instead of deployed account
        FACTORY_ADDRESS = "0x06c7f300f61309e954c1f56b5bad6b71af50d087ba8f8286ffbbad233bf41e21"
        if contract_address and contract_address.lower() == FACTORY_ADDRESS.lower():
            logger.error(
                "CRITICAL: Attempt to send tokens from factory contract address. "
                "Account %s wallet %s has factory address stored instead of deployed account address. "
                "This is a deployment error requiring account redeployment.",
                account_id, wallet_id
            )
            return {
                "tx_id": tx_id,
                "status": "deployment_error",
                "proof_valid": False,
                "error": (
                    "Account deployment incomplete: stored address is factory contract, not your deployed account. "
                    "This prevents token transfers. Deployment must be retried. "
                    "Please contact support or retry wallet deployment."
                ),
            }

        class_guard = await self._validate_sender_account_class_hash(
            contract_address=contract_address,
            stored_class_hash=account.get("contract_class_hash"),
        )
        if class_guard.get("status") == "error":
            return {
                "tx_id": tx_id,
                "status": "deployment_error",
                "proof_valid": False,
                "error": class_guard.get("error") or "Sender account class hash validation failed",
            }

        # 2. COMPUTE AMOUNTS
        amount_wei = str(int(amount_strk * (10 ** STRK_DECIMALS)))
        nonce = account["nonce"]

        # 3. BUILD CANONICAL TX
        strk_token = os.environ.get(
            "STRK_TOKEN_ADDRESS",
            "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
        )
        tx_payload = {
            "type": "transfer",
            "from": contract_address,
            "to": to_address,
            "amount_wei": amount_wei,
            "token": strk_token,
            "nonce": nonce,
        }
        canonical_json = json.dumps(tx_payload, sort_keys=True, separators=(",", ":"))
        message_bytes = canonical_json.encode("utf-8")
        message_hash = hashlib.sha256(message_bytes).hexdigest()

        # 4. SIGN WITH DILITHIUM (encrypted key from DB)
        enc_key = await self.key_svc.get_active_encrypted_key(conn, wallet_id)
        if not enc_key:
            raise RuntimeError(f"No active signing key for wallet {wallet_id}")

        enc_key_dict = dict(enc_key)
        signature = self.key_svc.sign_message(
            message_bytes, enc_key_dict["encrypted_key_material"]
        )
        sig_size = len(signature)

        # 5. RECORD TRANSACTION (status=signed)
        now = time.time()
        await conn.execute(
            """INSERT INTO transactions
               (tx_id, account_id, to_address, amount_wei, token_address,
                message_hash, signature_size, nonce,
                status, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
            tx_id, account_id, to_address, amount_wei, strk_token,
            message_hash, sig_size, nonce,
            TransactionStatus.SIGNED.value, now,
        )

        # Audit signing
        await self.audit_svc.log(
            conn, org_id, user_id,
            AuditEntityType.TRANSACTION.value, tx_id,
            AuditAction.TRANSACTION_SIGNED.value,
            details={"to": to_address, "amount_strk": str(amount_strk), "nonce": nonce},
            ip_address=ip_address,
        )

        logger.info("TX %s signed: %.6f STRK → %s", tx_id, amount_strk, to_address[:16])

        # 6. PROVE
        pk_bytes = base64.b64decode(account["public_key_pq"])
        proof = await self._prove(
            message_bytes, signature, pk_bytes, call_prover_fn
        )
        proof_valid = proof.get("valid", False)
        proof_commitment = proof.get("proof_commitment", "")
        prover_backend = proof.get("prover_backend") or proof.get("prover") or "unknown"
        prover_fallback_reason = proof.get("prover_fallback_reason")

        await conn.execute(
            """UPDATE transactions
               SET proof_commitment = $1, proof_valid = $2, status = $3,
                   prover_backend = $4, prover_fallback_reason = $5
               WHERE tx_id = $6""",
            proof_commitment, int(proof_valid),
            TransactionStatus.PROVED.value if proof_valid else TransactionStatus.FAILED.value,
            prover_backend,
            prover_fallback_reason,
            tx_id,
        )

        if not proof_valid:
            logger.error("TX %s: proof FAILED", tx_id)
            await self.audit_svc.log(
                conn, org_id, user_id,
                AuditEntityType.TRANSACTION.value, tx_id,
                "transaction_proof_failed",
                details={"proof_commitment": proof_commitment},
            )
            return {
                "tx_id": tx_id,
                "status": "proof_failed",
                "proof_valid": False,
                "error": "Proof verification failed",
            }

        logger.info("TX %s: proof verified (%s)", tx_id, proof_commitment[:16])

        await self.audit_svc.log(
            conn, org_id, user_id,
            AuditEntityType.TRANSACTION.value, tx_id,
            AuditAction.TRANSACTION_PROVED.value,
            details={"proof_commitment": proof_commitment},
        )

        # 7. ADD TO MERKLE BATCH
        batch_id = None
        if self.merkle_svc:
            batch_id = await self.merkle_svc.add_transaction_to_batch(
                conn, org_id, tx_id, message_hash, proof_commitment
            )

        # 8. SUBMIT TO STARKNET
        starknet_tx_hash = ""
        explorer_url = ""
        submission_mode = self._resolve_submission_mode(account.get("sender_model"))
        sender_account_address = contract_address
        submitted_by_address = (
            account.get("submitter_address")
            or self._resolve_submitter_identity_from_env()
        )
        submitter_private_key = self._resolve_submitter_private_key(
            submission_mode=submission_mode,
            encrypted_submitter_private_key=account.get("submitter_private_key_encrypted"),
        )
        try:
            starknet_result = await self._submit_to_starknet(
                contract_address=contract_address,
                to_address=to_address,
                amount_wei=amount_wei,
                proof_commitment=proof_commitment,
                pubkey_hash=account["public_key_pq_hash"],
                nonce=nonce,
                submission_mode=submission_mode,
                submitter_address=account.get("submitter_address"),
                submitter_account_config=account.get("submitter_account_config"),
                submitter_private_key=submitter_private_key,
            )
            starknet_tx_hash = starknet_result.get("tx_hash", "")
            submission_mode = starknet_result.get("submission_mode", submission_mode)
            sender_account_address = starknet_result.get("sender_account_address", sender_account_address)
            submitted_by_address = starknet_result.get("submitted_by_address", submitted_by_address)
            if starknet_tx_hash:
                explorer_url = f"https://sepolia.voyager.online/tx/{starknet_tx_hash}"

            await conn.execute(
                """UPDATE transactions
                   SET tx_hash = $1, status = $2, starknet_status = $3,
                       submission_mode = $4, sender_account_address = $5, submitted_by_address = $6
                   WHERE tx_id = $7""",
                starknet_tx_hash,
                TransactionStatus.SUBMITTED.value,
                "submitted",
                submission_mode,
                sender_account_address,
                submitted_by_address,
                tx_id,
            )

            # Increment nonce
            await conn.execute(
                "UPDATE accounts SET nonce = nonce + 1, updated_at = $1 WHERE account_id = $2",
                time.time(), account_id,
            )

            await self.audit_svc.log(
                conn, org_id, user_id,
                AuditEntityType.TRANSACTION.value, tx_id,
                AuditAction.TRANSACTION_SUBMITTED.value,
                details={"starknet_tx_hash": starknet_tx_hash},
            )

            logger.info("TX %s submitted to Starknet: %s", tx_id, starknet_tx_hash)

        except Exception as e:
            await conn.execute(
                """UPDATE transactions
                   SET status = $1, starknet_status = $2, error_message = $3,
                       submission_mode = $4, sender_account_address = $5, submitted_by_address = $6
                   WHERE tx_id = $7""",
                TransactionStatus.FAILED.value,
                "submission_failed",
                str(e),
                submission_mode,
                sender_account_address,
                submitted_by_address,
                tx_id,
            )
            logger.error("TX %s Starknet submission failed: %s", tx_id, e)
            return {
                "tx_id": tx_id,
                "status": "submission_failed",
                "proof_valid": True,
                "prover_backend": prover_backend,
                "proof_commitment": proof_commitment,
                "submission_mode": submission_mode,
                "sender_account_address": sender_account_address,
                "submitted_by_address": submitted_by_address,
                "error": str(e),
            }

        return {
            "tx_id": tx_id,
            "starknet_tx_hash": starknet_tx_hash,
            "status": "submitted",
            "proof_valid": True,
            "prover_backend": prover_backend,
            "proof_commitment": proof_commitment,
            "batch_id": batch_id,
            "to_address": to_address,
            "amount_strk": f"{amount_strk:.6f}",
            "amount_wei": amount_wei,
            "submission_mode": submission_mode,
            "sender_account_address": sender_account_address,
            "submitted_by_address": submitted_by_address,
            "explorer_url": explorer_url,
        }

    # ── Helpers ───────────────────────────────────────────────

    async def _get_user_wallet_or_fail(self, conn, user_id: str, org_id: str) -> dict:
        """Fetch user, wallet, account constrained to organization ownership."""
        user = await conn.fetchrow(
            "SELECT user_id FROM users WHERE user_id = $1 AND org_id = $2",
            user_id,
            org_id,
        )
        if not user:
            raise RuntimeError("User not found for organization")

        wallet = await conn.fetchrow(
            "SELECT * FROM wallets WHERE user_id = $1", user_id
        )
        if not wallet:
            raise RuntimeError(f"No wallet found for user {user_id}")

        wallet_dict = dict(wallet)
        account = await conn.fetchrow(
            "SELECT * FROM accounts WHERE wallet_id = $1", wallet_dict["wallet_id"]
        )
        if not account:
            raise RuntimeError(f"No account found for wallet {wallet_dict['wallet_id']}")

        return {"wallet": wallet_dict, "account": dict(account)}

    async def _prove(
        self,
        message: bytes,
        signature: bytes,
        public_key: bytes,
        call_prover_fn: Optional[Callable] = None,
    ) -> dict:
        """Generate proof commitment via Rust prover or Python fallback."""
        fallback_reasons: list[str] = []

        if call_prover_fn:
            try:
                proof = await call_prover_fn(
                    base64.b64encode(message).decode(),
                    base64.b64encode(signature).decode(),
                    base64.b64encode(public_key).decode(),
                )
                if isinstance(proof, dict):
                    proof.setdefault("prover_backend", "injected")
                    proof.setdefault("prover_fallback_reason", None)
                return proof
            except Exception as e:
                fallback_reasons.append(f"injected_prover_failed: {e}")
                logger.warning("Rust prover failed, falling back to Python: %s", e)

        prover_url = self._resolve_prover_url()
        if prover_url:
            try:
                proof = await self._prove_via_http(prover_url, message, signature, public_key)
                proof["prover"] = proof.get("prover", "rust_http")
                proof.setdefault("prover_backend", "rust_http")
                proof.setdefault(
                    "prover_fallback_reason",
                    "; ".join(fallback_reasons) if fallback_reasons else None,
                )
                return proof
            except Exception as e:
                fallback_reasons.append(f"http_prover_failed: {e}")
                logger.warning("HTTP prover failed, falling back to Python: %s", e)
        else:
            fallback_reasons.append("http_prover_not_configured")

        # Python fallback
        valid = self.key_svc.verify_signature(message, signature, public_key)
        msg_hash = hashlib.sha256(message).hexdigest()
        sig_hash = hashlib.sha256(signature).hexdigest()
        pk_hash = hashlib.sha256(public_key).hexdigest()
        commitment = hashlib.sha256(
            f"{valid}:{msg_hash}:{sig_hash}:{pk_hash}".encode()
        ).hexdigest()

        return {
            "valid": valid,
            "proof_commitment": commitment,
            "message_hash": msg_hash,
            "signature_hash": sig_hash,
            "pubkey_hash": pk_hash,
            "prover": "python_fallback",
            "prover_backend": "python_fallback",
            "prover_fallback_reason": "; ".join(fallback_reasons) if fallback_reasons else None,
        }

    async def _prove_via_http(
        self,
        prover_url: str,
        message: bytes,
        signature: bytes,
        public_key: bytes,
    ) -> dict:
        timeout = float(os.environ.get("PROVER_TIMEOUT_SECONDS", "8"))
        endpoint = f"{prover_url.rstrip('/')}/verify"
        
        sig_size = len(signature)
        push_telemetry(f"Routing ML-DSA-44 payload to Rust Co-Processor...", "INFO")
        push_telemetry(f"Ingesting raw payload (Size: {sig_size} bytes).", "WARN")

        payload = {
            "message": base64.b64encode(message).decode(),
            "signature": base64.b64encode(signature).decode(),
            "public_key": base64.b64encode(public_key).decode(),
        }
        
        start_time = time.time()
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
        
        elapsed = (time.time() - start_time) * 1000
        proof = response.json()
        
        if not isinstance(proof, dict):
            push_telemetry("Invalid prover response payload", "ERROR")
            raise RuntimeError("Invalid prover response payload")
        if "valid" not in proof or "proof_commitment" not in proof:
            push_telemetry("Incomplete prover response", "ERROR")
            raise RuntimeError("Incomplete prover response")
            
        if proof.get("valid"):
            push_telemetry(f"Signature Valid. O(1) Proof Gen Time: {elapsed:.2f}ms.", "SUCCESS")
            push_telemetry(f"Hashing leaf into Merkle batch pool...", "MERKLE")
        else:
            push_telemetry("Rust Prover rejected mathematical signature natively.", "ERROR")
            
        return proof

    async def _submit_to_starknet(
        self,
        contract_address: str,
        to_address: str,
        amount_wei: str,
        proof_commitment: str,
        pubkey_hash: str,
        nonce: int,
        submission_mode: str = "relayer",
        submitter_address: Optional[str] = None,
        submitter_account_config: Optional[str] = None,
        submitter_private_key: Optional[str] = None,
    ) -> dict:
        """Submit execute_with_proof to Starknet via starkli."""
        resolved_mode = (submission_mode or "relayer").strip().lower() or "relayer"

        private_key = submitter_private_key or os.environ.get("STARKNET_PRIVATE_KEY", "")
        account_addr = os.environ.get("STARKNET_ACCOUNT_ADDRESS", "")
        account_config = os.environ.get("STARKNET_ACCOUNT_CONFIG", "")
        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )

        if not private_key:
            raise RuntimeError("STARKNET_PRIVATE_KEY is required")

        if resolved_mode == "user_account":
            if not submitter_address or not submitter_address.startswith("0x"):
                raise RuntimeError("sender_model=user_account requires submitter_address (0x...)")
            if not submitter_account_config:
                raise RuntimeError("sender_model=user_account requires submitter_account_config")
            if not submitter_private_key:
                raise RuntimeError("sender_model=user_account requires submitter_private_key")

        account_config_path = ""
        if submitter_account_config:
            account_config_path = submitter_account_config
        elif account_config:
            account_config_path = account_config
        elif account_addr and ("/" in account_addr or "\\" in account_addr or account_addr.endswith(".json")):
            account_config_path = account_addr

        if not account_config_path:
            raise RuntimeError(
                "Starkli requires an account config file path. "
                "Set STARKNET_ACCOUNT_CONFIG=/path/to/account.json (or set STARKNET_ACCOUNT_ADDRESS to that path)."
            )

        expanded_account_path = str(Path(account_config_path).expanduser())
        if not os.path.isfile(expanded_account_path):
            raise RuntimeError(
                f"Starkli account config file not found: {expanded_account_path}. "
                "Generate one with: starkli account fetch <ACCOUNT_ADDRESS> --rpc <RPC_URL> --output <PATH>."
            )

        proof_felt = "0x" + proof_commitment[:62]
        pubkey_felt = pubkey_hash_to_felt(pubkey_hash)

        strk_token = os.environ.get(
            "STRK_TOKEN_ADDRESS",
            "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
        )
        transfer_selector = (
            "0x0083afd3f4caedc6eebf44246fe54e38c95e3179a5ec9ea81740eca5b482d12e"
        )

        amount_int = int(amount_wei)
        amount_low = hex(amount_int & ((1 << 128) - 1))
        amount_high = hex(amount_int >> 128)

        cmd = [
            "starkli", "invoke",
            contract_address,
            "execute_with_proof",
            strk_token,
            transfer_selector,
            "3",
            to_address,
            amount_low,
            amount_high,
            proof_felt,
            pubkey_felt,
            str(nonce),
            "--rpc", rpc,
            "--private-key", private_key,
            "--account", expanded_account_path,
        ]

        max_retries = int(os.environ.get("STARKNET_SUBMIT_MAX_RETRIES", "3"))
        result = None
        for attempt in range(max_retries):
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                break

            detail = (result.stderr or result.stdout or "").strip()
            nonce_error = self._is_nonce_error(detail)
            if nonce_error and attempt < max_retries - 1:
                time.sleep(1.2 * (attempt + 1))
                continue

            raise RuntimeError(f"starkli invoke failed: {result.stderr}")

        if result is None or result.returncode != 0:
            raise RuntimeError("starkli invoke failed after retries")

        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        tx_hash = self._extract_starknet_tx_hash(combined)

        return {
            "tx_hash": tx_hash,
            "status": "submitted",
            "submission_mode": resolved_mode,
            "sender_account_address": contract_address,
            "submitted_by_address": (
                submitter_address
                or self._resolve_submitter_identity_from_env(account_addr)
            ),
        }

    @staticmethod
    def _extract_starknet_tx_hash(output: str) -> str:
        """Extract tx hash from starkli output in either labeled or raw formats."""
        text = output or ""

        labeled = re.search(
            r"(?:transaction_hash|tx_hash)\s*[:=]\s*(0x[0-9a-fA-F]{40,66})",
            text,
            flags=re.IGNORECASE,
        )
        if labeled:
            return labeled.group(1)

        for line in text.splitlines():
            stripped = line.strip()
            if re.fullmatch(r"0x[0-9a-fA-F]{40,66}", stripped):
                return stripped

        fallback = re.findall(r"0x[0-9a-fA-F]{40,66}", text)
        return fallback[0] if fallback else ""

    @staticmethod
    def _is_nonce_error(detail: str) -> bool:
        normalized = (detail or "").lower()
        return (
            "invalid transaction nonce" in normalized
            or "invalidtransactionnonce" in normalized
        )

    @staticmethod
    def _looks_like_hex_address(value: Optional[str]) -> bool:
        text = (value or "").strip()
        return bool(re.fullmatch(r"0x[0-9a-fA-F]{40,66}", text))

    @staticmethod
    def _extract_factory_address_from_deploy_command() -> str:
        configured = (os.environ.get("STARKNET_FACTORY_ADDRESS", "") or "").strip()
        if configured:
            return configured

        template = (os.environ.get("WALLET_DEPLOY_COMMAND", "") or "").strip()
        if not template:
            return ""

        candidates = re.findall(r"0x[0-9a-fA-F]{40,66}", template)
        return candidates[0] if candidates else ""

    async def _validate_sender_account_class_hash(
        self,
        contract_address: str,
        stored_class_hash: Optional[str],
    ) -> dict:
        enforce = (os.environ.get("ENFORCE_SENDER_CLASS_HASH", "true") or "").strip().lower()
        if enforce not in {"1", "true", "yes", "on"}:
            return {"status": "ok"}

        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )
        onchain_hash = await self._get_onchain_class_hash(contract_address, rpc)
        if not onchain_hash:
            logger.warning(
                "Skipping sender class-hash enforcement because on-chain class hash could not be resolved for %s",
                contract_address,
            )
            return {"status": "ok"}

        normalized_onchain = self._normalize_starknet_address(onchain_hash)
        normalized_stored = self._normalize_starknet_address(stored_class_hash or "")

        if normalized_stored and normalized_onchain != normalized_stored:
            return {
                "status": "error",
                "error": (
                    "Sender account class hash mismatch. "
                    f"stored={stored_class_hash}, onchain={onchain_hash}. "
                    "Wallet deployment metadata is stale; redeploy this wallet before sending."
                ),
            }

        expected_factory_hash = await self._get_factory_account_class_hash(rpc)
        normalized_expected = self._normalize_starknet_address(expected_factory_hash)
        if normalized_expected and normalized_onchain != normalized_expected:
            return {
                "status": "error",
                "error": (
                    "Wallet account uses an outdated contract class. "
                    f"onchain={onchain_hash}, expected={expected_factory_hash}. "
                    "Redeploy this wallet with the latest account class before sending tokens."
                ),
            }

        return {"status": "ok"}

    async def _get_onchain_class_hash(self, contract_address: str, rpc: str) -> str:
        try:
            result = subprocess.run(
                ["starkli", "class-hash-at", contract_address, "--rpc", rpc],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode != 0:
                return ""
            values = re.findall(r"0x[0-9a-fA-F]{40,66}", (result.stdout or "") + "\n" + (result.stderr or ""))
            return values[0] if values else ""
        except Exception:
            return ""

    async def _get_factory_account_class_hash(self, rpc: str) -> str:
        factory_address = self._extract_factory_address_from_deploy_command()
        if not self._looks_like_hex_address(factory_address):
            return ""

        try:
            result = subprocess.run(
                ["starkli", "call", factory_address, "get_account_class_hash", "--rpc", rpc],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode != 0:
                return ""
            values = re.findall(r"0x[0-9a-fA-F]{40,66}", (result.stdout or "") + "\n" + (result.stderr or ""))
            return values[0] if values else ""
        except Exception:
            return ""

    @classmethod
    def _resolve_submitter_identity_from_env(cls, account_addr: Optional[str] = None) -> str:
        relayer = (os.environ.get("STARKNET_RELAYER_ADDRESS", "") or "").strip()
        if cls._looks_like_hex_address(relayer):
            return relayer

        candidate = (account_addr or os.environ.get("STARKNET_ACCOUNT_ADDRESS", "") or "").strip()
        if cls._looks_like_hex_address(candidate):
            return candidate

        return ""

    @staticmethod
    def _resolve_submission_mode(account_mode: Optional[str] = None) -> str:
        mode = (account_mode or os.environ.get("STARKNET_SUBMISSION_MODE", "relayer") or "").strip().lower()
        return mode or "relayer"

    @staticmethod
    def _resolve_prover_url() -> Optional[str]:
        configured = (os.environ.get("PROVER_URL", "") or "").strip()
        if configured:
            return configured

        port = (os.environ.get("PROVER_PORT", "") or "").strip()
        if not port:
            return None

        host = (os.environ.get("PROVER_HOST", "127.0.0.1") or "127.0.0.1").strip()
        return f"http://{host}:{port}"

    def _resolve_submitter_private_key(
        self,
        submission_mode: str,
        encrypted_submitter_private_key: Optional[str],
    ) -> Optional[str]:
        if (submission_mode or "").strip().lower() != "user_account":
            return None
        if not encrypted_submitter_private_key:
            return None

        try:
            raw = self.key_svc.decrypt_secret_key(encrypted_submitter_private_key)
            return raw.decode("utf-8").strip()
        except Exception as e:
            raise RuntimeError(f"Unable to decrypt account submitter_private_key: {e}")

    # ── Query ─────────────────────────────────────────────────

    async def get_transaction(self, conn, tx_id: str) -> Optional[dict]:
        row = await conn.fetchrow(
            "SELECT * FROM transactions WHERE tx_id = $1", tx_id
        )
        return dict(row) if row else None

    async def list_transactions(
        self,
        conn,
        account_id: str,
        limit: int = 50,
        offset: int = 0,
        account_address: Optional[str] = None,
    ) -> list[dict]:
        if account_address:
            import re
            addr = account_address.lower()
            full_addr = self._normalize_starknet_address(addr).lower()
            stripped_addr = re.sub(r'^0x0+', '0x', addr)
            if stripped_addr == '0x':
                stripped_addr = '0x0'

            rows = await conn.fetch(
                """SELECT tx_id, account_id, to_address, amount_wei, status,
                          proof_commitment, tx_hash, nonce, created_at, confirmed_at,
                          sender_account_address, submitted_by_address, submission_mode,
                          prover_backend, prover_fallback_reason
                   FROM transactions
                   WHERE account_id = $1 OR lower(to_address) = $2 OR lower(to_address) = $3 OR lower(to_address) = $4
                   ORDER BY created_at DESC
                   LIMIT $5 OFFSET $6""",
                account_id, addr, full_addr, stripped_addr, limit, offset,
            )
        else:
            rows = await conn.fetch(
                """SELECT tx_id, account_id, to_address, amount_wei, status,
                          proof_commitment, tx_hash, nonce, created_at, confirmed_at,
                          sender_account_address, submitted_by_address, submission_mode,
                          prover_backend, prover_fallback_reason
                   FROM transactions
                   WHERE account_id = $1
                   ORDER BY created_at DESC
                   LIMIT $2 OFFSET $3""",
                account_id, limit, offset,
            )
        return [dict(r) for r in rows]

    async def count_transactions(self, conn, account_id: str, account_address: Optional[str] = None) -> int:
        if account_address:
            import re
            addr = account_address.lower()
            full_addr = self._normalize_starknet_address(addr).lower()
            stripped_addr = re.sub(r'^0x0+', '0x', addr)
            if stripped_addr == '0x':
                stripped_addr = '0x0'

            result = await conn.fetchval(
                "SELECT COUNT(*) FROM transactions WHERE account_id = $1 OR lower(to_address) = $2 OR lower(to_address) = $3 OR lower(to_address) = $4",
                account_id, addr, full_addr, stripped_addr,
            )
        else:
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM transactions WHERE account_id = $1",
                account_id,
            )
        return result or 0

    async def get_transaction_status_from_starknet(
        self,
        starknet_tx_hash: str,
        expected_from_address: Optional[str] = None,
        expected_to_address: Optional[str] = None,
        expected_amount_wei: Optional[str] = None,
    ) -> dict:
        """Poll Starknet receipt and verify transfer execution semantics."""
        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )
        strk_token = os.environ.get(
            "STRK_TOKEN_ADDRESS",
            "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
        )

        # Prefer JSON-RPC receipt for structured status and events.
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "starknet_getTransactionReceipt",
                "params": [starknet_tx_hash],
                "id": 1,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(rpc, json=payload)
                response.raise_for_status()

            body = response.json()
            if isinstance(body, dict) and body.get("error"):
                message = str(body.get("error", {}).get("message", "")).lower()
                if "not found" in message or "not received" in message:
                    return {"status": "pending"}
                return {"status": "unknown", "error": body.get("error")}

            receipt = body.get("result") if isinstance(body, dict) else None
            if isinstance(receipt, dict):
                execution_status = str(receipt.get("execution_status", "")).upper()
                finality_status = str(receipt.get("finality_status", "")).upper()
                revert_reason = (
                    str(receipt.get("revert_reason", ""))
                    or str((receipt.get("execution_result") or {}).get("revert_reason", ""))
                )

                if execution_status == "REVERTED":
                    return {"status": "rejected", "error": revert_reason or "execution reverted"}

                if finality_status in {"ACCEPTED_ON_L2", "ACCEPTED_ON_L1"}:
                    if self._has_token_transfer_event(
                        receipt,
                        strk_token,
                        expected_from_address=expected_from_address,
                        expected_to_address=expected_to_address,
                        expected_amount_wei=expected_amount_wei,
                    ):
                        return {"status": "confirmed"}
                    sample_event_sources = []
                    for event in (receipt.get("events") or [])[:3]:
                        if isinstance(event, dict):
                            sample_event_sources.append(str(event.get("from_address", "")))
                    logger.warning(
                        "No STRK transfer event for accepted tx %s. token=%s sample_event_sources=%s",
                        starknet_tx_hash,
                        strk_token,
                        sample_event_sources,
                    )
                    return {
                        "status": "failed",
                        "starknet_status": "no_transfer_event",
                        "error": "Transaction confirmed but expected STRK transfer event was not found",
                    }

                return {"status": "pending"}
        except Exception:
            pass

        # Fallback: starkli textual status.
        try:
            result = subprocess.run(
                ["starkli", "receipt", starknet_tx_hash, "--rpc", rpc],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                output = result.stdout.upper()
                if "ACCEPTED" in output:
                    return {"status": "confirmed"}
                elif "REJECTED" in output:
                    return {"status": "rejected"}
                return {"status": "pending"}
            return {"status": "pending", "error": result.stderr}
        except Exception as e:
            return {"status": "unknown", "error": str(e)}

    @staticmethod
    def _normalize_starknet_address(address: str) -> str:
        raw = str(address or "").strip().lower()
        if not raw:
            return ""
        if raw.startswith("0x"):
            raw = raw[2:]
        if not raw:
            return ""
        if not re.fullmatch(r"[0-9a-f]+", raw):
            return ""
        if len(raw) > 64:
            return ""
        return "0x" + raw.zfill(64)

    @staticmethod
    def _normalize_felt_hex(value: str) -> str:
        return TransactionService._normalize_starknet_address(value)

    @staticmethod
    def _parse_uint256_from_event_data(data: Any) -> Optional[int]:
        if not isinstance(data, list) or len(data) < 2:
            return None
        try:
            low = int(str(data[0]), 16)
            high = int(str(data[1]), 16)
            return low + (high << 128)
        except Exception:
            return None

    @staticmethod
    def _has_token_transfer_event(
        receipt: dict,
        token_address: str,
        expected_from_address: Optional[str] = None,
        expected_to_address: Optional[str] = None,
        expected_amount_wei: Optional[str] = None,
    ) -> bool:
        events = receipt.get("events") if isinstance(receipt, dict) else None
        if not isinstance(events, list):
            return False

        normalized_token = TransactionService._normalize_starknet_address(token_address)
        if not normalized_token:
            return False

        expected_from = TransactionService._normalize_starknet_address(
            expected_from_address or ""
        )
        expected_to = TransactionService._normalize_starknet_address(
            expected_to_address or ""
        )
        transfer_selector = TransactionService._normalize_felt_hex(
            ERC20_TRANSFER_EVENT_SELECTOR
        )
        expected_amount = None
        if expected_amount_wei is not None and str(expected_amount_wei).strip() != "":
            try:
                expected_amount = int(str(expected_amount_wei))
            except Exception:
                expected_amount = None

        for event in events:
            if not isinstance(event, dict):
                continue
            from_addr = TransactionService._normalize_starknet_address(
                str(event.get("from_address", ""))
            )
            if from_addr != normalized_token:
                continue

            keys = event.get("keys") if isinstance(event.get("keys"), list) else []
            if not keys:
                continue
            key0 = TransactionService._normalize_felt_hex(str(keys[0]))
            if key0 != transfer_selector:
                continue

            event_from = (
                TransactionService._normalize_starknet_address(str(keys[1]))
                if len(keys) > 1
                else ""
            )
            event_to = (
                TransactionService._normalize_starknet_address(str(keys[2]))
                if len(keys) > 2
                else ""
            )
            event_amount = TransactionService._parse_uint256_from_event_data(
                event.get("data")
            )

            if expected_from and event_from and event_from != expected_from:
                continue
            if expected_to and event_to and event_to != expected_to:
                continue
            if expected_amount is not None and event_amount is not None and event_amount != expected_amount:
                continue
            if expected_amount is not None and event_amount is None:
                continue

            return True
        return False
