import logging

import psycopg
from fastmcp import FastMCP

from db import DatabaseConfigError, get_connection


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("postgres_mcp")

mcp = FastMCP("PostgreSQL MCP Server")


def read_db_health() -> dict:
    try:
        with get_connection() as conn:
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

    except DatabaseConfigError:
        logger.error("Database configuration is invalid")
        return {
            "status": "error",
            "error": "Database configuration is incomplete or invalid",
        }

    except psycopg.Error:
        logger.error("get_db_health failed")
        return {
            "status": "error",
            "error": "Database connection or health query failed",
        }


@mcp.tool
def get_db_health() -> dict:
    """Return PostgreSQL connectivity, version and transaction read-only status."""
    return read_db_health()


from schema_tools import register_schema_tools

register_schema_tools(mcp)


if __name__ == "__main__":
    mcp.run()
