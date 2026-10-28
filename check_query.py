import json

from query_tools import read_select_query


def main():
    result = read_select_query(
        "SELECT id, name FROM clients ORDER BY id LIMIT 3"
    )
    print("CLIENTS:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    assert result.get("row_count") == 3, result
    assert result["columns"] == ["id", "name"]
    print("BASIC SELECT: PASS")

    result = read_select_query("SELECT id FROM orders ORDER BY id")
    assert result.get("row_count") == 100, result
    print("ROW LIMIT: PASS")

    result = read_select_query(
        "WITH x AS (SELECT id FROM clients) "
        "SELECT COUNT(*) AS total FROM x"
    )
    assert result.get("row_count") == 1, result
    assert isinstance(result["rows"][0][0], int)
    print("CTE: PASS")

    result = read_select_query("SELECT 1 AS value, 2 AS value")
    assert result.get("columns") == ["value", "value"], result
    assert result["rows"] == [[1, 2]], result
    print("DUPLICATE COLUMN NAMES: PASS")

    result = read_select_query("SELECT price FROM products LIMIT 1")
    assert result.get("row_count") == 1, result
    assert isinstance(result["rows"][0][0], str), result
    print("DECIMAL SERIALIZATION: PASS")

    for sql in [
        "DELETE FROM clients",
        "SELECT pg_sleep(1)",
        "SELECT * FROM pg_catalog.pg_class",
        "SELECT 1; SELECT 2",
    ]:
        result = read_select_query(sql)
        assert result.get("status") == "error", result
    print("FORBIDDEN SQL: PASS")

    result = read_select_query("SELECT * FROM __missing_demo_table__")
    assert result["error"]["code"] == "TABLE_NOT_ALLOWED", result
    print("MISSING TABLE: PASS")

    print("RESULT: PASS")


if __name__ == "__main__":
    main()
