#!/usr/bin/env python3
"""Mede o relatório final do turno contra o formato da skill `plain-report`.

Motivo (03/08/2026): o usuário relatou que precisa ler os relatórios mais de
uma vez para entender — jargão interno demais, ordem invertida (mecanismo antes
do resultado) e detalhe irrelevante. A regra já existia no CLAUDE.md global
("2 frases leigas, recomendação default, técnico por último") e vinha sendo
aplicada só a findings isolados. Regra clara que segue violada precisa de
medição, não de mais prosa — mesmo princípio do proof-verdict-guard.

Dois eventos, um arquivo:

  Stop              — lê a última mensagem do assistente no transcript, mede, e
                      grava o desvio (telemetria + pendência da sessão). NUNCA
                      bloqueia: sai 0 sempre. O usuário escolheu "avisa e mede"
                      justamente para ver, pela telemetria, se o aviso basta
                      antes de decidir apertar.
  UserPromptSubmit  — se houver desvio pendente da vez anterior, injeta o aviso
                      no contexto do próximo turno e apaga a pendência. É assim
                      que o aviso chega ao modelo sem travar o turno.

Escopo (decisão do usuário, 03/08/2026): só relatório de TRABALHO FEITO. O sinal
mecânico é o turno ter alterado alguma coisa (Edit/Write/MultiEdit/NotebookEdit
ou um `git commit`). Conversa, pergunta curta e discussão de design ficam de
fora — formatar um "sim, existe" em três blocos seria pior que o problema.

Saída: sempre exit 0. Este hook mede; ele não é um portão.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── limites do formato (common/skills/plain-report/SKILL.md) ────────────────
MAX_FRASES_ABERTURA = 3
MAX_PALAVRAS_ANTES_DO_TECNICO = 200
MIN_PALAVRAS_PARA_MEDIR = 80   # abaixo disso não é relatório, é recado

MARCADOR_TECNICO = re.compile(r"^\s{0,3}#{1,6}\s*detalhe\s+t[ée]cnico", re.I | re.M)
MARCADOR_PRA_VOCE = re.compile(r"(^\s{0,3}#{1,6}\s*pra\s+voc[êe]|\*\*\s*pra\s+voc[êe]\s*:?\s*\*\*)",
                               re.I | re.M)

STATE_DIR = Path(os.environ.get("CEPA_REPORT_STYLE_DIR")
                 or (Path.home() / ".claude" / "cepa-report-style"))


def _t_emit(event: str, cwd: str = None, **fields) -> None:
    """Espelho mínimo de common/hooks/_telemetry.py (import cross-plugin é
    frágil entre diretórios de cache versionados). Estritamente fail-silent."""
    try:
        import subprocess
        repo = ""
        try:
            out = subprocess.run(
                ["git", "-C", cwd or os.getcwd(), "rev-parse",
                 "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                common = out.stdout.strip()
                repo = Path(common).parent.name if common.endswith("/.git") else Path(common).name
        except Exception:
            pass
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "repo": repo}
        entry.update(fields)
        tdir = Path(os.environ.get("CEPA_TELEMETRY_DIR") or (Path.home() / ".claude" / "cepa-telemetry"))
        tdir.mkdir(parents=True, exist_ok=True)
        with open(tdir / f"events-{entry['ts'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


# ── glossário ───────────────────────────────────────────────────────────────
def load_jargao() -> list:
    """Termos da seção 'Traduzir sempre' do common/glossario.md.

    Só a PRIMEIRA seção é lida: a segunda ('Aceitos sem tradução') existe
    justamente para o vocabulário que já é corrente entre o usuário e o
    harness, e sinalizá-lo geraria ruído que faria o medidor ser ignorado.
    """
    for base in (Path(__file__).resolve().parent.parent,          # common/
                 Path(__file__).resolve().parent.parent.parent):  # repo/common
        f = base / "glossario.md"
        if f.is_file():
            break
    else:
        return []
    try:
        texto = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    m = re.search(r"^##\s*Traduzir sempre\s*$(.*?)(?=^##\s|\Z)", texto,
                  re.S | re.M | re.I)
    if not m:
        return []
    termos = []
    for linha in m.group(1).splitlines():
        m2 = re.match(r"^\s*-\s*\*\*(.+?)\*\*", linha)
        if not m2:
            continue
        # "portão", "falha aberto / falha fechado", "perturbar / perturbação"
        for termo in m2.group(1).split("/"):
            termo = termo.strip().lower()
            if len(termo) >= 4:
                termos.append(termo)
    return termos


# ── leitura do transcript ───────────────────────────────────────────────────
def read_rows(transcript_path: str) -> list:
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except Exception:
        return []


def _is_user_prompt(row) -> bool:
    """Turno do usuário de verdade — não um tool_result travestido de user."""
    if row.get("type") != "user" or row.get("isSidechain"):
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" for b in content)
    return False


def turno_alterou_algo(rows) -> bool:
    """Houve escrita, edição ou commit desde o último prompt do usuário?

    É o sinal mecânico de 'relatório de trabalho feito'. Inclui sidechain de
    propósito: trabalho feito por subagente é trabalho feito.
    """
    inicio = 0
    for i in range(len(rows) - 1, -1, -1):
        if _is_user_prompt(rows[i]):
            inicio = i
            break
    for row in rows[inicio:]:
        if row.get("type") != "assistant":
            continue
        for bloco in (row.get("message") or {}).get("content") or []:
            if not isinstance(bloco, dict) or bloco.get("type") != "tool_use":
                continue
            nome = bloco.get("name", "")
            if nome in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                return True
            if nome == "Bash":
                cmd = str((bloco.get("input") or {}).get("command", ""))
                if re.search(r"\bgit\s+(commit|merge|push)\b", cmd):
                    return True
    return False


def ultimo_relatorio(rows) -> str:
    """O último texto do assistente na conversa principal (nunca sidechain:
    a resposta de um subagente não é o relatório que o usuário lê)."""
    for row in reversed(rows):
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        content = (row.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        textos = [b.get("text", "") for b in content
                  if isinstance(b, dict) and b.get("type") == "text"]
        junto = "\n".join(t for t in textos if t.strip())
        if junto.strip():
            return junto
    return ""


# ── medição ─────────────────────────────────────────────────────────────────
def conta_palavras(texto: str) -> int:
    return len(re.findall(r"\S+", texto))


def frases(texto: str) -> list:
    """Divisão pobre de propósito: só precisa distinguir 3 de 8. Abreviações
    e números com ponto contam a mais, então o limite é generoso."""
    partes = re.split(r"(?<=[.!?…])\s+", texto.strip())
    return [p for p in partes if p.strip()]


def primeiro_paragrafo(texto: str) -> str:
    """A abertura: tudo até a primeira linha em branco, cabeçalho ou lista."""
    linhas = []
    for linha in texto.strip().splitlines():
        if not linha.strip():
            break
        if re.match(r"^\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|\||>)", linha):
            break
        linhas.append(linha)
    return " ".join(linhas).strip()


def medir(relatorio: str, jargao: list) -> list:
    """Devolve os desvios como (categoria, mensagem). Categoria é rótulo
    estável para a telemetria; mensagem é o que o modelo lê. Lista vazia =
    relatório dentro do formato."""
    desvios = []

    m = MARCADOR_TECNICO.search(relatorio)
    cabeca = relatorio[:m.start()] if m else relatorio

    abertura = primeiro_paragrafo(relatorio)
    if not abertura:
        desvios.append(("sem-abertura",
                        "não abre com um parágrafo de resultado — a primeira "
                        "coisa é cabeçalho, lista ou tabela"))
    else:
        n = len(frases(abertura))
        if n > MAX_FRASES_ABERTURA:
            desvios.append(("abertura-longa",
                            f"abertura com {n} frases (máximo {MAX_FRASES_ABERTURA})"))
        achados = sorted({t for t in jargao if t in abertura.lower()})
        if achados:
            desvios.append(("jargao",
                            "jargão na abertura: " + ", ".join(achados) +
                            " — traduza ou mova para o detalhe técnico"))

    if not MARCADOR_PRA_VOCE.search(cabeca):
        desvios.append(("sem-pra-voce",
                        "falta a linha `**Pra você:**` — mesmo que seja "
                        "\"nada pra decidir\""))

    palavras = conta_palavras(cabeca)
    if palavras > MAX_PALAVRAS_ANTES_DO_TECNICO:
        desvios.append(("acima-do-teto",
                        f"{palavras} palavras antes do detalhe técnico "
                        f"(teto {MAX_PALAVRAS_ANTES_DO_TECNICO}) — o resto desce "
                        f"para `### Detalhe técnico`"))

    return desvios


# ── pendência entre turnos ──────────────────────────────────────────────────
def pendencia_path(session_id: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "sem-sessao")
    return STATE_DIR / f"{slug}.json"


def on_stop(payload) -> None:
    rows = read_rows(payload.get("transcript_path", ""))
    if not rows or not turno_alterou_algo(rows):
        return

    relatorio = ultimo_relatorio(rows)
    if conta_palavras(relatorio) < MIN_PALAVRAS_PARA_MEDIR:
        return

    desvios = medir(relatorio, load_jargao())
    cwd = payload.get("cwd") or os.getcwd()
    _t_emit("report_style", cwd=cwd,
            palavras=conta_palavras(relatorio),
            desvios=len(desvios),
            tipos=[cat for cat, _ in desvios])

    p = pendencia_path(payload.get("session_id", ""))
    if not desvios:
        p.unlink(missing_ok=True)
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"desvios": [m for _, m in desvios]},
                                ensure_ascii=False),
                     encoding="utf-8")
    except Exception:
        pass


def on_prompt(payload) -> None:
    p = pendencia_path(payload.get("session_id", ""))
    if not p.is_file():
        return
    try:
        desvios = json.loads(p.read_text(encoding="utf-8")).get("desvios") or []
    except Exception:
        desvios = []
    p.unlink(missing_ok=True)
    if not desvios:
        return
    print("[cepa report-style] Seu relatório anterior saiu do formato "
          "`plain-report`:\n" +
          "".join(f"  - {d}\n" for d in desvios) +
          "  Formato: abertura de até 3 frases sem jargão → **Pra você:** → "
          "### Detalhe técnico. Isso é um aviso, não um bloqueio: aplique no "
          "próximo relatório em vez de reescrever o anterior.")


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    evento = payload.get("hook_event_name") or ""
    try:
        if evento == "Stop":
            on_stop(payload)
        elif evento == "UserPromptSubmit":
            on_prompt(payload)
    except Exception:
        pass  # medidor nunca atrapalha o turno
    sys.exit(0)


if __name__ == "__main__":
    main()
