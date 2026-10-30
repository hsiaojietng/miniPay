import os

import psycopg

# Defaults match the db service in docker-compose.yml; override with the DATABASE_URL env var.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://minipay:minipay_dev@localhost:5432/minipay",
)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)
