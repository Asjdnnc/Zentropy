# QuantumGuard

**QuantumGuard** is a robust, multi-layered system designed to provide quantum-resistant digital signatures and transaction security for the Starknet ecosystem. It bridges Post-Quantum Cryptography (PQC) with Zero-Knowledge (ZK) proofs to create a future-proof, secure wallet and transaction infrastructure.

## 🚀 Project Overview

The project is structured into four main phases/components, working together to deliver a secure, multi-user, quantum-resistant environment:

1. **Phase 1: Post-Quantum Cryptography Backend (`pqc_backend`)**
   - Built in **Python**.
   - Utilizes `liboqs-python` for implementing **ML-DSA-44 (Dilithium)** quantum-resistant digital signatures.
   - Features hybrid seed generation and verifiable randomness from the **Drand** beacon network.
   - Maintains a tamper-evident audit trail using append-only SHA-256 Merkle trees.
   - Includes SQLite persistence for key management and Merkle batch/leaf storage.
   - A background service (`batch_committer`) periodically commits Merkle roots to Starknet.
   - Provides a V2 Multi-User Custodial API.

2. **Phase 2: ZK Prover (`zk_prover`)**
   - Built in **Rust**.
   - A high-performance prover service designed to generate cryptographic zero-knowledge proofs for the transactions, verifying the PQC signatures and Merkle inclusion before interacting with the blockchain.

3. **Phase 3: Smart Contracts (`starknet_contracts`)**
   - Built in **Cairo** utilizing the **Scarb** toolchain.
   - Smart contracts designed to be deployed on **Starknet Sepolia**.
   - Handles the on-chain verification of proofs and the settlement of quantum-secured transactions.

4. **Phase 4: API & Frontend (`quantum_wallet_ui`)**
   - Built with **Python (FastAPI)** and **React**.
   - Exposes a REST API (`server.py`) for wallet creation, transaction signing, and execution.
   - Includes a user-friendly web interface (`frontend`) and a command-line interface (`cli.py`) for interacting with the QuantumGuard ecosystem.

## 🛠️ Prerequisites & Setup

Ensure you have the following installed:
- **Python 3.10+**
- **Rust & Cargo** (For Phase 2)
- **Scarb** (For Phase 3: Cairo contracts)
- **Node.js & npm** (For Phase 4: Frontend)
- **liboqs**: Required for the Python bindings.

### Installation

1. **Clone and setup dependencies:**
   ```bash
   make setup
   ```
   *This command installs all required Python packages (including fastapi, asyncpg, mnemonic, etc.), verifies the `liboqs` python bindings, and checks whether your machine has Rust and Scarb properly configured.*

2. **Build liboqs (if it's not setup yet):**
   ```bash
   cd ../liboqs/build && cmake -GNinja -DBUILD_SHARED_LIBS=ON .. && ninja
   ```

## 🏗️ Build & Run Instructions

QuantumGuard provides a comprehensive `Makefile` to quickly manage builds, tests, and services.

### Testing
- **Phase 1 (Python PQC Backend):** `make test-phase1`
- **Phase 2 (Rust Prover):** `make test-phase2`
- **Phase 3 (Cairo Contracts):** `make test-phase3`
- **All Core Tests:** `make test-all`
- **End-to-end Integration Tests:** `make integration-test`

### Running the Services
- **Start the API Server (v1):** `make run-api`
- **Start the API Server (v2 Multi-User):** `make run-v2-api`
- **Start the Rust Prover Server:** `make run-prover`
- **Start the Frontend Dev Server:** `make frontend-dev`

### Smart Contracts
- **Build Contracts:** `make build-phase3`
- **Deploy to Starknet Sepolia:** `make deploy-contract`

## 🔐 Architecture Breakdown

1. **Transaction Lifecycle**
   - A user initiates a transaction via the **React UI** or **CLI**.
   - The **PQC Backend** signs the transaction payload using the ML-DSA-44 algorithm.
   - The transaction is securely hashed and appended to a local **Merkle Tree** for an irrepudiable audit trail.
   - The **Rust Prover** generates a mathematical proof demonstrating the signature's validity and the Merkle tree's integrity.
   - This proof, alongside the transaction details, is published to the **Starknet Smart Contract** for secure on-chain verification and execution.

2. **Security Features**
   - **Post-Quantum Security**: Secures user funds and data against potential future quantum computing attacks (such as Shor's algorithm).
   - **Drand Integration**: Injects transparent and biased-resistant randomness into key generation to ensure optimal entropy.
   - **Tamper-Evident Logs**: The local Merkle tree acts as a universally verifiable log, whose roots are securely anchored to the Starknet network layout by the `batch_committer`.

## 🧹 Maintenance

To easily clean up any build artifacts, python cache files, and compiled binaries from submodules:
```bash
make clean
```
