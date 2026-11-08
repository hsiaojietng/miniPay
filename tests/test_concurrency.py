"""Concurrency test for the transfer service: many transfers racing to drain one account.

Unlike the other integration tests, every thread commits for real on its own connection,
because a race only shows up between separate transactions.
"""

import threading

import psycopg
import pytest

from app.db import repo
from app.domain.errors import InsufficientFunds
from app.services.account_service import deposit, open_account
from app.services.transfer_service import transfer

STARTING_BALANCE = 10_000
AMOUNT = 1_000
THREADS = 50


def test_concurrent_transfers_never_overdraw_the_account(clean_database):
    with psycopg.connect(clean_database, autocommit=True) as setup:
        sender = open_account(setup, "sender")
        receiver = open_account(setup, "receiver")
        deposit(setup, sender, STARTING_BALANCE)

    barrier = threading.Barrier(THREADS)
    succeeded, rejected, unexpected = [], [], []
    record = threading.Lock()

    def attempt():
        with psycopg.connect(clean_database, autocommit=True) as conn:
            barrier.wait()  # release all threads at once to maximise overlap
            try:
                result, bucket = transfer(conn, sender, receiver, AMOUNT), succeeded
            except InsufficientFunds as e:
                result, bucket = e, rejected
            except Exception as e:  # anything else is a bug, not a lost race
                result, bucket = repr(e), unexpected
            with record:
                bucket.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert unexpected == []

    with psycopg.connect(clean_database, autocommit=True) as check:
        # 1. The balance is never negative, at any point in the sender's history.
        running_balances = [line.balance_after for line in repo.statement(check, sender)]
        assert min(running_balances) >= 0, f"sender went negative: {running_balances}"
        assert repo.balance_of(check, sender) == 0

        # 2. Exactly enough transfers succeeded to drain the account, and no more.
        assert len(succeeded) == STARTING_BALANCE // AMOUNT
        assert len(rejected) == THREADS - STARTING_BALANCE // AMOUNT

        # 3. Double entry still holds: every cent debited was credited somewhere.
        assert sum(e.amount for e in repo.all_entries(check)) == 0
