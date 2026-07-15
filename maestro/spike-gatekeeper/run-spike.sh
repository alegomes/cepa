#!/usr/bin/env bash
# Spike do porteiro: sobe o gatekeeper e dispara filhas fake `claude -p`
# cobrindo os 4 cenários que o design v1 precisa provar.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${1:?uso: run-spike.sh <dir-de-trabalho>}"
PORT="${PORT:-8765}"
STATE="$WORK/state"
mkdir -p "$WORK" "$STATE"
cd "$WORK"

MCP_CONFIG='{"mcpServers":{"gatekeeper":{"type":"http","url":"http://127.0.0.1:'"$PORT"'/mcp"}}}'
PPT="mcp__gatekeeper__permission_prompt"

child() { # child <nome> <prompt>
  local name="$1" prompt="$2"
  echo "=== filha: $name ==="
  # A regra ask força a rota do permission-prompt-tool: sem ela, o modo
  # default do headless pré-aprova comandos seguros e o porteiro nunca é
  # consultado (achado do 1º run do spike).
  claude -p "$prompt" \
    --mcp-config "$MCP_CONFIG" --strict-mcp-config \
    --permission-prompt-tool "$PPT" \
    --settings '{"permissions":{"ask":["Bash"]}}' \
    --max-turns 4 2>&1 | tee "child-$name.txt" || true
  echo "--- exit: ${PIPESTATUS[0]} ---"
}

# sobe o porteiro
python3 "$HERE/gatekeeper.py" --port "$PORT" --state-dir "$STATE" &
GK_PID=$!
trap 'kill $GK_PID 2>/dev/null || true' EXIT
sleep 1
kill -0 "$GK_PID" || { echo "gatekeeper não subiu"; exit 1; }

# cenário 1 — allow por regra mecânica
child allow "Rode exatamente este comando bash: touch spike-allowed-proof.txt — depois responda apenas OK."

# cenário 2 — deny por regra mecânica
child deny "Rode exatamente este comando bash: touch FORBIDDEN-file.txt — se for negado, responda apenas NEGADO e pare."

# cenário 3 — zona cinza → escalação
child gray "Rode exatamente este comando bash: mkdir -p zona-cinza-dir — se a permissão for negada com mensagem MAESTRO-ESCALATED, responda apenas a linha MAESTRO-EXIT:ESCALATED:<id> com o id da mensagem e pare."

# cenário 4 — duas filhas concorrentes no MESMO porteiro
child c1 "Rode exatamente este comando bash: touch spike-allowed-c1.txt — depois responda apenas OK." &
P1=$!
child c2 "Rode exatamente este comando bash: touch spike-allowed-c2.txt — depois responda apenas OK." &
P2=$!
wait $P1 $P2

echo
echo "=== decisões do porteiro ==="
cat "$STATE/decisions.jsonl" 2>/dev/null || echo "(vazio — NENHUMA chamada chegou ao porteiro)"
echo
echo "=== escalações ==="
ls -la "$STATE/escalations/" 2>/dev/null || echo "(nenhuma)"
echo
echo "=== evidências no cwd ==="
ls -la "$WORK" | grep -E "spike-allowed|FORBIDDEN|zona-cinza" || echo "(nenhum arquivo criado)"
