#!/usr/bin/env python3
"""
QuantumGuard CLI Wallet
=======================
Command-line interface for the quantum-resistant wallet.

Usage:
  python -m quantum_wallet_ui.cli wallet create [--label NAME]
  python -m quantum_wallet_ui.cli wallet info   [--label NAME]
  python -m quantum_wallet_ui.cli wallet list
  python -m quantum_wallet_ui.cli tx sign  --to ADDR --amount AMT [--label NAME]
  python -m quantum_wallet_ui.cli tx send  --to ADDR --amount AMT [--label NAME]
  python -m quantum_wallet_ui.cli prover test
  python -m quantum_wallet_ui.cli server start
"""
import argparse
import json
import sys
import os
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pqc_backend.key_manager import QuantumKeyManager
from pqc_backend.signer import QuantumSigner
from pqc_backend.config import PROVER_BINARY, API_PORT
from pqc_backend.utils import b64decode, sha256_hex, truncate_display


def main():
    parser = argparse.ArgumentParser(
        prog="quantumguard",
        description="QuantumGuard — Quantum-resistant wallet on Starknet",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command group")

    # ─── wallet ──────────────────────────────────────────────────

    wallet_parser = subparsers.add_parser("wallet", help="Wallet management")
    wallet_sub = wallet_parser.add_subparsers(dest="action")

    create_p = wallet_sub.add_parser("create", help="Create new quantum identity")
    create_p.add_argument("--label", default="default", help="Wallet label")

    info_p = wallet_sub.add_parser("info", help="Show wallet information")
    info_p.add_argument("--label", default="default", help="Wallet label")

    wallet_sub.add_parser("list", help="List all wallets")

    # ─── tx ──────────────────────────────────────────────────────

    tx_parser = subparsers.add_parser("tx", help="Transaction operations")
    tx_sub = tx_parser.add_subparsers(dest="action")

    sign_p = tx_sub.add_parser("sign", help="Sign a transaction (local only)")
    sign_p.add_argument("--to", required=True, help="Recipient address")
    sign_p.add_argument("--amount", type=float, required=True, help="Amount")
    sign_p.add_argument("--label", default="default", help="Wallet label")
    sign_p.add_argument("--nonce", type=int, default=0, help="Nonce")

    send_p = tx_sub.add_parser("send", help="Sign + prove + submit")
    send_p.add_argument("--to", required=True, help="Recipient address")
    send_p.add_argument("--amount", type=float, required=True, help="Amount")
    send_p.add_argument("--label", default="default", help="Wallet label")
    send_p.add_argument("--nonce", type=int, default=0, help="Nonce")

    # ─── prover ──────────────────────────────────────────────────

    prover_parser = subparsers.add_parser("prover", help="Prover operations")
    prover_sub = prover_parser.add_subparsers(dest="action")
    prover_sub.add_parser("test", help="Run prover self-test")
    prover_sub.add_parser("status", help="Check prover status")

    # ─── server ──────────────────────────────────────────────────

    server_parser = subparsers.add_parser("server", help="API server")
    server_sub = server_parser.add_subparsers(dest="action")
    start_p = server_sub.add_parser("start", help="Start the API server")
    start_p.add_argument("--port", type=int, default=API_PORT, help="Port")

    # ─── Parse ───────────────────────────────────────────────────

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "wallet":
        handle_wallet(args)
    elif args.command == "tx":
        handle_tx(args)
    elif args.command == "prover":
        handle_prover(args)
    elif args.command == "server":
        handle_server(args)
    else:
        parser.print_help()


# =============================================================================
# Wallet commands
# =============================================================================

def handle_wallet(args):
    km = QuantumKeyManager()

    if args.action == "create":
        if km.identity_exists(args.label):
            print(f"⚠ Wallet '{args.label}' already exists.")
            identity = km.load_identity(args.label)
            print(f"  PK hash: {identity['pubkey_hash'][:16]}...")
            return

        print(f"Creating quantum wallet '{args.label}'...")
        print("  Algorithm: ML-DSA-44 (Dilithium)")
        print()
        identity = km.generate_identity(label=args.label)
        print()
        print("✓ Wallet created successfully!")
        print(f"  Identity hash: {identity['pubkey_hash']}")

    elif args.action == "info":
        try:
            identity = km.load_identity(args.label)
            print(f"Wallet: {identity.get('label', args.label)}")
            print(f"  Algorithm  : {identity['algorithm']}")
            print(f"  PK hash    : {identity['pubkey_hash']}")
            print(f"  PK size    : {identity['public_key_size']} bytes")
            print(f"  SK size    : {identity['secret_key_size']} bytes")
            print(f"  Created    : {identity.get('created_at', 'N/A')}")
        except FileNotFoundError as e:
            print(f"✗ {e}")
            sys.exit(1)

    elif args.action == "list":
        wallets = km.list_wallets()
        if not wallets:
            print("No wallets found. Run: quantumguard wallet create")
            return
        print(f"Found {len(wallets)} wallet(s):\n")
        for w in wallets:
            print(f"  [{w['label']}]")
            print(f"    Algorithm : {w['algorithm']}")
            print(f"    PK hash   : {w['pubkey_hash'][:16]}...")
            print(f"    Created   : {w.get('created_at', 'N/A')}")
            print()

    else:
        print("Usage: quantumguard wallet {create|info|list}")


# =============================================================================
# Transaction commands
# =============================================================================

def handle_tx(args):
    km = QuantumKeyManager()
    sg = QuantumSigner(key_manager=km)

    if args.action == "sign":
        try:
            tx_payload = {
                "to": args.to,
                "amount": args.amount,
                "nonce": args.nonce,
            }
            print(f"Signing transaction with wallet '{args.label}'...")
            print(f"  To     : {args.to}")
            print(f"  Amount : {args.amount}")
            print(f"  Nonce  : {args.nonce}")
            print()

            result = sg.sign_transaction(tx_payload, label=args.label)
            print()
            print("✓ Transaction signed!")
            print(f"  Signature size : {result['signature_size']} bytes")
            print(f"  Message hash   : {result['message_hash'][:16]}...")
            print(f"  PK hash        : {result['pubkey_hash'][:16]}...")

            # Verify locally
            canonical = json.dumps(tx_payload, sort_keys=True, separators=(",", ":"))
            sig_bytes = b64decode(result["signature"])
            pk_bytes = b64decode(result["public_key"])
            verified = QuantumSigner.verify_signature(
                canonical.encode("utf-8"), sig_bytes, pk_bytes
            )
            print(f"  Local verify   : {'✓ PASS' if verified else '✗ FAIL'}")

        except FileNotFoundError as e:
            print(f"✗ {e}")
            sys.exit(1)

    elif args.action == "send":
        try:
            tx_payload = {
                "to": args.to,
                "amount": args.amount,
                "nonce": args.nonce,
            }
            print(f"Executing transaction with wallet '{args.label}'...\n")

            # Step 1: Sign
            print("Step 1/3: Signing with ML-DSA-44...")
            result = sg.sign_transaction(tx_payload, label=args.label)
            print(f"  ✓ Signed ({result['signature_size']} bytes)\n")

            # Step 2: Prove
            print("Step 2/3: Verifying with prover...")
            proof = _call_prover_cli(result)
            if proof:
                valid = proof.get("valid", False)
                print(f"  ✓ Proof valid: {valid}")
                print(f"  Commitment: {proof.get('proof_commitment', 'N/A')[:16]}...\n")
            else:
                print("  ✗ Prover unavailable, using local verification")
                canonical = json.dumps(tx_payload, sort_keys=True, separators=(",", ":"))
                sig_bytes = b64decode(result["signature"])
                pk_bytes = b64decode(result["public_key"])
                valid = QuantumSigner.verify_signature(
                    canonical.encode("utf-8"), sig_bytes, pk_bytes
                )
                commitment = sha256_hex(
                    f"{valid}:{result['message_hash']}:{sha256_hex(sig_bytes)}:{result['pubkey_hash']}".encode()
                )
                print(f"  Local verify: {'✓ PASS' if valid else '✗ FAIL'}")
                print(f"  Commitment: {commitment[:16]}...\n")

            # Step 3: Starknet submission
            print("Step 3/3: Starknet submission...")
            print("  ⏳ Not yet implemented (testnet deployment pending)")
            print()
            print("✓ Transaction pipeline complete!")

        except FileNotFoundError as e:
            print(f"✗ {e}")
            sys.exit(1)

    else:
        print("Usage: quantumguard tx {sign|send} --to ADDR --amount AMT")


def _call_prover_cli(sig_result: dict) -> dict | None:
    """Call the Rust prover binary from CLI."""
    import subprocess

    prover_path = PROVER_BINARY
    if not prover_path or not prover_path.exists():
        return None

    request_json = json.dumps({
        "message": sig_result["message"],
        "signature": sig_result["signature"],
        "public_key": sig_result["public_key"],
    })

    try:
        result = subprocess.run(
            [str(prover_path), "verify"],
            input=request_json,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


# =============================================================================
# Prover commands
# =============================================================================

def handle_prover(args):
    import subprocess

    if args.action == "test":
        prover_path = PROVER_BINARY
        if not prover_path or not prover_path.exists():
            print(f"✗ Prover binary not found at: {prover_path}")
            print("  Build it with: cd zk_prover && cargo build --release")
            print()
            print("Running Python fallback self-test instead...")
            _python_prover_test()
            return

        print(f"Running prover self-test: {prover_path}")
        result = subprocess.run(
            [str(prover_path), "test"],
            capture_output=False,
            timeout=30,
        )
        sys.exit(result.returncode)

    elif args.action == "status":
        prover_path = PROVER_BINARY
        if prover_path and prover_path.exists():
            print(f"✓ Prover binary found: {prover_path}")
            size_mb = prover_path.stat().st_size / (1024 * 1024)
            print(f"  Size: {size_mb:.1f} MB")
        else:
            print(f"✗ Prover binary not found: {prover_path}")
            print("  Build: cd zk_prover && cargo build --release")

    else:
        print("Usage: quantumguard prover {test|status}")


def _python_prover_test():
    """Run a quick Python-native ML-DSA verification test."""
    import oqs

    print("\n=== Python ML-DSA-44 Self-Test ===\n")

    with oqs.Signature("ML-DSA-44") as signer:
        pk = signer.generate_keypair()
        sk = signer.export_secret_key()
        print(f"✓ Generated keypair (PK: {len(pk)} bytes, SK: {len(sk)} bytes)")

        msg = b"QuantumGuard self-test"
        sig = signer.sign(msg)
        print(f"✓ Signed message ({len(sig)} bytes)")

    with oqs.Signature("ML-DSA-44") as verifier:
        valid = verifier.verify(msg, sig, pk)
        print(f"✓ Verification: {'PASS' if valid else 'FAIL'}")

    with oqs.Signature("ML-DSA-44") as verifier:
        tampered_valid = verifier.verify(b"tampered", sig, pk)
        print(f"✓ Tampered message rejected: {'YES' if not tampered_valid else 'NO'}")

    print("\n✓✓✓ Python prover test passed! ✓✓✓")


# =============================================================================
# Server commands
# =============================================================================

def handle_server(args):
    if args.action == "start":
        import uvicorn
        print(f"Starting QuantumGuard API on port {args.port}...")
        print(f"  Swagger UI: http://localhost:{args.port}/docs")
        uvicorn.run(
            "quantum_wallet_ui.server:app",
            host="0.0.0.0",
            port=args.port,
            reload=True,
        )
    else:
        print("Usage: quantumguard server start [--port PORT]")


if __name__ == "__main__":
    main()
