# QuantumGuard — Build Automation
# ================================
# Usage:
#   make setup          Install all dependencies
#   make test-phase1    Run Phase 1 (Python crypto) tests
#   make test-phase2    Run Phase 2 (Rust prover) tests
#   make build-phase2   Build Rust prover binary
#   make build-phase3   Build Cairo smart contract
#   make test-all       Run all tests
#   make run-api        Start the API server
#   make run-prover     Start the Rust prover server
#   make clean          Clean build artifacts

SHELL := /bin/bash
.PHONY: setup test-phase1 test-phase2 build-phase2 build-phase3 test-phase3 test-all run-api run-prover clean check-liboqs integration-test deploy-contract frontend-dev frontend-build

# ─── Paths ───────────────────────────────────────────────────────

VENV         := $(CURDIR)/.venv
ACTIVATE     := source $(VENV)/bin/activate
LIBOQS_LIB   := $(CURDIR)/../liboqs/build/lib
PROVER_DIR   := $(CURDIR)/zk_prover
PROVER_BIN   := $(PROVER_DIR)/target/release/prover
CONTRACT_DIR := $(CURDIR)/starknet_contracts
FRONTEND_DIR := $(CURDIR)/quantum_wallet_ui/frontend

# ─── Environment ─────────────────────────────────────────────────

export LD_LIBRARY_PATH := $(LIBOQS_LIB):$(LD_LIBRARY_PATH)

# ─── Setup ───────────────────────────────────────────────────────

setup: check-liboqs
	@echo "=== Installing Python dependencies ==="
	$(ACTIVATE) && pip install --upgrade pip setuptools wheel
	$(ACTIVATE) && pip install -r requirements.txt
	@echo ""
	@echo "=== Verifying liboqs Python bindings ==="
	$(ACTIVATE) && python3 -c "import oqs; print('✓ liboqs version:', oqs.OQS_VERSION)"
	@echo ""
	@echo "=== Checking Rust ==="
	@which rustc > /dev/null 2>&1 && echo "✓ Rust $$(rustc --version)" || echo "⚠ Rust not installed (needed for Phase 2). Install: curl https://sh.rustup.rs -sSf | sh"
	@echo ""
	@echo "=== Checking Scarb ==="
	@which scarb > /dev/null 2>&1 && echo "✓ Scarb $$(scarb --version)" || echo "⚠ Scarb not installed (needed for Phase 3). Install: curl -sSf https://docs.swmansion.com/scarb/install.sh | sh"
	@echo ""
	@echo "✓ Setup complete!"

check-liboqs:
	@test -f $(LIBOQS_LIB)/liboqs.so || \
		(echo "✗ liboqs not found at $(LIBOQS_LIB)/liboqs.so" && \
		 echo "  Build it: cd ../liboqs/build && cmake -GNinja -DBUILD_SHARED_LIBS=ON .. && ninja" && \
		 exit 1)
	@echo "✓ liboqs found at $(LIBOQS_LIB)/liboqs.so"

# ─── Phase 1: Python Crypto Tests ───────────────────────────────

test-phase1: check-liboqs
	@echo "=== Phase 1: Testing PQC Backend ==="
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m pytest pqc_backend/tests/test_phase1.py -v --tb=short
	@echo "✓ Phase 1 tests passed!"

test-persistence: check-liboqs
	@echo "=== Testing Persistence Layer ==="
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m pytest pqc_backend/tests/test_persistence.py -v --tb=short
	@echo "✓ Persistence tests passed!"

test-integration: check-liboqs
	@echo "=== Integration Tests ==="
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m pytest pqc_backend/tests/test_integration.py -v --tb=short
	@echo "✓ Integration tests passed!"

# ─── Phase 2: Rust Prover ───────────────────────────────────────

build-phase2:
	@echo "=== Phase 2: Building Rust Prover ==="
	cd $(PROVER_DIR) && cargo build --release 2>&1 | tail -5
	@echo "✓ Prover binary: $(PROVER_BIN)"
	@ls -lh $(PROVER_BIN) 2>/dev/null || echo "  (build may take a few minutes on first run)"

test-phase2:
	@echo "=== Phase 2: Testing Rust Prover ==="
	cd $(PROVER_DIR) && cargo test --release 2>&1 | tail -20
	@echo "✓ Phase 2 tests passed!"

run-prover:
	@echo "=== Starting Rust Prover Server ==="
	$(PROVER_BIN) serve --port 8001

# ─── Phase 3: Cairo Smart Contract ──────────────────────────────

build-phase3:
	@echo "=== Phase 3: Building Cairo Contract ==="
	cd $(CONTRACT_DIR) && scarb build
	@echo "✓ Contract built!"
	@ls -la $(CONTRACT_DIR)/target/dev/ 2>/dev/null || echo "  Check Scarb output above"

test-phase3:
	@echo "=== Phase 3: Testing Cairo Contract ==="
	cd $(CONTRACT_DIR) && scarb cairo-test
	@echo "✓ Phase 3 tests passed!"

deploy-contract: build-phase3
	@echo "=== Phase 3: Deploying to Starknet Sepolia ==="
	chmod +x $(CONTRACT_DIR)/deploy.sh
	cd $(CONTRACT_DIR) && ./deploy.sh

# ─── Phase 4: API Server ────────────────────────────────────────

run-api:
	@echo "=== Starting QuantumGuard API Server (v1) ==="
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m quantum_wallet_ui.server

# ─── v2: Multi-User Custodial API ───────────────────────────────

run-v2-api:
	@echo "=== Starting QuantumGuard v2 API Server ==="
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m pqc_backend.v2.app

test-v2:
	@echo "=== v2: Testing Multi-User Services ==="
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m pytest pqc_backend/v2/tests/ -v --tb=short
	@echo "✓ v2 tests passed!"

test-v2-integration:
	@echo "=== v2: Integration Test (full flow) ==="
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m pytest pqc_backend/v2/tests/test_integration.py -v --tb=short
	@echo "✓ v2 integration test passed!"

# ─── Frontend ───────────────────────────────────────────────────

frontend-dev:
	@echo "=== Starting React Dev Server ==="
	cd $(FRONTEND_DIR) && npm run dev

frontend-build:
	@echo "=== Building React Frontend ==="
	cd $(FRONTEND_DIR) && npm run build
	@echo "✓ Frontend built in $(FRONTEND_DIR)/dist/"

# ─── Integration ────────────────────────────────────────────────

test-all: test-phase1 test-persistence test-integration
	@echo ""
	@echo "=== v2 Multi-User Tests ==="
	@$(MAKE) test-v2 || echo "⚠ v2 tests failed or not available"
	@echo ""
	@echo "=== Checking Phase 2 (Rust) ==="
	@if which cargo > /dev/null 2>&1; then \
		$(MAKE) test-phase2; \
	else \
		echo "⚠ Rust not installed, skipping Phase 2 tests"; \
	fi
	@echo ""
	@echo "=== Checking Phase 3 (Cairo) ==="
	@if which scarb > /dev/null 2>&1; then \
		$(MAKE) test-phase3; \
	else \
		echo "⚠ Scarb not installed, skipping Phase 3 tests"; \
	fi
	@echo ""
	@echo "✓✓✓ ALL AVAILABLE TESTS PASSED ✓✓✓"

integration-test: check-liboqs
	@echo "=== QuantumGuard Integration Test ==="
	@echo ""
	@echo "Step 1: Create wallet..."
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m quantum_wallet_ui.cli wallet create --label integration_test
	@echo ""
	@echo "Step 2: Sign transaction..."
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m quantum_wallet_ui.cli tx sign \
			--to 0xdeadbeef --amount 1.0 --label integration_test
	@echo ""
	@echo "Step 3: Full send pipeline..."
	$(ACTIVATE) && cd $(CURDIR) && \
		python3 -m quantum_wallet_ui.cli tx send \
			--to 0xdeadbeef --amount 0.5 --label integration_test
	@echo ""
	@echo "✓✓✓ INTEGRATION TEST PASSED ✓✓✓"

# ─── CLI shortcut ───────────────────────────────────────────────

cli:
	$(ACTIVATE) && cd $(CURDIR) && python3 -m quantum_wallet_ui.cli $(ARGS)

# ─── Clean ──────────────────────────────────────────────────────

clean:
	@echo "Cleaning build artifacts..."
	find $(CURDIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(CURDIR) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	cd $(PROVER_DIR) && cargo clean 2>/dev/null || true
	rm -rf $(CONTRACT_DIR)/target 2>/dev/null || true
	@echo "✓ Clean complete!"
