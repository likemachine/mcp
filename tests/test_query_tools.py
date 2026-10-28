from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import psycopg
import pytest

import query_tools
from db import DatabaseConfigError


@pytest.fixture
def mocked_db(monkeypatch):
    connection = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = connection
    factory = MagicMock(return_value=context)
    monkeypatch.setattr(query_tools, "get_connection", factory)

    connection.execute.return_value.fetchone.return_value = {
        "mode": "on",
        "oid": 123,
    }

    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.description = [SimpleNamespace(name="id")]
    cursor.fetchall.return_value = [(1,), (2,)]

    return connection, cursor, factory


def test_returns_rows_and_columns(mocked_db):
    _, _, _ = mocked_db

    result = query_tools.read_select_query("SELECT id FROM clients")

    assert result["columns"] == ["id"]
    assert result["rows"] == [[1], [2]]
    assert result["row_count"] == 2
    assert result["execution_time_ms"] >= 0


def test_wraps_query_with_limit(mocked_db):
    _, cursor, _ = mocked_db

    query_tools.read_select_query(
        "SELECT id FROM clients ORDER BY id LIMIT 3"
    )

    sql = cursor.execute.call_args.args[0]
    assert sql.startswith("SELECT * FROM (")
    assert "public.clients" in sql
    assert "ORDER BY id LIMIT 3" in sql
    assert sql.endswith(") AS mcp_result LIMIT 100")


def test_sets_transaction_options(mocked_db):
    connection, _, _ = mocked_db

    query_tools.read_select_query("SELECT 1")

    statements = [
        call.args[0] for call in connection.execute.call_args_list
    ]
    assert "SET LOCAL search_path TO pg_catalog" in statements
    assert "SET LOCAL statement_timeout = '5s'" in statements


def test_checks_table_using_parameter(mocked_db):
    connection, _, _ = mocked_db

    query_tools.read_select_query("SELECT id FROM clients")

    table_calls = [
        call for call in connection.execute.call_args_list
        if len(call.args) == 2
    ]
    assert len(table_calls) == 1
    assert table_calls[0].args[1] == ("clients",)


def test_rejects_writable_transaction(mocked_db):
    connection, cursor, _ = mocked_db
    connection.execute.return_value.fetchone.return_value = {"mode": "off"}

    result = query_tools.read_select_query("SELECT 1")

    assert result["error"]["code"] == "READ_ONLY_REQUIRED"
    cursor.execute.assert_not_called()


def test_rejects_unavailable_table(mocked_db):
    connection, cursor, _ = mocked_db
    connection.execute.return_value.fetchone.side_effect = [
        {"mode": "on"},
        None,
    ]

    result = query_tools.read_select_query("SELECT id FROM missing")

    assert result["error"]["code"] == "TABLE_NOT_ALLOWED"
    cursor.execute.assert_not_called()


@pytest.mark.parametrize("sql", [
    "DELETE FROM clients",
    "SELECT pg_sleep(1)",
    "SELECT 1; SELECT 2",
    "",
])
def test_invalid_sql_does_not_connect(mocked_db, sql):
    _, _, factory = mocked_db

    result = query_tools.read_select_query(sql)

    assert result["status"] == "error"
    factory.assert_not_called()


def test_preserves_duplicate_column_names(mocked_db):
    _, cursor, _ = mocked_db
    cursor.description = [
        SimpleNamespace(name="value"),
        SimpleNamespace(name="value"),
    ]
    cursor.fetchall.return_value = [(1, 2)]

    result = query_tools.read_select_query("SELECT 1 AS value, 2 AS value")

    assert result["columns"] == ["value", "value"]
    assert result["rows"] == [[1, 2]]


def test_empty_result(mocked_db):
    _, cursor, _ = mocked_db
    cursor.fetchall.return_value = []

    result = query_tools.read_select_query("SELECT id FROM clients")

    assert result["columns"] == ["id"]
    assert result["rows"] == []
    assert result["row_count"] == 0


@pytest.mark.parametrize("exception, code", [
    (DatabaseConfigError("private detail"), "DATABASE_CONFIG_ERROR"),
    (psycopg.OperationalError("private detail"), "DATABASE_ERROR"),
])
def test_connection_errors_are_sanitized(mocked_db, exception, code):
    _, _, factory = mocked_db
    factory.side_effect = exception

    result = query_tools.read_select_query("SELECT 1")

    assert result["error"]["code"] == code
    assert "private detail" not in str(result)


def test_query_cancellation(mocked_db):
    _, cursor, _ = mocked_db
    cursor.execute.side_effect = psycopg.errors.QueryCanceled("private detail")

    result = query_tools.read_select_query("SELECT 1")

    assert result["error"]["code"] == "QUERY_CANCELED"
    assert "private detail" not in str(result)


def test_query_error(mocked_db):
    _, cursor, _ = mocked_db
    cursor.execute.side_effect = psycopg.ProgrammingError("private detail")

    result = query_tools.read_select_query("SELECT 1")

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private detail" not in str(result)


@pytest.mark.parametrize("value, expected", [
    (Decimal("12.30"), "12.30"),
    (
        datetime(2026, 10, 28, tzinfo=timezone.utc),
        "2026-10-28T00:00:00+00:00",
    ),
    (UUID("00000000-0000-0000-0000-000000000001"),
     "00000000-0000-0000-0000-000000000001"),
    (b"\x00\xff", "00ff"),
    ([Decimal("1.20")], ["1.20"]),
    ({"amount": Decimal("1.20")}, {"amount": "1.20"}),
    (None, None),
])
def test_json_serialization(value, expected):
    assert query_tools.json_value(value) == expected


def test_explain_returns_plan(mocked_db):
    _, cursor, _ = mocked_db
    document = [{
        "Plan": {
            "Node Type": "Seq Scan",
            "Total Cost": 12.5,
            "Plan Rows": 200,
        }
    }]
    cursor.fetchone.return_value = (document,)

    result = query_tools.read_explain_query("SELECT id FROM orders")

    assert result["plan"] == document
    assert result["estimated_cost"] == 12.5
    assert result["estimated_rows"] == 200
    assert result["planning_request_time_ms"] >= 0
    assert "rows" not in result
    cursor.fetchall.assert_not_called()


def test_explain_disables_analyze(mocked_db):
    _, cursor, _ = mocked_db
    cursor.fetchone.return_value = (
        [{"Plan": {"Total Cost": 1.0, "Plan Rows": 1}}],
    )

    query_tools.read_explain_query("SELECT 1")

    sql = cursor.execute.call_args.args[0]
    assert sql == "EXPLAIN (FORMAT JSON, ANALYZE FALSE) SELECT 1"


def test_explain_does_not_add_result_limit(mocked_db):
    _, cursor, _ = mocked_db
    cursor.fetchone.return_value = (
        [{"Plan": {"Total Cost": 12.5, "Plan Rows": 200}}],
    )

    query_tools.read_explain_query("SELECT id FROM orders")

    sql = cursor.execute.call_args.args[0]
    assert "public.orders" in sql
    assert "LIMIT" not in sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM clients",
    "SELECT pg_sleep(1)",
    "SELECT * FROM pg_catalog.pg_class",
    "EXPLAIN ANALYZE SELECT * FROM clients",
])
def test_explain_rejects_invalid_sql_before_connection(mocked_db, sql):
    _, _, factory = mocked_db

    result = query_tools.read_explain_query(sql)

    assert result["status"] == "error"
    factory.assert_not_called()


def test_explain_checks_read_only_mode(mocked_db):
    connection, cursor, _ = mocked_db
    connection.execute.return_value.fetchone.return_value = {"mode": "off"}

    result = query_tools.read_explain_query("SELECT 1")

    assert result["error"]["code"] == "READ_ONLY_REQUIRED"
    cursor.execute.assert_not_called()


def test_explain_rejects_unavailable_table(mocked_db):
    connection, cursor, _ = mocked_db
    connection.execute.return_value.fetchone.side_effect = [
        {"mode": "on"},
        None,
    ]

    result = query_tools.read_explain_query("SELECT * FROM missing")

    assert result["error"]["code"] == "TABLE_NOT_ALLOWED"
    cursor.execute.assert_not_called()


def test_explain_handles_cancellation(mocked_db):
    _, cursor, _ = mocked_db
    cursor.execute.side_effect = psycopg.errors.QueryCanceled("private detail")

    result = query_tools.read_explain_query("SELECT 1")

    assert result["error"]["code"] == "QUERY_CANCELED"
    assert "private detail" not in str(result)


def test_explain_handles_database_error(mocked_db):
    _, cursor, _ = mocked_db
    cursor.execute.side_effect = psycopg.ProgrammingError("private detail")

    result = query_tools.read_explain_query("SELECT 1")

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private detail" not in str(result)
