import logging
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from fastmcp import FastMCP
from psycopg.rows import dict_row

BASE_DIR = Path(__file__).resolve().parent
config = dotenv_values(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("postgres_mcp")

mcp = FastMCP("PostgreSQL MCP Server")


def read_db_health() -> dict:
    required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
    if any(config.get(key) is None for key in required):
        return {"status": "error", "error": "Database configuration is incomplete"}

    try:
        with psycopg.connect(
            host=config["PGHOST"],
            port=int(config["PGPORT"]),
            dbname=config["PGDATABASE"],
            user=config["PGUSER"],
            password=config["PGPASSWORD"],
            connect_timeout=5,
            options="-c statement_timeout=5000",
            row_factory=dict_row,
        ) as conn:
            conn.read_only = True
            row = conn.execute("""
                SELECT
                    current_database() AS database,
                    current_user AS db_user,
                    current_setting('server_version') AS postgres_version,
                    (
                        SELECT count(*)
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                    ) AS active_connections,
                    current_timestamp AS server_time,
                    current_setting('transaction_read_only') AS read_only
            """).fetchone()

        row["server_time"] = row["server_time"].isoformat()
        row["read_only"] = row["read_only"] == "on"
        row["status"] = "ok"
        logger.info("get_db_health succeeded")
        return row

    except (psycopg.Error, ValueError):
        logger.error("get_db_health failed")
        return {
            "status": "error",
            "error": "Database connection or health query failed",
        }


@mcp.tool
def get_db_health() -> dict:
    """Return PostgreSQL connectivity, version and transaction read-only status."""
    return read_db_health()


if __name__ == "__main__":
    mcp.run()
