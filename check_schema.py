import asyncio
import json

from fastmcp import Client

from server import mcp


def extract_json(result):
    if result.is_error:
        raise RuntimeError("MCP tool execution failed")

    for content in result.content:
        if getattr(content, "type", None) == "text":
            return json.loads(content.text)

    raise RuntimeError("No JSON text returned")


async def main():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        names = [tool.name for tool in tools]
        assert "list_tables" in names
        print("TOOLS:", names)

        result = await client.call_tool(
            "list_tables", {"schema": "public"}
        )
        data = extract_json(result)
        print("PUBLIC:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        assert "tables" in data, data
        actual = {table["name"] for table in data["tables"]}
        expected = {
            "clients",
            "products",
            "orders",
            "order_items",
            "customer_observations",
        }
        assert expected <= actual, f"Missing tables: {expected - actual}"

        result = await client.call_tool(
            "list_tables", {"schema": "pg_catalog"}
        )
        denied = extract_json(result)
        assert denied["error"]["code"] == "SCHEMA_NOT_ALLOWED", denied
        print("FORBIDDEN SCHEMA: PASS")
        print("RESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
