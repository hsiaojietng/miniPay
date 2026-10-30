"""SQL data access for miniPay. Every function takes an open connection so the caller controls the transaction."""

import uuid
from dataclasses import dataclass

from app.domain.ledger import Entry, StatementLine


@dataclass(frozen=True)
class AccountRow:
    id: str
    owner_name: str
    currency: str


@dataclass(frozen=True)
class TransferRow:
    id: str
    from_account_id: str
    to_account_id: str
    amount: int
    status: str
    idempotency_key: str | None


# Accounts

def insert_account(conn, owner_name, currency="SGD"):
    account_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO accounts (id, owner_name, currency) VALUES (%s, %s, %s)",
        (account_id, owner_name, currency),
    )
    return str(account_id)


def get_account(conn, account_id):
    row = conn.execute(
        "SELECT id, owner_name, currency FROM accounts WHERE id = %s",
        (account_id,),
    ).fetchone()
    return _to_account(row)


def get_account_by_owner(conn, owner_name):
    row = conn.execute(
        "SELECT id, owner_name, currency FROM accounts WHERE owner_name = %s",
        (owner_name,),
    ).fetchone()
    return _to_account(row)


def lock_accounts(conn, *account_ids):
    """Row-lock accounts until the transaction ends, so concurrent transfers on them run one at a time.

    Locks in sorted order so two transfers between the same pair of accounts cannot deadlock.
    """
    for account_id in sorted(str(a) for a in account_ids):
        conn.execute("SELECT 1 FROM accounts WHERE id = %s FOR UPDATE", (account_id,))


# Transfers

def insert_transfer(conn, from_account_id, to_account_id, amount, status, idempotency_key=None):
    transfer_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO transfers (id, from_account, to_account, amount_cents, status, idempotency_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (transfer_id, from_account_id, to_account_id, amount, status, idempotency_key),
    )
    return str(transfer_id)


def get_transfer(conn, transfer_id):
    row = conn.execute(
        """
        SELECT id, from_account, to_account, amount_cents, status, idempotency_key
        FROM transfers WHERE id = %s
        """,
        (transfer_id,),
    ).fetchone()
    return _to_transfer(row)


def get_transfer_by_idempotency_key(conn, idempotency_key):
    row = conn.execute(
        """
        SELECT id, from_account, to_account, amount_cents, status, idempotency_key
        FROM transfers WHERE idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()
    return _to_transfer(row)


def update_transfer_status(conn, transfer_id, status):
    conn.execute("UPDATE transfers SET status = %s WHERE id = %s", (status, transfer_id))


# Ledger entries

def insert_entries(conn, entries):
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO ledger_entries (transfer_id, account_id, amount_cents) VALUES (%s, %s, %s)",
            [(e.transfer_id, e.account_id, e.amount) for e in entries],
        )


def balance_of(conn, account_id):
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM ledger_entries WHERE account_id = %s",
        (account_id,),
    ).fetchone()
    return int(row[0])


def entries_for(conn, transfer_id):
    rows = conn.execute(
        "SELECT transfer_id, account_id, amount_cents FROM ledger_entries WHERE transfer_id = %s ORDER BY id",
        (transfer_id,),
    ).fetchall()
    return [_to_entry(r) for r in rows]


def all_entries(conn):
    rows = conn.execute(
        "SELECT transfer_id, account_id, amount_cents FROM ledger_entries ORDER BY id"
    ).fetchall()
    return [_to_entry(r) for r in rows]


def statement(conn, account_id):
    rows = conn.execute(
        """
        SELECT transfer_id, amount_cents,
               SUM(amount_cents) OVER (ORDER BY id) AS balance_after
        FROM ledger_entries
        WHERE account_id = %s
        ORDER BY id
        """,
        (account_id,),
    ).fetchall()
    return [StatementLine(str(r[0]), int(r[1]), int(r[2])) for r in rows]


def _to_account(row):
    if row is None:
        return None
    return AccountRow(str(row[0]), row[1], row[2])


def _to_transfer(row):
    if row is None:
        return None
    return TransferRow(str(row[0]), str(row[1]), str(row[2]), int(row[3]), row[4], row[5])


def _to_entry(row):
    return Entry(str(row[0]), str(row[1]), int(row[2]))
