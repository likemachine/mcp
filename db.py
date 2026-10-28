from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row


BASE_DIR = Path(__file__).resolve().parent


class DatabaseConfigError(ValueError):
    """Database configuration is missing or invalid."""


@contextmanager
def get_connection():
    config = dotenv_values(BASE_DIR / ".env")

    required = (
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
    )

    missing = [key for key in required if not config.get(key)]
    if missing:
        raise DatabaseConfigError(
            "Missing database settings: " + ", ".join(missing)
        )

    try:
        port = int(config["PGPORT"])
    except (TypeError, ValueError) as exc:
        raise DatabaseConfigError("PGPORT must be an integer") from exc

    if not 1 <= port <= 65535:
        raise DatabaseConfigError("PGPORT is outside the valid range")

    with psycopg.connect(
        host=config["PGHOST"],
        port=port,
        dbname=config["PGDATABASE"],
        user=config["PGUSER"],
        password=config["PGPASSWORD"],
        connect_timeout=5,
        options="-c statement_timeout=5000",
        row_factory=dict_row,
    ) as conn:
        conn.read_only = True
        yield conn
