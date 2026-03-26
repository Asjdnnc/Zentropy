"""API validation and auth regression tests for QuantumGuard v2."""

# pyright: reportMissingImports=false

import os

from starlette.testclient import TestClient

from pqc_backend.v2.app import app


def _create_org(client: TestClient) -> dict:
    response = client.post(
        "/api/v2/org/create",
        json={
            "org_name": "Validation Test Org",
            "admin_email": "validation-org@example.com",
            "bootstrap_secret": os.environ.get("BOOTSTRAP_SECRET", "test_bootstrap_secret"),
        },
    )
    assert response.status_code == 200
    return response.json()


def test_list_users_requires_authorization_header() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v2/users", params={"limit": 50, "offset": 0})
        assert response.status_code == 422


def test_register_requires_authorization_header() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/users/register",
            json={"email": "test@example.com", "username": "tester"},
        )
        assert response.status_code == 422


def test_register_rejects_invalid_email_with_auth() -> None:
    with TestClient(app) as client:
        org = _create_org(client)
        api_key = org["api_key"]

        response = client.post(
            "/api/v2/users/register",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"email": "not-an-email", "username": "tester"},
        )
        assert response.status_code == 422


def test_register_accepts_valid_email_with_auth() -> None:
    with TestClient(app) as client:
        org = _create_org(client)
        api_key = org["api_key"]

        response = client.post(
            "/api/v2/users/register",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"email": "valid.user+tag@example.com", "username": "tester"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("user_id")
        assert body.get("wallet_id")


def test_user_transactions_requires_authorization_header() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v2/users/some-user/transactions", params={"limit": 1, "offset": 0})
        assert response.status_code == 422


def test_audit_verify_chain_route_not_shadowed() -> None:
    with TestClient(app) as client:
        org = _create_org(client)
        api_key = org["api_key"]
        response = client.get(
            "/api/v2/audit/verify-chain",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "valid" in body
        assert "checked" in body


    def test_wallet_route_scoped_to_requesting_org() -> None:
        with TestClient(app) as client:
            org1 = _create_org(client)
            org2 = client.post(
                "/api/v2/org/create",
                json={
                    "org_name": "Validation Test Org 2",
                    "admin_email": "validation-org2@example.com",
                    "bootstrap_secret": os.environ.get("BOOTSTRAP_SECRET", "test_bootstrap_secret"),
                },
            ).json()

            create_user = client.post(
                "/api/v2/users/register",
                headers={"Authorization": f"Bearer {org1['api_key']}"},
                json={"email": "org1-user@example.com", "username": "org1user"},
            )
            assert create_user.status_code == 200
            user_id = create_user.json()["user_id"]

            forbidden_read = client.get(
                f"/api/v2/users/{user_id}/wallet",
                headers={"Authorization": f"Bearer {org2['api_key']}"},
            )
            assert forbidden_read.status_code == 404
