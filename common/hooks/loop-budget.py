#!/usr/bin/env python3
"""PreToolUse + PostToolUse em Task: separa ITERAR de REPETIR.

## O problema

`engineering-lead.md` manda "iterate until each Task is APPROVED", e o skill
`till-done` reforça não parar cedo. Nenhum dos dois tem teto. Um card
patológico — teste que não passa por um motivo que o worker não enxerga — cicla
dev→qa→dev com a mesma falha até a sessão acabar.

O remédio NÃO é afrouxar o `till-done`: parar cedo continua sendo o erro mais
comum e mais caro do harness. O que falta é a distinção entre

  - **iterar** — cada volta traz informação nova, e
  - **repetir** — a mesma volta, com o mesmo vermelho.

A segunda não é persistência, é loop. E o sinal de que ela começou está
disponível sem adivinhação: **a falha é a mesma**.

## Por que a assinatura é da FALHA, e não do prompt

O prompt muda a cada volta (carrega o retorno do qa), então contar prompts
iguais não acha nada. O que se repete é o resultado: o mesmo teste vermelho, a
mesma exceção, o mesmo arquivo. Daí a assinatura ser extraída do texto do
RESULTADO da delegação.

## Como funciona

- **PostToolUse(Task)**: extrai a assinatura de falha do resultado e incrementa
  o contador dela em `.claude/loop-state.json`. Sem falha reconhecível, nada é
  contado (silêncio é o caso normal).
- **PreToolUse(Task)**: se alguma assinatura já bateu o teto duro, BLOQUEIA
  nomeando a falha que se repete e dizendo o que fazer — diagnosticar ou
  declarar BLOCKED, nunca a enésima tentativa idêntica.

O contador vive fora do alcance do agente, pelo mesmo motivo do
`last-build.json`: quem é julgado não escreve o número que o julga.

## Zeragem

Uma assinatura some quando o problema sai de cena — build verde depois dela, ou
`AGE_OUT` delegações sem ela aparecer. Não há botão de "ignorar": desligar é
uma decisão explícita e declarada (`CEPA_LOOP_BUDGET=off`), como o
`.claude/no-build` do gate-advance.

Nunca bloqueia por erro próprio: payload ilegível, disco cheio ou estado
corrompido saem como exit 0.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _wtlib as L  # noqa: E402

try:
    import _telemetry as T
except Exception:  # noqa: BLE001 — telemetria nunca quebra o gate
    class T:  # noqa: N801
        @staticmethod
        def emit(*a, **k):
            pass

STATE = ".claude/loop-state.json"

# Teto duro: a 3ª aparição da MESMA falha bloqueia. Duas é iteração legítima
# (a primeira revela, a segunda tenta o conserto); três é o mesmo vermelho
# olhando de volta pela terceira vez.
HARD_LIMIT = int(os.environ.get("CEPA_LOOP_LIMIT", "3"))

# Assinatura que não aparece em N delegações seguidas é esquecida — senão um
# vermelho já resolvido segue contando meia hora depois.
AGE_OUT = 6

# Linhas que carregam identidade de falha. Amplo de propósito: o que não casar
# aqui simplesmente não é contado, e não contar é o modo seguro.
FAILURE_PATTERNS = [
    re.compile(r"Tests run:.*?Failures:\s*[1-9]\d*.*", re.I),
    re.compile(r"Tests run:.*?Errors:\s*[1-9]\d*.*", re.I),
    re.compile(r"^\s*(?:FAILED|FAIL)\s+(\S+).*", re.M),
    re.compile(r"^\s*\[ERROR\]\s+(\S+).*", re.M),
    re.compile(r"(\w+(?:Error|Exception)):\s*(.{0,120})"),
    re.compile(r"^\s*E\s+(\w*(?:Error|Exception|assert).{0,120})", re.M),
    re.compile(r"\bBUILD FAILURE\b.*"),
    re.compile(r"\b(?:REJECT|BLOCKED|INCOMPLETE|UNPROVEN)\b:?\s*(.{0,120})"),
]

# Ruído que muda a cada run e faria duas falhas idênticas parecerem diferentes.
NOISE = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"), "<TS>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|seconds)\b", re.I), "<DUR>"),
    (re.compile(r"0x[0-9a-f]{4,}", re.I), "<ADDR>"),
    (re.compile(r"/tmp/\S+"), "<TMP>"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "<SHA>"),
    (re.compile(r"\s+"), " "),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def result_text(payload: dict) -> str:
    """O texto do resultado da Task, tolerando as formas que o CC já usou."""
    resp = payload.get("tool_response")
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        for k in ("content", "output", "result", "stdout", "text"):
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, list):  # lista de blocos {type, text}
                return "\n".join(
                    b.get("text", "") for b in v if isinstance(b, dict)
                )
    if isinstance(resp, list):
        return "\n".join(b.get("text", "") for b in resp if isinstance(b, dict))
    return ""


def failure_signature(text: str) -> str:
    """Identidade estável da falha, ou "" quando não há falha reconhecível.

    Junta o que casou, normaliza o ruído volátil e corta. Não é hash: a
    assinatura legível é o que permite a mensagem de bloqueio NOMEAR a falha
    que se repete, em vez de mostrar um número que ninguém pode conferir.
    """
    if not text:
        return ""
    hits = []
    for pat in FAILURE_PATTERNS:
        for m in pat.finditer(text):
            hits.append(m.group(0))
            if len(hits) >= 6:
                break
        if len(hits) >= 6:
            break
    if not hits:
        return ""
    sig = " | ".join(hits)
    for pat, repl in NOISE:
        sig = pat.sub(repl, sig)
    return sig.strip()[:400]


def state_path(cwd: str) -> Path:
    return Path(cwd) / STATE


def load(cwd: str) -> dict:
    try:
        return json.loads(state_path(cwd).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"delegations": 0, "signatures": {}}


def save(cwd: str, data: dict) -> None:
    try:
        p = state_path(cwd)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[loop-budget] não consegui gravar o estado: {e}", file=sys.stderr)


def build_is_green(cwd: str) -> bool:
    try:
        st = json.loads((Path(cwd) / ".claude" / "last-build.json").read_text(encoding="utf-8"))
        return st.get("status") == "SUCCESS"
    except (OSError, json.JSONDecodeError):
        return False


def prune(data: dict) -> dict:
    """Esquece assinatura ausente há AGE_OUT delegações."""
    n = data.get("delegations", 0)
    data["signatures"] = {
        sig: rec for sig, rec in data.get("signatures", {}).items()
        if n - rec.get("last_delegation", n) < AGE_OUT
    }
    return data


def on_post(payload: dict, cwd: str) -> None:
    data = load(cwd)
    data["delegations"] = data.get("delegations", 0) + 1

    # Verde limpa a mesa: se o build passou, o que estava vermelho parou de
    # estar, e contar aquilo daqui em diante seria contar passado.
    if build_is_green(cwd):
        data["signatures"] = {}
        save(cwd, prune(data))
        return

    sig = failure_signature(result_text(payload))
    if not sig:
        save(cwd, prune(data))
        return

    sigs = data.setdefault("signatures", {})
    rec = sigs.setdefault(sig, {"count": 0, "first_seen": now(), "agents": []})
    rec["count"] += 1
    rec["last_seen"] = now()
    rec["last_delegation"] = data["delegations"]
    agent = payload.get("agent_type") or (payload.get("tool_input") or {}).get("subagent_type") or "?"
    if agent not in rec["agents"]:
        rec["agents"].append(agent)
    save(cwd, prune(data))

    if rec["count"] == HARD_LIMIT - 1:
        print(
            f"[loop-budget] ⚠ a mesma falha voltou {rec['count']}x nesta sessão:\n"
            f"  {sig[:200]}\n"
            f"  A próxima delegação com este mesmo vermelho será BLOQUEADA. Antes de "
            f"tentar de novo: mude o que você sabe, não a tentativa — leia o erro "
            f"inteiro, reproduza isoladamente, ou declare BLOCKED com o diagnóstico.",
            file=sys.stderr,
        )
        T.emit("loop_warn", cwd=cwd, count=rec["count"], agent=agent)


def on_pre(payload: dict, cwd: str) -> None:
    data = load(cwd)
    stuck = [(s, r) for s, r in data.get("signatures", {}).items()
             if r.get("count", 0) >= HARD_LIMIT]
    if not stuck:
        sys.exit(0)
    sig, rec = max(stuck, key=lambda kv: kv[1]["count"])
    agents = ", ".join(rec.get("agents", [])) or "?"
    print(
        f"[loop-budget] BLOQUEADO: esta mesma falha já voltou {rec['count']}x "
        f"nesta sessão, sem mudar.\n"
        f"  Falha: {sig[:300]}\n"
        f"  Envolvidos: {agents}\n"
        f"  Delegar de novo com o mesmo vermelho na mesa não é persistir, é "
        f"repetir — `till-done` pede que você não pare cedo, não que você tente "
        f"a mesma coisa uma quarta vez.\n"
        f"  Saídas, nesta ordem:\n"
        f"   1. DIAGNOSTIQUE: leia o erro inteiro, rode o teste isolado, "
        f"reproduza na mão. Uma delegação com informação NOVA passa (a "
        f"assinatura muda quando a falha muda).\n"
        f"   2. Se o build ficar verde, o contador zera sozinho.\n"
        f"   3. Se não há caminho, declare BLOCKED com o diagnóstico — um "
        f"bloqueio nomeado vale mais que a sessão inteira gasta no mesmo ponto.\n"
        f"  Estado: {STATE}. Desligar é decisão explícita: CEPA_LOOP_BUDGET=off.",
        file=sys.stderr,
    )
    T.emit("loop_block", cwd=cwd, count=rec["count"])
    sys.exit(2)


def main():
    if os.environ.get("CEPA_LOOP_BUDGET") == "off":
        sys.exit(0)
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)
    if payload.get("tool_name") != "Task":
        sys.exit(0)
    # RAIZ da worktree: com o cwd cru, um `cd subdir` faz o load() achar
    # `subdir/.claude/loop-state.json`, que não existe — a contagem volta
    # a zero a cada delegação e o teto de 3 repetições nunca dispara.
    cwd = L.session_root(payload.get("cwd") or os.getcwd())
    try:
        if payload.get("hook_event_name") == "PreToolUse":
            on_pre(payload, cwd)
        else:
            on_post(payload, cwd)
    except Exception as e:  # noqa: BLE001 — nunca derruba a sessão
        print(f"[loop-budget] erro interno, liberando: {e}", file=sys.stderr)
        sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
