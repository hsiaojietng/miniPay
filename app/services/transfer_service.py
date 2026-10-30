"""Transfer service for miniPay: checks the business rules and writes through the repository in one transaction."""

import uuid

from app.db import repo
from app.domain.errors import (
    AccountNotFound,
    InsufficientFunds,
    InvalidAmount,
    SameAccountTransfer,
    UnsupportedCurrency,
)
from app.domain.ledger import CURRENCY, Entry

COMPLETED = "COMPLETED"


def transfer(conn, from_account_id, to_account_id, amount, currency=CURRENCY, idempotency_key=None):
    """Move amount cents from one account to another and return the transfer id.

    A rule violation raises before anything is written, and any error rolls the whole
    transaction back, so a transfer row never exists without both of its entries.
    """
    _check_currency(currency)
    _check_amount(amount)
    from_account_id = _normalise_account_id(from_account_id)
    to_account_id = _normalise_account_id(to_account_id)

    with conn.transaction():
        # Lock first so concurrent transfers touching these accounts run one at a time.
        # That also serialises retries of the same request, so the idempotency check below
        # sees a transfer that a concurrent retry has just committed.
        repo.lock_accounts(conn, from_account_id, to_account_id)

        if idempotency_key is not None:
            existing = repo.get_transfer_by_idempotency_key(conn, idempotency_key)
            if existing is not None:
                return existing.id

        _check_account_exists(conn, from_account_id)
        _check_account_exists(conn, to_account_id)
        _check_self_transfer(from_account_id, to_account_id)
        _check_sufficient_funds(conn, from_account_id, amount)

        transfer_id = repo.insert_transfer(
            conn, from_account_id, to_account_id, amount, COMPLETED, idempotency_key
        )
        repo.insert_entries(conn, [
            Entry(transfer_id, from_account_id, -amount),
            Entry(transfer_id, to_account_id, amount),
        ])
        return transfer_id


def _normalise_account_id(account_id):
    # accounts.id is a UUID column; a malformed id cannot match any account.
    try:
        return str(uuid.UUID(str(account_id)))
    except ValueError:
        raise AccountNotFound(f"Account {account_id} does not exist") from None


def _check_currency(currency):
    if currency != CURRENCY:
        raise UnsupportedCurrency(f"Only {CURRENCY} is supported, got {currency!r}")


def _check_amount(amount):
    if amount <= 0:
        raise InvalidAmount(f"Amount must be greater than 0, got {amount}")


def _check_account_exists(conn, account_id):
    if repo.get_account(conn, account_id) is None:
        raise AccountNotFound(f"Account {account_id} does not exist")


def _check_self_transfer(from_account_id, to_account_id):
    if from_account_id == to_account_id:
        raise SameAccountTransfer(f"Cannot transfer to the same account {to_account_id}")


def _check_sufficient_funds(conn, account_id, amount):
    available = repo.balance_of(conn, account_id)
    if amount > available:
        raise InsufficientFunds(
            f"Account {account_id} has {available}, cannot transfer {amount}"
        )
