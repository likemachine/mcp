from datetime import datetime, timezone
from unittest.mock import MagicMock

import psycopg
import pytest

import schema_tools
from db import DatabaseConfigError


@pytest.fixture
def mocked_db(monkeypatch):
    connection = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = connection

    factory = MagicMock(return_value=context)
    monkeypatch.setattr(schema_tools, "get_connection", factory)

    return connection, factory


def prepare_stats(
    connection,
    stats,
    indexes=None,
):
    stats_result = MagicMock()
    stats_result.fetchone.return_value = stats

    index_result = MagicMock()
    index_result.fetchall.return_value = indexes or []

    connection.execute.side_effect = [stats_result, index_result]


def test_returns_table_statistics(mocked_db):
    connection, _ = mocked_db
    analyzed_at = datetime(2026, 10, 28, 11, 24, 19, tzinfo=timezone.utc)
    prepare_stats(
        connection,
        {
            "oid": 123,
            "table": "orders",
            "estimated_rows": 200,
            "size": "96 kB",
            "last_analyze": analyzed_at,
            "last_autoanalyze": None,
        },
        indexes=[{"name": "orders_pkey"}, {"name": "idx_orders_client_id"}],
    )

    result = schema_tools.read_table_stats("orders")

    assert result == {
        "table": "orders",
        "estimated_rows": 200,
        "size": "96 kB",
        "last_analyze": "2026-10-28T11:24:19+00:00",
        "last_autoanalyze": None,
        "schema": "public",
        "indexes": ["orders_pkey", "idx_orders_client_id"],
    }


def test_sql_converts_negative_row_estimate_to_null(mocked_db):
    connection, _ = mocked_db
    prepare_stats(
        connection,
        {
            "oid": 123,
            "table": "empty",
            "estimated_rows": 0,
            "size": "8192 bytes",
            "last_analyze": None,
            "last_autoanalyze": None,
        },
    )

    result = schema_tools.read_table_stats("empty")

    sql, params = connection.execute.call_args_list[0].args
    assert "CASE" in sql
    assert "WHEN c.reltuples < 0 THEN NULL" in sql
    assert result["estimated_rows"] == 0
    assert result["last_analyze"] is None
    assert result["last_autoanalyze"] is None
    assert result["indexes"] == []


def test_missing_table_stops_index_query(mocked_db):
    connection, _ = mocked_db
    connection.execute.return_value.fetchone.return_value = None

    result = schema_tools.read_table_stats("missing")

    assert result["error"]["code"] == "TABLE_NOT_FOUND"
    connection.execute.assert_called_once()


@pytest.mark.parametrize("table", ["", "   ", None, 123])
def test_rejects_invalid_table_name(mocked_db, table):
    _, factory = mocked_db

    result = schema_tools.read_table_stats(table)

    assert result["error"]["code"] == "INVALID_TABLE_NAME"
    factory.assert_not_called()


@pytest.mark.parametrize("schema", ["pg_catalog", "private"])
def test_rejects_forbidden_schema(mocked_db, schema):
    _, factory = mocked_db

    result = schema_tools.read_table_stats("orders", schema)

    assert result["error"]["code"] == "SCHEMA_NOT_ALLOWED"
    factory.assert_not_called()


def test_table_name_is_passed_as_parameter(mocked_db):
    connection, _ = mocked_db
    connection.execute.return_value.fetchone.return_value = None
    table = "orders'; DROP TABLE clients; --"

    result = schema_tools.read_table_stats(table)

    sql, params = connection.execute.call_args.args
    assert params == ("public", table)
    assert table not in sql
    assert result["error"]["code"] == "TABLE_NOT_FOUND"


def test_index_query_uses_resolved_oid(mocked_db):
    connection, _ = mocked_db
    prepare_stats(
        connection,
        {
            "oid": 456,
            "table": "orders",
            "estimated_rows": 0,
            "size": "0 bytes",
            "last_analyze": None,
            "last_autoanalyze": None,
        },
    )

    schema_tools.read_table_stats("orders")

    calls = connection.execute.call_args_list
    assert len(calls) == 2
    assert calls[0].args[1] == ("public", "orders")
    assert calls[1].args[1] == (456,)


def test_handles_configuration_error(mocked_db):
    _, factory = mocked_db
    factory.side_effect = DatabaseConfigError("private config detail")

    result = schema_tools.read_table_stats("orders")

    assert result["error"]["code"] == "DATABASE_CONFIG_ERROR"
    assert "private config detail" not in str(result)


def test_handles_connection_error(mocked_db):
    _, factory = mocked_db
    factory.side_effect = psycopg.OperationalError("private connection detail")

    result = schema_tools.read_table_stats("orders")

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private connection detail" not in str(result)


def test_handles_query_error(mocked_db):
    connection, _ = mocked_db
    connection.execute.side_effect = psycopg.ProgrammingError(
        "private query detail"
    )

    result = schema_tools.read_table_stats("orders")

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private query detail" not in str(result)
