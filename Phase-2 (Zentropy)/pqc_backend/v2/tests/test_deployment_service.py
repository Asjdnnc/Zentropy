"""Targeted unit tests for deployment address resolution helpers."""

import json
import os

import pytest

from pqc_backend.v2.services.deployment_service import DeploymentService


class _Completed:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_zero_hex_detection_handles_padded_values():
    svc = DeploymentService()

    assert svc._is_zero_hex("0x0") is True
    assert svc._is_zero_hex("0x0000000000000000000000000000000000000000000000000000000000000000") is True
    assert svc._is_zero_hex("0x0001") is False


def test_normalize_hex_rejects_invalid_values():
    svc = DeploymentService()

    assert svc._normalize_hex("") is None
    assert svc._normalize_hex("123") is None
    assert svc._normalize_hex("0xGG") is None
    assert svc._normalize_hex("0xAbCd") == "0xabcd"


def test_retryable_transient_error_detection():
    svc = DeploymentService()

    assert svc._is_retryable_transient_error("503 Service Unavailable") is True
    assert svc._is_retryable_transient_error("HTTP 429 Too Many Requests") is True
    assert svc._is_retryable_transient_error("Request timed out while submitting") is True
    assert svc._is_retryable_transient_error("invalid transaction signature") is False


def test_coerce_rpc_arg_overrides_existing_rpc(monkeypatch):
    svc = DeploymentService()
    monkeypatch.setenv("STARKNET_RPC", "https://alchemy-rpc")

    argv = ["starkli", "invoke", "0xabc", "fn", "--rpc", "https://old-rpc", "--account", "/tmp/a.json"]
    out = svc._coerce_rpc_arg(argv)

    idx = out.index("--rpc")
    assert out[idx + 1] == "https://alchemy-rpc"


def test_coerce_rpc_arg_appends_when_missing(monkeypatch):
    svc = DeploymentService()
    monkeypatch.setenv("STARKNET_RPC", "https://alchemy-rpc")

    argv = ["starkli", "invoke", "0xabc", "fn", "--account", "/tmp/a.json"]
    out = svc._coerce_rpc_arg(argv)

    assert out[-2:] == ["--rpc", "https://alchemy-rpc"]


def test_validate_starkli_args_requires_all_required_flags():
    svc = DeploymentService()
    argv = ["starkli", "invoke", "0xabc", "deploy_account"]

    with pytest.raises(RuntimeError) as exc:
        svc._validate_starkli_args(argv)

    assert "missing required flag" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_receipt_resolver_ignores_zero_equivalent(monkeypatch):
    svc = DeploymentService()
    factory = "0x06c7f300f61309e954c1f56b5bad6b71af50d087ba8f8286ffbbad233bf41e21"

    payload = {
        "events": [
            {
                "from_address": factory,
                "data": ["0x0000000000000000000000000000000000000000000000000000000000000000"],
            }
        ]
    }

    def _fake_run(*args, **kwargs):
        return _Completed(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("subprocess.run", _fake_run)

    resolved = await svc._resolve_deployed_address_from_receipt(
        tx_hash="0x123",
        factory_address=factory,
        rpc="https://example-rpc",
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_receipt_resolver_returns_non_zero_address(monkeypatch):
    svc = DeploymentService()
    factory = "0x06c7f300f61309e954c1f56b5bad6b71af50d087ba8f8286ffbbad233bf41e21"
    deployed = "0x018039a904274562ac27129e07e232269ae4f4099a2147015923ed918bf88a30"

    payload = {
        "events": [
            {
                "from_address": factory,
                "data": [deployed],
            }
        ]
    }

    def _fake_run(*args, **kwargs):
        return _Completed(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("subprocess.run", _fake_run)

    resolved = await svc._resolve_deployed_address_from_receipt(
        tx_hash="0x123",
        factory_address=factory,
        rpc="https://example-rpc",
    )
    assert resolved == deployed


@pytest.mark.asyncio
async def test_invoke_deploy_command_maps_0x_public_key_hash_to_felt(monkeypatch):
    svc = DeploymentService()
    env_key = "WALLET_DEPLOY_COMMAND"
    old_template = os.environ.get(env_key)

    os.environ[env_key] = (
        "starkli invoke 0xabc deploy_account 0x{public_key_hash} 0xclass {account_address} "
        "--rpc https://rpc --private-key 0xpk --account /tmp/account.json"
    )

    seen = {"argv": None}

    def _fake_run(argv, *args, **kwargs):
        seen["argv"] = argv
        return _Completed(returncode=0, stdout="0xdeadbeef", stderr="")

    monkeypatch.setattr("subprocess.run", _fake_run)

    try:
        await svc._invoke_deploy_command(
            account_id="acc_1",
            wallet_id="wal_1",
            account_address="0x1234",
            public_key_hash="f" * 64,
        )
    finally:
        if old_template is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = old_template

    assert seen["argv"] is not None
    expected_felt = "0x" + ("f" * 62)
    assert expected_felt in seen["argv"]
