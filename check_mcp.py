import asyncio

from fastmcp import Client

from server import mcp


async def main():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        print("TOOLS:", [tool.name for tool in tools])

        result = await client.call_tool("get_db_health", {})
        print("RESULT:")
        for content in result.content:
            if hasattr(content, "text"):
                print(content.text)


if __name__ == "__main__":
    asyncio.run(main())
