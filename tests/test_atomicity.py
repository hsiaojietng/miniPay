"""Atomicity test for the transfer service: a crash halfway through a transfer leaves nothing behind.

The connection commits for real (autocommit), so the only thing that can undo a partial write
is the transfer's own transaction, not the rolled-back outer transaction the other tests use.
"""

import psycopg
import pytest

from app.db import repo
from app.services import transfer_service
from app.services.account_service import deposit, open_account


class CrashBetweenEntries(Exception):
    pass


def crash_after_debit(conn, entries):
    """Test hook for repo.insert_entries: write the debit entry, then fail before the credit."""
    debit, _credit = entries
    assert debit.amount < 0
    conn.execute(
        "INSERT INTO ledger_entries (transfer_id, account_id, amount_cents) VALUES (%s, %s, %s)",
        (debit.transfer_id, debit.account_id, debit.amount),
    )
    raise CrashBetweenEntries("simulated crash between the debit and the credit entry")


def test_transfer_that_fails_between_entries_leaves_no_trace(clean_database, monkeypatch):
    with psycopg.connect(clean_database, autocommit=True) as conn:
        sender = open_account(conn, "sender")
        receiver = open_account(conn, "receiver")
        deposit(conn, sender, 10_000)
        transfers_before = conn.execute("SELECT count(*) FROM transfers").fetchone()[0]
        entries_before = repo.all_entries(conn)

        monkeypatch.setattr(repo, "insert_entries", crash_after_debit)
        with pytest.raises(CrashBetweenEntries):
            transfer_service.transfer(conn, sender, receiver, 1_000)
        monkeypatch.undo()

    # A fresh connection sees only what was actually committed.
    with psycopg.connect(clean_database, autocommit=True) as check:
        transfers = check.execute(
            "SELECT id FROM transfers WHERE from_account = %s AND to_account = %s",
            (sender, receiver),
        ).fetchall()
        assert transfers == [], "the transfer row survived the crash"
        assert check.execute("SELECT count(*) FROM transfers").fetchone()[0] == transfers_before
        assert repo.all_entries(check) == entries_before, "a ledger entry survived the crash"
        assert repo.balance_of(check, sender) == 10_000
        assert repo.balance_of(check, receiver) == 0
