import pytest

from pqc_backend.v2.services.starknet_felt_utils import (
    normalize_sha256_hex,
    pubkey_hash_to_felt,
)


def test_normalize_sha256_hex_accepts_prefixed_and_unprefixed_values():
    raw = "Ab" * 32
    assert normalize_sha256_hex(raw) == ("ab" * 32)
    assert normalize_sha256_hex("0x" + raw) == ("ab" * 32)


def test_pubkey_hash_to_felt_truncates_to_31_bytes():
    source = "f" * 64
    assert pubkey_hash_to_felt(source) == "0x" + ("f" * 62)


def test_pubkey_hash_to_felt_keeps_shorter_values():
    assert pubkey_hash_to_felt("0x1234") == "0x1234"


def test_normalize_sha256_hex_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        normalize_sha256_hex("")
    with pytest.raises(ValueError):
        normalize_sha256_hex("0xzz")
    with pytest.raises(ValueError):
        normalize_sha256_hex("a" * 65)
