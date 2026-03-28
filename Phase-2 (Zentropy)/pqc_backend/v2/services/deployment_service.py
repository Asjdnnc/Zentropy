"""
QuantumGuard v2 — Account Deployment Service
============================================
Handles asynchronous Starknet account deployment for newly created wallets.

Deployment command is configured via WALLET_DEPLOY_COMMAND and may use:
    {account_id}, {wallet_id}, {account_address}, {public_key_hash}
    {public_key_hash_raw}, {public_key_hash_body}, {public_key_hash_felt}

Example:
  WALLET_DEPLOY_COMMAND="starkli invoke <factory_addr> deploy_wallet {public_key_hash} --rpc $STARKNET_RPC --account $STARKNET_ACCOUNT_CONFIG --private-key $STARKNET_PRIVATE_KEY"
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import subprocess
import time
from typing import Optional

from ..db.connection import get_db
from ..models.enums import AuditAction, AuditEntityType, DeploymentStatus
from .starknet_felt_utils import normalize_sha256_hex, pubkey_hash_to_felt
from .audit_service import AuditService

logger = logging.getLogger("quantumguard.deployment_service")


class DeploymentService:
    """Background deployment orchestration for user accounts."""

    def __init__(self, audit_service: Optional[AuditService] = None):
        self.audit_svc = audit_service or AuditService()

    @staticmethod
    def auto_deploy_enabled() -> bool:
        """Enable auto deploy explicitly or by production env default."""
        configured = os.environ.get("AUTO_DEPLOY_WALLET_ON_REGISTER")
        if configured is not None:
            return configured.strip().lower() in {"1", "true", "yes", "on"}
        # Default to True instead of relying on ENV=production matching exactly.
        # This fixes deployment timeouts on platforms that don't set ENV=production.
        return True

    async def enqueue_deployment(self, account_id: str, org_id: str, user_id: str) -> None:
        """Fire-and-forget deployment task."""
        asyncio.create_task(self._run_deployment(account_id, org_id, user_id))

    async def deploy_account_via_new_connection(self, account_id: str, org_id: str, user_id: str) -> dict:
        """Deploy an account using a fresh DB connection context."""
        async with get_db() as conn:
            return await self.deploy_account(conn, account_id, org_id, user_id)

    async def _run_deployment(self, account_id: str, org_id: str, user_id: str) -> None:
        async with get_db() as conn:
            await self.deploy_account(conn, account_id, org_id, user_id)

    async def deploy_account(self, conn, account_id: str, org_id: str, user_id: str) -> dict:
        """Deploy account via configured command and persist outcome."""
        account = await conn.fetchrow("SELECT * FROM accounts WHERE account_id = $1", account_id)
        if not account:
            raise RuntimeError(f"Account not found: {account_id}")

        account_dict = dict(account)
        wallet_id = account_dict["wallet_id"]
        account_address = account_dict["account_address"]
        public_key_hash = account_dict["public_key_pq_hash"]

        now = time.time()
        await conn.execute(
            """UPDATE accounts
               SET deployment_status = $1,
                   deployment_attempts = COALESCE(deployment_attempts, 0) + 1,
                   last_deployment_attempt = $2,
                   deployment_error_message = NULL,
                   updated_at = $3
               WHERE account_id = $4""",
            DeploymentStatus.PENDING.value,
            now,
            now,
            account_id,
        )

        try:
            confirm_timeout = float(os.environ.get("WALLET_DEPLOY_CONFIRM_TIMEOUT_SECONDS", "180"))
            confirm_poll = float(os.environ.get("WALLET_DEPLOY_CONFIRM_POLL_SECONDS", "3"))
            confirm_deadline = time.time() + max(confirm_timeout, 1.0)

            deploy_result = await self._invoke_deploy_command(
                account_id=account_id,
                wallet_id=wallet_id,
                account_address=account_address,
                public_key_hash=public_key_hash,
            )
            tx_hash = deploy_result.get("tx_hash", "")
            deployed_address = deploy_result.get("contract_address", account_address)
            invoke_argv = deploy_result.get("invoke_argv", [])
            factory_address = self._extract_invoke_contract_address(invoke_argv)

            if tx_hash:
                await conn.execute(
                    """UPDATE accounts
                       SET deployment_tx_hash = $1,
                           updated_at = $2
                       WHERE account_id = $3""",
                    tx_hash,
                    time.time(),
                    account_id,
                )

            # CRITICAL FIX: For factory deployments, ALWAYS resolve the actual deployed address
            # Do not use the naively extracted address if it matches the factory address
            if factory_address and deployed_address == factory_address:
                logger.warning(
                    "Detected factory address as extracted endpoint. "
                    "Forcing address resolution for account %s (factory=%s)",
                    account_id, factory_address
                )
                resolved_address = await self._resolve_deployed_address(
                    expected_address=account_address,
                    invoke_argv=invoke_argv,
                    tx_hash=tx_hash,
                    deadline=confirm_deadline,
                    poll_seconds=confirm_poll,
                )
                if resolved_address:
                    deployed_address = resolved_address
                    logger.info(
                        "Resolved deployed address for account %s: %s (was factory: %s)",
                        account_id, deployed_address, factory_address
                    )
                else:
                    raise RuntimeError(
                        f"Failed to resolve deployed address for account {account_id}. "
                        f"Got factory address {factory_address} but could not locate actual account address."
                    )
            else:
                # Standard resolution path for non-factory deployments or when address looks correct
                resolved_address = await self._resolve_deployed_address(
                    expected_address=account_address,
                    invoke_argv=invoke_argv,
                    tx_hash=tx_hash,
                    deadline=confirm_deadline,
                    poll_seconds=confirm_poll,
                )
                if resolved_address:
                    deployed_address = resolved_address

            class_hash = deploy_result.get("class_hash", account_dict.get("contract_class_hash"))

            # CRITICAL VALIDATION: Never store factory address as the deployed account address
            if factory_address and deployed_address == factory_address:
                raise RuntimeError(
                    f"CRITICAL: Refusing to deploy account {account_id}. "
                    f"The resolved address is still the factory contract ({factory_address}). "
                    f"This would prevent users from sending tokens. "
                    f"Check factory.get_deployed_address() or deployment tx events for the actual account address."
                )

            await self._wait_for_contract_deployment(
                deployed_address,
                tx_hash=tx_hash,
                deadline=confirm_deadline,
                poll_seconds=confirm_poll,
            )

            deployed_at = time.time()
            await conn.execute(
                """UPDATE accounts
                   SET account_address = $1,
                       contract_class_hash = $2,
                       deployment_status = $3,
                       deployment_tx_hash = $4,
                       deployed_at = $5,
                       deployment_error_message = NULL,
                       updated_at = $6
                   WHERE account_id = $7""",
                deployed_address,
                class_hash,
                DeploymentStatus.DEPLOYED.value,
                tx_hash,
                deployed_at,
                deployed_at,
                account_id,
            )

            await self.audit_svc.log(
                conn,
                org_id,
                user_id,
                AuditEntityType.ACCOUNT.value,
                account_id,
                AuditAction.ACCOUNT_DEPLOYED.value,
                details={
                    "contract_address": deployed_address,
                    "class_hash": class_hash,
                    "tx_hash": tx_hash,
                },
            )

            logger.info("Account %s deployed: %s", account_id, tx_hash)
            return {
                "status": DeploymentStatus.DEPLOYED.value,
                "tx_hash": tx_hash,
                "contract_address": deployed_address,
                "class_hash": class_hash,
            }
        except Exception as e:
            failed_at = time.time()
            err = str(e)
            await conn.execute(
                """UPDATE accounts
                   SET deployment_status = $1,
                       deployment_error_message = $2,
                       updated_at = $3
                   WHERE account_id = $4""",
                DeploymentStatus.FAILED.value,
                err,
                failed_at,
                account_id,
            )

            await self.audit_svc.log(
                conn,
                org_id,
                user_id,
                AuditEntityType.ACCOUNT.value,
                account_id,
                "account_deploy_failed",
                details={"error": err},
            )

            logger.error("Account %s deployment failed: %s", account_id, err)
            return {"status": DeploymentStatus.FAILED.value, "error": err}

    async def _invoke_deploy_command(
        self,
        account_id: str,
        wallet_id: str,
        account_address: str,
        public_key_hash: str,
    ) -> dict:
        template = os.environ.get("WALLET_DEPLOY_COMMAND", "").strip()
        if not template:
            raise RuntimeError("WALLET_DEPLOY_COMMAND is required for automatic deployment")

        expanded_template = os.path.expandvars(template)
        pubkey_hash_raw = normalize_sha256_hex(public_key_hash)
        pubkey_hash_felt = pubkey_hash_to_felt(pubkey_hash_raw)

        # Backward compatible migration path:
        # if template used 0x{public_key_hash}, route it to canonical felt encoding.
        command_template = expanded_template.replace("0x{public_key_hash}", "{public_key_hash_felt}")

        command = command_template.format(
            account_id=account_id,
            wallet_id=wallet_id,
            account_address=account_address,
            public_key_hash=pubkey_hash_raw,
            public_key_hash_raw=pubkey_hash_raw,
            public_key_hash_body=pubkey_hash_felt[2:],
            public_key_hash_felt=pubkey_hash_felt,
        )
        argv = shlex.split(command)
        argv = self._coerce_rpc_arg(argv)
        self._validate_starkli_args(argv)
        logger.info("Deployment command prepared for account %s (rpc=%s)", account_id, self._get_flag_value(argv, "--rpc"))
        timeout = float(os.environ.get("WALLET_DEPLOY_TIMEOUT_SECONDS", "90"))
        max_retries = int(os.environ.get("WALLET_DEPLOY_MAX_RETRIES", "3"))

        last_detail = ""
        for attempt in range(max_retries):
            result = await asyncio.to_thread(
                subprocess.run,
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0:
                combined_output = "\n".join(filter(None, [result.stdout, result.stderr]))
                parsed = self._parse_deploy_output(combined_output, default_address=account_address)
                parsed["invoke_argv"] = argv
                return parsed

            detail = (result.stderr or result.stdout).strip()
            last_detail = detail
            nonce_error = self._is_nonce_error(detail)
            transient_error = self._is_retryable_transient_error(detail)
            if (nonce_error or transient_error) and attempt < max_retries - 1:
                # Give the sequencer time to reflect latest account nonce.
                await asyncio.sleep(1.2 * (attempt + 1))
                continue

            raise RuntimeError(f"deploy command failed: {detail}")

        raise RuntimeError(f"deploy command failed: {last_detail}")

    @staticmethod
    def _is_nonce_error(detail: str) -> bool:
        normalized = (detail or "").lower()
        return (
            "invalid transaction nonce" in normalized
            or "invalidtransactionnonce" in normalized
        )

    @staticmethod
    def _is_retryable_transient_error(detail: str) -> bool:
        normalized = (detail or "").lower()
        transient_markers = [
            "503 service unavailable",
            "502 bad gateway",
            "504 gateway timeout",
            "gateway timeout",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "timed out",
            "timeout",
            "too many requests",
            "http 429",
        ]
        return any(marker in normalized for marker in transient_markers)

    @staticmethod
    def _parse_deploy_output(stdout: str, default_address: str) -> dict:
        output = (stdout or "").strip()
        if not output:
            return {"tx_hash": "", "contract_address": default_address}

        try:
            payload = json.loads(output)
            if isinstance(payload, dict):
                return {
                    "tx_hash": str(payload.get("tx_hash", "")),
                    "contract_address": str(payload.get("contract_address", default_address)),
                    "class_hash": payload.get("class_hash"),
                }
        except json.JSONDecodeError:
            pass

        felts = re.findall(r"0x[0-9a-fA-F]+", output)
        tx_hash = felts[0] if felts else ""
        contract_address = felts[1] if len(felts) > 1 else default_address
        return {
            "tx_hash": tx_hash,
            "contract_address": contract_address,
            "class_hash": None,
        }

    @staticmethod
    def _validate_starkli_args(argv: list[str]) -> None:
        """Validate required starkli CLI flag values before subprocess execution."""
        required_flags = ["--private-key", "--account", "--rpc"]

        for flag in required_flags:
            if flag not in argv:
                raise RuntimeError(
                    f"WALLET_DEPLOY_COMMAND is missing required flag {flag}. "
                    "Include explicit --private-key, --account, and --rpc arguments."
                )

            idx = argv.index(flag)
            if idx + 1 >= len(argv) or not argv[idx + 1].strip() or argv[idx + 1].startswith("--"):
                raise RuntimeError(
                    f"WALLET_DEPLOY_COMMAND has missing value for {flag}. "
                    "Use either literal values or env vars that resolve at runtime."
                )

    @staticmethod
    def _get_flag_value(argv: list[str], flag: str) -> Optional[str]:
        if flag not in argv:
            return None
        idx = argv.index(flag)
        if idx + 1 >= len(argv):
            return None
        return argv[idx + 1]

    @staticmethod
    def _coerce_rpc_arg(argv: list[str]) -> list[str]:
        """Ensure deploy command always uses runtime STARKNET_RPC when provided."""
        rpc = (os.environ.get("STARKNET_RPC", "") or "").strip()
        if not rpc:
            return argv

        out = list(argv)
        if "--rpc" in out:
            idx = out.index("--rpc")
            if idx + 1 < len(out) and out[idx + 1] and not out[idx + 1].startswith("--"):
                out[idx + 1] = rpc
                return out

            if idx + 1 < len(out):
                out[idx + 1] = rpc
                return out

            out.append(rpc)
            return out

        out.extend(["--rpc", rpc])
        return out

    @staticmethod
    def _normalize_hex(value: str) -> Optional[str]:
        raw = (value or "").strip().lower()
        if not raw:
            return None
        if not raw.startswith("0x"):
            return None
        body = raw[2:]
        if not body or not re.fullmatch(r"[0-9a-f]+", body):
            return None
        # Keep Starknet-style felt shape but normalize case.
        return "0x" + body

    @classmethod
    def _is_zero_hex(cls, value: str) -> bool:
        normalized = cls._normalize_hex(value)
        if not normalized:
            return True
        return int(normalized, 16) == 0

    async def _wait_for_contract_deployment(
        self,
        contract_address: str,
        tx_hash: str,
        deadline: float,
        poll_seconds: float,
    ) -> None:
        """Block until Starknet reports a non-zero class hash for the account address."""
        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )

        while time.time() < deadline:
            rejection = await self._deployment_tx_rejection_reason(tx_hash, rpc)
            if rejection:
                raise RuntimeError(f"Deployment tx rejected ({tx_hash}): {rejection}")

            result = await asyncio.to_thread(
                subprocess.run,
                ["starkli", "class-hash-at", contract_address, "--rpc", rpc],
                capture_output=True,
                text=True,
                timeout=20,
            )

            if result.returncode == 0:
                class_hash_output = (result.stdout or "").strip()
                if class_hash_output and not self._is_zero_hex(class_hash_output):
                    return

            await asyncio.sleep(max(poll_seconds, 0.5))

        raise RuntimeError(
            f"Deployment confirmation timed out for {contract_address}: class hash not available on-chain"
        )

    async def _resolve_deployed_address(
        self,
        expected_address: str,
        invoke_argv: list[str],
        tx_hash: str,
        deadline: float,
        poll_seconds: float,
    ) -> Optional[str]:
        """Resolve actual deployed address from factory by salt (expected address)."""
        factory_address = self._extract_invoke_contract_address(invoke_argv)
        if not factory_address:
            return expected_address

        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )

        while time.time() < deadline:
            rejection = await self._deployment_tx_rejection_reason(tx_hash, rpc)
            if rejection:
                raise RuntimeError(f"Deployment tx rejected ({tx_hash}): {rejection}")

            resolved_from_receipt = await self._resolve_deployed_address_from_receipt(
                tx_hash=tx_hash,
                factory_address=factory_address,
                rpc=rpc,
            )
            if resolved_from_receipt:
                return resolved_from_receipt

            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "starkli",
                    "call",
                    factory_address,
                    "get_deployed_address",
                    expected_address,
                    "--rpc",
                    rpc,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0:
                output = (result.stdout or "").strip()
                candidates = re.findall(r"0x[0-9a-fA-F]+", output)
                if candidates:
                    resolved = self._normalize_hex(candidates[0])
                    if resolved and not self._is_zero_hex(resolved):
                        logger.info("Resolved deployed address from factory.get_deployed_address(): %s", resolved)
                        return resolved
                    logger.debug("Ignoring zero-equivalent factory candidate: %s", candidates[0])
            else:
                logger.warning(
                    "factory.get_deployed_address() call failed for expected_address %s. "
                    "returncode=%d, stderr=%s",
                    expected_address, result.returncode, (result.stderr or "").strip()[:200]
                )

            await asyncio.sleep(max(poll_seconds, 0.5))

        raise RuntimeError(
            f"Deployment confirmation timed out while resolving deployed address for salt {expected_address}"
        )

    async def _resolve_deployed_address_from_receipt(
        self,
        tx_hash: str,
        factory_address: str,
        rpc: str,
    ) -> Optional[str]:
        """Extract deployed account address from deployment tx receipt events."""
        if not tx_hash:
            return None

        result = await asyncio.to_thread(
            subprocess.run,
            ["starkli", "receipt", tx_hash, "--rpc", rpc],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None

        try:
            payload = json.loads((result.stdout or "").strip() or "{}")
        except json.JSONDecodeError:
            return None

        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            return None

        normalized_factory = (factory_address or "").lower()
        for event in events:
            if not isinstance(event, dict):
                continue
            from_address = str(event.get("from_address", "")).lower()
            if normalized_factory and from_address != normalized_factory:
                continue
            data = event.get("data")
            if isinstance(data, list) and data:
                candidate = self._normalize_hex(str(data[0]))
                if candidate and not self._is_zero_hex(candidate):
                    logger.debug("Resolved deployed address from receipt event: %s", candidate)
                    return candidate
                logger.debug("Ignoring zero-equivalent receipt candidate: %s", data[0])

        return None

    async def _deployment_tx_rejection_reason(self, tx_hash: str, rpc: str) -> Optional[str]:
        """Return rejection summary if deployment transaction is rejected."""
        if not tx_hash:
            return None

        result = await asyncio.to_thread(
            subprocess.run,
            ["starkli", "status", tx_hash, "--rpc", rpc],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return None

        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        if "REJECTED" in output.upper():
            return output.replace("\n", " ")
        return None

    @staticmethod
    def _extract_invoke_contract_address(argv: list[str]) -> Optional[str]:
        """Extract invoke target contract address from starkli command argv."""
        if not argv:
            return None

        try:
            idx = argv.index("invoke")
        except ValueError:
            return None

        if idx + 1 >= len(argv):
            return None

        candidate = argv[idx + 1]
        if candidate.startswith("0x"):
            return candidate
        return None
