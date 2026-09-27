#!/usr/bin/env python3
"""PostToolUse hook: mark .claude/last-build.json as STALE after source edits.

Fires after Edit / Write / MultiEdit on production code (source files,
build/dependency files, migrations) — and after a Bash command that writes one
(`sed -i`, heredoc or `>` into a file, `tee`, `cp`, `mv`...), read by
`_shellscan.edited_paths`. Without the Bash half, a session editing by `sed`
(what autonomous mode prefers) left a green baseline describing code that no
longer existed. Records the path + timestamp + the
previous known-good status (if any). The /common:green-or-revert skill
reads this file and the PreToolUse gate-advance hook blocks "wrap-up"
operations until verify confirms green.

Never blocks. Failures are stderr-only.

What counts as source:
  - JVM/JS/Python/Go/Rust/etc. by extension (allowlist below).
  - Build/dependency manifests (pom.xml, build.gradle, package.json, ...).
  - Database migrations under db/, migrations/, **/V*__*.sql.

What does NOT count:
  - Docs (.md, .rst, .txt).
  - Spec files under specs/, spec/.
  - .claude/** plumbing.
  - Test sources (changes there don't invalidate "is the production code
    working" — they extend coverage. We could gate this differently if
    needed; for v1, conservative skip.)

The heuristic itself (`is_source`, the extension/manifest/exclusion lists)
lives in `_buildsource.py` — shared with `maven-reactor-guard.py`, which asks
the same question ("does this path count as source?") over a timestamp
instead of an Edit/Write event. See that module's docstring for why.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _wtlib as L  # noqa: E402
import _shellscan as S  # noqa: E402
import _buildsource as B  # noqa: E402


is_source = B.is_source


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[mark-build-stale] could not parse hook payload; skipping", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name", "") not in {*S.WRITE_TOOLS, "Bash"}:
        sys.exit(0)

    # RAIZ da worktree, não o diretório corrente: o cwd do Bash persiste
    # entre chamadas, e um `cd subdir` desviaria o estado desta sessão
    # para `subdir/.claude/` pelo resto dela (ver _wtlib.session_root).
    cwd = Path(L.session_root(payload.get("cwd") or os.getcwd())).resolve()

    rel = None
    for edited in S.edited_paths(payload):
        try:
            candidate = str(Path(edited).resolve().relative_to(cwd))
        except ValueError:
            # Edit landed OUTSIDE the session tree — e.g. a proof worktree
            # perturbation in /tmp. It does not invalidate THIS project's
            # build; marking the main baseline STALE for it poisons the
            # advance gate (and the bare relative_to() used to crash here).
            continue
        # A barra na frente: os fragmentos excluídos (`/tests/`, `/specs/`)
        # pedem um separador antes, e o caminho relativo à raiz não tem —
        # `tests/test_x.py` virava código de produção.
        if is_source("/" + candidate):
            rel = candidate
            break
    if rel is None:
        sys.exit(0)

    state_path = cwd / ".claude" / "last-build.json"

    previous = {}
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}

    # `last_known_*` é a última execução REAL. Uma edição sobre um STALE
    # herda a linhagem dele: copiar `status: STALE` apagava o EMPTY de origem
    # na segunda edição, e o acceptance-gate/cepa-plan finish liberavam o card.
    if str(previous.get("status", "")).upper() == "STALE":
        last = {
            "status": previous.get("last_known_status", "UNKNOWN"),
            "at": previous.get("last_known_at"),
            "command": previous.get("last_known_command"),
        }
    else:
        last = previous
    new_state = {
        "status": "STALE",
        "since": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "after_edit_to": rel,
        "last_known_status": last.get("status", "UNKNOWN"),
        "last_known_at": last.get("at"),
        "last_known_command": last.get("command"),
    }

    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[mark-build-stale] could not write {state_path}: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
