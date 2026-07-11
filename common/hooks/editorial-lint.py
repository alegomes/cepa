#!/usr/bin/env python3
"""PostToolUse hook: lint editorial de conteúdo pt-BR — opt-in por projeto.

As regras de estilo do usuário (zero travessão, não soar LinkedIn-ês, hashtags
específicas do nicho) eram re-ensinadas a cada sessão — a auditoria de 07/2026
achou a mesma correção de travessão feita duas vezes e retrofit manual de
estoque inteiro. Regra clara que ainda é violada precisa de enforcement, não de
mais prosa (mesmo princípio do proof-verdict-guard).

OPT-IN estrito: o hook só age se existir `.claude/editorial-lint` na raiz do
projeto, contendo globs de arquivos de CONTEÚDO (um por linha, # comenta):

    posts/**/*.md
    legendas/*.txt
    docs/produto/**/*.md

Sem o arquivo → inerte (código-fonte nunca é lintado; docstrings usam travessão
legitimamente). Exit 2 em PostToolUse devolve o aviso ao modelo SEM desfazer a
escrita — o modelo corrige em seguida. Nunca bloqueia o turno.

Checagens (v1):
  - travessão (—) e meia-risca usada como travessão ( – )
  - frases-marca de texto de IA/LinkedIn-ês pt-BR
  - hashtags genéricas demais para o nicho
"""

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

EM_DASH = re.compile(r"—|\s–\s")

# Frases-marca: presença = cheiro, não crime; o aviso lista, o modelo julga.
FRASES_MARCA = [
    "além disso,", "é importante ressaltar", "é importante destacar",
    "vale destacar", "vale ressaltar", "nesse sentido,", "em suma,",
    "não é apenas", "mais do que nunca", "em um mundo cada vez mais",
    "game changer", "divisor de águas", "revolucionando",
]

HASHTAGS_GENERICAS = [
    "#tecnologia", "#programacao", "#programação", "#engenhariadesoftware",
    "#desenvolvimento", "#software", "#coding", "#developer", "#tech",
    "#inovacao", "#inovação", "#ia",
]


def load_globs(root: Path):
    cfg = root / ".claude" / "editorial-lint"
    if not cfg.is_file():
        return None
    globs = []
    for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            globs.append(line)
    return globs or None


def find_root(start: Path):
    """Sobe até achar .claude/editorial-lint (limite: raiz do git ou 8 níveis)."""
    d = start if start.is_dir() else start.parent
    for _ in range(8):
        if (d / ".claude" / "editorial-lint").is_file():
            return d
        if (d / ".git").exists() or d == d.parent:
            return d
        d = d.parent
    return d


def matches(rel: str, globs) -> bool:
    # fnmatch não conhece "**": "posts/**/*.md" não casaria "posts/a.md".
    # Testa cada glob também com "**/" colapsado, cobrindo profundidade zero.
    for g in globs:
        if fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.replace("**/", "")):
            return True
    return False


def lint(text: str):
    findings = []
    n_dash = len(EM_DASH.findall(text))
    if n_dash:
        findings.append(f"{n_dash} travessão(ões) '—' — regra do usuário: ZERO travessão em conteúdo; reescreva com vírgula, dois-pontos ou frase nova")
    low = text.lower()
    hits = [f for f in FRASES_MARCA if f in low]
    if hits:
        findings.append(f"frases-marca de texto de IA/LinkedIn-ês: {', '.join(repr(h) for h in hits[:5])} — soe humano")
    tags = [t for t in HASHTAGS_GENERICAS if t in low]
    if tags:
        findings.append(f"hashtag(s) genérica(s): {', '.join(tags[:5])} — use hashtags específicas do nicho")
    return findings


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    fp = Path(file_path)
    root = find_root(Path(payload.get("cwd") or os.getcwd()))
    globs = load_globs(root)
    if not globs:
        sys.exit(0)  # projeto não opta pelo lint — inerte

    try:
        rel = str(fp.resolve().relative_to(root.resolve()))
    except ValueError:
        sys.exit(0)  # arquivo fora do projeto configurado
    if not matches(rel, globs):
        sys.exit(0)

    # Linta o conteúdo NOVO: no Write vem inteiro; em Edit/MultiEdit, os trechos.
    if payload.get("tool_name") == "Write":
        texts = [tool_input.get("content") or ""]
    elif payload.get("tool_name") == "Edit":
        texts = [tool_input.get("new_string") or ""]
    else:  # MultiEdit
        texts = [e.get("new_string") or "" for e in (tool_input.get("edits") or [])]

    findings = []
    for t in texts:
        findings.extend(lint(t))
    if not findings:
        sys.exit(0)

    print(
        f"[editorial-lint] {rel} viola regras editoriais do usuário "
        f"(config: .claude/editorial-lint):\n"
        + "\n".join(f"  - {f}" for f in findings[:8])
        + "\n  Corrija o arquivo agora (a escrita foi aplicada; edite por cima).",
        file=sys.stderr,
    )
    sys.exit(2)  # PostToolUse: stderr volta ao modelo; não desfaz nada


if __name__ == "__main__":
    main()
