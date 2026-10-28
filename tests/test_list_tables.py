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


def test_returns_tables(mocked_db):
    connection, factory = mocked_db
    tables = [
        {"name": "clients", "rows_estimate": 20, "size": "48 kB"},
        {"name": "orders", "rows_estimate": 200, "size": "96 kB"},
    ]
    connection.execute.return_value.fetchall.return_value = tables

    result = schema_tools.read_tables()

    assert result == {"tables": tables}
    factory.assert_called_once_with()


def test_returns_empty_list(mocked_db):
    connection, _ = mocked_db
    connection.execute.return_value.fetchall.return_value = []

    assert schema_tools.read_tables() == {"tables": []}


def test_preserves_unknown_estimate(mocked_db):
    connection, _ = mocked_db
    connection.execute.return_value.fetchall.return_value = [
        {"name": "clients", "rows_estimate": None, "size": "0 bytes"}
    ]

    result = schema_tools.read_tables()

    assert result["tables"][0]["rows_estimate"] is None


@pytest.mark.parametrize(
    "schema",
    ["pg_catalog", "information_schema", "private", "", "PUBLIC"],
)
def test_rejects_forbidden_schema_without_connecting(mocked_db, schema):
    _, factory = mocked_db

    result = schema_tools.read_tables(schema)

    assert result["status"] == "error"
    assert result["error"]["code"] == "SCHEMA_NOT_ALLOWED"
    factory.assert_not_called()


def test_passes_schema_as_query_parameter(mocked_db):
    connection, _ = mocked_db
    connection.execute.return_value.fetchall.return_value = []

    schema_tools.read_tables("public")

    connection.execute.assert_called_once()
    sql, params = connection.execute.call_args.args
    assert params == ("public",)
    assert "n.nspname = %s" in sql


def test_handles_configuration_error(mocked_db):
    _, factory = mocked_db
    factory.side_effect = DatabaseConfigError("internal configuration detail")

    result = schema_tools.read_tables()

    assert result["error"]["code"] == "DATABASE_CONFIG_ERROR"
    assert "internal configuration detail" not in str(result)


def test_handles_connection_error(mocked_db):
    _, factory = mocked_db
    factory.side_effect = psycopg.OperationalError("private connection detail")

    result = schema_tools.read_tables()

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private connection detail" not in str(result)


def test_handles_query_error(mocked_db):
    connection, _ = mocked_db
    connection.execute.side_effect = psycopg.ProgrammingError(
        "private query detail"
    )

    result = schema_tools.read_tables()

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private query detail" not in str(result)
