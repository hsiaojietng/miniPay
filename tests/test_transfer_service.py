"""Integration tests for the Postgres-backed transfer service (docs/specs.md, "Transfer Amount").

Needs the db service from docker-compose.yml with docs/schema.sql applied; skipped otherwise.
Each test runs inside an outer transaction that is rolled back, so nothing is left behind.
"""

import uuid

import psycopg
import pytest

from app.db import repo
from app.db.connection import DATABASE_URL
from app.domain.errors import (
    AccountNotFound,
    InsufficientFunds,
    InvalidAmount,
    SameAccountTransfer,
    UnsupportedCurrency,
)
from app.domain.ledger import Entry
from app.services.transfer_service import transfer


@pytest.fixture(scope="module")
def database():
    # Probe once per module so a missing database costs one connect timeout, not one per test.
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as probe:
            probe.execute("SELECT 1 FROM ledger_entries LIMIT 1")
    except psycopg.OperationalError as e:
        pytest.skip(f"Postgres not reachable: {e}")
    except psycopg.errors.UndefinedTable:
        pytest.skip("Schema not applied (docs/schema.sql)")
    return DATABASE_URL


@pytest.fixture
def conn(database):
    connection = psycopg.connect(database)
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def cash(conn):
    return repo.insert_account(conn, f"CASH-{uuid.uuid4()}")


def _open_with_balance(conn, cash, owner, amount):
    account_id = repo.insert_account(conn, owner)
    if amount:
        transfer_id = repo.insert_transfer(conn, cash, account_id, amount, "COMPLETED")
        repo.insert_entries(conn, [
            Entry(transfer_id, cash, -amount),
            Entry(transfer_id, account_id, amount),
        ])
    return account_id


@pytest.fixture
def alice(conn, cash):
    return _open_with_balance(conn, cash, "alice", 10000)


@pytest.fixture
def bob(conn, cash):
    return _open_with_balance(conn, cash, "bob", 0)


def test_transfer_moves_money_and_entries_sum_to_zero(conn, alice, bob):
    transfer_id = transfer(conn, alice, bob, 2000)

    assert repo.balance_of(conn, alice) == 8000
    assert repo.balance_of(conn, bob) == 2000
    entries = repo.entries_for(conn, transfer_id)
    assert entries == [Entry(transfer_id, alice, -2000), Entry(transfer_id, bob, 2000)]
    assert sum(e.amount for e in entries) == 0
    assert repo.get_transfer(conn, transfer_id).status == "COMPLETED"


def test_transfer_of_entire_balance_is_allowed(conn, alice, bob):
    transfer(conn, alice, bob, 10000)

    assert repo.balance_of(conn, alice) == 0


@pytest.mark.parametrize("amount", [0, -1])
def test_non_positive_amount_is_rejected(conn, alice, bob, amount):
    with pytest.raises(InvalidAmount):
        transfer(conn, alice, bob, amount)


def test_amount_exceeding_balance_by_one_cent_is_rejected(conn, alice, bob):
    with pytest.raises(InsufficientFunds):
        transfer(conn, alice, bob, 10001)

    assert repo.balance_of(conn, alice) == 10000
    assert repo.balance_of(conn, bob) == 0


def test_transfer_to_self_is_rejected(conn, alice):
    with pytest.raises(SameAccountTransfer):
        transfer(conn, alice, alice, 100)


@pytest.mark.parametrize("unknown", [str(uuid.uuid4()), "not-a-uuid"])
def test_unknown_receiver_is_rejected(conn, alice, unknown):
    with pytest.raises(AccountNotFound):
        transfer(conn, alice, unknown, 100)


def test_unknown_sender_is_rejected(conn, bob):
    with pytest.raises(AccountNotFound):
        transfer(conn, str(uuid.uuid4()), bob, 100)


def test_non_sgd_currency_is_rejected(conn, alice, bob):
    with pytest.raises(UnsupportedCurrency):
        transfer(conn, alice, bob, 100, currency="USD")


def test_rejected_transfer_writes_nothing(conn, alice, bob):
    before = repo.all_entries(conn)

    with pytest.raises(InsufficientFunds):
        transfer(conn, alice, bob, 10001, idempotency_key="k-rejected")

    assert repo.all_entries(conn) == before
    assert repo.get_transfer_by_idempotency_key(conn, "k-rejected") is None


def test_same_request_sent_twice_is_applied_once(conn, alice, bob):
    key = f"k-{uuid.uuid4()}"

    first = transfer(conn, alice, bob, 3000, idempotency_key=key)
    second = transfer(conn, alice, bob, 3000, idempotency_key=key)

    assert second == first
    assert repo.balance_of(conn, alice) == 7000
    assert repo.balance_of(conn, bob) == 3000
