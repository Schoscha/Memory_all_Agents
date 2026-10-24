import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://100.71.9.93:8798/mcp"

FRAGEN = [
    ("wohin kommen fertige Videos?", "central-station"),
    ("was tun bei 502 vom Proxy?", "vps"),
    ("wie sichern wir Dateien vor dem Aendern?", "vps"),
    ("welche Adresse hat der Gedaechtnisdienst?", "agenten-gedaechtnis"),
    ("warum halten zwei Dienste denselben Index nicht aus?", "agenten-gedaechtnis"),
    ("wer schreibt die Erinnerungen, wenn Claude arbeitet?", "agenten-gedaechtnis"),
]


def bloecke(res):
    out = []
    for c in res.content:
        t = getattr(c, "text", "")
        try:
            d = json.loads(t)
        except Exception:
            out.append({"text": t})
            continue
        out.extend(d if isinstance(d, list) else [d])
    return out


async def main():
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            gut = 0
            for frage, erwartet in FRAGEN:
                daten = bloecke(await s.call_tool("memory_recall", {"query": frage, "limit": 2, "auch_vault": False}))
                erster = daten[0] if daten else {}
                ok = erster.get("projekt") == erwartet
                gut += ok
                print(("OK  " if ok else "MISS"), frage, "->", erster.get("projekt"), "|", erster.get("titel"))
                for d in daten[1:]:
                    print("        weiter:", d.get("projekt"), "|", d.get("titel"))
            print(f"\n{gut}/{len(FRAGEN)} richtig an erster Stelle")


asyncio.run(main())
