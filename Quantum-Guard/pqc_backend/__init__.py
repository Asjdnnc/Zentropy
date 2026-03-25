"""
QuantumGuard PQC Backend v2
===========================
Multi-user custodial wallet system using ML-DSA-44 (Dilithium)
for quantum-resistant digital signatures on Starknet.

Core Services:
    KeyService              - ML-DSA-44 keypair generation, AES-256-GCM encryption, signing
    WalletService           - Organization/user/wallet management with counterfactual addresses
    TransactionService      - Full pipeline: sign → prove → batch → Starknet submit
    MerkleService           - SHA-256 Merkle tree batching with finalization
    AuditService            - Hash-chained immutable audit log for tamper detection

Infrastructure:
    db/                     - PostgreSQL (primary) / SQLite (fallback) connection pool & migrations
    models/                 - Pydantic schemas & algorithm constants (ML-DSA-44, ML-KEM-768)
    api/                    - FastAPI REST router (14+ endpoints, Bearer token auth)
    tests/                  - Unit & integration tests
"""

__version__ = "2.0.0"
