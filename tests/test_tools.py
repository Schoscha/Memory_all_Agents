import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://100.71.9.93:8798/mcp"


def zeig(x):
    try:
        return json.dumps(x, ensure_ascii=False)[:1200]
    except Exception:
        return str(x)[:1200]


async def main():
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("TOOLS:", [t.name for t in tools.tools])
            if len(sys.argv) > 1 and sys.argv[1] == "nurliste":
                return

            res = await s.call_tool(
                "memory_remember",
                {
                    "content": "Der Gedaechtnis-Dienst laeuft auf dem VPS unter /opt/agent-memory, "
                    "gebunden an 100.71.9.93:8798, Erinnerungen liegen in "
                    "10-wissen/gedaechtnis/<projekt>/. Eigener Index, damit second-brain-mcp unberuehrt bleibt.",
                    "title": "Aufbau des Agenten-Gedaechtnisses",
                    "category": "architecture",
                    "project": "agenten-gedaechtnis",
                    "tags": ["mcp", "vps", "obsidian", "gedaechtnis"],
                    "author": "opencode",
                },
            )
            print("REMEMBER:", zeig([c.text for c in res.content]))

            res = await s.call_tool(
                "memory_recall",
                {"query": "wo werden die Notizen der Agenten abgelegt?", "limit": 3},
            )
            print("RECALL:", zeig([c.text for c in res.content]))

            res = await s.call_tool("memory_get_context", {"project": "agenten-gedaechtnis", "limit": 3})
            print("CONTEXT:", zeig([c.text for c in res.content]))

            res = await s.call_tool("memory_stats", {})
            print("STATS:", zeig([c.text for c in res.content]))


asyncio.run(main())
