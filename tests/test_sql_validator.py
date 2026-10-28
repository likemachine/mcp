import pytest

from sql_validator import SQLValidationError, validate_select


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "SELECT id, name FROM public.clients",
    "SELECT id FROM clients",
    "SELECT COUNT(*), SUM(quantity) FROM order_items",
    "SELECT category, AVG(price) FROM products GROUP BY category",
    "SELECT id FROM orders WHERE status = 'completed' ORDER BY id LIMIT 5",
    "SELECT c.id FROM clients c JOIN orders o ON o.client_id = c.id",
    "WITH x AS (SELECT id FROM clients) SELECT * FROM x",
    "SELECT * FROM (SELECT id FROM clients) AS x",
    "SELECT 'DELETE FROM clients' AS note",
    "SELECT COALESCE(name, 'unknown') FROM clients",
])
def test_accepts_supported_select(sql):
    assert isinstance(validate_select(sql), str)


@pytest.mark.parametrize("sql", [
    "DELETE FROM clients",
    "INSERT INTO clients (id) VALUES (1)",
    "UPDATE clients SET name = 'x'",
    "DROP TABLE clients",
    "SELECT 1; SELECT 2",
    "SELECT * INTO copied_clients FROM clients",
    "SELECT * FROM clients FOR UPDATE",
    "WITH x AS (DELETE FROM clients RETURNING *) SELECT * FROM x",
    "SELECT pg_sleep(1)",
    "SELECT public.custom_function()",
    "SELECT * FROM pg_catalog.pg_class",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM private.clients",
    "SELECT * FROM pg_class",
    "SELECT * FROM generate_series(1, 10)",
    "WITH RECURSIVE x AS (SELECT 1) SELECT * FROM x",
    "SELECT 1 UNION SELECT 2",
])
def test_rejects_forbidden_or_unsupported_sql(sql):
    with pytest.raises(SQLValidationError):
        validate_select(sql)


@pytest.mark.parametrize("sql", ["", "   ", None, 123])
def test_rejects_empty_or_invalid_input(sql):
    with pytest.raises(SQLValidationError) as exc:
        validate_select(sql)
    assert exc.value.code == "EMPTY_SQL"


def test_rejects_long_sql():
    with pytest.raises(SQLValidationError) as exc:
        validate_select("SELECT '" + "x" * 4000 + "'")
    assert exc.value.code == "SQL_TOO_LONG"


def test_qualifies_real_table():
    assert "public.clients" in validate_select("SELECT id FROM clients")


def test_does_not_qualify_cte_reference():
    result = validate_select(
        "WITH x AS (SELECT id FROM clients) SELECT * FROM x"
    )
    assert "public.clients" in result
    assert "public.x" not in result


def test_preserves_quoted_table_case():
    result = validate_select('SELECT * FROM "Clients"')
    assert 'public."Clients"' in result
