#!/usr/bin/env python3
"""Stop hook: blocks "Safe to `exit`" while the MAIN clone is dirty.

Reason (fb-20261105-3, 2026-11-05): `/common:wrap-up` closed with "Safe to
exit" with `.claude/queues/WEGO/queue.yaml` modified and uncommitted in the
main clone, and `cepa-until` refused to start there right after. The two rules
contradicted each other in the owner's daily sequence. The definition of dirt
is the one `cepa-until` uses (`_dirt.py`).

Modes:
  (Stop payload on stdin)  -- if the last assistant text says "Safe to exit"
                              and the main clone is dirty, block once and name
                              the files. `stop_hook_active` = already blocked
                              once: let it through (anti-loop).
  --check <repo>           -- print the classification; exit 0 clean / 1 dirty.
  --exclude <repo>         -- add the untracked runtime files to
                              .git/info/exclude; exit 0 if clean afterwards.
"""

import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _dirt  # noqa: E402
import _wtlib  # noqa: E402

SAFE_EXIT = re.compile(r"Safe to\s+`?exit`?", re.I)
SELF = Path(__file__).resolve()


def _t_emit(event, cwd=None, **fields):
    """Minimal mirror of _telemetry.py; strictly fail-silent."""
    try:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "repo": Path(_wtlib.main_root(cwd or os.getcwd())).name}
        entry.update(fields)
        tdir = Path(os.environ.get("CEPA_TELEMETRY_DIR") or (Path.home() / ".claude" / "cepa-telemetry"))
        tdir.mkdir(parents=True, exist_ok=True)
        with open(tdir / f"events-{entry['ts'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def read_rows(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except Exception:
        return []


def last_assistant_text(rows):
    for row in reversed(rows):
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        content = (row.get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
            if text.strip():
                return text
    return ""


def _shown(paths, n=12):
    s = "\n".join(f"  - {p}" for p in paths[:n])
    return s + (f"\n  ... e mais {len(paths) - n}" if len(paths) > n else "")


def build_reason(main, c):
    parts = [f"O clone principal `{main}` está sujo: dizer \"Safe to exit\" está "
             "recusado enquanto o `cepa-until` se recusaria a largar nele "
             "(mesma definição de sujeira)."]
    if c["tracked"]:
        paths = " ".join(shlex.quote(p) for p in c["tracked"])
        q = shlex.quote(str(main))
        parts.append(f"Arquivos versionados alterados ({len(c['tracked'])}):\n"
                     f"{_shown(c['tracked'])}\nUm commit só deles, ANTES de repetir o relatório:\n"
                     f"git -C {q} add -u -- {paths} && git -C {q} commit -m "
                     f"\"wrap-up: estado do harness ({len(c['tracked'])} arquivo(s))\"")
    if c["runtime"]:
        parts.append(f"Estado de runtime dos hooks, não versionado ({len(c['runtime'])}):\n"
                     f"{_shown(c['runtime'])}\nIgnore-os:\n"
                     f"python3 \"${{CLAUDE_PLUGIN_ROOT}}/hooks/safe-exit-gate.py\" --exclude {shlex.quote(str(main))}")
    if c["untracked"]:
        parts.append(f"Arquivos novos sem versão ({len(c['untracked'])}):\n"
                     f"{_shown(c['untracked'])}\nCada um é trabalho desta sessão "
                     "(commite por caminho) ou lixo (remova); nenhum some em silêncio.")
    parts.append("Com o clone limpo, reemita o mesmo relatório final.")
    return "\n\n".join(parts)


def on_stop(payload):
    rows = read_rows(payload.get("transcript_path") or "")
    if not SAFE_EXIT.search(last_assistant_text(rows)):
        return None
    cwd = payload.get("cwd") or os.getcwd()
    main = _wtlib.main_root(cwd)
    c = _dirt.classify(main)
    if not c or not any(c.values()):
        return None
    n = sum(len(v) for v in c.values())
    block = not payload.get("stop_hook_active")
    _t_emit("safe_exit_gate", cwd=cwd, sujos=n, bloqueou=block)
    return build_reason(main, c) if block else None


def cli(mode, repo):
    c = _dirt.classify(repo)
    if c is None:
        print(f"não consegui ler o git em {repo}")
        return 1
    if mode == "--exclude":
        added = _dirt.exclude_runtime(repo, c["runtime"])
        print("padrões adicionados a .git/info/exclude: " + (", ".join(added) or "nenhum"))
        c = _dirt.classify(repo) or c
    labels = (("tracked", "versionados alterados (commit próprio)"),
              ("runtime", "runtime dos hooks (--exclude)"),
              ("untracked", "novos sem versão (commitar por caminho ou remover)"))
    for key, label in labels:
        print(f"{label}: " + ("limpo" if not c[key] else ""))
        for p in c[key]:
            print(f"  - {p}")
    return 1 if any(c.values()) else 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] in ("--check", "--exclude"):
        sys.exit(cli(sys.argv[1], sys.argv[2]))
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if payload.get("hook_event_name", "Stop") == "Stop":
            reason = on_stop(payload)
            if reason:
                print(json.dumps({"decision": "block", "reason": reason},
                                 ensure_ascii=False))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
