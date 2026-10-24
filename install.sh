#!/bin/bash
# Installiert das Agenten-Gedaechtnis auf einem Debian-VPS (als root).
# Voraussetzungen: python3-venv, git, Tailscale laeuft, Vault liegt unter $VAULT.
#
#   ZIEL=/opt/agent-memory VAULT=/root/Second-Brain BIND=100.71.9.93 PORT=8798 ./install.sh
#
# Das Skript ist absichtlich vorsichtig: es ueberschreibt keine vorhandene Unit
# ohne Sicherung und startet den Dienst erst, wenn venv und Modell da sind.
set -euo pipefail

ZIEL="${ZIEL:-/opt/agent-memory}"
VAULT="${VAULT:-/root/Second-Brain}"
PORT="${PORT:-8798}"
BIND="${BIND:-$(tailscale ip -4 2>/dev/null | head -1)}"
HIER="$(cd "$(dirname "$0")" && pwd)"

if [ "$(id -u)" != "0" ]; then
  echo "Bitte als root ausfuehren." >&2
  exit 1
fi
if [ -z "$BIND" ]; then
  echo "Keine Tailscale-Adresse gefunden. BIND=... setzen." >&2
  exit 1
fi
if [ ! -d "$VAULT/10-wissen" ]; then
  echo "Vault nicht gefunden: $VAULT/10-wissen" >&2
  exit 1
fi

echo "== Ziel: $ZIEL | Vault: $VAULT | Adresse: $BIND:$PORT"

mkdir -p "$ZIEL/modelle" "$VAULT/10-wissen/gedaechtnis"
cp "$HIER/memory_server.py" "$ZIEL/memory_server.py"
cp "$HIER/README.md" "$ZIEL/README.md"
mkdir -p "$ZIEL/tools" "$ZIEL/tests"
cp "$HIER/tools/reindex.py" "$ZIEL/tools/reindex.py" 2>/dev/null || true
cp "$HIER/tests/"*.py "$ZIEL/tests/" 2>/dev/null || true

if [ ! -x "$ZIEL/venv/bin/python" ]; then
  echo "== venv anlegen"
  python3 -m venv "$ZIEL/venv"
fi
"$ZIEL/venv/bin/pip" install -q --upgrade pip wheel
"$ZIEL/venv/bin/pip" install -q "mcp[cli]<2" model2vec sqlite-vec

echo "== Modell vorladen (einmalig, ~120 MB)"
HF_HOME="$ZIEL/modelle" "$ZIEL/venv/bin/python" - <<'PY'
from model2vec import StaticModel
StaticModel.from_pretrained("minishlab/potion-multilingual-128M")
print("Modell bereit")
PY

echo "== Unit installieren"
UNIT=/etc/systemd/system/agent-memory.service
if [ -f "$UNIT" ]; then
  cp -a "$UNIT" "$UNIT.bak-$(date +%Y%m%d-%H%M)"
fi
sed -e "s|/opt/agent-memory|$ZIEL|g" \
    -e "s|100\.71\.9\.93|$BIND|g" \
    -e "s|8798|$PORT|g" \
    "$HIER/systemd/agent-memory.service" > "$UNIT"

systemctl daemon-reload
systemctl enable --now agent-memory.service
echo "== Warte auf den Port (Modell + Index brauchen ~30 s)"
for i in $(seq 1 30); do
  if ss -tln | grep -q "$BIND:$PORT"; then break; fi
  sleep 2
done
ss -tlnp | grep "$PORT" || echo "Port $PORT lauscht noch nicht - Log: journalctl -u agent-memory -n 50"

echo "== Fertig. Anbindung: http://$BIND:$PORT/mcp"
echo "   Claude Code: claude mcp add --transport http --scope user agent-memory http://$BIND:$PORT/mcp"
