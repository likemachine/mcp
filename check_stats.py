import asyncio
import json
from datetime import datetime

from fastmcp import Client

from check_schema import extract_json
from server import mcp


async def main():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "get_table_stats" in [tool.name for tool in tools]

        async def get_stats(table, schema="public"):
            result = await client.call_tool(
                "get_table_stats",
                {"table": table, "schema": schema},
            )
            return extract_json(result)

        orders = await get_stats("orders")
        print("ORDERS:")
        print(json.dumps(orders, indent=2, ensure_ascii=False))

        assert orders["table"] == "orders"
        assert orders["schema"] == "public"
        assert (
            orders["estimated_rows"] is None
            or isinstance(orders["estimated_rows"], int)
        )
        assert isinstance(orders["size"], str)
        assert {
            "orders_pkey",
            "idx_orders_client_id",
            "idx_orders_created_at",
        } <= set(orders["indexes"])

        for key in ("last_analyze", "last_autoanalyze"):
            if orders[key] is not None:
                datetime.fromisoformat(orders[key])

        print("ORDERS STATS: PASS")

        observations = await get_stats("customer_observations")
        assert observations["table"] == "customer_observations", observations
        assert isinstance(observations["indexes"], list)
        print("OBSERVATIONS STATS: PASS")

        missing = await get_stats("__missing_demo_table__")
        assert missing["error"]["code"] == "TABLE_NOT_FOUND"

        denied = await get_stats("pg_class", "pg_catalog")
        assert denied["error"]["code"] == "SCHEMA_NOT_ALLOWED"

        invalid = await get_stats("")
        assert invalid["error"]["code"] == "INVALID_TABLE_NAME"

        print("ERROR HANDLING: PASS")
        print("RESULT: PASS")


if __name__ == "__main__":
    asyncio.run(main())
