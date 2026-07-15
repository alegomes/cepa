#!/usr/bin/env python3
"""Spike do porteiro do Maestro — servidor MCP (streamable HTTP) mínimo.

Prova o elo nunca spikado do design v1 (Componente 3): um processo separado
servindo `--permission-prompt-tool` para N filhas `claude -p` simultâneas.

Escopo de spike, deliberadamente: sem auth, sem TLS, bind em 127.0.0.1,
regras hardcoded simples. O que ele PROVA:
  - transporte HTTP compartilhado por N filhas funciona;
  - o payload que a tool recebe (logado integralmente em decisions.jsonl);
  - o formato de resposta allow/deny que a CLI aceita;
  - o caminho de escalação: zona cinza → deny + escalations/<id>.yaml.

Uso: gatekeeper.py --port 8765 --state-dir <dir> [--shadow]
  --shadow: aprova tudo, loga o que TERIA decidido (D3/shadow-mode).
"""
import argparse
import json
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ARGS = None

# Regras mecânicas do spike (D5: zona cinza NUNCA decide sozinha — escala).
ALLOW_PATTERNS = [
    ("bash-base", "Bash", r"^(echo|ls|cat|pwd|true|touch spike-allowed)\b"),
]
DENY_PATTERNS = [
    ("deny-forbidden", "*", r"FORBIDDEN"),
]


def decide(tool_name: str, tool_input: dict) -> tuple[str, str, str | None]:
    """Retorna (decisao, regra, escalation_id)."""
    haystack = json.dumps(tool_input, ensure_ascii=False)
    for rule, tname, pat in DENY_PATTERNS:
        if tname in ("*", tool_name) and re.search(pat, haystack):
            return "deny", rule, None
    for rule, tname, pat in ALLOW_PATTERNS:
        if tname == tool_name and re.search(pat, tool_input.get("command", "")):
            return "allow", rule, None
    # Zona cinza → escala SEMPRE (D5)
    esc_id = uuid.uuid4().hex[:8]
    esc_dir = Path(ARGS.state_dir) / "escalations"
    esc_dir.mkdir(parents=True, exist_ok=True)
    (esc_dir / f"{esc_id}.yaml").write_text(
        "id: {id}\nslice: spike\nacao: {tool}\ncontexto: {ctx}\n"
        "estado: pending\ncriado_em: {ts}\nttl: 3600\n".format(
            id=esc_id, tool=tool_name,
            ctx=json.dumps(haystack, ensure_ascii=False),
            ts=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
    )
    return "escalate", "gray-zone", esc_id


def handle_permission(params: dict) -> dict:
    t0 = time.monotonic()
    args = params.get("arguments", {})
    tool_name = args.get("tool_name", "?")
    tool_input = args.get("input", {})
    decision, rule, esc_id = decide(tool_name, tool_input)

    effective = decision
    if ARGS.shadow and decision != "allow":
        effective = "allow"  # shadow-mode: aprova, loga o que TERIA feito

    if effective == "allow":
        payload = {"behavior": "allow", "updatedInput": tool_input}
    elif decision == "escalate":
        payload = {"behavior": "deny",
                   "message": f"MAESTRO-ESCALATED:{esc_id} — decisão fora das "
                              "regras mecânicas; termine o turno imediatamente "
                              f"reportando MAESTRO-EXIT:ESCALATED:{esc_id}"}
    else:
        payload = {"behavior": "deny", "message": f"negado pela regra {rule}"}

    log = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool_name": tool_name,
        "input": tool_input,
        "raw_params": args,  # payload integral — objetivo do spike
        "decision": decision,
        "effective": effective,
        "shadow": bool(ARGS.shadow),
        "rule": rule,
        "escalation_id": esc_id,
        "latency_ms": round((time.monotonic() - t0) * 1000, 2),
    }
    with open(Path(ARGS.state_dir) / "decisions.jsonl", "a") as f:
        f.write(json.dumps(log, ensure_ascii=False) + "\n")

    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


TOOL_DEF = {
    "name": "permission_prompt",
    "description": "Decide permissões das filhas do maestro (spike).",
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string"},
            "input": {"type": "object"},
        },
        "additionalProperties": True,
    },
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):  # silencia o access log do stdlib
        pass

    def _reply(self, code: int, obj=None):
        body = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(code)
        if body:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):  # stream SSE opcional do streamable HTTP — não usamos
        self._reply(405)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            msg = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self._reply(400)
            return
        method = msg.get("method")
        msg_id = msg.get("id")

        if msg_id is None:  # notification (ex.: notifications/initialized)
            self._reply(202)
            return

        if method == "initialize":
            result = {
                "protocolVersion": msg.get("params", {}).get(
                    "protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "maestro-gatekeeper-spike",
                               "version": "0.0.1"},
            }
        elif method == "tools/list":
            result = {"tools": [TOOL_DEF]}
        elif method == "tools/call":
            params = msg.get("params", {})
            if params.get("name") == "permission_prompt":
                result = handle_permission(params)
            else:
                self._reply(200, {"jsonrpc": "2.0", "id": msg_id,
                                  "error": {"code": -32602,
                                            "message": "unknown tool"}})
                return
        elif method == "ping":
            result = {}
        else:
            self._reply(200, {"jsonrpc": "2.0", "id": msg_id,
                              "error": {"code": -32601,
                                        "message": f"unknown method {method}"}})
            return
        self._reply(200, {"jsonrpc": "2.0", "id": msg_id, "result": result})


def main():
    global ARGS
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--state-dir", required=True)
    p.add_argument("--shadow", action="store_true")
    ARGS = p.parse_args()
    Path(ARGS.state_dir).mkdir(parents=True, exist_ok=True)
    pidfile = Path(ARGS.state_dir) / "gatekeeper.pid"
    pidfile.write_text(str(__import__("os").getpid()))
    srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    print(f"gatekeeper spike ouvindo em 127.0.0.1:{ARGS.port} "
          f"(shadow={ARGS.shadow}) state={ARGS.state_dir}", flush=True)
    try:
        srv.serve_forever()
    finally:
        pidfile.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
