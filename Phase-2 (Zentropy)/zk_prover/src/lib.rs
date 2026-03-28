//! QuantumGuard Off-Chain Prover Library
//!
//! Verifies ML-DSA-44 (Dilithium) signatures off-chain and generates
//! compact proof commitments for on-chain submission.
//!
//! The proof commitment is SHA-256(valid || msg_hash || sig_hash || pk_hash),
//! which is ~32 bytes vs. the 2420-byte raw signature — a ~98.7% reduction.

pub mod prover;
pub mod server;
