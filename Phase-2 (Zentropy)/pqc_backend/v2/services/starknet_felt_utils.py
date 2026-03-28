"""Helpers for canonical Starknet felt argument formatting."""

from __future__ import annotations

import re


_HEX_RE = re.compile(r"^[0-9a-f]+$")


def normalize_sha256_hex(value: str) -> str:
    """Normalize a SHA-256 hex string (with or without 0x) to lowercase hex body."""
    raw = (value or "").strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]

    if not raw or not _HEX_RE.fullmatch(raw):
        raise ValueError("hash must be non-empty lowercase/uppercase hex")
    if len(raw) > 64:
        raise ValueError("hash length must be <= 64 hex chars")

    return raw


def pubkey_hash_to_felt(pubkey_hash: str) -> str:
    """
    Convert a SHA-256 pubkey hash into the felt encoding used by contracts.

    Account contracts store the first 31 bytes of the hash to fit felt252.
    """
    body = normalize_sha256_hex(pubkey_hash)
    felt_body = body[:62]
    return "0x" + felt_body
