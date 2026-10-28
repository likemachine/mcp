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


def prepare_results(connection, columns=None, primary_key=None, foreign_keys=None):
    relation = MagicMock()
    relation.fetchone.return_value = {"oid": 123}

    column_result = MagicMock()
    column_result.fetchall.return_value = columns or []

    primary_result = MagicMock()
    primary_result.fetchall.return_value = primary_key or []

    foreign_result = MagicMock()
    foreign_result.fetchall.return_value = foreign_keys or []

    connection.execute.side_effect = [
        relation,
        column_result,
        primary_result,
        foreign_result,
    ]


def test_returns_description(mocked_db):
    connection, _ = mocked_db
    columns = [
        {"name": "id", "type": "bigint", "nullable": False},
        {"name": "client_id", "type": "bigint", "nullable": False},
    ]
    foreign_keys = [
        {
            "constraint_name": "orders_client_id_fkey",
            "column": "client_id",
            "referenced_schema": "public",
            "referenced_table": "clients",
            "referenced_column": "id",
            "references": "clients.id",
            "position": 1,
        }
    ]
    prepare_results(
        connection,
        columns=columns,
        primary_key=[{"name": "id"}],
        foreign_keys=foreign_keys,
    )

    result = schema_tools.read_table_description("orders")

    assert result == {
        "schema": "public",
        "table": "orders",
        "columns": columns,
        "primary_key": ["id"],
        "foreign_keys": foreign_keys,
    }


def test_table_without_keys(mocked_db):
    connection, _ = mocked_db
    prepare_results(
        connection,
        columns=[{"name": "note", "type": "text", "nullable": True}],
    )

    result = schema_tools.read_table_description("notes")

    assert result["primary_key"] == []
    assert result["foreign_keys"] == []
    assert result["columns"][0]["nullable"] is True


def test_preserves_composite_primary_key_order(mocked_db):
    connection, _ = mocked_db
    prepare_results(
        connection,
        primary_key=[{"name": "order_id"}, {"name": "product_id"}],
    )

    result = schema_tools.read_table_description("items")

    assert result["primary_key"] == ["order_id", "product_id"]


def test_missing_table_stops_further_queries(mocked_db):
    connection, _ = mocked_db
    connection.execute.return_value.fetchone.return_value = None

    result = schema_tools.read_table_description("missing")

    assert result["error"]["code"] == "TABLE_NOT_FOUND"
    connection.execute.assert_called_once()


@pytest.mark.parametrize("table", ["", "   ", None, 123])
def test_rejects_invalid_table_name(mocked_db, table):
    _, factory = mocked_db

    result = schema_tools.read_table_description(table)

    assert result["error"]["code"] == "INVALID_TABLE_NAME"
    factory.assert_not_called()


@pytest.mark.parametrize("schema", ["pg_catalog", "private"])
def test_rejects_forbidden_schema(mocked_db, schema):
    _, factory = mocked_db

    result = schema_tools.read_table_description("orders", schema)

    assert result["error"]["code"] == "SCHEMA_NOT_ALLOWED"
    factory.assert_not_called()


def test_table_name_is_passed_as_parameter(mocked_db):
    connection, _ = mocked_db
    connection.execute.return_value.fetchone.return_value = None
    table = "orders'; DROP TABLE clients; --"

    result = schema_tools.read_table_description(table)

    sql, params = connection.execute.call_args.args
    assert params == ("public", table)
    assert table not in sql
    assert result["error"]["code"] == "TABLE_NOT_FOUND"


def test_metadata_queries_use_resolved_oid(mocked_db):
    connection, _ = mocked_db
    prepare_results(connection)

    schema_tools.read_table_description("orders")

    calls = connection.execute.call_args_list
    assert len(calls) == 4
    assert calls[0].args[1] == ("public", "orders")
    for call in calls[1:]:
        assert call.args[1] == (123,)


def test_handles_configuration_error(mocked_db):
    _, factory = mocked_db
    factory.side_effect = DatabaseConfigError("private config detail")

    result = schema_tools.read_table_description("orders")

    assert result["error"]["code"] == "DATABASE_CONFIG_ERROR"
    assert "private config detail" not in str(result)


def test_handles_connection_error(mocked_db):
    _, factory = mocked_db
    factory.side_effect = psycopg.OperationalError("private connection detail")

    result = schema_tools.read_table_description("orders")

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private connection detail" not in str(result)


def test_handles_query_error(mocked_db):
    connection, _ = mocked_db
    connection.execute.side_effect = psycopg.ProgrammingError(
        "private query detail"
    )

    result = schema_tools.read_table_description("orders")

    assert result["error"]["code"] == "DATABASE_ERROR"
    assert "private query detail" not in str(result)
