# Agenten-Gedächtnis (gemeinsam)

Ein Langzeitgedächtnis für **alle** Agenten auf dem VPS (Claude Code, OpenCode, Hermes …).
Erinnerungen werden als ganz normale **Markdown-Notizen im Obsidian-Vault** abgelegt – Sascha
kann sie lesen, bearbeiten und verschieben wie jede andere Notiz.

- Dienst: `agent-memory.service` (systemd)
- Adresse: `http://100.71.9.93:8798/mcp` – **nur im Tailnet**, kein `0.0.0.0`, kein Schlüssel
- Code: `/opt/agent-memory/memory_server.py`
- venv: `/opt/agent-memory/venv`
- Modell-Cache: `/opt/agent-memory/modelle` (`HF_HOME`)
- Ablage der Erinnerungen: `/root/Second-Brain/10-wissen/gedaechtnis/<projekt>/<datum>_<slug>.md`
- Index: `/root/Second-Brain/.agent-memory-index.sqlite` (eigene DB)

## Warum eine eigene Index-Datenbank?

Der bestehende `second-brain-mcp` (127.0.0.1:8796) arbeitet auf `.vault-index.sqlite`.
Zwei Prozesse auf derselben SQLite-Datei mit Schreibzugriff führen zu Sperren und falschen
Treffern. Deshalb hat dieser Dienst eine eigene DB. Beide lesen denselben Vault, nur mit
getrennten Indizes. `vaultindex.py` wurde dafür minimal erweitert
(siehe `patches/vaultindex.patch`):

- `Index(vault, db_path=...)` – Indexdatei frei wählbar (vorher fest im Vault)
- `Index.search(q, limit, prefix=...)` – nur Pfade unter einem Präfix (Erinnerungen bekommen
  eine eigene Rangliste und werden nicht von Vault-Texten verdrängt)
- `STOPP` (deutsche Füllwörter) und `W_BM25 = 0.8` – Stichwortsuche wird gegen die
  Bedeutungssuche gewichtet, sonst gewinnen Treffer auf „der/die/und"

Die Änderungen sind abwärtskompatibel; `second-brain-mcp` läuft unverändert weiter
(nachgeprüft: `tools/list` und `search` funktionieren, neue Notizen erscheinen dort).

## Werkzeuge (MCP)

| Werkzeug | Zweck |
|---|---|
| `memory_remember` | Entscheidung, Muster, Konvention, Bugfix oder Fakt dauerhaft speichern (schreibt die Markdown-Notiz und indexiert sie sofort) |
| `memory_recall` | Über die **Bedeutung** wiederfinden, auch bei anderer Formulierung; optional `project` / `category`; `auch_vault=True` liefert zusätzlich Treffer aus dem restlichen Vault |
| `memory_get_context` | Arbeitskontext eines Projekts: letzte Erinnerungen, offene Aufgaben aus `TASKS.md`, passende Vault-Notizen. Für den Sitzungsbeginn |
| `memory_list` | Erinnerungen auflisten (neueste zuerst), optional nur ein Projekt |
| `memory_stats` | Anzahl Erinnerungen je Projekt, Indexgröße, ob die Vektorsuche aktiv ist |
| `search` | Hybride Suche über Wissensbank, Projektkatalog **und** Gedächtnis |
| `read_note` | Notiz vollständig lesen (Pfad aus `search` / `memory_recall`) |

Kategorien: `decision`, `architecture`, `bugfix`, `convention`, `fact`, `note`.
`author` ist der eigene Agentenname (`claude-code`, `opencode`, `hermes`), damit nachvollziehbar
bleibt, wer was abgelegt hat.

## Aufruf

```bash
# Status
systemctl status agent-memory.service --no-pager

# neu starten (Modell + Index brauchen ~30 s, bis der Port lauscht)
systemctl restart agent-memory.service && sleep 30 && ss -tlnp | grep 8798

# Log
journalctl -u agent-memory.service -n 50 --no-pager

# Port prüfen (muss 100.71.9.93:8798 sein, nie 0.0.0.0)
ss -tlnp | grep 8798
```

Tests über den MCP-Client (das venv bringt den Client mit):

```bash
cd /opt/agent-memory
./venv/bin/python tests/test_tools.py          # tools/list + remember/recall/context/stats
./venv/bin/python tests/test_recall.py         # 6 Fragen, erwartet 6/6 an erster Stelle
./venv/bin/python tests/test_second_brain.py   # prüft, dass second-brain-mcp weiterläuft
```

Index neu bauen (nur nötig, wenn etwas klemmt – der Dienst baut inkrementell selbst):

```bash
cd /opt/agent-memory
HF_HOME=/opt/agent-memory/modelle ./venv/bin/python tools/reindex.py
```

## Anbindung der Agenten

**OpenCode** (`/root/.config/opencode/opencode.jsonc`):

```jsonc
"agent-memory": {
  "type": "remote",
  "url": "http://100.71.9.93:8798/mcp",
  "enabled": true
}
```

**Claude Code** (User-Scope):

```bash
claude mcp add --transport http --scope user agent-memory http://100.71.9.93:8798/mcp
claude mcp list | grep agent-memory      # erwartet: ✔ Connected
```

**Hermes / andere:** Eintrag analog als Remote-MCP auf `http://100.71.9.93:8798/mcp`.
Hermes läuft auf dem Homeserver; von dort ist die Tailnet-Adresse erreichbar, sofern
Tailscale läuft.

## Arbeitsweise für Agenten

1. **Sitzungsbeginn:** `memory_get_context(project="<projekt>")` – oder `memory_recall(query=...)`
   bei einer konkreten Frage.
2. **Nach jeder Entscheidung, jedem Bugfix, jeder Konvention:** `memory_remember(...)` mit
   `author=<eigener Name>`, kurzem `title`, passender `category` und `project`.
3. **Nichts erfinden:** Erst `search` / `read_note`, dann antworten.

## Installation auf einem anderen Rechner

```bash
git clone <repo> agent-memory && cd agent-memory
ZIEL=/opt/agent-memory VAULT=/root/Second-Brain BIND=100.x.y.z PORT=8798 ./install.sh
```

Das Skript legt venv an, lädt das Modell, sichert eine vorhandene Unit und startet den Dienst.
Voraussetzung: Debian, `python3-venv`, `git`, Tailscale, Vault vorhanden.
Die Erweiterung in `vaultindex.py` muss separat eingespielt werden (`patches/vaultindex.patch`),
weil die Datei zum Second-Brain-Projekt gehört.

## Grenzen

- Ersetzt das Stand-System (`STATUS.md` / `LOGBUCH.md`) **nicht**, ergänzt es.
- Erinnerungen werden nicht automatisch gelöscht oder verdichtet. Aufräumen ist Handarbeit
  (Dateien verschieben/löschen, danach Index neu bauen).
- Vektorsuche braucht RAM: ~2,1 GB im Betrieb, `MemoryMax=3G` in der Unit.
- Kein Zugriff aus dem Internet. Wer von außen zugreifen will, braucht nginx mit Schlüssel
  davor (wie bei `second-brain-mcp`) – bewusst nicht eingerichtet.

## Sicherungen und Rückbau

Sicherungen der berührten Dateien liegen neben den Originalen als `.bak-<datum>-<uhrzeit>`:

- `/root/.config/opencode/opencode.jsonc.bak-*`
- `/root/.claude.json.bak-*`
- `/root/Second-Brain/scripts/vaultindex.py.bak-*`
- `/opt/werkzeuge/registry.json.bak-*`

Rückbau in drei Schritten:

```bash
systemctl disable --now agent-memory.service
rm /etc/systemd/system/agent-memory.service && systemctl daemon-reload
# optional: MCP-Einträge entfernen
claude mcp remove --scope user agent-memory
# opencode: "agent-memory"-Block aus opencode.jsonc löschen
# Erinnerungen bleiben als normale Notizen im Vault erhalten
```

## Verwandt

- `second-brain-mcp` (127.0.0.1:8796) – Vault-Suche, Aufgaben, Notizen schreiben; läuft weiter.
- `nexusmem` auf dem Homeserver (100.114.8.45) – gleiche Idee, anderer Ort. Kann später
  abgeschaltet werden, wenn dieser Dienst alles abdeckt (Entscheidung Sascha).
- Werkzeugkatalog: `/root/Second-Brain/WERKZEUGE.md`, Eintrag `agent-memory`
  (Quelle `/opt/werkzeuge/registry.json`, Erzeugung `/opt/werkzeuge/katalog.py`).
