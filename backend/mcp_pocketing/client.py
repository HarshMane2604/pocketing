import asyncio

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            await session.initialize()

            print("\nConnected to MCP server!")

            tools = await session.list_tools()

            print("\nAvailable tools:")

            for tool in tools.tools:
                print(f"- {tool.name}")

            print("\nSearching for MCP...")

            result = await session.call_tool(
                "search_resources",
                {"query": "MCP"},
            )

            print("\nSearch result:")
            print(result)

            # Get the first matching resource ID

            if result.structured_content:
                search_results = result.structured_content.get("result", [])
            else:
                search_results = []
            
            if not search_results:
                print("\nNo response found.")
            
            resource_id = search_results[0]["id"]

            print(f"\nFound resource ID: {resource_id}")

            full_result =   await session.call_tool(
                "get_resource",
                {"resource_id": resource_id}
            ) 


            print("\nFull resource:")
            print(full_result)



if __name__ == "__main__":
    asyncio.run(main())
