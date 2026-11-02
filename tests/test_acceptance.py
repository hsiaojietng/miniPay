"""Week 1 acceptance criteria (docs/specs.md, "Acceptance Criteria"), re-run over HTTP.

Every request goes through FastAPI, the services and a real COMMIT to minipay_test, which is
emptied before each test. Test names follow the spec's section and criterion number, and each
docstring is the criterion's text. Amounts are written in dollars, as the spec does.
"""

import psycopg
import pytest

from app.services.account_service import CASH_HOLDER

DOLLARS = 100  # cents per dollar


class Bank:
    """The HTTP calls the criteria need, phrased the way the spec talks about them."""

    def __init__(self, client):
        self.client = client

    def open_account(self, holder):
        return self.client.post("/v1/accounts", json={"holder": holder})

    def open(self, holder, dollars=0):
        response = self.open_account(holder)
        assert response.status_code == 201, response.json()
        account_id = response.json()["id"]
        if dollars:
            assert self.deposit(account_id, dollars).status_code == 201
        return account_id

    def deposit(self, account_id, dollars):
        return self.client.post(
            f"/v1/accounts/{account_id}/deposits", json={"amount_cents": dollars * DOLLARS}
        )

    def transfer(self, from_account_id, to_account_id, dollars):
        return self.client.post("/v1/transfers", json={
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "amount_cents": dollars * DOLLARS,
        })

    def reverse(self, transfer_id):
        return self.client.post(f"/v1/transfers/{transfer_id}/reversals")

    def balance(self, account_id, holder):
        response = self.client.get(f"/v1/accounts/{account_id}/balance", headers={"X-Holder": holder})
        assert response.status_code == 200, response.json()
        return response.json()["balance_cents"]

    def statement(self, account_id, holder):
        response = self.client.get(f"/v1/accounts/{account_id}/statement", headers={"X-Holder": holder})
        assert response.status_code == 200, response.json()
        return response.json()["lines"]


@pytest.fixture
def bank(client):
    return Bank(client)


def assert_error(response, status_code, code):
    assert response.status_code == status_code, response.json()
    assert response.json()["code"] == code


def cash_balance(database):
    # No route exposes the system's cash account, so this one check reads the database directly.
    with psycopg.connect(database) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(e.amount_cents), 0)
            FROM ledger_entries e JOIN accounts a ON a.id = e.account_id
            WHERE a.owner_name = %s
            """,
            (CASH_HOLDER,),
        ).fetchone()
    return int(row[0])


# Open Account

def test_open_account_1_new_account_starts_at_zero(bank):
    """Given Alice do not have an account, when she opts to create an account,
    then Alice's account will be created with $0."""
    response = bank.open_account("alice")

    assert response.status_code == 201
    assert bank.balance(response.json()["id"], "alice") == 0


def test_open_account_2_second_account_is_rejected(bank):
    """Given Alice already has an account, when she opts to create an account,
    the system will prompt account already exists."""
    bank.open("alice")

    assert_error(bank.open_account("alice"), 409, "account_already_exists")


# Deposit Amount

def test_deposit_1_moves_money_from_cash_to_account(bank, clean_database):
    """Given Alice has $10, when she deposits $30, then the special cash account will
    decrease by $30 and Alice account will increase by $30 to become $40."""
    alice = bank.open("alice", dollars=10)
    cash_before = cash_balance(clean_database)

    assert bank.deposit(alice, 30).status_code == 201

    assert bank.balance(alice, "alice") == 40 * DOLLARS
    assert cash_balance(clean_database) == cash_before - 30 * DOLLARS


def test_deposit_2_zero_deposit_is_rejected(bank):
    """Given Alice has $0, when Alice [deposits] $0, then system will prompt deposit has to be greater than 0."""
    alice = bank.open("alice")

    assert_error(bank.deposit(alice, 0), 422, "invalid_amount")
    assert bank.balance(alice, "alice") == 0


# Transfer Amount

def test_transfer_1_moves_money_and_entries_sum_to_zero(bank):
    """Given Alice has $100, Bob has $0. When Alice transfers $20 to Bob, then Alice will have
    $80 left and Bob will have $20. Also, the sum of entries will be 0."""
    alice = bank.open("alice", dollars=100)
    bob = bank.open("bob")

    response = bank.transfer(alice, bob, 20)

    assert response.status_code == 201
    assert bank.balance(alice, "alice") == 80 * DOLLARS
    assert bank.balance(bob, "bob") == 20 * DOLLARS
    transfer_id = response.json()["transfer_id"]
    entries = [
        line["amount_cents"]
        for line in bank.statement(alice, "alice") + bank.statement(bob, "bob")
        if line["transfer_id"] == transfer_id
    ]
    assert sorted(entries) == [-20 * DOLLARS, 20 * DOLLARS]
    assert sum(entries) == 0


def test_transfer_2_zero_transfer_is_rejected(bank):
    """Given Alice has $0, when Alice transfers $0, then system will prompt transfer has to be greater than 0."""
    alice = bank.open("alice")
    bob = bank.open("bob")

    assert_error(bank.transfer(alice, bob, 0), 422, "invalid_amount")


def test_transfer_3_transfer_above_balance_is_rejected(bank):
    """Given Alice has $20, when Alice transfers $30, then system will prompt account balance is not enough."""
    alice = bank.open("alice", dollars=20)
    bob = bank.open("bob")

    assert_error(bank.transfer(alice, bob, 30), 422, "insufficient_funds")
    assert bank.balance(alice, "alice") == 20 * DOLLARS
    assert bank.balance(bob, "bob") == 0


# View Account Balance

def test_view_balance_1_shows_current_balance(bank):
    """Given Alice has $30, when she views account balance, then system should present $30."""
    alice = bank.open("alice", dollars=30)

    assert bank.balance(alice, "alice") == 30 * DOLLARS


# View Account Statement

def test_view_statement_1_shows_running_balance(bank):
    """Given Alice has $30 and made a transfer of $20 to Bob and deposit of $20, when she views
    account statement, then system should present Alice had $30 at the start, show the account
    -$20 to Bob to become $10 and then +$20 to become $30 from the deposit."""
    alice = bank.open("alice", dollars=30)
    bob = bank.open("bob")
    assert bank.transfer(alice, bob, 20).status_code == 201
    assert bank.deposit(alice, 20).status_code == 201

    lines = bank.statement(alice, "alice")

    assert [(line["amount_cents"], line["balance_after_cents"]) for line in lines] == [
        (30 * DOLLARS, 30 * DOLLARS),
        (-20 * DOLLARS, 10 * DOLLARS),
        (20 * DOLLARS, 30 * DOLLARS),
    ]


def test_view_statement_2_shows_received_transfer(bank):
    """Given Bob has $20, when [he] views account statement, then system should present $20."""
    alice = bank.open("alice", dollars=20)
    bob = bank.open("bob")
    assert bank.transfer(alice, bob, 20).status_code == 201

    lines = bank.statement(bob, "bob")

    assert [(line["amount_cents"], line["balance_after_cents"]) for line in lines] == [
        (20 * DOLLARS, 20 * DOLLARS),
    ]


# Reverse an amount transfer
# No HTTP route exists yet: reversal is only implemented in the in-memory Ledger. These are written
# against the proposed POST /v1/transfers/{id}/reversals; strict=True fails the run once they pass,
# as a reminder to remove the marker.

no_reverse_route = pytest.mark.xfail(strict=True, reason="No reverse route yet")


@no_reverse_route
def test_reverse_1_reversal_returns_the_money(bank):
    """Given Alice made a transfer of $30 to Bob, when Alice makes a reverse transfer,
    then Alice's account +$30 and Bob's account -$30."""
    alice = bank.open("alice", dollars=30)
    bob = bank.open("bob")
    transfer_id = bank.transfer(alice, bob, 30).json()["transfer_id"]

    assert bank.reverse(transfer_id).status_code == 201

    assert bank.balance(alice, "alice") == 30 * DOLLARS
    assert bank.balance(bob, "bob") == 0


@no_reverse_route
def test_reverse_2_second_reversal_is_rejected(bank):
    """Given Alice has already made a reverse transfer, when Alice makes a reverse transfer,
    then system should prompt that no transfer has been made to be reversed."""
    alice = bank.open("alice", dollars=30)
    bob = bank.open("bob")
    transfer_id = bank.transfer(alice, bob, 30).json()["transfer_id"]
    assert bank.reverse(transfer_id).status_code == 201

    assert_error(bank.reverse(transfer_id), 409, "transfer_already_reversed")


@no_reverse_route
def test_reverse_3_reversing_unknown_transfer_is_rejected(bank):
    """Given Alice did not make a transfer, when Alice makes a reverse transfer,
    then system should prompt that no transfer has been made to be reversed."""
    bank.open("alice", dollars=30)

    assert_error(bank.reverse("0b8e2d71-63a9-4f1c-b5e4-9a2d7c6f1e30"), 404, "transfer_not_found")
