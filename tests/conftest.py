"""Postgres fixtures shared by the integration tests.

Tests never touch the dev database: they run against minipay_test, which is rebuilt from
docs/schema.sql once per session and emptied before every test that uses it.
"""

import os
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://minipay:minipay_dev@localhost:5432/minipay_test",
)
# Set before anything imports app.db.connection, so the app itself (get_conn included) uses the test database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

SCHEMA = Path(__file__).resolve().parent.parent / "docs" / "schema.sql"
TABLES = "ledger_entries, transfers, accounts"


@pytest.fixture(scope="session")
def database():
    """Drop and recreate the test database from docs/schema.sql, so it always matches the schema file."""
    name = conninfo_to_dict(TEST_DATABASE_URL)["dbname"]
    if not name.endswith("_test"):
        pytest.exit(f"Refusing to recreate {name!r}: the test database name must end in _test")

    try:
        with psycopg.connect(make_conninfo(TEST_DATABASE_URL, dbname="postgres"), autocommit=True, connect_timeout=3) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            admin.execute(f'CREATE DATABASE "{name}"')
    except psycopg.OperationalError as e:
        pytest.skip(f"Postgres not reachable: {e}")

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as setup:
        setup.execute(SCHEMA.read_text())
    return TEST_DATABASE_URL


@pytest.fixture
def clean_database(database):
    # Empty before (not after) each test, so a failed test's rows stay around to inspect.
    with psycopg.connect(database, autocommit=True) as cleaner:
        cleaner.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    return database


@pytest.fixture
def conn(clean_database):
    # Open the outer transaction up front: a service's conn.transaction() then becomes a savepoint.
    # Without it, a service call as the first statement would BEGIN and COMMIT for real.
    with psycopg.connect(clean_database) as connection:
        with connection.transaction(force_rollback=True):
            yield connection


@pytest.fixture
def client(clean_database):
    """The real app, committing for real, against the emptied test database."""
    return TestClient(app)
