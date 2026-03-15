//! HTTP server mode for the prover.
//!
//! Exposes a REST API so the Python backend can call the prover over HTTP
//! instead of spawning a subprocess.
//!
//! Endpoints:
//!   POST /verify  — Accept a VerifyRequest, return a SignatureProof
//!   GET  /health  — Health check

use actix_web::{web, App, HttpServer, HttpResponse};
use crate::prover::{QuantumProver, VerifyRequest};

/// POST /verify — Verify an ML-DSA signature and return proof
async fn verify_handler(req: web::Json<VerifyRequest>) -> HttpResponse {
    match QuantumProver::verify_from_request(&req) {
        Ok(proof) => HttpResponse::Ok().json(proof),
        Err(e) => HttpResponse::BadRequest().json(serde_json::json!({
            "error": e,
        })),
    }
}

/// GET /health — Simple health check
async fn health_handler() -> HttpResponse {
    HttpResponse::Ok().json(serde_json::json!({
        "status": "healthy",
        "service": "quantum_prover",
        "algorithm": "ML-DSA-44",
    }))
}

/// Start the prover HTTP server on the given port.
pub async fn run_server(port: u16) -> std::io::Result<()> {
    println!("🔐 QuantumGuard Prover Server starting on port {}", port);
    println!("   POST /verify  — Verify ML-DSA signature");
    println!("   GET  /health  — Health check");
    println!();

    HttpServer::new(|| {
        App::new()
            .route("/verify", web::post().to(verify_handler))
            .route("/health", web::get().to(health_handler))
    })
    .bind(("0.0.0.0", port))?
    .run()
    .await
}
