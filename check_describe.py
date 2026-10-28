import asyncio
import json

from fastmcp import Client

from check_schema import extract_json
from server import mcp


async def main():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "describe_table" in [tool.name for tool in tools]

        async def describe(table, schema="public"):
            result = await client.call_tool(
                "describe_table",
                {"table": table, "schema": schema},
            )
            return extract_json(result)

        orders = await describe("orders")
        print("ORDERS:")
        print(json.dumps(orders, indent=2, ensure_ascii=False))

        assert orders["primary_key"] == ["id"], orders
        columns = {column["name"]: column for column in orders["columns"]}
        assert columns["client_id"]["nullable"] is False
        assert any(
            key["column"] == "client_id"
            and key["references"] == "clients.id"
            for key in orders["foreign_keys"]
        )
        print("ORDERS: PASS")

        items = await describe("order_items")
        references = {
            (key["column"], key["references"])
            for key in items["foreign_keys"]
        }
        assert ("order_id", "orders.id") in references
        assert ("product_id", "products.id") in references
        print("ORDER_ITEMS: PASS")

        products = await describe("products")
        assert products["foreign_keys"] == []
        assert any(
            column["name"] == "price"
            and column["type"] == "numeric(12,2)"
            for column in products["columns"]
        )
        print("PRODUCTS: PASS")

        missing = await describe("__missing_demo_table__")
        assert missing["error"]["code"] == "TABLE_NOT_FOUND"

        denied = await describe("pg_class", "pg_catalog")
        assert denied["error"]["code"] == "SCHEMA_NOT_ALLOWED"

        invalid = await describe("")
        assert invalid["error"]["code"] == "INVALID_TABLE_NAME"

        print("ERROR HANDLING: PASS")
        print("RESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
