#!/usr/bin/env python3
"""Validade declarada das memórias do Claude Code.

Uma memória de ESTADO ("não instalado ainda", "falta rodar em repo real") é
verdadeira no dia em que foi escrita e apodrece calada; o índice `MEMORY.md`
entra no contexto de toda sessão, e uma linha vencida chega com a mesma cara de
uma fresca. O campo `validade: AAAA-MM-DD` no frontmatter da memória diz até
quando o fato pode ser repetido sem reconferir. Depois dessa data, `sweep()`
marca a linha dela no índice e `notice()` avisa a sessão que está abrindo.

Memória sem o campo não vence — lição permanente não tem prazo, e alarme
inventado a partir de dado ausente é pior que silêncio. A marca é reversível:
estendeu a validade, a próxima varredura a tira.

Pure stdlib. Importado pelo session-registry (SessionStart); também roda à mão:

    python3 _memval.py sweep [<memory-dir>]
"""

import os
import re
import sys
from datetime import date
from pathlib import Path

MARK_PREFIX = "[VENCIDA desde "
_MARK_RE = re.compile(r"\[VENCIDA desde \d{4}-\d{2}-\d{2}, reconfira antes de afirmar\] ")
_VALIDADE_RE = re.compile(r"^\s*validade:\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?\s*$", re.M)
_LINK_RE = re.compile(r"^(\s*-\s*\[[^\]]*\]\(([^)]+\.md)\)\s*(?:—|-)\s*)(.*)$")


def memory_dir(main_root: str, home: str = None) -> Path:
    """Onde o Claude Code guarda as memórias deste repo: o caminho do clone
    principal com todo caractere não alfanumérico trocado por `-`."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(main_root))
    return Path(home or Path.home()) / ".claude" / "projects" / slug / "memory"


def validade_of(path: Path):
    """A data de validade declarada no frontmatter, ou None (ausente/ilegível)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    m = _VALIDADE_RE.search(text[4:end if end != -1 else len(text)])
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def sweep(mdir: Path, today: date = None):
    """Marca no índice as memórias vencidas, desmarca as que voltaram a valer.
    Devolve as vencidas: [{"file", "validade"}]."""
    today = today or date.today()
    mdir = Path(mdir)
    if not mdir.is_dir():
        return []
    vencidas = {}
    for f in sorted(mdir.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        v = validade_of(f)
        if v and v < today:
            vencidas[f.name] = v

    index = mdir / "MEMORY.md"
    try:
        old = index.read_text(encoding="utf-8")
    except OSError:
        old = None
    if old is not None:
        out = []
        for line in old.splitlines(keepends=True):
            body = line.rstrip("\n")
            m = _LINK_RE.match(body)
            if m:
                head, fname, rest = m.group(1), m.group(2), _MARK_RE.sub("", m.group(3))
                if fname in vencidas:
                    rest = (f"{MARK_PREFIX}{vencidas[fname].isoformat()}, "
                            f"reconfira antes de afirmar] {rest}")
                body = head + rest
            out.append(body + ("\n" if line.endswith("\n") else ""))
        new = "".join(out)
        if new != old:
            tmp = index.with_suffix(".md.tmp")
            tmp.write_text(new, encoding="utf-8")
            os.replace(tmp, index)
    return [{"file": k, "validade": v.isoformat()} for k, v in vencidas.items()]


def notice(vencidas):
    if not vencidas:
        return None
    itens = ", ".join(f"`{v['file'][:-3]}` (venceu em {v['validade']})" for v in vencidas)
    return (
        f"[memória] {len(vencidas)} memória(s) com validade vencida: {itens}. "
        "O que elas afirmam sobre estado (instalado ou não, rodado ou não, pendente) "
        "pode ter mudado: reconfira no disco/git antes de repetir. Ao reconferir, "
        "atualize o texto e a `validade:` da memória; a marca no MEMORY.md sai sozinha."
    )


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "sweep":
        if len(sys.argv) >= 3:
            target = Path(sys.argv[2])
        else:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import _wtlib as L
            target = memory_dir(L.main_root(os.getcwd()) or os.getcwd())
        found = sweep(target)
        print(f"{target}: {len(found)} vencida(s)")
        for v in found:
            print(f"  {v['file']}  validade {v['validade']}")
        sys.exit(0)
    print("usage: _memval.py sweep [<memory-dir>]", file=sys.stderr)
    sys.exit(2)
