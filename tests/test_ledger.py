"""Business rule tests for the miniPay ledger (docs/specs.md, "Business Rules").

All amounts are integer cents in SGD. Deposits are funded from the special CASH
account, so the sum of every entry in the ledger is always 0.
"""

import pytest

from app.domain.errors import (
    AccessDenied,
    AccountAlreadyExists,
    AccountNotFound,
    InsufficientFunds,
    InvalidAmount,
    SameAccountTransfer,
    TransferAlreadyReversed,
    TransferNotFound,
    UnsupportedCurrency,
)
from app.domain.ledger import Ledger


@pytest.fixture
def ledger():
    return Ledger()


@pytest.fixture
def alice(ledger):
    account_id = ledger.open_account("alice")
    ledger.deposit(account_id, 10000)
    return account_id


@pytest.fixture
def bob(ledger):
    return ledger.open_account("bob")


def balance_of(ledger, account_id, holder):
    return ledger.balance(account_id, requested_by=holder)


def cash_balance(ledger):
    return sum(
        e.amount for e in ledger.all_entries() if e.account_id == ledger.cash_account_id
    )


# Rule 1: Transfer/deposit amount must be greater than 0

@pytest.mark.parametrize("amount", [0, -1, -10000])
def test_deposit_rejects_non_positive_amount(ledger, alice, amount):
    with pytest.raises(InvalidAmount):
        ledger.deposit(alice, amount)

    assert balance_of(ledger, alice, "alice") == 10000


@pytest.mark.parametrize("amount", [0, -1, -10000])
def test_transfer_rejects_non_positive_amount(ledger, alice, bob, amount):
    with pytest.raises(InvalidAmount):
        ledger.transfer(alice, bob, amount)

    assert balance_of(ledger, alice, "alice") == 10000
    assert balance_of(ledger, bob, "bob") == 0


def test_smallest_positive_amount_is_accepted(ledger, alice, bob):
    ledger.deposit(bob, 1)
    ledger.transfer(alice, bob, 1)

    assert balance_of(ledger, alice, "alice") == 9999
    assert balance_of(ledger, bob, "bob") == 2


# Rule 2: Sender must have enough amount to perform transfer

def test_transfer_exceeding_balance_by_one_cent_is_rejected(ledger, alice, bob):
    with pytest.raises(InsufficientFunds):
        ledger.transfer(alice, bob, 10001)

    assert balance_of(ledger, alice, "alice") == 10000
    assert balance_of(ledger, bob, "bob") == 0


def test_transfer_of_exact_balance_is_allowed(ledger, alice, bob):
    ledger.transfer(alice, bob, 10000)

    assert balance_of(ledger, alice, "alice") == 0
    assert balance_of(ledger, bob, "bob") == 10000


def test_rejected_transfer_writes_no_entries(ledger, alice, bob):
    entries_before = list(ledger.all_entries())

    with pytest.raises(InsufficientFunds):
        ledger.transfer(alice, bob, 20000)

    assert list(ledger.all_entries()) == entries_before


# Rule 3: Sender and receiver must be different accounts

def test_transfer_to_self_is_rejected(ledger, alice):
    with pytest.raises(SameAccountTransfer):
        ledger.transfer(alice, alice, 2000)

    assert balance_of(ledger, alice, "alice") == 10000


# Rule 4: Both sender and receiver accounts must exist

def test_transfer_from_unknown_account_is_rejected(ledger, bob):
    with pytest.raises(AccountNotFound):
        ledger.transfer("does-not-exist", bob, 1000)

    assert balance_of(ledger, bob, "bob") == 0


def test_transfer_to_unknown_account_is_rejected(ledger, alice):
    with pytest.raises(AccountNotFound):
        ledger.transfer(alice, "does-not-exist", 1000)

    assert balance_of(ledger, alice, "alice") == 10000


def test_deposit_to_unknown_account_is_rejected(ledger):
    with pytest.raises(AccountNotFound):
        ledger.deposit("does-not-exist", 1000)


# Rule 5: Only one currency (SGD)

def test_transfer_in_sgd_is_accepted(ledger, alice, bob):
    ledger.transfer(alice, bob, 1000, currency="SGD")

    assert balance_of(ledger, bob, "bob") == 1000


@pytest.mark.parametrize("currency", ["USD", "MYR", "sgd", ""])
def test_transfer_in_other_currency_is_rejected(ledger, alice, bob, currency):
    with pytest.raises(UnsupportedCurrency):
        ledger.transfer(alice, bob, 1000, currency=currency)

    assert balance_of(ledger, alice, "alice") == 10000
    assert balance_of(ledger, bob, "bob") == 0


@pytest.mark.parametrize("currency", ["USD", "MYR", "sgd", ""])
def test_deposit_in_other_currency_is_rejected(ledger, alice, currency):
    with pytest.raises(UnsupportedCurrency):
        ledger.deposit(alice, 1000, currency=currency)

    assert balance_of(ledger, alice, "alice") == 10000


# Rule 6: Only one account per unique sender/receiver

def test_new_account_starts_at_zero(ledger):
    account_id = ledger.open_account("carol")

    assert balance_of(ledger, account_id, "carol") == 0


def test_holder_cannot_open_second_account(ledger, alice):
    with pytest.raises(AccountAlreadyExists):
        ledger.open_account("alice")


def test_different_holders_get_different_accounts(ledger, alice, bob):
    assert alice != bob


# Rule 7: Transfer/deposit amount must only apply to one destination account
# Rule 8: Transfer/deposit amount must only come from one source account

def test_transfer_writes_one_debit_and_one_credit(ledger, alice, bob):
    transfer_id = ledger.transfer(alice, bob, 3000)

    entries = ledger.entries_for(transfer_id)

    assert sorted((e.account_id, e.amount) for e in entries) == sorted(
        [(alice, -3000), (bob, 3000)]
    )


def test_deposit_writes_one_debit_from_cash_and_one_credit(ledger, bob):
    transfer_id = ledger.deposit(bob, 3000)

    entries = ledger.entries_for(transfer_id)

    assert sorted((e.account_id, e.amount) for e in entries) == sorted(
        [(ledger.cash_account_id, -3000), (bob, 3000)]
    )


def test_all_entries_sum_to_zero(ledger, alice, bob):
    ledger.deposit(bob, 2500)
    ledger.transfer(alice, bob, 3000)
    ledger.transfer(bob, alice, 500)

    assert sum(e.amount for e in ledger.all_entries()) == 0


# Rule 9: Account holder can only view account balance/statement of their own account

def test_holder_can_view_own_balance(ledger, alice):
    assert ledger.balance(alice, requested_by="alice") == 10000


def test_holder_cannot_view_other_balance(ledger, alice, bob):
    with pytest.raises(AccessDenied):
        ledger.balance(alice, requested_by="bob")


def test_holder_can_view_own_statement(ledger, alice, bob):
    ledger.transfer(alice, bob, 2000)

    statement = ledger.statement(alice, requested_by="alice")

    assert [line.amount for line in statement] == [10000, -2000]


def test_holder_cannot_view_other_statement(ledger, alice, bob):
    with pytest.raises(AccessDenied):
        ledger.statement(alice, requested_by="bob")


# Rule 10: Reverse amount transfer can only occur once

def test_transfer_can_be_reversed(ledger, alice, bob):
    transfer_id = ledger.transfer(alice, bob, 3000)

    ledger.reverse(transfer_id)

    assert balance_of(ledger, alice, "alice") == 10000
    assert balance_of(ledger, bob, "bob") == 0


def test_transfer_cannot_be_reversed_twice(ledger, alice, bob):
    transfer_id = ledger.transfer(alice, bob, 3000)
    ledger.reverse(transfer_id)

    with pytest.raises(TransferAlreadyReversed):
        ledger.reverse(transfer_id)

    assert balance_of(ledger, alice, "alice") == 10000
    assert balance_of(ledger, bob, "bob") == 0


def test_reversing_unknown_transfer_is_rejected(ledger, alice, bob):
    with pytest.raises(TransferNotFound):
        ledger.reverse("does-not-exist")


def test_reversal_keeps_original_entries(ledger, alice, bob):
    transfer_id = ledger.transfer(alice, bob, 3000)
    original_entries = list(ledger.entries_for(transfer_id))

    ledger.reverse(transfer_id)

    assert list(ledger.entries_for(transfer_id)) == original_entries
    assert sum(e.amount for e in ledger.all_entries()) == 0


# Rule 11: Reverse amount transfer can only be of the full amount, not partial

def test_reversal_mirrors_full_original_amount(ledger, alice, bob):
    transfer_id = ledger.transfer(alice, bob, 3000)

    reversal_id = ledger.reverse(transfer_id)

    assert sorted((e.account_id, e.amount) for e in ledger.entries_for(reversal_id)) == sorted(
        [(alice, 3000), (bob, -3000)]
    )


def test_partial_reversal_is_not_possible(ledger, alice, bob):
    transfer_id = ledger.transfer(alice, bob, 3000)

    with pytest.raises(TypeError):
        ledger.reverse(transfer_id, amount=1000)

    assert balance_of(ledger, alice, "alice") == 7000
    assert balance_of(ledger, bob, "bob") == 3000


# Function: open_account

def test_open_account_returns_account_id(ledger):
    account_id = ledger.open_account("carol")

    assert isinstance(account_id, str)
    assert account_id


def test_open_account_gives_every_holder_a_unique_id(ledger):
    account_ids = {ledger.open_account(holder) for holder in ["carol", "dave", "erin"]}

    assert len(account_ids) == 3


def test_new_account_has_empty_statement(ledger):
    account_id = ledger.open_account("carol")

    assert list(ledger.statement(account_id, requested_by="carol")) == []


def test_failed_duplicate_open_leaves_existing_account_untouched(ledger, alice):
    with pytest.raises(AccountAlreadyExists):
        ledger.open_account("alice")

    assert balance_of(ledger, alice, "alice") == 10000


# Function: deposit

def test_deposit_adds_to_balance_and_takes_from_cash(ledger):
    account_id = ledger.open_account("carol")
    ledger.deposit(account_id, 1000)
    cash_before = cash_balance(ledger)

    ledger.deposit(account_id, 3000)

    assert balance_of(ledger, account_id, "carol") == 4000
    assert cash_balance(ledger) == cash_before - 3000


def test_deposits_accumulate(ledger, bob):
    ledger.deposit(bob, 1000)
    ledger.deposit(bob, 250)
    ledger.deposit(bob, 1)

    assert balance_of(ledger, bob, "bob") == 1251


def test_deposit_returns_unique_transfer_id(ledger, bob):
    first = ledger.deposit(bob, 1000)
    second = ledger.deposit(bob, 1000)

    assert first != second


def test_deposit_does_not_affect_other_accounts(ledger, alice, bob):
    ledger.deposit(bob, 3000)

    assert balance_of(ledger, alice, "alice") == 10000


def test_deposit_defaults_to_sgd(ledger, bob):
    ledger.deposit(bob, 1000)

    assert balance_of(ledger, bob, "bob") == 1000


def test_deposit_shows_on_statement(ledger, bob):
    ledger.deposit(bob, 3000)

    assert [line.amount for line in ledger.statement(bob, requested_by="bob")] == [3000]


# Function: balance

def test_balance_shows_current_amount(ledger):
    account_id = ledger.open_account("carol")
    ledger.deposit(account_id, 3000)

    assert ledger.balance(account_id, requested_by="carol") == 3000


def test_balance_is_integer_cents(ledger, alice):
    assert isinstance(ledger.balance(alice, requested_by="alice"), int)


def test_balance_reflects_money_in_and_out(ledger, alice, bob):
    ledger.transfer(alice, bob, 2000)
    ledger.transfer(bob, alice, 500)

    assert balance_of(ledger, alice, "alice") == 8500
    assert balance_of(ledger, bob, "bob") == 1500


def test_balance_of_unknown_account_is_rejected(ledger):
    with pytest.raises(AccountNotFound):
        ledger.balance("does-not-exist", requested_by="alice")


def test_viewing_balance_does_not_change_it(ledger, alice):
    balance_of(ledger, alice, "alice")
    balance_of(ledger, alice, "alice")

    assert balance_of(ledger, alice, "alice") == 10000
    assert sum(e.amount for e in ledger.all_entries()) == 0
