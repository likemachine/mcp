import asyncio
import json

from fastmcp import Client

from check_schema import extract_json
from server import mcp


async def main():
    async with Client(mcp) as client:
        names = [tool.name for tool in await client.list_tools()]
        assert "explain_query" in names
        print("MCP REGISTRATION: PASS")

        result = await client.call_tool(
            "explain_query",
            {"sql": "SELECT id FROM orders WHERE client_id = 1"},
        )
        data = extract_json(result)
        print(json.dumps(data, indent=2, ensure_ascii=False))

        assert isinstance(data.get("plan"), list), data
        root = data["plan"][0]["Plan"]
        assert "Node Type" in root
        assert data["estimated_cost"] == root["Total Cost"]
        assert data["estimated_rows"] == root["Plan Rows"]
        assert data["estimated_cost"] >= 0
        assert "Actual Rows" not in root
        print("EXPLAIN PLAN: PASS")

        result = await client.call_tool(
            "explain_query",
            {
                "sql": (
                    "WITH x AS (SELECT id FROM clients) "
                    "SELECT COUNT(*) FROM x"
                )
            },
        )
        data = extract_json(result)
        assert "plan" in data, data
        print("CTE PLAN: PASS")

        for sql in [
            "DELETE FROM clients",
            "SELECT pg_sleep(1)",
            "SELECT * FROM pg_catalog.pg_class",
            "EXPLAIN ANALYZE SELECT * FROM clients",
        ]:
            result = await client.call_tool("explain_query", {"sql": sql})
            data = extract_json(result)
            assert data.get("status") == "error", data

        print("FORBIDDEN SQL: PASS")

        result = await client.call_tool(
            "explain_query",
            {"sql": "SELECT * FROM __missing_demo_table__"},
        )
        data = extract_json(result)
        assert data["error"]["code"] == "TABLE_NOT_ALLOWED", data
        print("MISSING TABLE: PASS")

    print("RESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
