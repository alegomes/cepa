#!/usr/bin/env python3
"""UserPromptSubmit: quando você reclama do harness, lembra que existe onde gravar.

O incômodo com a Cepa aparece SEMPRE no meio de outra coisa — o gate barrou o
que não devia, o comando perguntou de novo, o relatório saiu ilegível. Nesse
instante o texto da queixa existe (você acabou de escrever), e ele se perde:
o agente responde ao pedido do turno e a reclamação vira histórico de conversa,
que morre com a sessão.

O que este hook faz é uma linha só: ao ver um prompt com forma de queixa E um
alvo do harness no meio, injeta a instrução de gravar pelo skill
`feedback-capture` antes de seguir com o trabalho do turno. Não bloqueia, não
responde, não decide se a queixa procede.

Por que hook e não só a skill: a mesma lição que o repo já catalogou três vezes
— controle que depende do agente lembrar sozinho não é controle. A skill declara
COMO gravar; o hook garante que a hora de gravar seja notada.

Uma vez por sessão. Repetir a mesma linha todo turno é como se ensina a ignorá-la
— e depois do primeiro registro o mecanismo já está no contexto.

Falha ABERTO em tudo: sem estado, sem payload, sem nada — sai em silêncio.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import _wtlib as L
except Exception:  # noqa: BLE001
    L = None

# Alvo: a queixa precisa ser SOBRE o harness. Sem isto, "que porcaria de API" —
# uma reclamação do código do cliente — viraria feedback da Cepa.
ALVO = re.compile(
    r"\b(cepa|harness|hook|hooks|gate|porteiro|comando|skill|agente|subagente|"
    r"worktree|plugin|prompt|relat[óo]rio|sess[ãa]o|/[a-z-]+:[a-z-]+)\b",
    re.IGNORECASE,
)

# Forma de queixa. Deliberadamente estreito: falso positivo aqui custa uma linha
# de ruído em todo turno de trabalho normal, e ruído é o que faz gate virar
# paisagem.
QUEIXA = re.compile(
    r"(n[ãa]o (gost|curt|quero|deveria|devia|era pra|faz sentido)|"
    r"me (irrit|incomod|atrapalh|cansa)|"
    r"irritante|chato|chata|incômod|incomod|atrapalh|"
    r"p[ée]ssim|horr[íi]vel|ruim demais|que saco|de novo\?|"
    r"pare de|para de|parou de|"
    r"por que (voc[êe]|ele|isso) (fez|fica|insiste)|"
    r"est[áa] errado|t[áa] errado|n[ãa]o funciona|"
    r"perd(i|e) tempo|perda de tempo|"
    r"feedback)",
    re.IGNORECASE,
)

LINHA = (
    "[feedback] Este turno tem forma de queixa sobre o harness. Antes de seguir "
    "com o trabalho pedido, registre-a pelo skill `feedback-capture` "
    "(`cepa-feedback add`), com o texto do dono verbatim e o alvo (comando, hook "
    "ou agente). Registre e siga — não pergunte se deve registrar, e não "
    "interrompa a tarefa do turno para discutir a queixa."
)


def ja_avisou(root, sessao):
    """Marcador por sessão. Ancorado na raiz da worktree (não no cwd cru, que o
    `cd` de um Bash anterior desvia — ver _wtlib.session_root)."""
    if not sessao:
        return None, False
    arq = Path(root) / ".claude" / "feedback-nudge"
    try:
        return arq, arq.read_text(encoding="utf-8").strip() == str(sessao)
    except OSError:
        return arq, False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_FEEDBACK_NUDGE", "on") == "off":
            sys.exit(0)

        prompt = (payload.get("prompt") or "").strip()
        if not prompt or len(prompt) > 4000:
            sys.exit(0)
        if not (QUEIXA.search(prompt) and ALVO.search(prompt)):
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        root = L.session_root(cwd) if L else cwd
        arq, avisado = ja_avisou(root, payload.get("session_id"))
        if avisado:
            sys.exit(0)
        if arq:
            try:
                arq.parent.mkdir(parents=True, exist_ok=True)
                arq.write_text(str(payload.get("session_id")), encoding="utf-8")
            except OSError:
                pass  # sem marcador o aviso repete; nunca deixa de avisar

        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": LINHA,
        }}))
    except Exception as e:  # noqa: BLE001
        print(f"[feedback-nudge] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
