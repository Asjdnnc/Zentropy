"""Unit tests for wallet balance parsing helpers."""

from pqc_backend.v2.services.wallet_service import WalletService


def test_parse_starkli_u256_output_single_felt():
    out = "0xc8"
    assert WalletService._parse_starkli_u256_output(out) == "200"


def test_parse_starkli_u256_output_u256_two_felts():
    # low=0x2a, high=0x1 => 2^128 + 42
    out = "0x2a\n0x1"
    expected = str((1 << 128) + 42)
    assert WalletService._parse_starkli_u256_output(out) == expected


def test_parse_starkli_u256_output_no_felts():
    assert WalletService._parse_starkli_u256_output("error: bad output") is None
