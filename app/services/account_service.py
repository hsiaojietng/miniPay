"""Account service for miniPay: opening accounts, deposits, balances and statements."""

import psycopg

from app.db import repo
from app.domain.errors import AccessDenied, AccountAlreadyExists
from app.domain.ledger import CURRENCY, Entry
from app.services.checks import (
    check_account_exists,
    check_amount,
    check_currency,
    check_self_transfer,
    normalise_account_id,
)
from app.services.transfer_service import COMPLETED

# Deposits are transfers from this account, so its balance goes negative as money enters the system.
CASH_HOLDER = "CASH"


def open_account(conn, holder):
    """Open an account for holder with a zero balance and return its id."""
    if holder == CASH_HOLDER:
        raise AccountAlreadyExists(f"{holder} is reserved for the system")
    try:
        with conn.transaction():
            return repo.insert_account(conn, holder)
    except psycopg.errors.UniqueViolation:
        # accounts.owner_name is UNIQUE, which also covers two concurrent requests for one holder.
        raise AccountAlreadyExists(f"{holder} already has an account") from None


def deposit(conn, account_id, amount, currency=CURRENCY):
    """Move amount cents from the cash account into account_id and return the transfer id."""
    check_currency(currency)
    check_amount(amount)
    account_id = normalise_account_id(account_id)

    with conn.transaction():
        check_account_exists(conn, account_id)
        cash_id = repo.get_or_insert_account(conn, CASH_HOLDER).id
        check_self_transfer(cash_id, account_id)

        transfer_id = repo.insert_transfer(conn, cash_id, account_id, amount, COMPLETED)
        repo.insert_entries(conn, [
            Entry(transfer_id, cash_id, -amount),
            Entry(transfer_id, account_id, amount),
        ])
        return transfer_id


def balance(conn, account_id, requested_by):
    account = _check_holder(conn, account_id, requested_by)
    return repo.balance_of(conn, account.id)


def statement(conn, account_id, requested_by):
    account = _check_holder(conn, account_id, requested_by)
    return repo.statement(conn, account.id)


def _check_holder(conn, account_id, requested_by):
    account = check_account_exists(conn, normalise_account_id(account_id))
    if account.owner_name != requested_by:
        raise AccessDenied(f"{requested_by} cannot view account {account.id}")
    return account
