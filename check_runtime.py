from time import perf_counter

import psycopg

from db import get_connection


def main():
    with get_connection() as conn:
        settings = conn.execute("""
            SELECT
                current_user AS db_user,
                current_setting('transaction_read_only') AS read_only,
                current_setting('statement_timeout') AS statement_timeout
        """).fetchone()

        print("SETTINGS:", settings)
        assert settings["db_user"] == "mcp_readonly", settings
        assert settings["read_only"] == "on", settings

        # PostgreSQL returns this setting as a human-readable duration.
        timeout_ms = conn.execute("""
            SELECT setting::integer AS milliseconds
            FROM pg_catalog.pg_settings
            WHERE name = 'statement_timeout'
        """).fetchone()["milliseconds"]
        assert timeout_ms == 5000, timeout_ms

    print("READ-ONLY SETTINGS: PASS")

    started = perf_counter()
    try:
        with get_connection() as conn:
            conn.execute("SELECT pg_catalog.pg_sleep(10)")
    except psycopg.errors.QueryCanceled:
        elapsed = perf_counter() - started
        print(f"SERVER TIMEOUT: PASS ({elapsed:.2f}s)")
    else:
        raise AssertionError("Expected PostgreSQL to cancel pg_sleep")

    # Confirm a new connection still works after cancellation.
    with get_connection() as conn:
        result = conn.execute("SELECT 1 AS value").fetchone()
        assert result["value"] == 1

    print("CONNECTION AFTER TIMEOUT: PASS")
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
