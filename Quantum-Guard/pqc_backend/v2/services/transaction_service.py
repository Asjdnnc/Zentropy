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
import subprocess
import time
import uuid
from typing import Any, Callable, Optional

from ..models.enums import (
    TransactionStatus, AuditAction, AuditEntityType, STRK_DECIMALS,
)
from .key_service import KeyService
from .audit_service import AuditService

logger = logging.getLogger("quantumguard.tx_service")


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
        call_prover_fn: Optional[Callable] = None,
        ip_address: Optional[str] = None,
    ) -> dict:
        """
        Full transfer pipeline.
        Returns a result dict with tx_id, status, proof info, etc.
        """
        tx_id = f"tx_{uuid.uuid4().hex[:16]}"

        # 1. FETCH USER WALLET + ACCOUNT
        user_wallet = await self._get_user_wallet_or_fail(conn, user_id)
        wallet = user_wallet["wallet"]
        account = user_wallet["account"]
        wallet_id = wallet["wallet_id"]
        account_id = account["account_id"]
        contract_address = account["account_address"]

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

        await conn.execute(
            """UPDATE transactions
               SET proof_commitment = $1, proof_valid = $2, status = $3
               WHERE tx_id = $4""",
            proof_commitment, int(proof_valid),
            TransactionStatus.PROVED.value if proof_valid else TransactionStatus.FAILED.value,
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
        try:
            starknet_result = await self._submit_to_starknet(
                contract_address=contract_address,
                to_address=to_address,
                amount_wei=amount_wei,
                proof_commitment=proof_commitment,
                pubkey_hash=account["public_key_pq_hash"],
                nonce=nonce,
            )
            starknet_tx_hash = starknet_result.get("tx_hash", "")
            if starknet_tx_hash:
                explorer_url = f"https://sepolia.starkscan.co/tx/{starknet_tx_hash}"

            await conn.execute(
                """UPDATE transactions
                   SET tx_hash = $1, status = $2, starknet_status = $3
                   WHERE tx_id = $4""",
                starknet_tx_hash,
                TransactionStatus.SUBMITTED.value,
                "submitted",
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
                   SET status = $1, starknet_status = $2, error_message = $3
                   WHERE tx_id = $4""",
                TransactionStatus.FAILED.value, "submission_failed", str(e), tx_id,
            )
            logger.error("TX %s Starknet submission failed: %s", tx_id, e)
            return {
                "tx_id": tx_id,
                "status": "submission_failed",
                "proof_valid": True,
                "proof_commitment": proof_commitment,
                "error": str(e),
            }

        return {
            "tx_id": tx_id,
            "starknet_tx_hash": starknet_tx_hash,
            "status": "submitted",
            "proof_valid": True,
            "proof_commitment": proof_commitment,
            "batch_id": batch_id,
            "amount_strk": f"{amount_strk:.6f}",
            "amount_wei": amount_wei,
            "explorer_url": explorer_url,
        }

    # ── Helpers ───────────────────────────────────────────────

    async def _get_user_wallet_or_fail(self, conn, user_id: str) -> dict:
        """Fetch user, wallet, account — raise if missing."""
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
        if call_prover_fn:
            try:
                return await call_prover_fn(
                    base64.b64encode(message).decode(),
                    base64.b64encode(signature).decode(),
                    base64.b64encode(public_key).decode(),
                )
            except Exception as e:
                logger.warning("Rust prover failed, falling back to Python: %s", e)

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
        }

    async def _submit_to_starknet(
        self,
        contract_address: str,
        to_address: str,
        amount_wei: str,
        proof_commitment: str,
        pubkey_hash: str,
        nonce: int,
    ) -> dict:
        """Submit execute_with_proof to Starknet via starkli."""
        private_key = os.environ.get("STARKNET_PRIVATE_KEY", "")
        account_addr = os.environ.get("STARKNET_ACCOUNT_ADDRESS", "")
        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )

        if not private_key or not account_addr:
            raise RuntimeError("STARKNET_PRIVATE_KEY and STARKNET_ACCOUNT_ADDRESS required")

        proof_felt = "0x" + proof_commitment[:62]
        pubkey_felt = "0x" + pubkey_hash[:62]

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

        result = subprocess.run(
            [
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
                "--account", account_addr,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise RuntimeError(f"starkli invoke failed: {result.stderr}")

        tx_hash = ""
        combined = result.stdout + "\n" + result.stderr
        for line in combined.splitlines():
            stripped = line.strip()
            if stripped.startswith("0x") and len(stripped) > 10:
                tx_hash = stripped
                break

        return {"tx_hash": tx_hash, "status": "submitted"}

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
    ) -> list[dict]:
        rows = await conn.fetch(
            """SELECT tx_id, account_id, to_address, amount_wei, status,
                      proof_commitment, tx_hash, nonce, created_at, confirmed_at
               FROM transactions
               WHERE account_id = $1
               ORDER BY created_at DESC
               LIMIT $2 OFFSET $3""",
            account_id, limit, offset,
        )
        return [dict(r) for r in rows]

    async def count_transactions(self, conn, account_id: str) -> int:
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE account_id = $1",
            account_id,
        )
        return result or 0

    async def get_transaction_status_from_starknet(
        self, starknet_tx_hash: str
    ) -> dict:
        """Poll Starknet for transaction receipt."""
        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )
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
