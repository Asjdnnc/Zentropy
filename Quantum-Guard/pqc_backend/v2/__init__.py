"""
QuantumGuard v2 — Multi-User Custodial Wallet System
=====================================================
Post-quantum cryptographic custodial wallet with:
  - Per-user Dilithium (ML-DSA-44) key pairs
  - Per-user Starknet account contracts
  - Merkle-batched transaction auditing
  - HSM-backed key encryption (AES-256-GCM)
  - PostgreSQL persistence with full audit trail

Subpackages:
    models    — Pydantic data models & enums
    db        — PostgreSQL schema, migrations, and async connection pool
    services  — Business logic (wallet, transaction, merkle, key management)
    api       — FastAPI router endpoints
"""

__version__ = "2.0.0"
