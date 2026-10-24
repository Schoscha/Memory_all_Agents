import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    async with streamablehttp_client("http://127.0.0.1:8796/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("second-brain TOOLS:", [t.name for t in tools.tools])
            res = await s.call_tool("search", {"query": "agenten gedaechtnis", "limit": 3})
            for c in res.content:
                print("  ", c.text[:160].replace("\n", " "))


asyncio.run(main())
