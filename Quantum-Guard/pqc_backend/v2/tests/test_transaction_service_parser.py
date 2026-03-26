"""Unit tests for Starknet tx hash output parsing."""

from pqc_backend.v2.services.transaction_service import TransactionService
from pqc_backend.v2.services.key_service import KeyService


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


def test_resolve_submitter_prefers_explicit_relayer(monkeypatch):
    monkeypatch.setenv("STARKNET_RELAYER_ADDRESS", "0x" + "a" * 64)
    monkeypatch.setenv("STARKNET_ACCOUNT_ADDRESS", "0x" + "b" * 64)
    got = TransactionService._resolve_submitter_identity_from_env()
    assert got == "0x" + "a" * 64


def test_resolve_submitter_falls_back_to_account_address(monkeypatch):
    monkeypatch.delenv("STARKNET_RELAYER_ADDRESS", raising=False)
    monkeypatch.setenv("STARKNET_ACCOUNT_ADDRESS", "0x" + "c" * 64)
    got = TransactionService._resolve_submitter_identity_from_env()
    assert got == "0x" + "c" * 64


def test_resolve_submitter_ignores_non_hex_account(monkeypatch):
    monkeypatch.delenv("STARKNET_RELAYER_ADDRESS", raising=False)
    monkeypatch.setenv("STARKNET_ACCOUNT_ADDRESS", "/home/shubham/.starkli/account.json")
    got = TransactionService._resolve_submitter_identity_from_env()
    assert got == ""


def test_resolve_submission_mode_default(monkeypatch):
    monkeypatch.delenv("STARKNET_SUBMISSION_MODE", raising=False)
    assert TransactionService._resolve_submission_mode() == "relayer"


def test_resolve_submission_mode_custom(monkeypatch):
    monkeypatch.setenv("STARKNET_SUBMISSION_MODE", "USER_ACCOUNT")
    assert TransactionService._resolve_submission_mode() == "user_account"


def test_resolve_submission_mode_prefers_account_mode(monkeypatch):
    monkeypatch.setenv("STARKNET_SUBMISSION_MODE", "relayer")
    assert TransactionService._resolve_submission_mode("user_account") == "user_account"


def test_extract_factory_address_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("STARKNET_FACTORY_ADDRESS", "0x" + "f" * 64)
    monkeypatch.setenv("WALLET_DEPLOY_COMMAND", "starkli invoke 0x" + "a" * 64 + " deploy_account ...")
    assert TransactionService._extract_factory_address_from_deploy_command() == "0x" + "f" * 64


def test_extract_factory_address_from_wallet_deploy_command(monkeypatch):
    monkeypatch.delenv("STARKNET_FACTORY_ADDRESS", raising=False)
    monkeypatch.setenv("WALLET_DEPLOY_COMMAND", "starkli invoke 0x" + "a" * 64 + " deploy_account 0x123")
    assert TransactionService._extract_factory_address_from_deploy_command() == "0x" + "a" * 64


def test_resolve_submitter_private_key_for_user_account():
    key_svc = KeyService()
    tx_svc = TransactionService(key_service=key_svc)
    encrypted = key_svc.encrypt_secret_key(b"0xabc123")
    got = tx_svc._resolve_submitter_private_key(
        submission_mode="user_account",
        encrypted_submitter_private_key=encrypted,
    )
    assert got == "0xabc123"


def test_resolve_submitter_private_key_ignored_for_relayer():
    key_svc = KeyService()
    tx_svc = TransactionService(key_service=key_svc)
    encrypted = key_svc.encrypt_secret_key(b"0xabc123")
    got = tx_svc._resolve_submitter_private_key(
        submission_mode="relayer",
        encrypted_submitter_private_key=encrypted,
    )
    assert got is None


def test_resolve_prover_url_prefers_explicit_url(monkeypatch):
    monkeypatch.setenv("PROVER_URL", "http://prover.internal:9000")
    monkeypatch.setenv("PROVER_PORT", "8001")
    assert TransactionService._resolve_prover_url() == "http://prover.internal:9000"


def test_resolve_prover_url_from_port(monkeypatch):
    monkeypatch.delenv("PROVER_URL", raising=False)
    monkeypatch.setenv("PROVER_PORT", "8001")
    monkeypatch.setenv("PROVER_HOST", "127.0.0.1")
    assert TransactionService._resolve_prover_url() == "http://127.0.0.1:8001"


def test_resolve_prover_url_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("PROVER_URL", raising=False)
    monkeypatch.delenv("PROVER_PORT", raising=False)
    assert TransactionService._resolve_prover_url() is None


def test_has_token_transfer_event_true():
    receipt = {
        "events": [
            {"from_address": "0x1234", "data": []},
            {
                "from_address": "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
                "keys": [
                    "0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9",
                    "0x1",
                    "0x2",
                ],
                "data": ["0x1", "0x0"],
            },
        ]
    }
    assert TransactionService._has_token_transfer_event(
        receipt,
        "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
    ) is True


def test_has_token_transfer_event_false():
    receipt = {
        "events": [
            {"from_address": "0x1234", "data": ["0x1"]},
        ]
    }
    assert TransactionService._has_token_transfer_event(
        receipt,
        "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
    ) is False


def test_normalize_starknet_address_pads_to_64_hex():
    got = TransactionService._normalize_starknet_address("0x1234")
    assert got == "0x" + ("0" * 60) + "1234"


def test_normalize_starknet_address_accepts_no_prefix_and_uppercase():
    got = TransactionService._normalize_starknet_address("ABCD")
    assert got == "0x" + ("0" * 60) + "abcd"


def test_normalize_starknet_address_rejects_invalid_hex():
    assert TransactionService._normalize_starknet_address("0xZZ11") == ""


def test_has_token_transfer_event_true_with_unpadded_receipt_address():
    receipt = {
        "events": [
            {
                "from_address": "0x4718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
                "keys": ["0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"],
                "data": ["0x1", "0x0"],
            },
        ]
    }
    assert TransactionService._has_token_transfer_event(
        receipt,
        "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
    ) is True


def test_has_token_transfer_event_true_with_no_prefix_receipt_address():
    receipt = {
        "events": [
            {
                "from_address": "04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
                "keys": ["0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"],
                "data": ["0x1", "0x0"],
            },
        ]
    }
    assert TransactionService._has_token_transfer_event(
        receipt,
        "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
    ) is True


def test_has_token_transfer_event_true_with_uppercase_receipt_address():
    receipt = {
        "events": [
            {
                "from_address": "0x04718F5A0FC34CC1AF16A1CDEE98FFB20C31F5CD61D6AB07201858F4287C938D",
                "keys": ["0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9"],
                "data": ["0x1", "0x0"],
            },
        ]
    }
    assert TransactionService._has_token_transfer_event(
        receipt,
        "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
    ) is True


def test_has_token_transfer_event_rejects_fee_transfer_when_expected_mismatch():
    receipt = {
        "events": [
            {
                "from_address": "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
                "keys": [
                    "0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9",
                    "0x07f5a30559c3b1d76cf0edd79ec7c442410a0fc885a6534a829078463a650c29",
                    "0x01176a1bd84444c89232ec27754698e5d2e7e1a7f1539f12027f28b23ec9f3d8",
                ],
                "data": ["0x22e3622d543400", "0x0"],
            }
        ]
    }
    assert TransactionService._has_token_transfer_event(
        receipt,
        "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
        expected_from_address="0x05c08f467e60c54414ae0268adc3daa215147b6ff90609dc4ebd6b1fd66f0d6f",
        expected_to_address="0x05c1fcbc4dba8900000000000000000000000000000000000000000000000000",
        expected_amount_wei="100000000000000000000",
    ) is False


def test_has_token_transfer_event_matches_expected_transfer_fields():
    receipt = {
        "events": [
            {
                "from_address": "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
                "keys": [
                    "0x99cd8bde557814842a3121e8ddfd433a539b8c9f14bf31ebf108d12e6196e9",
                    "0x05c08f467e60c54414ae0268adc3daa215147b6ff90609dc4ebd6b1fd66f0d6f",
                    "0x05c1fcbc4dba8900000000000000000000000000000000000000000000000000",
                ],
                "data": ["0x56bc75e2d63100000", "0x0"],
            }
        ]
    }
    assert TransactionService._has_token_transfer_event(
        receipt,
        "0x04718f5a0fc34cc1af16a1cdee98ffb20c31f5cd61d6ab07201858f4287c938d",
        expected_from_address="0x05c08f467e60c54414ae0268adc3daa215147b6ff90609dc4ebd6b1fd66f0d6f",
        expected_to_address="0x05c1fcbc4dba8900000000000000000000000000000000000000000000000000",
        expected_amount_wei="100000000000000000000",
    ) is True
