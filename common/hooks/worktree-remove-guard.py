#!/usr/bin/env python3
"""PreToolUse hook (common) — `git worktree remove` / `git branch -D|-d` cru
não derruba o chão de OUTRA sessão viva. Bloqueia.

WHY THIS EXISTS
---------------
`worktree-guard.py` responde bem à pergunta "alguma sessão viva segura este
worktree/branch?", mas só os comandos em markdown (`worktree-merge`, `wrap-up`)
o chamam. Quem roda git direto passa por fora. Foi o que aconteceu em
2026-08-17 no wego-acesso-backend: uma sessão fazendo faxina rodou
`git worktree remove <worktree-de-outra> && git branch -D session/prove_...`
com a dona ainda viva dentro dele. A vítima perdeu o cwd (todo hook passou a
falhar com `ENOENT ... posix_spawn '/bin/sh'`), nenhum resgate de artefatos
rodou, e o `-D` teria apagado commit não mesclado sem aviso.

Este hook leva a mesma pergunta para o ponto onde o dano acontece: o comando
Bash. A lógica de vida/dono é do `_wtlib` (`live_sessions_in`, `branch_owners`,
`entry_is_live`); aqui só se lê a linha de comando e se decide o alvo.

A sessão que chama é excluída pelo SEU `session_id` (o do payload), NUNCA pelo
cwd. Episódio `fb-20261013-1` (2026-10-13): o `--exclude-cwd` do guard em CLI
sumia com uma segunda sessão viva que estava no mesmo diretório, e o guard
respondeu OK quando não devia. Sem `session_id` no payload, nada é excluído.

ESCOPO
------
Só segmentos cujo comando é de fato `git` (basename do argv[0], atrás de prefixo
de env, `-C X`, `-c k=v`); `echo "git worktree remove"` e `grep` são texto.
  - `git worktree remove [-f] <caminho|nome>`: protege as sessões vivas com cwd
    naquele worktree E as que estão no branch dele. O alvo é resolvido contra o
    diretório do segmento (`cd X &&`, `git -C X`); se não bater com nenhum
    worktree, um nome sem `/` casa com o basename de um worktree (o nome do slice).
  - `git branch -d|-D|--delete [--force] <nome>...`: protege as sessões vivas no
    branch. `-r` (remote-tracking) e listagem não entram.
Fora do escopo: subshell `( git branch -D x )` e strings de `bash -c "git ..."` /
`sh -c` não são varridas (limite da leitura textual, o mesmo dos hooks irmãos).
Sessão morta (pid ausente ou >24h) nunca bloqueia: isso é do `entry_is_live`.
Falha aberto: payload ilegível, fora de repo git, aspas que não fecham.

Exit codes:
  0 — liberado
  2 — bloqueado: há sessão viva de outra janela no alvo
"""

import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _telemetry as T
except Exception:  # telemetria nunca pode quebrar o gate

    class T:  # type: ignore
        @staticmethod
        def emit(*a, **k):
            pass


import _shellscan as S  # noqa: E402
import _wtlib as L  # noqa: E402

_GIT_FLAGS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
_WRAPPERS = {"env", "command", "sudo", "nice", "time"}


def _is_env_assign(tok: str) -> bool:
    name, eq, _ = tok.partition("=")
    return bool(eq) and name.replace("_", "a").isalnum() and not name[0].isdigit()


def git_args(segment: str):
    """Argv do git depois das opções globais (`-C X`, `-c k=v`, ...), ou None
    quando o segmento não executa git."""
    try:
        toks = shlex.split(segment, posix=True)
    except ValueError:
        return None  # fail open
    i = 0
    while i < len(toks) and (_is_env_assign(toks[i]) or toks[i] in _WRAPPERS):
        i += 1
    if i >= len(toks) or os.path.basename(toks[i]) != "git":
        return None
    i += 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 2 if toks[i] in _GIT_FLAGS_WITH_VALUE else 1
    return toks[i:]


def _is_delete_cluster(tok: str) -> bool:
    """`-d`, `-D`, `-df`, `-fd`, `-Df`... (cluster curto com d/D, sem r)."""
    if not tok.startswith("-") or tok.startswith("--") or len(tok) < 2:
        return False
    letters = tok[1:]
    return set(letters) <= set("dDfq") and ("d" in letters or "D" in letters)


def targets_of(args):
    """`("worktree", [nome|caminho])`, `("branch", [nomes])` ou None."""
    if not args:
        return None
    if args[0] == "worktree" and len(args) > 1 and args[1] == "remove":
        pos = [a for a in args[2:] if not a.startswith("-")]
        return ("worktree", pos[:1])
    if args[0] == "branch":
        rest = args[1:]
        if any(a in ("-r", "--remotes") for a in rest):
            return None
        deleting = any(a == "--delete" or _is_delete_cluster(a) for a in rest)
        if not deleting:
            return None
        return ("branch", [a for a in rest if not a.startswith("-")])
    return None


def find_worktree(root: str, name: str, seg_dir: str):
    trees = L.list_worktrees(root)
    cand = os.path.normpath(os.path.join(seg_dir, os.path.expanduser(name)))
    for t in trees:
        if L.same_path(t["path"], cand):
            return t
    if "/" not in name:
        for t in trees[1:]:  # [0] é o worktree principal: nunca por nome
            if os.path.basename(t["path"].rstrip("/")) == name:
                return t
    return None


def _foreign(entries, sid):
    """Tira a sessão que chama — pela chave de sessão, nunca pelo cwd."""
    if not sid:
        return list(entries)
    return [e for e in entries if e.get("session_id") != sid]


def owners_of(root, sid, tree=None, branches=()):
    """Entradas vivas de OUTRAS sessões no worktree `tree` e/ou nos `branches`."""
    found, seen = [], set()
    pool = []
    if tree is not None:
        pool += L.live_sessions_in(root, tree["path"], exclude_key=sid)
    for b in branches:
        if b:
            pool += L.branch_owners(root, b)
    for e in _foreign(pool, sid):
        k = (e.get("session_id"), e.get("pid"), e.get("cwd"))
        if k not in seen:
            seen.add(k)
            found.append(e)
    return found


def describe(e):
    return (f"{e.get('hostname', '?')}:{e.get('cwd', '?')} "
            f"(sessão {str(e.get('session_id', '?'))[:8]}, pid {e.get('pid', '?')}, "
            f"ativa há {L.age_str(e.get('last_seen') or e.get('started_at'))})")


def find_offences(command, cwd, sid):
    out = []
    for seg, seg_dir, _ in S.segment_dirs(command, cwd):
        t = targets_of(git_args(seg))
        if not t:
            continue
        root = L.main_root(seg_dir)
        if not root:
            continue
        kind, names = t
        if kind == "worktree":
            for n in names:
                wt = find_worktree(root, n, seg_dir)
                if wt is None:
                    continue
                own = owners_of(root, sid, tree=wt, branches=[wt.get("branch")])
                if own:
                    out.append((seg, f"worktree {wt['path']}"
                                + (f" (branch {wt['branch']})" if wt.get("branch") else ""),
                                own, os.path.basename(wt["path"].rstrip("/"))))
        else:
            for b in names:
                own = owners_of(root, sid, branches=[b])
                if own:
                    out.append((seg, f"branch {b}", own, b.split("/")[-1]))
    return out


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[worktree-remove-guard] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        sys.exit(0)
    command = (payload.get("tool_input") or {}).get("command", "") or ""
    if not command or "git" not in command:
        sys.exit(0)
    cwd = payload.get("cwd") or os.getcwd()
    sid = payload.get("session_id") or ""

    try:
        offences = find_offences(command, cwd, sid)
    except Exception:  # um bug aqui nunca pode travar o Bash
        sys.exit(0)
    if not offences:
        T.emit("worktree_remove_allow", cwd=str(cwd))
        sys.exit(0)

    seg, target, owners, slice_name = offences[0]
    T.emit("worktree_remove_block", cwd=str(cwd), segment=seg, target=target)
    lines = ["[worktree-remove-guard] BLOQUEADO: há sessão viva de outra janela no alvo.",
             f"  Comando: {seg}",
             f"  Alvo: {target}",
             "  Dona(s):"]
    lines += [f"    - {describe(e)}" for e in owners]
    if len(offences) > 1:
        lines.append("  Outros trechos do comando também esbarram em sessão viva:")
        lines += [f"    - {s}  →  {t}" for s, t, _, _ in offences[1:]]
    lines += [
        "",
        "  Remover isso derruba o diretório debaixo dela: todo hook dela passa a falhar",
        "  com ENOENT e nenhum resgate de artefatos roda (incidente de 2026-08-17).",
        f"  Saída: `/common:worktree-merge {slice_name}` para aterrissar o trabalho dela,",
        f"  `/common:worktree-discard {slice_name}` para descartar — ou peça à outra",
        "  janela que encerre. Worktree de outra janela não é sua para remover.",
    ]
    print("\n".join(lines), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
