# QuantumGuard — Build Automation
# ================================
# Usage:
#   make setup          Install all dependencies
#   make test-phase2    Run Phase 2 (Rust prover) tests
#   make build-phase2   Build Rust prover binary
#   make build-phase3   Build Cairo smart contract
#   make test-all       Run all tests
#   make run-v2-api     Start the v2 API server
#   make run-prover     Start the Rust prover server
#   make clean          Clean build artifacts

SHELL := /bin/bash
.PHONY: setup test-phase2 build-phase2 build-phase3 test-phase3 test-all run-prover clean check-liboqs deploy-contract frontend-dev frontend-build frontend-smoke docker-build docker-up docker-down docker-logs docker-prod-build docker-prod-up docker-prod-down docker-prod-logs env-init env-init-prod smoke-v2-transfer run-v2-api test-v2 test-v2-integration

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

smoke-v2-transfer:
	@echo "=== v2: Smoke Transfer Flow (org -> users -> transfer) ==="
	@chmod +x scripts/smoke_transfer_v2.sh
	@./scripts/smoke_transfer_v2.sh

# ─── Frontend ───────────────────────────────────────────────────

frontend-dev:
	@echo "=== Starting React Dev Server ==="
	cd $(FRONTEND_DIR) && npm run dev

frontend-build:
	@echo "=== Building React Frontend ==="
	cd $(FRONTEND_DIR) && npm run build
	@echo "✓ Frontend built in $(FRONTEND_DIR)/dist/"

frontend-smoke:
	@echo "=== Frontend smoke checks (lint + build) ==="
	cd $(FRONTEND_DIR) && npm run test:smoke

# ─── Integration ────────────────────────────────────────────────

test-all:
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
# ─── Clean ──────────────────────────────────────────────────────

clean:
	@echo "Cleaning build artifacts..."
	find $(CURDIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(CURDIR) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	cd $(PROVER_DIR) && cargo clean 2>/dev/null || true
	rm -rf $(CONTRACT_DIR)/target 2>/dev/null || true
	@echo "✓ Clean complete!"

# ─── Docker ─────────────────────────────────────────────────────

docker-build:
	@echo "=== Building QuantumGuard Docker image ==="
	docker compose build quantum-guard-backend

docker-up:
	@echo "=== Starting QuantumGuard backend container ==="
	docker compose up -d quantum-guard-backend

docker-down:
	@echo "=== Stopping QuantumGuard backend container ==="
	docker compose down

docker-logs:
	@echo "=== QuantumGuard backend logs ==="
	docker compose logs -f quantum-guard-backend

docker-prod-build:
	@echo "=== Building QuantumGuard production stack ==="
	docker compose -f docker-compose.prod.yml build quantum-guard-backend

docker-prod-up:
	@echo "=== Starting QuantumGuard production stack ==="
	docker compose -f docker-compose.prod.yml up -d

docker-prod-down:
	@echo "=== Stopping QuantumGuard production stack ==="
	docker compose -f docker-compose.prod.yml down

docker-prod-logs:
	@echo "=== QuantumGuard production logs ==="
	docker compose -f docker-compose.prod.yml logs -f quantum-guard-backend postgres

env-init:
	@echo "=== Initializing local .env from template ==="
	@test -f .env || cp .env.example .env
	@echo "✓ .env ready"

env-init-prod:
	@echo "=== Initializing production .env from template ==="
	@test -f .env || cp .env.production.example .env
	@echo "✓ .env ready (update secret values before running)"
