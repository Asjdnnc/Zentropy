"""
QuantumGuard PQC Backend
========================
Post-quantum cryptographic kernel using ML-DSA-44 (Dilithium)
for quantum-resistant digital signatures with hybrid seed generation.

Modules:
    config            - Algorithm parameters & path configuration
    key_manager       - Generate, store, and load ML-DSA keypairs (system PRNG + hybrid seed)
    signer            - Create and verify ML-DSA detached signatures
    utils             - Shared utilities (encoding, hashing, hybrid seed generation)
    drand_integration - Fetch publicly verifiable randomness from Drand beacon network
    merkle_audit      - Append-only SHA-256 Merkle tree for tamper-evident audit trail
    batch_committer   - Background service to commit Merkle batches to Starknet
    persistence       - SQLite persistence + Merkle batch/leaf storage
    transfer_handler  - Full transfer pipeline (sign, prove, execute, audit)
"""

__version__ = "0.2.0"
