"""Concurrency tests for the transfer service: many transfers racing on the same accounts.

Unlike the other integration tests, every thread commits for real on its own connection,
because a race only shows up between separate transactions.
"""

import threading
from collections import Counter

import psycopg

from app.db import repo
from app.domain.errors import InsufficientFunds
from app.services.account_service import deposit, open_account
from app.services.transfer_service import transfer

STARTING_BALANCE = 10_000
AMOUNT = 1_000
THREADS = 50

SUCCEEDED, REJECTED = "succeeded", "rejected"


def run_concurrently(database, transfers):
    """Run each (from, to, amount) transfer on its own thread and connection, all released at once.

    Returns a Counter of ((from, to), SUCCEEDED | REJECTED), plus a list of unexpected errors
    such as a deadlock, which are bugs rather than lost races.
    """
    barrier = threading.Barrier(len(transfers))
    outcomes, unexpected = Counter(), []
    record = threading.Lock()

    def attempt(from_id, to_id, amount):
        with psycopg.connect(database, autocommit=True) as conn:
            barrier.wait()  # release all threads at once to maximise overlap
            try:
                transfer(conn, from_id, to_id, amount)
                outcome = SUCCEEDED
            except InsufficientFunds:
                outcome = REJECTED
            except Exception as e:
                with record:
                    unexpected.append(repr(e))
                return
            with record:
                outcomes[(from_id, to_id), outcome] += 1

    threads = [threading.Thread(target=attempt, args=t) for t in transfers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return outcomes, unexpected


def running_balances(conn, account_id):
    return [line.balance_after for line in repo.statement(conn, account_id)]


def assert_ledger_consistent(conn):
    # Double entry: every cent debited was credited somewhere.
    assert sum(e.amount for e in repo.all_entries(conn)) == 0
    # The cached balance never drifts from the entries.
    mismatched = conn.execute(
        """
        SELECT a.owner_name, a.balance_cents, COALESCE(SUM(e.amount_cents), 0) AS summed
        FROM accounts a LEFT JOIN ledger_entries e ON e.account_id = a.id
        GROUP BY a.id HAVING a.balance_cents <> COALESCE(SUM(e.amount_cents), 0)
        """
    ).fetchall()
    assert mismatched == []


def test_concurrent_transfers_never_overdraw_the_account(clean_database):
    with psycopg.connect(clean_database, autocommit=True) as setup:
        sender = open_account(setup, "sender")
        receiver = open_account(setup, "receiver")
        deposit(setup, sender, STARTING_BALANCE)

    outcomes, unexpected = run_concurrently(
        clean_database, [(sender, receiver, AMOUNT)] * THREADS
    )

    assert unexpected == []
    with psycopg.connect(clean_database, autocommit=True) as check:
        # 1. The balance is never negative, at any point in the sender's history.
        history = running_balances(check, sender)
        assert min(history) >= 0, f"sender went negative: {history}"
        assert repo.balance_of(check, sender) == 0

        # 2. Exactly enough transfers succeeded to drain the account, and no more.
        assert outcomes[(sender, receiver), SUCCEEDED] == STARTING_BALANCE // AMOUNT
        assert outcomes[(sender, receiver), REJECTED] == THREADS - STARTING_BALANCE // AMOUNT

        # 3. Double entry still holds.
        assert_ledger_consistent(check)


def test_opposing_transfers_neither_deadlock_nor_lose_money(clean_database):
    each_side = THREADS // 2
    with psycopg.connect(clean_database, autocommit=True) as setup:
        a = open_account(setup, "a")
        b = open_account(setup, "b")
        deposit(setup, a, STARTING_BALANCE // 2)
        deposit(setup, b, STARTING_BALANCE // 2)

    # Interleave the directions so A->B and B->A transactions start side by side.
    outcomes, unexpected = run_concurrently(
        clean_database, [(a, b, AMOUNT), (b, a, AMOUNT)] * each_side
    )

    # A deadlock surfaces here as psycopg.errors.DeadlockDetected.
    assert unexpected == []
    a_to_b = outcomes[(a, b), SUCCEEDED]
    b_to_a = outcomes[(b, a), SUCCEEDED]
    assert a_to_b + outcomes[(a, b), REJECTED] == each_side
    assert b_to_a + outcomes[(b, a), REJECTED] == each_side

    with psycopg.connect(clean_database, autocommit=True) as check:
        # Every successful transfer moved exactly AMOUNT, so the final balances follow from the counts.
        assert repo.balance_of(check, a) == STARTING_BALANCE // 2 - (a_to_b - b_to_a) * AMOUNT
        assert repo.balance_of(check, b) == STARTING_BALANCE // 2 + (a_to_b - b_to_a) * AMOUNT
        # Money only moved between A and B, so their total is unchanged.
        assert repo.balance_of(check, a) + repo.balance_of(check, b) == STARTING_BALANCE

        for account_id in (a, b):
            history = running_balances(check, account_id)
            assert min(history) >= 0, f"account went negative: {history}"

        transfer_rows = check.execute(
            "SELECT count(*) FROM transfers "
            "WHERE (from_account, to_account) IN ((%s::uuid, %s::uuid), (%s::uuid, %s::uuid))",
            (a, b, b, a),
        ).fetchone()[0]
        assert transfer_rows == a_to_b + b_to_a
        assert_ledger_consistent(check)
