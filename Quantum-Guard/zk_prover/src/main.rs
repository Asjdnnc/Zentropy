//! QuantumGuard Prover — CLI entry point.
//!
//! Usage:
//!   prover test              Run self-test (generate + verify + prove)
//!   prover verify            Read JSON from stdin, output proof JSON to stdout
//!   prover serve --port 8001 Start HTTP server mode

use clap::{Parser, Subcommand};
use quantum_prover::prover::{QuantumProver, VerifyRequest};

#[derive(Parser)]
#[command(name = "quantum_prover")]
#[command(about = "Off-chain ML-DSA-44 signature verifier for QuantumGuard")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run self-test: generate keypair, sign, verify, produce proof
    Test,
    /// Read a JSON VerifyRequest from stdin, output SignatureProof to stdout
    Verify,
    /// Start HTTP server mode for the Python backend to call
    Serve {
        #[arg(short, long, default_value = "8001")]
        port: u16,
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Test => cmd_test(),
        Commands::Verify => cmd_verify(),
        Commands::Serve { port } => cmd_serve(port),
    }
}

// ─── Test command ──────────────────────────────────────────────────

fn cmd_test() {
    println!("=== QuantumGuard Prover Self-Test ===\n");

    // 1. Generate keypair
    let sig_alg = oqs::sig::Sig::new(oqs::sig::Algorithm::MlDsa44)
        .expect("Failed to init ML-DSA-44");
    let (pk, sk) = sig_alg.keypair().expect("Keypair generation failed");
    println!("✓ Generated ML-DSA-44 keypair");
    println!("  Public key : {} bytes", pk.len());
    println!("  Secret key : {} bytes", sk.len());

    // 2. Sign a test message
    let message = b"QuantumGuard self-test message";
    let signature = sig_alg.sign(message, &sk).expect("Signing failed");
    println!("✓ Signed message ({} bytes)", signature.len());

    // 3. Verify and produce proof
    let proof = QuantumProver::verify_and_prove(message, signature.as_ref(), pk.as_ref())
        .expect("Verification failed");
    println!("✓ Verification result: {}", proof.valid);
    println!("  Proof commitment : {}...", &proof.proof_commitment[..16]);
    println!(
        "  Size reduction   : {} bytes → 32 bytes ({}% savings)",
        proof.signature_size,
        100 - (32 * 100 / proof.signature_size)
    );

    // 4. Negative test: tampered message
    let bad_proof = QuantumProver::verify_and_prove(b"tampered", signature.as_ref(), pk.as_ref())
        .expect("Verification call failed");
    assert!(!bad_proof.valid, "Tampered message should fail!");
    println!("✓ Tampered message correctly rejected");

    println!("\n✓✓✓ All prover tests passed! ✓✓✓");
}

// ─── Verify command (stdin JSON → stdout JSON) ────────────────────

fn cmd_verify() {
    use std::io::Read;

    let mut input = String::new();
    std::io::stdin()
        .read_to_string(&mut input)
        .expect("Failed to read stdin");

    let req: VerifyRequest = serde_json::from_str(&input).unwrap_or_else(|e| {
        eprintln!("Invalid JSON input: {}", e);
        std::process::exit(1);
    });

    match QuantumProver::verify_from_request(&req) {
        Ok(proof) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&proof).expect("JSON serialization failed")
            );
        }
        Err(e) => {
            eprintln!("Verification error: {}", e);
            std::process::exit(1);
        }
    }
}

// ─── Serve command (HTTP server) ───────────────────────────────────

fn cmd_serve(port: u16) {
    let rt = tokio::runtime::Runtime::new().expect("Failed to create Tokio runtime");
    rt.block_on(async {
        quantum_prover::server::run_server(port)
            .await
            .expect("Server failed");
    });
}
