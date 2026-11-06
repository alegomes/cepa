#!/usr/bin/env python3
"""Session chaining for the `cepa` launcher (CS-3 of the cepa-espiral-c1 cycle).

Runs AFTER the `claude` launched by `cepa` exits. If the session that just
exited left the next step recorded in
`<main-root>/.claude/sessions/<session_id>.next.json`:

    {"repo": "/abs/path", "mode": "discovery", "comando": "/common:epic x", "brief": "<text>"}

this script deletes the file, enters `repo` and replaces its own process with
`cepa` again, with `--mode <mode>` and the initial prompt. The prompt is the
brief alone; when the file carries a non-empty `comando` (optional, a string),
the prompt is `<comando>\n\n<brief>`, so the command is line 1 and the next
session runs it instead of relying on the brief to cite it. A missing, empty or
non-string `comando` never invalidates the file (old files have none). If the
file carries `intent` ({purpose, by_when, plan}; the old `intencao` with
proposito/para_quando/plano is also valid), `--purpose`, `--by-when` and
`--plan` go too (cepa records the session's intent);
without it, the next session is born without intent, never with the brief in
its place. The next session opens in the right repo and mode without the owner
typing anything. Without the file, it exits with the code it received and
nothing happens.

How the launcher knows which `<session_id>` is the one that just exited: it
only knows the `CEPA_LAUNCH_ID` it generated. The `session-registry` hook, at
SessionStart, notes each `session_id` born from that opening in
`<main-root>/.claude/sessions/<launch_id>.launch`, one per line (a `/clear`
opens another `session_id` in the same process). Here the most recent one that
left a `.next.json` wins.

Usage: session-chain.py <launch_id> <cepa> <rc>
Output: exec of `cepa` (chained), or exit <rc> (nothing to chain, or invalid
file, which stays in place for the owner to see).
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402
try:
    from _modes import normalize_mode as _normalize_mode
except Exception:  # noqa: BLE001 — chaining never breaks because of the table
    def _normalize_mode(v):
        return v


def breadcrumb_path(root: str, launch_id: str):
    return L.sessions_dir(root) / f"{launch_id}.launch"


def next_path(root: str, session_id: str):
    return L.sessions_dir(root) / f"{session_id}.next.json"


def main() -> int:
    if len(sys.argv) != 4:
        return 0
    launch_id, cepa, rc_s = sys.argv[1:]
    try:
        rc = int(rc_s)
    except ValueError:
        rc = 0
    if os.environ.get("CEPA_ENCADEAR", "on") == "off" or not launch_id:
        return rc
    root = L.main_root(os.getcwd())
    if not root:
        return rc

    crumb = breadcrumb_path(root, launch_id)
    try:
        sids = [s.strip() for s in crumb.read_text(encoding="utf-8").splitlines() if s.strip()]
    except OSError:
        return rc
    try:
        crumb.unlink()
    except OSError:
        pass

    nxt = next((next_path(root, s) for s in reversed(sids) if next_path(root, s).exists()), None)
    if nxt is None:
        return rc

    try:
        spec = json.loads(nxt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"✗ cepa: próximo passo ilegível em {nxt} ({e}); não encadeei", file=sys.stderr)
        return rc
    repo = spec.get("repo") if isinstance(spec, dict) else None
    # `mode` (or the old `modo`); the old value (`descoberta`) becomes the new one
    mode = (spec.get("mode") or spec.get("modo")) if isinstance(spec, dict) else None
    if isinstance(mode, str):
        mode = _normalize_mode(mode)
    brief = spec.get("brief") if isinstance(spec, dict) else None
    if not (isinstance(repo, str) and os.path.isdir(repo)
            and isinstance(mode, str) and mode
            and isinstance(brief, str) and brief.strip()):
        print(f"✗ cepa: próximo passo inválido em {nxt} (precisa de repo existente, "
              f"modo e brief); não encadeei", file=sys.stderr)
        return rc

    try:
        nxt.unlink()
    except OSError:
        pass
    comando = spec.get("comando")
    prompt = brief
    if isinstance(comando, str) and comando.strip():
        prompt = f"{comando.strip()}\n\n{brief}"
    # The registry entry of the session that left carries `cepa`'s pid (the
    # claim is written with it), which is this process. Without SessionEnd, it
    # would look like a live session in the tree and the next opening would
    # isolate itself in a worktree for nothing.
    for f, e in L.read_entries(root):
        if e.get("pid") == os.getpid() and e.get("hostname") in (None, L.host()):
            try:
                f.unlink()
            except OSError:
                pass
    print(f"↻ cepa: próxima sessão em {repo} (modo {mode}) — CEPA_ENCADEAR=off desliga",
          file=sys.stderr)
    os.chdir(repo)
    os.execv(cepa, [cepa, "--mode", mode, *intent_args(spec.get("intent") or spec.get("intencao"), nxt), prompt])
    return rc  # unreachable


def intent_args(it, nxt) -> list:
    """`cepa` flags that record the next session's intent. Only with all three
    parts written for it; the brief talks about the session that left and does
    not become purpose."""
    if it is None:
        return []
    plan = (it.get("plan") or it.get("plano")) if isinstance(it, dict) else None
    texts = ([it.get("purpose") or it.get("proposito"), it.get("by_when") or it.get("para_quando")]
              if isinstance(it, dict) else [])
    if not (len(texts) == 2 and all(isinstance(t, str) and t.strip() for t in texts)
            and isinstance(plan, list) and plan
            and all(isinstance(i, str) and i.strip() and "\n" not in i for i in plan)):
        print(f"⚠ cepa: intenção inválida em {nxt}; a sessão seguinte abre sem ela",
              file=sys.stderr)
        return []
    return ["--purpose", texts[0], "--by-when", texts[1], "--plan", "\n".join(plan)]


if __name__ == "__main__":
    sys.exit(main())
