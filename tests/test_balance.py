"""Cached balances (accounts.balance_cents) and the balance_not_negative safety net.

docs/migrations/002_balance.sql adds the cached balance and a CHECK constraint, so the database
itself refuses a negative balance on any account that is not allowed one (only CASH is).
"""

from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.db import repo
from app.services import transfer_service
from app.services.account_service import CASH_HOLDER, deposit, open_account

DOCS = Path(__file__).resolve().parent.parent / "docs"


def cached_vs_ledger(conn):
    """Each account's cached balance next to the sum of its ledger entries."""
    return conn.execute(
        """
        SELECT a.owner_name, a.balance_cents, COALESCE(SUM(e.amount_cents), 0)
        FROM accounts a LEFT JOIN ledger_entries e ON e.account_id = a.id
        GROUP BY a.id, a.owner_name, a.balance_cents
        ORDER BY a.owner_name
        """
    ).fetchall()


def assert_cached_balances_match_entries(conn):
    rows = cached_vs_ledger(conn)
    assert rows, "no accounts to check"
    mismatched = [(owner, cached, summed) for owner, cached, summed in rows if cached != summed]
    assert mismatched == [], f"cached balance != sum of entries (owner, cached, summed): {mismatched}"


def test_every_cached_balance_equals_the_sum_of_its_entries(conn):
    alice = open_account(conn, "alice")
    bob = open_account(conn, "bob")
    carol = open_account(conn, "carol")
    deposit(conn, alice, 10_000)
    deposit(conn, bob, 2_500)
    transfer_service.transfer(conn, alice, bob, 3_000)
    transfer_service.transfer(conn, bob, carol, 5_500)
    transfer_service.transfer(conn, alice, carol, 7_000)

    assert_cached_balances_match_entries(conn)
    balances = {owner: cached for owner, cached, _ in cached_vs_ledger(conn)}
    assert balances == {"alice": 0, "bob": 0, "carol": 12_500, CASH_HOLDER: -12_500}


def test_cash_account_is_allowed_to_go_negative(conn):
    alice = open_account(conn, "alice")
    deposit(conn, alice, 10_000)

    cash = repo.get_account_by_owner(conn, CASH_HOLDER)
    allow_negative, balance = conn.execute(
        "SELECT allow_negative, balance_cents FROM accounts WHERE id = %s", (cash.id,)
    ).fetchone()
    assert allow_negative is True
    assert balance == -10_000


def test_database_refuses_a_negative_balance_on_an_ordinary_account(conn):
    alice = open_account(conn, "alice")

    with pytest.raises(psycopg.errors.CheckViolation, match="balance_not_negative"):
        with conn.transaction():
            conn.execute("UPDATE accounts SET balance_cents = -1 WHERE id = %s", (alice,))


def test_database_stops_an_overdraft_even_when_the_funds_check_is_skipped(conn, monkeypatch):
    alice = open_account(conn, "alice")
    bob = open_account(conn, "bob")
    deposit(conn, alice, 1_000)
    entries_before = repo.all_entries(conn)

    # Simulate an application bug: the business rule that should stop this is gone.
    monkeypatch.setattr(transfer_service, "check_sufficient_funds", lambda *args: None)
    with pytest.raises(psycopg.errors.CheckViolation, match="balance_not_negative"):
        transfer_service.transfer(conn, alice, bob, 1_001)

    assert repo.all_entries(conn) == entries_before
    assert_cached_balances_match_entries(conn)


@pytest.fixture
def pre_migration_database(database):
    """A throwaway database built from docs/schema.sql alone, i.e. as it was before 002."""
    url = make_conninfo(database, dbname=conninfo_to_dict(database)["dbname"] + "_migration")
    name = conninfo_to_dict(url)["dbname"]
    admin_url = make_conninfo(database, dbname="postgres")
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{name}"')
    with psycopg.connect(url, autocommit=True) as setup:
        setup.execute((DOCS / "schema.sql").read_text())
    yield url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def test_migration_backfills_cached_balances_and_flags_cash(pre_migration_database):
    with psycopg.connect(pre_migration_database, autocommit=True) as conn:
        # Existing data written before the migration: CASH funded alice, alice paid bob.
        # Plain SQL, not repo, because repo now writes columns this old schema does not have.
        cash, alice, bob = (
            conn.execute(
                "INSERT INTO accounts (id, owner_name) VALUES (gen_random_uuid(), %s) RETURNING id",
                (owner,),
            ).fetchone()[0]
            for owner in (CASH_HOLDER, "alice", "bob")
        )
        for source, target, amount in [(cash, alice, 10_000), (alice, bob, 4_000)]:
            transfer_id = conn.execute(
                "INSERT INTO transfers (id, from_account, to_account, amount_cents, status) "
                "VALUES (gen_random_uuid(), %s, %s, %s, 'COMPLETED') RETURNING id",
                (source, target, amount),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO ledger_entries (transfer_id, account_id, amount_cents) "
                "VALUES (%s, %s, %s), (%s, %s, %s)",
                (transfer_id, source, -amount, transfer_id, target, amount),
            )

        conn.execute((DOCS / "migrations" / "002_balance.sql").read_text())

        assert_cached_balances_match_entries(conn)
        flags = dict(conn.execute("SELECT owner_name, allow_negative FROM accounts").fetchall())
        assert flags == {CASH_HOLDER: True, "alice": False, "bob": False}


def test_migration_creates_cash_when_it_does_not_exist_yet(pre_migration_database):
    with psycopg.connect(pre_migration_database, autocommit=True) as conn:
        conn.execute((DOCS / "migrations" / "002_balance.sql").read_text())

        row = conn.execute(
            "SELECT allow_negative, balance_cents FROM accounts WHERE owner_name = %s",
            (CASH_HOLDER,),
        ).fetchone()
        assert row == (True, 0)
