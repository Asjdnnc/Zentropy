//! Core prover logic: ML-DSA-44 signature verification + proof generation.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// Input to the prover: a base64-encoded signature bundle from the Python signer.
#[derive(Debug, Deserialize)]
pub struct VerifyRequest {
    pub message: String,    // base64-encoded
    pub signature: String,  // base64-encoded
    pub public_key: String, // base64-encoded
}

/// Output of the prover: verification result + compact proof commitment.
#[derive(Debug, Serialize, Clone)]
pub struct SignatureProof {
    pub valid: bool,
    pub message_hash: String,     // SHA-256 hex of raw message
    pub signature_hash: String,   // SHA-256 hex of raw signature
    pub pubkey_hash: String,      // SHA-256 hex of raw public key
    pub proof_commitment: String, // SHA-256 hex of (valid+hashes) — submitted on-chain
    pub signature_size: usize,
}

/// The core prover engine.
pub struct QuantumProver;

impl QuantumProver {
    /// Verify an ML-DSA-44 signature and produce a proof commitment.
    ///
    /// # Arguments
    /// * `message`    - Raw message bytes
    /// * `signature`  - Raw ML-DSA-44 signature bytes (2420 bytes)
    /// * `public_key` - Raw ML-DSA-44 public key bytes (1312 bytes)
    ///
    /// # Returns
    /// A `SignatureProof` containing the verification result and a compact
    /// SHA-256 commitment suitable for on-chain submission.
    pub fn verify_and_prove(
        message: &[u8],
        signature: &[u8],
        public_key: &[u8],
    ) -> Result<SignatureProof, String> {
        // 1. Verify the ML-DSA-44 signature using liboqs
        let sig_alg = oqs::sig::Sig::new(oqs::sig::Algorithm::MlDsa44)
            .map_err(|e| format!("Failed to init ML-DSA-44: {}", e))?;

        let pk = sig_alg
            .public_key_from_bytes(public_key)
            .ok_or_else(|| "Invalid public key length".to_string())?;

        let sig_ref = sig_alg
            .signature_from_bytes(signature)
            .ok_or_else(|| "Invalid signature length".to_string())?;

        let valid = sig_alg.verify(message, sig_ref, &pk).is_ok();

        // 2. Compute hashes for the proof
        let message_hash = sha256_hex(message);
        let signature_hash = sha256_hex(signature);
        let pubkey_hash = sha256_hex(public_key);

        // 3. Generate proof commitment
        //    commitment = SHA-256(valid || message_hash || signature_hash || pubkey_hash)
        let proof_input = format!(
            "{}:{}:{}:{}",
            valid, message_hash, signature_hash, pubkey_hash
        );
        let proof_commitment = sha256_hex(proof_input.as_bytes());

        Ok(SignatureProof {
            valid,
            message_hash,
            signature_hash,
            pubkey_hash,
            proof_commitment,
            signature_size: signature.len(),
        })
    }

    /// Verify from a JSON request (base64-encoded fields).
    pub fn verify_from_request(req: &VerifyRequest) -> Result<SignatureProof, String> {
        use base64::Engine;
        let engine = base64::engine::general_purpose::STANDARD;

        let message = engine
            .decode(&req.message)
            .map_err(|e| format!("Invalid base64 message: {}", e))?;
        let signature = engine
            .decode(&req.signature)
            .map_err(|e| format!("Invalid base64 signature: {}", e))?;
        let public_key = engine
            .decode(&req.public_key)
            .map_err(|e| format!("Invalid base64 public_key: {}", e))?;

        Self::verify_and_prove(&message, &signature, &public_key)
    }
}

/// Compute SHA-256 hex digest of arbitrary data.
fn sha256_hex(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    format!("{:x}", hasher.finalize())
}

// ─── Tests ──────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_signature_proof() {
        // Generate a fresh keypair and sign
        let sig_alg = oqs::sig::Sig::new(oqs::sig::Algorithm::MlDsa44).unwrap();
        let (pk, sk) = sig_alg.keypair().unwrap();
        let message = b"QuantumGuard test message";
        let signature = sig_alg.sign(message, &sk).unwrap();

        // Verify and prove
        let proof =
            QuantumProver::verify_and_prove(message, signature.as_ref(), pk.as_ref()).unwrap();
        assert!(proof.valid, "Valid signature should verify");
        assert_eq!(proof.signature_size, 2420);
        assert_eq!(proof.message_hash.len(), 64); // SHA-256 hex = 64 chars
        assert_eq!(proof.proof_commitment.len(), 64);
    }

    #[test]
    fn test_invalid_signature_proof() {
        let sig_alg = oqs::sig::Sig::new(oqs::sig::Algorithm::MlDsa44).unwrap();
        let (pk, sk) = sig_alg.keypair().unwrap();
        let message = b"Original message";
        let signature = sig_alg.sign(message, &sk).unwrap();

        // Verify with wrong message
        let proof =
            QuantumProver::verify_and_prove(b"tampered message", signature.as_ref(), pk.as_ref())
                .unwrap();
        assert!(!proof.valid, "Tampered message should fail verification");
    }

    #[test]
    fn test_wrong_key_fails() {
        let sig_alg = oqs::sig::Sig::new(oqs::sig::Algorithm::MlDsa44).unwrap();
        let (_pk1, sk1) = sig_alg.keypair().unwrap();
        let (pk2, _sk2) = sig_alg.keypair().unwrap();
        let message = b"Key mismatch test";
        let signature = sig_alg.sign(message, &sk1).unwrap();

        // Verify with wrong public key
        let proof =
            QuantumProver::verify_and_prove(message, signature.as_ref(), pk2.as_ref()).unwrap();
        assert!(!proof.valid, "Wrong key should fail verification");
    }

    #[test]
    fn test_proof_commitment_deterministic() {
        let sig_alg = oqs::sig::Sig::new(oqs::sig::Algorithm::MlDsa44).unwrap();
        let (pk, sk) = sig_alg.keypair().unwrap();
        let message = b"Determinism test";
        let signature = sig_alg.sign(message, &sk).unwrap();

        let proof1 =
            QuantumProver::verify_and_prove(message, signature.as_ref(), pk.as_ref()).unwrap();
        let proof2 =
            QuantumProver::verify_and_prove(message, signature.as_ref(), pk.as_ref()).unwrap();

        assert_eq!(
            proof1.proof_commitment, proof2.proof_commitment,
            "Same inputs must produce same proof commitment"
        );
    }
}
