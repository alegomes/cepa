#!/usr/bin/env python3
"""PreToolUse hook for the docs topology — the BASH half of the path-lock.

WHY THIS EXISTS
---------------
`path-lock.py` gates Edit / Write / MultiEdit / NotebookEdit. It does NOT see
Bash. An agent whose Write is blocked can reach for the shell — `sed -i`,
`cat > file`, `tee`, a heredoc — and land the exact write the path-lock was
meant to stop. That is not a hypothetical: a lead once edited source via Bash
because Write was locked and Bash wasn't. The artifact happened to be correct,
so nothing in the pipeline flagged it. A control enforced on one tool but not
its equivalent is not a control.

This hook is the SECOND lock. It reuses path-lock.py's per-agent allowlist
(single source of truth — never re-declare globs here) and applies it to
shell-level writes.

DESIGN — deliberately narrow, to keep false positives near zero
---------------------------------------------------------------
- We only fire on writes the SHELL performs explicitly: redirections
  (`>`, `>>`), `tee`, `sed -i`, `cp`, `mv`, `install`, `dd of=`, `truncate`.
- We do NOT inspect what a subprocess writes internally. `./mvnw test` and
  `git merge` create files, but via the JVM / git, not via shell redirection,
  so they are invisible here. That is correct: those are the lead's legitimate
  Bash uses.
- We only flag a target that resolves INSIDE the project tree. Writes to
  /tmp, /dev/null, caches, $HOME — out of scope, always allowed. (The
  Write-tool lock now applies the same out-of-root carve-out, so both halves
  agree: writes outside the project tree are nobody's business here. Bash
  always touched paths outside the repo legitimately; the Write lock had to
  catch up so proof-reviewer could perturb code in its /tmp worktree.)
- Main session / built-in agents (no plugin-prefixed agent_type) are NOT
  gated — same fail-open contract as path-lock.py.

HONEST LIMITS (this is a guardrail, not a sandbox)
--------------------------------------------------
Parsing shell to know what it writes is undecidable. We cannot see writes
done by `python -c`, `perl -e`, `ruby -e`, `node -e`, `awk -i inplace`, `ed`,
`patch`, or a heredoc body fed to an interpreter. When we detect such a
construct we let the command through (fail-open) but record a line in the
coverage log (BASH_PATHLOCK_COVERAGE_LOG, default /tmp/docs-bash-pathlock-
uncovered.log) so the gap is visible, never silent. Layer A (the agent's own
discipline, encoded in its prompt + expertise) remains the primary control;
this is defense-in-depth under it.

Exit codes:
  0 — allowed (or out of scope, or could not analyze → fail-open + logged)
  2 — blocked: a shell write to an in-project path outside the agent's allowlist
"""

import importlib.util
import json
import os
import re
import shlex
import sys
from pathlib import Path

PLUGIN_NAME = "docs"

# ─── reuse path-lock.py as the single source of truth for allowlists ──────────

def _load_pathlock_module():
    """Import the sibling path-lock.py (hyphen in the filename → importlib)."""
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "docs_path_lock", str(here / "path-lock.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Redirection: `>` or `>>`, NOT preceded by a digit or `&` (excludes `2>`,
# `&>`, `1>&2`), and the target must not start with `&` (excludes `>&1`) or `=`
# (excludes the `>=` comparison operator — `>` immediately followed by `=` is
# never a redirect; without this, `sed -i 's/>=/>/'`, `grep '>='`, and
# `[[ $a >= $b ]]` capture junk targets and get falsely blocked).
_REDIR_RE = re.compile(r"""(?<![0-9&])>>?\s*(?![&=])("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")

# Constructs we cannot statically analyze — fail open but log.
_UNCOVERED_RE = re.compile(
    r"""(?:
        \bpython3?\s+-c\b | \bperl\s+-[eE]\b | \bruby\s+-e\b | \bnode\s+-e\b |
        \bawk\b[^|;&]*\b-i\b | \b-i\s+inplace\b | \bgawk\b[^|;&]*\binplace\b |
        \bed\b | \bpatch\b | <<-?\s*['"]?\w+   # heredoc
    )""",
    re.VERBOSE,
)

# Targets that are never real files.
_PSEUDO = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")

# Separadores de comando, aplicados só FORA de aspas (ver _quoted_mask).
_SEP_PAIRS = ("||", "&&")
_SEP_CHARS = ";|&\n"


def _quoted_mask(s: str) -> list:
    """Um booleano por caractere: True onde ele está entre aspas ou escapado.

    Existe porque o hook lia texto citado como se fosse shell. O caso real
    (22/08/2026, WEGO-2087): `git commit -m "titulo\n\ncorpo com A -> B"`. O
    `\n` do corpo era tratado como separador de comando, cada linha da mensagem
    virava um "segmento", e o `->` de uma frase casava com _REDIR_RE — o hook
    acusava escrita fantasma em `B` e barrava o commit. O dev só conseguiu
    commitar depois de encurtar a mensagem para uma linha.

    Aspas não fechadas mascaram o resto da string: é fail-open, coerente com o
    contrato do hook, e um comando com aspas não fechadas não roda no shell.
    """
    mask = [False] * len(s)
    quote = None
    i = 0
    while i < len(s):
        c = s[i]
        if quote is None:
            if c == "\\":
                mask[i] = True
                if i + 1 < len(s):
                    mask[i + 1] = True
                i += 2
                continue
            if c in "\"'":
                quote = c
                mask[i] = True
            i += 1
            continue
        mask[i] = True
        if quote == '"' and c == "\\":
            if i + 1 < len(s):
                mask[i + 1] = True
            i += 2
            continue
        if c == quote:
            quote = None
        i += 1
    return mask


def _split_segments(command: str) -> list:
    """Quebra em segmentos de comando ignorando separadores dentro de aspas."""
    mask = _quoted_mask(command)
    segments = []
    start = i = 0
    n = len(command)
    while i < n:
        if mask[i]:
            i += 1
            continue
        if command[i:i + 2] in _SEP_PAIRS:
            segments.append(command[start:i])
            i += 2
            start = i
            continue
        if command[i] in _SEP_CHARS:
            segments.append(command[start:i])
            i += 1
            start = i
            continue
        i += 1
    segments.append(command[start:])
    return segments


# Um redirecionamento inteiro — descritor opcional (`2>`), operador, `&`
# opcional (`>&2`) e o operando. Serve só para APAGAR o redirecionamento antes
# de tokenizar o comando: `tee saida.txt < entrada.txt` tokenizava como
# `["tee", "saida.txt", "<", "entrada.txt"]`, e a regra do `tee` — todo
# argumento que não é flag é escrito — registrava `<` e `entrada.txt` como
# alvos de escrita. `entrada.txt` está sendo LIDO. Mesma família do falso
# positivo do commit multilinha: um pedaço da linha lido como o que não é.
_REDIR_STRIP_RE = re.compile(
    r"""[0-9]?(?:>>?|<<?)&?\s*(?:"[^"]*"|'[^']*'|[^\s;&|<>()]+)?"""
)


def _strip_redirections(segment: str, mask: list) -> str:
    """Remove os redirecionamentos FORA de aspas, preservando o resto intacto."""
    cortes = [
        (m.start(), m.end())
        for m in _REDIR_STRIP_RE.finditer(segment)
        if m.group() and not mask[m.start()]
    ]
    if not cortes:
        return segment
    out, pos = [], 0
    for ini, fim in cortes:
        out.append(segment[pos:ini])
        pos = fim
    out.append(segment[pos:])
    return " ".join(p for p in out if p)


def _unquoted_view(command: str) -> str:
    """A linha de comando com o conteúdo citado trocado por espaço.

    O detector de construção indecidível (_UNCOVERED_RE) varria a linha inteira,
    aspas incluídas: uma mensagem de commit com a palavra `ed`, ou com um `<<`
    no meio da prosa, gerava uma entrada falsa no log de cobertura. O log só
    existe para dizer o que o hook NÃO conseguiu analisar — enchê-lo de prosa
    ensina a ignorá-lo.
    """
    mask = _quoted_mask(command)
    return "".join(" " if m else c for c, m in zip(command, mask))


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
        return tok[1:-1]
    return tok


def _is_flag(tok: str) -> bool:
    return tok.startswith("-") and tok != "-"


def _segment_targets(segment: str) -> list:
    """Best-effort extraction of shell-write targets from one command segment."""
    targets = []

    # 1. Redirections (covers `cat > f`, `echo .. >> f`, `cmd > f`, heredoc-to-file).
    #    O `>` precisa estar fora de aspas: um `->` no meio de uma mensagem de
    #    commit é prosa, não redirecionamento.
    redir_mask = _quoted_mask(segment)
    for m in _REDIR_RE.finditer(segment):
        if not redir_mask[m.start()]:
            targets.append(_unquote(m.group(1)))

    # 2. argv-shaped writers — tokenize; fall back silently if shlex chokes.
    #    Sem os redirecionamentos: eles já viraram alvo no passo 1, e deixá-los
    #    aqui faz o `tee` contar o operando de entrada como escrita.
    sem_redir = _strip_redirections(segment, redir_mask)
    try:
        argv = shlex.split(sem_redir, posix=True)
    except ValueError:
        argv = sem_redir.split()
    if not argv:
        return targets

    cmd = os.path.basename(argv[0])
    rest = argv[1:]
    nonflags = [t for t in rest if t and not _is_flag(t)]

    if cmd == "tee":
        # every non-flag arg is written (flags: -a/--append/-i…)
        targets.extend(nonflags)
    elif cmd == "sed":
        if any(t == "-i" or t.startswith("-i") or t == "--in-place"
               or t.startswith("--in-place") for t in rest):
            # in-place edits its file operands — everything after the script.
            # Heuristic: all non-flag args except the first (the sed program).
            if len(nonflags) >= 2:
                targets.extend(nonflags[1:])
            elif nonflags:
                targets.extend(nonflags)  # `sed -i'' file` form with no separate prog
    elif cmd in ("cp", "mv", "install"):
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])  # destination is the last operand
            if cmd == "mv":
                # `mv` DELETES its source(s) — that is a write on the origin
                # path too, not just the destination (P4, CS-5: renaming
                # counts as a write on both paths). `cp`/`install` only READ
                # their source, so they stay destination-only.
                targets.extend(nonflags[:-1])
    elif cmd == "dd":
        for t in rest:
            if t.startswith("of="):
                targets.append(t[3:])
    elif cmd == "git":
        # `git mv <src> <dst>` — move real de arquivo, que o path-lock precisa
        # governar como qualquer outra escrita. Estava só na cópia do docs
        # (structure-surgeon usa git mv para preservar histórico); as outras
        # quatro deixavam passar. Encontrado pelo detector de divergência.
        #
        # Origem E destino contam como escrita (P4, CS-5): `git mv` apaga o
        # caminho de origem tanto quanto cria o de destino — um slice travado
        # para escrever em domain/** que renomeia infrastructure/Foo.java para
        # domain/Foo.java "escreveu" fora da própria pista (removeu um arquivo
        # de infrastructure/), mesmo o destino sendo permitido. Checar só o
        # destino, como antes, deixava esse sentido passar batido.
        if len(nonflags) >= 3 and nonflags[0] == "mv":
            targets.extend(nonflags[1:])
        elif nonflags and nonflags[0] in ("checkout", "restore"):
            # `git checkout <ref> -- arquivo` e `git restore arquivo`
            # SOBRESCREVEM o arquivo no disco com a versão de outro lugar —
            # mesmo efeito do `git mv` acima, na mesma ferramenta já vigiada,
            # e era a forma mais fácil de reverter em silêncio um arquivo fora
            # da pista (achado do proof-reviewer, 26/08/2026).
            #
            # Sem `--`, o `checkout` é troca de branch: escreve muita coisa,
            # mas não é escrita dirigida a um caminho, e tratá-lo como alvo
            # transformaria todo `git checkout main` num bloqueio.
            if "--" in rest:
                targets.extend(t for t in rest[rest.index("--") + 1:]
                               if not _is_flag(t))
            elif nonflags[0] == "restore":
                targets.extend(nonflags[1:])
    elif cmd == "truncate":
        targets.extend(nonflags[1:] if nonflags else [])
    elif cmd in ("curl", "wget"):
        # Baixar para um arquivo é escrever nele. Achado do proof-reviewer em
        # 26/08/2026: `curl -o` e `wget -O` são estaticamente decidíveis — o
        # destino está explícito no argv — e mesmo assim passavam calados, nem
        # bloqueados nem registrados. A forma sem destino explícito (`curl -O`,
        # `wget <url>`, que gravam com o nome remoto no diretório corrente)
        # continua fora: ali o nome não está na linha de comando.
        destino = ("-o", "--output") if cmd == "curl" else ("-O", "--output-document")
        prefixos = tuple(f"{d}=" for d in destino if d.startswith("--"))
        for i, t in enumerate(rest):
            if t in destino and i + 1 < len(rest):
                targets.append(rest[i + 1])
            elif t.startswith(prefixos):
                targets.append(t.split("=", 1)[1])
    elif cmd == "touch":
        # Cria o arquivo se ele não existe: é escrita, mesmo com conteúdo vazio.
        targets.extend(nonflags)
    elif cmd == "rsync":
        # Como `cp`: lê a origem, escreve no último operando.
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])

    return targets


def extract_write_targets(command: str) -> tuple:
    """Return (targets, has_uncovered_construct)."""
    targets = []
    for seg in _split_segments(command):
        seg = seg.strip()
        if seg:
            targets.extend(_segment_targets(seg))
    # de-dup, drop pseudo-devices and fd dups
    clean = []
    seen = set()
    for t in targets:
        t = _unquote(t).strip()
        if not t or t in _PSEUDO or t.startswith("&") or t in seen:
            continue
        seen.add(t)
        clean.append(t)
    return clean, bool(_UNCOVERED_RE.search(_unquoted_view(command)))


def log_uncovered(command: str, agent: str) -> None:
    log_path = os.environ.get(
        "BASH_PATHLOCK_COVERAGE_LOG", "/tmp/docs-bash-pathlock-uncovered.log"
    )
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps({"agent": agent, "command": command[:500]}) + "\n")
    except OSError:
        pass


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[docs bash-path-lock] could not parse hook payload; allowing",
              file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    # Only act on THIS plugin's subagents. No prefix → main session or a
    # built-in agent → not ours. Same fail-open contract as path-lock.py.
    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" not in raw_agent_type or raw_agent_type.split(":", 1)[0] != PLUGIN_NAME:
        sys.exit(0)

    pl = _load_pathlock_module()
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    agent = pl.detect_agent(payload)
    allowed = pl.ALLOWED_WRITES.get(agent)

    targets, has_uncovered = extract_write_targets(command)
    if has_uncovered:
        log_uncovered(command, agent)

    if not targets:
        sys.exit(0)

    violations = []
    for t in targets:
        # Resolve against project root; out-of-tree targets are out of scope.
        cand = (project_root / t).resolve() if not os.path.isabs(t) else Path(t).resolve()
        try:
            cand.relative_to(project_root)
        except ValueError:
            continue  # /tmp, $HOME, etc. — not the path-lock's business
        cand_str = str(cand)
        if pl.is_own_expertise_file(cand_str, agent):
            continue
        if allowed and pl.path_matches(cand_str, allowed, project_root):
            continue
        violations.append(t)

    if not violations:
        sys.exit(0)

    allowed_disp = "\n  - ".join(allowed or ["(none — only own expertise file)"])
    print(
        f"[docs bash-path-lock] BLOCKED: agent {agent!r} attempted a "
        f"shell-level write to a path outside its allowlist via Bash.\n"
        f"  Offending target(s): {', '.join(violations)}\n"
        f"  Command: {command[:300]}\n"
        f"  Allowed write globs for {agent!r}:\n  - {allowed_disp}\n"
        f"  Writing artifacts via Bash (sed -i / cat > / tee / heredoc) bypasses "
        f"the path-lock — that is a delegation bypass, not a workaround.\n"
        f"  Use the Write tool (which the path-lock governs) for paths you own, "
        f"or delegate to the worker that owns this path.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
