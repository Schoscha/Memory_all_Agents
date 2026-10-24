#!/usr/bin/env python3
"""Gemeinsames Gedaechtnis fuer alle Agenten (MCP, nur im Tailnet).

Ein Speicher, den Claude, Hermes, OpenCode und andere gemeinsam nutzen:
schreiben (memory_remember), wiederfinden (memory_recall, Bedeutungssuche),
Projektkontext holen (memory_get_context) - und alles liegt als normale
Markdown-Notiz im Obsidian-Vault, damit Sascha es lesen und bearbeiten kann.

Ablage:   /root/Second-Brain/10-wissen/gedaechtnis/<projekt>/<datum>_<slug>.md
Index:    /root/Second-Brain/.agent-memory-index.sqlite  (eigene DB, damit der
          bestehende Second-Brain-Dienst nicht blockiert)
Suche:    FTS5/BM25 + sqlite-vec + model2vec (potion-multilingual-128M), RRF
Start:    /opt/agent-memory/venv/bin/python /opt/agent-memory/memory_server.py --http 100.71.9.93 8798
"""
import datetime
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/root/Second-Brain/scripts")
from vaultindex import Index  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

VAULT = Path("/root/Second-Brain")
GED = VAULT / "10-wissen" / "gedaechtnis"
GED_REL = "10-wissen/gedaechtnis/"
TASKS = VAULT / "TASKS.md"
KATEGORIEN = ("decision", "architecture", "bugfix", "convention", "fact", "note")

mcp = FastMCP(
    "agenten-gedaechtnis",
    instructions=(
        "Gemeinsames Langzeitgedaechtnis aller Agenten (Sascha). "
        "Vor der Arbeit memory_get_context(project=...) oder memory_recall(query=...) lesen. "
        "Nach jeder Entscheidung, jedem Bugfix und jeder Konvention memory_remember(...) schreiben, "
        "mit author=<eigener Agentenname>. Fuer Wissen aus dem Vault: search() und read_note()."
    ),
)

ix = Index(VAULT, db_path=VAULT / ".agent-memory-index.sqlite")
ix.build()
ix.search("warmup", 1)


def _slug(text: str, maxlen: int = 60) -> str:
    t = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:maxlen] or "erinnerung"


def _projekt_ordner(project: str) -> Path:
    return GED / (_slug(project or "global", 40))


def _safe(rel: str) -> Path:
    p = (VAULT / rel).resolve()
    if VAULT not in p.parents and p != VAULT:
        raise ValueError("Pfad ausserhalb des Vaults")
    return p


def _lesen(rel: str) -> dict:
    """Liest eine Erinnerung: Frontmatter + Text."""
    p = VAULT / rel
    text = p.read_text(encoding="utf-8", errors="ignore")
    fm = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                m = re.match(r"^([\w-]+):\s*(.*)$", line)
                if m:
                    fm[m.group(1)] = m.group(2).strip()
            body = text[end + 4:].lstrip("\n")
    return {
        "path": rel,
        "titel": fm.get("title", p.stem),
        "kategorie": fm.get("category", ""),
        "projekt": fm.get("project", ""),
        "autor": fm.get("author", ""),
        "tags": fm.get("tags", ""),
        "erstellt": fm.get("erstellt", ""),
        "text": body.strip(),
    }


@mcp.tool()
def memory_remember(
    content: str,
    title: str = "",
    category: str = "decision",
    project: str = "global",
    tags: list[str] | None = None,
    author: str = "agent",
) -> str:
    """Speichert eine Entscheidung, ein Muster, eine Konvention, einen Bugfix oder einen Fakt dauerhaft.

    content: Inhalt in knappem Markdown. title: kurzer Titel (sonst aus dem Inhalt).
    category: decision | architecture | bugfix | convention | fact | note.
    project: Projektname oder 'global'. tags: Schlagwoerter. author: Agentenname (z. B. 'claude-code', 'opencode', 'hermes').
    Legt eine Markdown-Notiz im Obsidian-Vault ab und indexiert sie sofort.
    """
    if category not in KATEGORIEN:
        category = "note"
    heute = datetime.datetime.now()
    titel = (title or content.strip().splitlines()[0])[:120]
    ordner = _projekt_ordner(project)
    ordner.mkdir(parents=True, exist_ok=True)
    p = ordner / f"{heute:%Y-%m-%d_%H%M}_{_slug(titel, 50)}.md"
    i = 2
    while p.exists():
        p = ordner / f"{heute:%Y-%m-%d_%H%M}_{_slug(titel, 50)}-{i}.md"
        i += 1
    tag_liste = ", ".join(tags or [])
    p.write_text(
        "---\n"
        f"title: {titel}\n"
        f"category: {category}\n"
        f"project: {project or 'global'}\n"
        f"tags: [{tag_liste}]\n"
        f"author: {author}\n"
        f"erstellt: {heute:%Y-%m-%d %H:%M}\n"
        "quelle: agent-memory\n"
        "---\n\n"
        f"{content.strip()}\n",
        encoding="utf-8",
    )
    rel = str(p.relative_to(VAULT))
    ix.build()  # inkrementell: nur die neue Datei
    return f"gespeichert: {rel}"


@mcp.tool()
def memory_recall(
    query: str,
    project: str = "",
    category: str = "",
    limit: int = 8,
    auch_vault: bool = True,
) -> list[dict]:
    """Findet Erinnerungen ueber Bedeutung, nicht nur ueber Stichworte (BM25 + Vektor, RRF).

    query: Frage oder Stichworte, gern anders formuliert als beim Speichern.
    project / category: optional einschraenken. auch_vault: zusaetzlich Treffer aus dem restlichen Vault liefern.
    """
    ix.build()
    # Erinnerungen bekommen eine eigene Rangliste, damit sie nicht von Vault-Texten verdraengt werden.
    out = []
    for t in ix.search(query, limit, prefix=GED_REL):
        d = _lesen(t["path"])
        out.append({**d, "score": t["score"], "treffer_aus": "gedaechtnis"})
    if auch_vault:
        for t in ix.search(query, limit * 2):
            if t["path"].startswith(GED_REL):
                continue
            out.append({
                "path": t["path"], "titel": t["title"], "kategorie": t["typ"],
                "projekt": "", "autor": "", "tags": "",
                "erstellt": "", "text": t["snippet"], "score": t["score"],
                "treffer_aus": "vault",
            })
            if len([o for o in out if o["treffer_aus"] == "vault"]) >= limit:
                break
    if project:
        out = [o for o in out if o["treffer_aus"] == "vault" or _slug(o["projekt"], 40) == _slug(project, 40)]
    if category:
        out = [o for o in out if o["treffer_aus"] == "vault" or o["kategorie"] == category]
    return out


@mcp.tool()
def memory_get_context(project: str = "global", limit: int = 12) -> str:
    """Liefert den Arbeitskontext eines Projekts: letzte Erinnerungen, offene Aufgaben, wichtige Vault-Notizen.

    Am Anfang einer Sitzung aufrufen, damit kein Agent bei null anfaengt.
    """
    ordner = _projekt_ordner(project)
    dateien = sorted(ordner.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit] if ordner.is_dir() else []
    zeilen = [f"# Kontext: {project}", ""]
    if dateien:
        zeilen.append(f"## Letzte Erinnerungen ({len(dateien)})")
        for f in dateien:
            d = _lesen(str(f.relative_to(VAULT)))
            zeilen.append(f"- **{d['titel']}** ({d['kategorie']}, {d['autor']}, {d['erstellt']}) `{d['path']}`")
            zeilen.append("  " + d["text"].replace("\n", "\n  ")[:600])
    else:
        zeilen.append(f"## Letzte Erinnerungen\n(noch keine unter {ordner.relative_to(VAULT)})")

    if TASKS.exists():
        offen = [
            l.strip() for l in TASKS.read_text(encoding="utf-8").splitlines()
            if l.startswith("- [ ]") and (project.lower() in l.lower() or project in ("global", ""))
        ]
        if offen:
            zeilen += ["", f"## Offene Aufgaben ({len(offen)})"] + [f"- {o[6:]}" for o in offen[:limit]]

    ix.build()
    treffer = [t for t in ix.search(project, 20) if not t["path"].startswith(GED_REL)][:5]
    if treffer:
        zeilen += ["", "## Passende Vault-Notizen"]
        zeilen += [f"- {t['path']} [{t['heading']}] - {t['snippet'][:140]}" for t in treffer]
    return "\n".join(zeilen)


@mcp.tool()
def memory_list(project: str = "", limit: int = 30) -> list[dict]:
    """Listet gespeicherte Erinnerungen (neueste zuerst), optional nur ein Projekt."""
    ordner = _projekt_ordner(project) if project else GED
    dateien = [f for f in ordner.rglob("*.md") if f.is_file()]
    dateien.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return [_lesen(str(f.relative_to(VAULT))) for f in dateien[:limit]]


@mcp.tool()
def search(query: str, limit: int = 8) -> list[dict]:
    """Hybride Suche (Stichwort + Bedeutung) ueber Wissensbank, Projektkatalog und Gedaechtnis. Liefert Pfad, Titel, Ausschnitt."""
    ix.build()
    return ix.search(query, limit)


@mcp.tool()
def read_note(path: str) -> str:
    """Liest eine Notiz komplett (Pfad aus search oder memory_recall)."""
    return _safe(path).read_text(encoding="utf-8", errors="ignore")


@mcp.tool()
def memory_stats() -> dict:
    """Zustand des Gedaechtnisses: Anzahl Notizen je Projekt, Indexgroesse, Vektorsuche an/aus."""
    pro_projekt = {}
    if GED.is_dir():
        for f in GED.rglob("*.md"):
            pro_projekt[f.parent.name] = pro_projekt.get(f.parent.name, 0) + 1
    s = ix.stats()
    s["vektor_fehler"] = "" if ix.vec else getattr(ix, "vec_error", "")
    s["erinnerungen"] = sum(pro_projekt.values())
    s["pro_projekt"] = dict(sorted(pro_projekt.items(), key=lambda x: -x[1]))
    return s


if __name__ == "__main__":
    if "--http" in sys.argv:
        i = sys.argv.index("--http")
        mcp.settings.host = sys.argv[i + 1]
        mcp.settings.port = int(sys.argv[i + 2])
        from mcp.server.transport_security import TransportSecuritySettings

        hosts = [mcp.settings.host, f"{mcp.settings.host}:{mcp.settings.port}", "localhost:*", "127.0.0.1:*"]
        hosts += [h.strip() for h in os.environ.get("AGENT_MEMORY_HOSTS", "").split(",") if h.strip()]
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=hosts
        )
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
