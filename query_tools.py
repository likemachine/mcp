import logging
from datetime import date, datetime, time
from decimal import Decimal
from time import perf_counter
from uuid import UUID

import psycopg
import sqlglot
from psycopg.rows import tuple_row
from sqlglot import exp

from db import DatabaseConfigError, get_connection
from sql_validator import SQLValidationError, validate_select


logger = logging.getLogger("postgres_mcp")
MAX_RESULT_ROWS = 100


def error_result(code: str, message: str) -> dict:
    return {
        "status": "error",
        "error": {"code": code, "message": message},
    }


def json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
        return value
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return str(value)


def _read_query(sql: str, *, explain: bool = False) -> dict:
    started = perf_counter()

    try:
        normalized = validate_select(sql)
    except SQLValidationError as exc:
        return error_result(exc.code, str(exc))

    # Only real tables were qualified by validate_select().
    tree = sqlglot.parse_one(normalized, read="postgres")
    table_names = sorted({
        table.name
        for table in tree.find_all(exp.Table)
        if table.db == "public"
    })

    limited_sql = (
        "SELECT * FROM ("
        + normalized
        + ") AS mcp_result LIMIT "
        + str(MAX_RESULT_ROWS)
    )

    if explain:
        limited_sql = "EXPLAIN (FORMAT JSON, ANALYZE FALSE) " + normalized

    try:
        with get_connection() as conn:
            conn.execute("SET LOCAL search_path TO pg_catalog")
            conn.execute("SET LOCAL statement_timeout = '5s'")

            mode = conn.execute(
                "SELECT current_setting('transaction_read_only') AS mode"
            ).fetchone()

            if mode["mode"] != "on":
                return error_result(
                    "READ_ONLY_REQUIRED",
                    "A read-only transaction is required",
                )

            for table_name in table_names:
                allowed = conn.execute("""
                    SELECT c.oid
                    FROM pg_catalog.pg_class AS c
                    JOIN pg_catalog.pg_namespace AS n
                        ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relname = %s
                      AND c.relkind = 'r'
                      AND pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                      AND pg_catalog.has_table_privilege(c.oid, 'SELECT')
                """, (table_name,)).fetchone()

                if allowed is None:
                    return error_result(
                        "TABLE_NOT_ALLOWED",
                        "A referenced table does not exist or is not allowed",
                    )

            with conn.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(limited_sql)

                if explain:
                    plan_document = cursor.fetchone()[0]
                    root_plan = plan_document[0]["Plan"]
                    elapsed = round((perf_counter() - started) * 1000, 2)
                    logger.info(
                        "explain_query succeeded: duration_ms=%s",
                        elapsed,
                    )
                    return {
                        "plan": json_value(plan_document),
                        "estimated_cost": root_plan["Total Cost"],
                        "estimated_rows": root_plan["Plan Rows"],
                        "planning_request_time_ms": elapsed,
                    }

                columns = [column.name for column in cursor.description]
                rows = [
                    [json_value(value) for value in row]
                    for row in cursor.fetchall()
                ]

        elapsed = round((perf_counter() - started) * 1000, 2)
        logger.info(
            "run_select_query succeeded: rows=%s duration_ms=%s",
            len(rows),
            elapsed,
        )
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "execution_time_ms": elapsed,
        }

    except DatabaseConfigError:
        logger.error("run_select_query: invalid database configuration")
        return error_result(
            "DATABASE_CONFIG_ERROR",
            "Database configuration is incomplete or invalid",
        )

    except psycopg.errors.QueryCanceled:
        logger.warning("run_select_query: query canceled")
        return error_result(
            "QUERY_CANCELED",
            "Query was canceled, possibly because the time limit was exceeded",
        )

    except (
        psycopg.errors.AmbiguousColumn,
        psycopg.errors.UndefinedColumn,
        psycopg.errors.UndefinedFunction,
        psycopg.errors.SyntaxError,
        psycopg.errors.DatatypeMismatch,
        psycopg.errors.GroupingError,
        psycopg.errors.DivisionByZero,
        psycopg.errors.InvalidTextRepresentation,
    ) as error:
        detail = (error.diag.message_primary or 'Invalid query')[:200]
        logger.warning('run_select_query: query error: %s', detail)
        return error_result('QUERY_ERROR', detail)

    except psycopg.Error:
        logger.error("run_select_query: database query failed")
        return error_result(
            "DATABASE_ERROR",
            "Unable to execute SELECT query",
        )


def read_select_query(sql: str) -> dict:
    return _read_query(sql)


def read_explain_query(sql: str) -> dict:
    return _read_query(sql, explain=True)


def register_query_tools(mcp):
    @mcp.tool
    def run_select_query(sql: str) -> dict:
        """Run a restricted read-only SELECT and return at most 100 rows.

        Only supported SELECT syntax and public tables are allowed.
        Decimal values are returned as strings to preserve precision.
        """
        return read_select_query(sql)

    @mcp.tool
    def explain_query(sql: str) -> dict:
        """Return the estimated PostgreSQL plan for a restricted SELECT.

        Pass SELECT SQL, not an EXPLAIN command.
        ANALYZE is disabled. Cost values are not milliseconds.
        """
        return read_explain_query(sql)
