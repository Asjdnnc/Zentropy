"""Unit tests for Starknet tx hash output parsing."""

from pqc_backend.v2.services.transaction_service import TransactionService


def test_extract_tx_hash_from_labeled_output():
    out = "transaction_hash: 0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    got = TransactionService._extract_starknet_tx_hash(out)
    assert got == "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def test_extract_tx_hash_from_standalone_line():
    out = "Invoking contract...\n0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\nDone"
    got = TransactionService._extract_starknet_tx_hash(out)
    assert got == "0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"


def test_extract_tx_hash_from_empty_output():
    assert TransactionService._extract_starknet_tx_hash("") == ""
