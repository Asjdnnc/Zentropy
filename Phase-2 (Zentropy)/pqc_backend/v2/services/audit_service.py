"""
QuantumGuard v2 — Audit Service
=================================
Immutable, hash-chained audit log for compliance and tamper detection.

Each audit entry hashes the previous entry, forming a chain:
  log_hash(N) = SHA256(log_hash(N-1) || action || entity_id || timestamp)

If any entry is modified or deleted, the chain breaks and
subsequent hashes no longer verify.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from ..db.connection import get_db

logger = logging.getLogger("quantumguard.audit")


class AuditService:
    """Append-only audit log with hash chaining."""

    async def log(
        self,
        conn,
        org_id: str,
        user_id: Optional[str],
        entity_type: str,
        entity_id: str,
        action: str,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> int:
        """
        Record an audit event.  Returns the log_id.
        """
        now = time.time()

        # Fetch previous hash for chaining
        prev = await conn.fetchrow(
            """SELECT log_hash FROM audit_log
               WHERE org_id = $1
               ORDER BY log_id DESC LIMIT 1""",
            org_id,
        )
        previous_hash = prev["log_hash"] if prev else "genesis"

        # Compute this entry's hash
        payload = f"{previous_hash}|{action}|{entity_type}|{entity_id}|{now}"
        log_hash = hashlib.sha256(payload.encode()).hexdigest()

        details_json = json.dumps(details) if details else None

        result = await conn.fetchval(
            """INSERT INTO audit_log
               (org_id, user_id, entity_type, entity_id, action,
                details, ip_address, user_agent,
                previous_log_hash, log_hash, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
               RETURNING log_id""",
            org_id, user_id, entity_type, entity_id, action,
            details_json, ip_address, user_agent,
            previous_hash, log_hash, now,
        )

        # For SQLite fallback which may not support RETURNING
        if result is None:
            row = await conn.fetchrow(
                "SELECT log_id FROM audit_log WHERE log_hash = $1", log_hash
            )
            result = row["log_id"] if row else 0

        logger.debug(
            "Audit: org=%s user=%s action=%s entity=%s/%s",
            org_id, user_id, action, entity_type, entity_id,
        )
        return result

    async def get_log(
        self,
        conn,
        org_id: str,
        user_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Query audit log with optional filters."""
        conditions = ["org_id = $1"]
        params: list[Any] = [org_id]
        idx = 2

        if user_id:
            conditions.append(f"user_id = ${idx}")
            params.append(user_id)
            idx += 1

        if entity_type:
            conditions.append(f"entity_type = ${idx}")
            params.append(entity_type)
            idx += 1

        where = " AND ".join(conditions)
        params.extend([limit, offset])

        rows = await conn.fetch(
            f"""SELECT log_id, org_id, user_id, entity_type, entity_id,
                       action, details, ip_address, previous_log_hash,
                       log_hash, created_at
                FROM audit_log
                WHERE {where}
                ORDER BY log_id DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params,
        )

        results = []
        for r in rows:
            entry = dict(r)
            if entry.get("details") and isinstance(entry["details"], str):
                try:
                    entry["details"] = json.loads(entry["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(entry)
        return results

    async def verify_chain_integrity(self, conn, org_id: str) -> dict:
        """
        Walk the audit chain and verify every hash.
        Returns {valid: bool, checked: int, first_broken: int|None}
        """
        rows = await conn.fetch(
            """SELECT log_id, action, entity_type, entity_id,
                      previous_log_hash, log_hash, created_at
               FROM audit_log
               WHERE org_id = $1
               ORDER BY log_id ASC""",
            org_id,
        )

        expected_prev = "genesis"
        checked = 0
        for r in rows:
            row = dict(r)
            # Recompute hash
            payload = (
                f"{row['previous_log_hash']}|{row['action']}|"
                f"{row['entity_type']}|{row['entity_id']}|{row['created_at']}"
            )
            recomputed = hashlib.sha256(payload.encode()).hexdigest()

            if recomputed != row["log_hash"]:
                return {
                    "valid": False,
                    "checked": checked,
                    "first_broken_log_id": row["log_id"],
                }

            if row["previous_log_hash"] != expected_prev:
                return {
                    "valid": False,
                    "checked": checked,
                    "first_broken_log_id": row["log_id"],
                }

            expected_prev = row["log_hash"]
            checked += 1

        return {"valid": True, "checked": checked, "first_broken_log_id": None}
