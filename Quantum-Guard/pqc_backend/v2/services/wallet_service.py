"""
QuantumGuard v2 — Wallet Service
==================================
Handles the full user onboarding flow:
  1. Create organization (if first time)
  2. Register user within organization
  3. Generate Dilithium keypair + seed phrase
  4. Encrypt & store keys in DB
  5. Compute counterfactual Starknet address
  6. Return wallet credentials (seed phrase shown once)

Also handles wallet queries, balance lookups, and key rotation.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import time
import urllib.request
import uuid
from typing import Optional

from ..models.enums import (
    WalletStatus, DeploymentStatus, KYCStatus,
    AuditAction, AuditEntityType,
)
from .key_service import KeyService
from .audit_service import AuditService

logger = logging.getLogger("quantumguard.wallet_service")


class WalletService:
    """Manages organizations, users, wallets, and accounts."""

    def __init__(
        self,
        key_service: Optional[KeyService] = None,
        audit_service: Optional[AuditService] = None,
    ):
        self.key_svc = key_service or KeyService()
        self.audit_svc = audit_service or AuditService()

    # ── Organization ──────────────────────────────────────────

    async def create_organization(self, conn, org_name: str, admin_email: str) -> dict:
        """Create a new organization with a unique API key."""
        org_id = str(uuid.uuid4())
        api_key = secrets.token_urlsafe(48)
        now = time.time()

        await conn.execute(
            """INSERT INTO organizations (org_id, org_name, admin_email, api_key, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            org_id, org_name, admin_email, api_key, now, now,
        )

        logger.info("Organization created: %s (%s)", org_name, org_id)
        return {
            "org_id": org_id,
            "org_name": org_name,
            "admin_email": admin_email,
            "api_key": api_key,
        }

    async def get_organization_by_api_key(self, conn, api_key: str) -> Optional[dict]:
        """Look up organization by API key (for auth)."""
        return await conn.fetchrow(
            "SELECT org_id, org_name, admin_email, api_key, created_at FROM organizations WHERE api_key = $1",
            api_key,
        )

    # ── User ──────────────────────────────────────────────────

    async def register_user(
        self,
        conn,
        org_id: str,
        email: str,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> dict:
        """
        Register a new user, create wallet with keys, and
        compute counterfactual Starknet address.

        Returns the full registration payload including seed phrase
        (which must be shown to the user exactly once).
        """
        # 1. Check duplicate
        existing = await conn.fetchrow(
            "SELECT user_id FROM users WHERE org_id = $1 AND email = $2",
            org_id, email,
        )
        if existing:
            raise ValueError(f"User with email {email} already exists in this organization")

        user_id = str(uuid.uuid4())
        now = time.time()

        await conn.execute(
            """INSERT INTO users
               (user_id, org_id, email, username, kyc_status, is_active, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            user_id, org_id, email, username,
            KYCStatus.PENDING.value, 1, now, now,
        )

        # 2. Create wallet
        wallet_result = await self._create_wallet(conn, user_id, org_id)

        # 3. Audit
        await self.audit_svc.log(
            conn, org_id, user_id,
            AuditEntityType.USER.value, user_id,
            AuditAction.USER_CREATED.value,
            details={"email": email},
            ip_address=ip_address,
        )

        return {
            "user_id": user_id,
            "org_id": org_id,
            "email": email,
            "username": username,
            **wallet_result,
        }

    async def _create_wallet(self, conn, user_id: str, org_id: str) -> dict:
        """
        Internal: create wallet + account + encrypted keys for user.
        """
        wallet_id = str(uuid.uuid4())
        now = time.time()

        # Generate keypair
        kp = self.key_svc.generate_keypair()
        pk_b64 = base64.b64encode(kp["public_key"]).decode()
        pk_hash = kp["public_key_hash"]

        # Generate seed phrase
        seed_phrase = self.key_svc.generate_seed_phrase()
        seed_encrypted = self.key_svc.encrypt_seed_phrase(seed_phrase)
        seed_hash = hashlib.sha256(seed_phrase.encode()).hexdigest()

        # Store wallet
        await conn.execute(
            """INSERT INTO wallets
               (wallet_id, user_id, wallet_name, seed_phrase_encrypted,
                seed_phrase_hash, status, pq_algorithm, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            wallet_id, user_id, "Default Wallet",
            seed_encrypted, seed_hash,
            WalletStatus.ACTIVE.value, "ML-DSA-44", now, now,
        )

        # Store encrypted secret key
        await self.key_svc.store_encrypted_key(conn, wallet_id, kp["secret_key"])

        # Create account with counterfactual address
        account_id = str(uuid.uuid4())
        # Deterministic address: hash of public key (simulates CREATE2)
        address_seed = hashlib.sha256(
            f"quantumguard:{pk_hash}:{wallet_id}".encode()
        ).hexdigest()
        counterfactual_address = "0x" + address_seed[:62]

        await conn.execute(
            """INSERT INTO accounts
               (account_id, wallet_id, blockchain, account_address,
                public_key_pq, public_key_pq_hash,
                deployment_status, nonce, balance_wei,
                created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
            account_id, wallet_id, "STARKNET", counterfactual_address,
            pk_b64, pk_hash,
            DeploymentStatus.COUNTERFACTUAL.value, 0, "0", now, now,
        )

        # Audit wallet creation
        await self.audit_svc.log(
            conn, org_id, user_id,
            AuditEntityType.WALLET.value, wallet_id,
            AuditAction.WALLET_CREATED.value,
            details={"pk_hash": pk_hash, "account_address": counterfactual_address},
        )

        logger.info(
            "Wallet created: user=%s wallet=%s address=%s",
            user_id, wallet_id, counterfactual_address,
        )

        return {
            "wallet_id": wallet_id,
            "account_id": account_id,
            "contract_address": counterfactual_address,
            "public_key": pk_b64,
            "public_key_hash": pk_hash,
            "seed_phrase": seed_phrase,
        }

    # ── Queries ───────────────────────────────────────────────

    async def get_user(self, conn, user_id: str) -> Optional[dict]:
        return await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )

    async def get_wallet_by_user(self, conn, user_id: str) -> Optional[dict]:
        return await conn.fetchrow(
            "SELECT * FROM wallets WHERE user_id = $1", user_id
        )

    async def get_account_by_wallet(self, conn, wallet_id: str) -> Optional[dict]:
        return await conn.fetchrow(
            "SELECT * FROM accounts WHERE wallet_id = $1", wallet_id
        )

    async def get_account_by_address(self, conn, address: str) -> Optional[dict]:
        return await conn.fetchrow(
            "SELECT * FROM accounts WHERE account_address = $1", address
        )

    async def get_full_user_wallet(self, conn, user_id: str) -> Optional[dict]:
        """Fetch user + wallet + account in one shot."""
        user = await self.get_user(conn, user_id)
        if not user:
            return None

        wallet = await self.get_wallet_by_user(conn, user_id)
        if not wallet:
            return None

        account = await self.get_account_by_wallet(conn, dict(wallet)["wallet_id"])

        return {
            "user": dict(user),
            "wallet": dict(wallet),
            "account": dict(account) if account else None,
        }

    async def list_users(
        self,
        conn,
        org_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        rows = await conn.fetch(
            """SELECT u.user_id, u.email, u.username, u.kyc_status,
                      w.wallet_id, a.account_address, a.deployment_status, a.balance_wei
               FROM users u
               LEFT JOIN wallets w ON u.user_id = w.user_id
               LEFT JOIN accounts a ON w.wallet_id = a.wallet_id
               WHERE u.org_id = $1
               ORDER BY u.created_at DESC
               LIMIT $2 OFFSET $3""",
            org_id, limit, offset,
        )
        return [dict(r) for r in rows]

    # ── Account Deployment ────────────────────────────────────

    async def mark_account_deployed(
        self,
        conn,
        account_id: str,
        contract_address: str,
        class_hash: str,
        deployment_tx_hash: str,
        org_id: str,
        user_id: str,
    ):
        """Update account after successful Starknet deployment."""
        now = time.time()
        await conn.execute(
            """UPDATE accounts
               SET account_address = $1, contract_class_hash = $2,
                   deployment_status = $3, deployment_tx_hash = $4,
                   deployed_at = $5, updated_at = $6
               WHERE account_id = $7""",
            contract_address, class_hash,
            DeploymentStatus.DEPLOYED.value, deployment_tx_hash,
            now, now, account_id,
        )

        await self.audit_svc.log(
            conn, org_id, user_id,
            AuditEntityType.ACCOUNT.value, account_id,
            AuditAction.ACCOUNT_DEPLOYED.value,
            details={
                "contract_address": contract_address,
                "class_hash": class_hash,
                "tx_hash": deployment_tx_hash,
            },
        )

    # ── Balance ───────────────────────────────────────────────

    async def refresh_account_balance_from_chain(
        self,
        conn,
        account_address: str,
        *,
        deployed: bool = True,
    ) -> Optional[str]:
        """Best-effort balance sync from Starknet STRK contract into accounts.balance_wei."""
        if not deployed or not account_address:
            return None

        balance_wei = await asyncio.to_thread(self._query_strk_balance_wei, account_address)
        if balance_wei is None:
            return None

        now = time.time()
        await conn.execute(
            """UPDATE accounts
               SET balance_wei = $1,
                   updated_at = $2
               WHERE account_address = $3""",
            balance_wei,
            now,
            account_address,
        )
        return balance_wei

    def _query_strk_balance_wei(self, account_address: str) -> Optional[str]:
        """Query STRK balance (starkli first, JSON-RPC fallback)."""
        rpc = os.environ.get(
            "STARKNET_RPC",
            "https://free-rpc.nethermind.io/sepolia-juno/v0_7",
        )
        strk_token = os.environ.get(
            "STRK_TOKEN_ADDRESS",
            "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
        )

        for entrypoint in ("balance_of", "balanceOf"):
            try:
                result = subprocess.run(
                    ["starkli", "call", strk_token, entrypoint, account_address, "--rpc", rpc],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                break

            if result.returncode != 0:
                continue

            parsed = self._parse_starkli_u256_output("\n".join([result.stdout or "", result.stderr or ""]))
            if parsed is not None:
                return parsed

        return self._query_strk_balance_wei_via_rpc(rpc, strk_token, account_address)

    def _query_strk_balance_wei_via_rpc(
        self,
        rpc: str,
        strk_token: str,
        account_address: str,
    ) -> Optional[str]:
        selectors = [
            # starkli selector balance_of
            "0x035a73cd311a05d46deda634c5ee045db92f811b4e74bca4437fcb5302b7af33",
            # starkli selector balanceOf
            "0x02e4263afad30923c891518314c3c95dbe830a16874e8abc5777a9a20b54c76e",
        ]

        for selector in selectors:
            payload = {
                "jsonrpc": "2.0",
                "method": "starknet_call",
                "params": [
                    {
                        "contract_address": strk_token,
                        "entry_point_selector": selector,
                        "calldata": [account_address],
                    },
                    "latest",
                ],
                "id": 1,
            }

            req = urllib.request.Request(
                rpc,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read().decode("utf-8")
                body = json.loads(raw)
            except Exception:
                continue

            if not isinstance(body, dict) or body.get("error"):
                continue

            result = body.get("result")
            if not isinstance(result, list) or not result:
                continue

            if len(result) == 1:
                return str(int(result[0], 16))

            low = int(result[0], 16)
            high = int(result[1], 16)
            return str(low + (high << 128))

        return None

    @staticmethod
    def _parse_starkli_u256_output(output: str) -> Optional[str]:
        """Parse starkli call output for felt/u256 return values."""
        felts = re.findall(r"0x[0-9a-fA-F]+", output or "")
        if not felts:
            return None

        if len(felts) == 1:
            return str(int(felts[0], 16))

        low = int(felts[0], 16)
        high = int(felts[1], 16)
        return str(low + (high << 128))

    async def update_balance_cache(
        self,
        conn,
        contract_address: str,
        balance_wei: str,
        token_address: str = "native",
    ):
        now = time.time()
        await conn.execute(
            """INSERT INTO balance_cache (contract_address, token_address, balance_wei, updated_at)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT(contract_address, token_address)
               DO UPDATE SET balance_wei = $3, updated_at = $4""",
            contract_address, token_address, balance_wei, now,
        )

    async def get_cached_balance(
        self, conn, contract_address: str, token_address: str = "native", ttl: float = 30.0
    ) -> Optional[str]:
        now = time.time()
        row = await conn.fetchrow(
            """SELECT balance_wei, updated_at FROM balance_cache
               WHERE contract_address = $1 AND token_address = $2""",
            contract_address, token_address,
        )
        if row and (now - dict(row)["updated_at"]) < ttl:
            return dict(row)["balance_wei"]
        return None
