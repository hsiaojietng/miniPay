"""Postgres fixtures shared by the integration tests."""

import psycopg
import pytest

from app.db.connection import DATABASE_URL


@pytest.fixture(scope="session")
def database():
    # Probe once per session so a missing database costs one connect timeout, not one per test.
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as probe:
            probe.execute("SELECT 1 FROM ledger_entries LIMIT 1")
    except psycopg.OperationalError as e:
        pytest.skip(f"Postgres not reachable: {e}")
    except psycopg.errors.UndefinedTable:
        pytest.skip("Schema not applied (docs/schema.sql)")
    return DATABASE_URL


@pytest.fixture
def conn(database):
    # Open the outer transaction up front: a service's conn.transaction() then becomes a savepoint.
    # Without it, a service call as the first statement would BEGIN and COMMIT for real.
    with psycopg.connect(database) as connection:
        with connection.transaction(force_rollback=True):
            yield connection
