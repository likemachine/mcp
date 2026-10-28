import asyncio
import json

from fastmcp import Client

from check_schema import extract_json
from server import mcp


async def main():
    async with Client(mcp) as client:
        names = [tool.name for tool in await client.list_tools()]
        assert "run_select_query" in names
        assert "explain_query" in names
        print("MCP REGISTRATION: PASS")

        async def query(sql):
            result = await client.call_tool(
                "run_select_query",
                {"sql": sql},
            )
            return extract_json(result)

        result = await query(
            "SELECT id, name FROM clients ORDER BY id LIMIT 3"
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        assert result.get("row_count") == 3, result
        assert result["columns"] == ["id", "name"]
        print("MCP SELECT: PASS")

        result = await query("SELECT id FROM orders ORDER BY id")
        assert result.get("row_count") == 100, result
        print("MCP ROW LIMIT: PASS")

        for sql in [
            "DELETE FROM clients",
            "SELECT pg_sleep(1)",
            "SELECT * FROM pg_catalog.pg_class",
            "SELECT 1; SELECT 2",
        ]:
            result = await query(sql)
            assert result.get("status") == "error", result

        print("MCP FORBIDDEN SQL: PASS")

    print("RESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
