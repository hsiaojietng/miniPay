"""Transfer service for miniPay: checks the business rules and writes through the repository in one transaction."""

from app.db import repo
from app.domain.ledger import CURRENCY, Entry
from app.services.checks import (
    check_account_exists,
    check_amount,
    check_currency,
    check_self_transfer,
    check_sufficient_funds,
    normalise_account_id,
)

COMPLETED = "COMPLETED"


def transfer(conn, from_account_id, to_account_id, amount, currency=CURRENCY, idempotency_key=None):
    """Move amount cents from one account to another and return the transfer id.

    A rule violation raises before anything is written, and any error rolls the whole
    transaction back, so a transfer row never exists without both of its entries.
    """
    check_currency(currency)
    check_amount(amount)
    from_account_id = normalise_account_id(from_account_id)
    to_account_id = normalise_account_id(to_account_id)

    with conn.transaction():
        # Lock first so concurrent transfers touching these accounts run one at a time.
        # That also serialises retries of the same request, so the idempotency check below
        # sees a transfer that a concurrent retry has just committed.
        repo.lock_accounts(conn, from_account_id, to_account_id)

        if idempotency_key is not None:
            existing = repo.get_transfer_by_idempotency_key(conn, idempotency_key)
            if existing is not None:
                return existing.id

        check_account_exists(conn, from_account_id)
        check_account_exists(conn, to_account_id)
        check_self_transfer(from_account_id, to_account_id)
        check_sufficient_funds(conn, from_account_id, amount)

        transfer_id = repo.insert_transfer(
            conn, from_account_id, to_account_id, amount, COMPLETED, idempotency_key
        )
        repo.insert_entries(conn, [
            Entry(transfer_id, from_account_id, -amount),
            Entry(transfer_id, to_account_id, amount),
        ])
        return transfer_id
