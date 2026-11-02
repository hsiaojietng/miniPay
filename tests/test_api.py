"""End-to-end tests for the v1 HTTP routes.

Requests go through FastAPI to the real services and commit to the minipay_test database,
which is emptied before each test (see conftest.py).
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.routes import get_conn
from app.main import app


def open_account(client, holder, deposit_cents=0):
    response = client.post("/v1/accounts", json={"holder": holder})
    assert response.status_code == 201, response.json()
    account_id = response.json()["id"]
    if deposit_cents:
        deposit(client, account_id, deposit_cents)
    return account_id


def deposit(client, account_id, amount_cents):
    response = client.post(f"/v1/accounts/{account_id}/deposits", json={"amount_cents": amount_cents})
    assert response.status_code == 201, response.json()
    return response.json()["transfer_id"]


def balance_of(client, account_id, holder):
    response = client.get(f"/v1/accounts/{account_id}/balance", headers={"X-Holder": holder})
    assert response.status_code == 200, response.json()
    return response.json()["balance_cents"]


def post_transfer(client, from_account_id, to_account_id, amount_cents, **extra):
    body = {"from_account_id": from_account_id, "to_account_id": to_account_id, "amount_cents": amount_cents}
    body.update(extra)
    return client.post("/v1/transfers", json=body)


@pytest.fixture
def alice(client):
    return open_account(client, "alice", deposit_cents=10000)


@pytest.fixture
def bob(client):
    return open_account(client, "bob")


# Open account

def test_open_account_starts_with_zero_balance(client):
    response = client.post("/v1/accounts", json={"holder": "alice"})

    assert response.status_code == 201
    body = response.json()
    assert body["holder"] == "alice"
    assert balance_of(client, body["id"], "alice") == 0


def test_open_account_twice_for_same_holder_is_rejected(client):
    open_account(client, "alice")

    response = client.post("/v1/accounts", json={"holder": "alice"})

    assert response.status_code == 409
    assert response.json()["code"] == "account_already_exists"


def test_cash_holder_is_reserved(client):
    response = client.post("/v1/accounts", json={"holder": "CASH"})

    assert response.status_code == 409


def test_open_account_rejects_unknown_field(client):
    response = client.post("/v1/accounts", json={"holder": "alice", "name": "Alice"})

    assert response.status_code == 422


# Deposit

def test_deposit_increases_balance(client, bob):
    deposit(client, bob, 3000)
    deposit(client, bob, 500)

    assert balance_of(client, bob, "bob") == 3500


def test_deposit_into_unknown_account_is_rejected(client):
    response = client.post(f"/v1/accounts/{uuid.uuid4()}/deposits", json={"amount_cents": 100})

    assert response.status_code == 404
    assert response.json()["code"] == "account_not_found"


@pytest.mark.parametrize("amount", [0, -1, 10.5])
def test_deposit_of_invalid_amount_is_rejected(client, bob, amount):
    response = client.post(f"/v1/accounts/{bob}/deposits", json={"amount_cents": amount})

    assert response.status_code == 422
    assert balance_of(client, bob, "bob") == 0


def test_deposit_in_other_currency_is_rejected(client, bob):
    response = client.post(f"/v1/accounts/{bob}/deposits", json={"amount_cents": 100, "currency": "USD"})

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_currency"


# Transfer

def test_transfer_moves_money(client, alice, bob):
    response = post_transfer(client, alice, bob, 3000)

    assert response.status_code == 201
    assert uuid.UUID(response.json()["transfer_id"])
    assert balance_of(client, alice, "alice") == 7000
    assert balance_of(client, bob, "bob") == 3000


def test_transfer_exceeding_balance_by_one_cent_is_rejected(client, alice, bob):
    response = post_transfer(client, alice, bob, 10001)

    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_funds"
    assert balance_of(client, alice, "alice") == 10000


def test_transfer_to_self_is_rejected(client, alice):
    response = post_transfer(client, alice, alice, 100)

    assert response.status_code == 422
    assert response.json()["code"] == "same_account_transfer"


def test_transfer_to_unknown_account_is_rejected(client, alice):
    response = post_transfer(client, alice, str(uuid.uuid4()), 100)

    assert response.status_code == 404
    assert response.json()["code"] == "account_not_found"


def test_same_transfer_sent_twice_is_applied_once(client, alice, bob):
    first = post_transfer(client, alice, bob, 3000, idempotency_key="k-1")
    second = post_transfer(client, alice, bob, 3000, idempotency_key="k-1")

    assert first.json()["transfer_id"] == second.json()["transfer_id"]
    assert balance_of(client, alice, "alice") == 7000


def test_transfer_with_misspelt_idempotency_key_is_rejected(client, alice, bob):
    response = post_transfer(client, alice, bob, 3000, idempotency_kye="k-1")

    assert response.status_code == 422
    assert balance_of(client, alice, "alice") == 10000


# Balance and statement

def test_balance_of_another_holders_account_is_denied(client, alice):
    response = client.get(f"/v1/accounts/{alice}/balance", headers={"X-Holder": "bob"})

    assert response.status_code == 403
    assert response.json()["code"] == "access_denied"


def test_balance_without_holder_header_is_rejected(client, alice):
    response = client.get(f"/v1/accounts/{alice}/balance")

    assert response.status_code == 422


def test_balance_of_unknown_account_is_not_found(client):
    response = client.get(f"/v1/accounts/{uuid.uuid4()}/balance", headers={"X-Holder": "alice"})

    assert response.status_code == 404


def test_balance_with_malformed_account_id_is_rejected(client):
    response = client.get("/v1/accounts/not-a-uuid/balance", headers={"X-Holder": "alice"})

    assert response.status_code == 422


def test_statement_shows_running_balance(client):
    # Spec: Alice has $30, sends $20 to Bob, deposits $20 -> 30, 10, 30.
    alice = open_account(client, "alice")
    bob = open_account(client, "bob")
    first_deposit = deposit(client, alice, 3000)
    sent = post_transfer(client, alice, bob, 2000).json()["transfer_id"]
    second_deposit = deposit(client, alice, 2000)

    response = client.get(f"/v1/accounts/{alice}/statement", headers={"X-Holder": "alice"})

    assert response.status_code == 200
    assert response.json() == {
        "account_id": alice,
        "currency": "SGD",
        "lines": [
            {"transfer_id": first_deposit, "amount_cents": 3000, "balance_after_cents": 3000},
            {"transfer_id": sent, "amount_cents": -2000, "balance_after_cents": 1000},
            {"transfer_id": second_deposit, "amount_cents": 2000, "balance_after_cents": 3000},
        ],
    }


def test_statement_of_another_holders_account_is_denied(client, alice):
    response = client.get(f"/v1/accounts/{alice}/statement", headers={"X-Holder": "bob"})

    assert response.status_code == 403


# Error shape: every error is {code, message}

def assert_error(response, status_code, code):
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"code", "message"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]


def test_insufficient_funds_is_422(client, alice, bob):
    assert_error(post_transfer(client, alice, bob, 10001), 422, "insufficient_funds")


def test_same_account_transfer_is_422(client, alice):
    assert_error(post_transfer(client, alice, alice, 100), 422, "same_account_transfer")


def test_unknown_account_is_404(client, alice):
    assert_error(post_transfer(client, alice, str(uuid.uuid4()), 100), 404, "account_not_found")


def test_invalid_amount_is_422(client, alice, bob):
    assert_error(post_transfer(client, alice, bob, 0), 422, "invalid_amount")


def test_other_validation_failure_is_422(client, alice, bob):
    response = post_transfer(client, alice, bob, 100, idempotency_kye="k-1")

    assert_error(response, 422, "validation_error")
    assert "idempotency_kye" in response.json()["message"]


def test_unknown_route_is_404(client):
    assert_error(client.get("/v1/nowhere"), 404, "not_found")


def test_unexpected_error_is_500_without_internal_details(database):
    # A closed connection makes the first query fail with an error no handler expects.
    broken = psycopg.connect(database)
    broken.close()
    app.dependency_overrides[get_conn] = lambda: broken
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(f"/v1/accounts/{uuid.uuid4()}/balance", headers={"X-Holder": "alice"})
    finally:
        app.dependency_overrides.clear()

    assert_error(response, 500, "internal_error")
    assert response.json()["message"] == "Internal server error"
