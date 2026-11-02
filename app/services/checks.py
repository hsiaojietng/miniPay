"""Business rule checks shared by the miniPay services. Each raises a domain error on violation."""

import uuid

from app.db import repo
from app.domain.errors import (
    AccountNotFound,
    InsufficientFunds,
    InvalidAmount,
    SameAccountTransfer,
    UnsupportedCurrency,
)
from app.domain.ledger import CURRENCY


def normalise_account_id(account_id):
    # accounts.id is a UUID column; a malformed id cannot match any account.
    try:
        return str(uuid.UUID(str(account_id)))
    except ValueError:
        raise AccountNotFound(f"Account {account_id} does not exist") from None


def check_currency(currency):
    if currency != CURRENCY:
        raise UnsupportedCurrency(f"Only {CURRENCY} is supported, got {currency!r}")


def check_amount(amount):
    if amount <= 0:
        raise InvalidAmount(f"Amount must be greater than 0, got {amount}")


def check_account_exists(conn, account_id):
    account = repo.get_account(conn, account_id)
    if account is None:
        raise AccountNotFound(f"Account {account_id} does not exist")
    return account


def check_self_transfer(from_account_id, to_account_id):
    if from_account_id == to_account_id:
        raise SameAccountTransfer(f"Cannot transfer to the same account {to_account_id}")


def check_sufficient_funds(conn, account_id, amount):
    available = repo.balance_of(conn, account_id)
    if amount > available:
        raise InsufficientFunds(
            f"Account {account_id} has {available}, cannot transfer {amount}"
        )
