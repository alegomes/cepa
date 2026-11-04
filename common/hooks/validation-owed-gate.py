#!/usr/bin/env python3
"""Stop hook (common) — the session does not end its turn owing a validation.

WHY THIS EXISTS
---------------
On 2026-11-02 a session built WEGO-2416 and WEGO-2012, recorded the evidence,
and left both items `pending`: `cepa-plan finish --status done` refuses an item
of a build-hex/build-team queue without the validation-lead verdict in
`docs/validation/<id>.yaml`. The gate held. The session then ended its turn
asking the owner "do I run the validator now?", and the two items waited for
the next unattended run (fb-20261103-1). The owner decided that a built item
is validated in the same session, without a question.

MECHANISM
---------
`cepa-plan finish` leaves a marker in
`~/.claude/cepa-validation-owed/<session-id>/<queue>__<item>.json` when it
refuses `done` for lack of the verdict, or when it returns the item to
`pending` without one. `done` or `blocked` on the item removes it. This hook
reads the folder of the session that is stopping:

  - no marker                          -> allow
  - marker, and the verdict file now
    exists in the marker's repo        -> block: the verdict is there, close
                                          the item with `finish --status done`
  - marker, no verdict                 -> block: delegate to validation-lead,
                                          or close `blocked` with the reason,
                                          or delete the marker if the item was
                                          never built
  - `stop_hook_active` (the turn was
    already continued by a Stop hook)  -> allow, so it never loops

Fails open: unreadable input, no session id, unreadable marker -> allow.
Turned off with CEPA_MODO=off.
"""

import json
import os
import re
import sys
from pathlib import Path


def owed_dir(session_id):
    home = Path(os.environ.get("HOME", str(Path.home())))
    return (home / ".claude" / "cepa-validation-owed"
            / re.sub(r"[^A-Za-z0-9._-]", "_", session_id))


def verdict_exists(repo, ident):
    root = Path(repo)
    return ((root / "docs" / "validation" / f"{ident}.yaml").exists()
            or (root / ".claude" / "validation" / f"{ident}.yaml").exists())


def owed(session_id):
    folder = owed_dir(session_id)
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("queue") and d.get("item"):
            found.append((path, d))
    return found


def message(entries):
    lines = ["Esta sessão está terminando o turno com item construído e sem "
             "o veredito do validation-lead. Não pergunte ao dono se roda o "
             "validador: rode agora.", ""]
    for path, d in entries:
        q, i, repo = d["queue"], d["item"], d.get("repo") or "."
        if verdict_exists(repo, i):
            lines.append(f"- {i} (fila {q}): o veredito já está em "
                         f"{repo}/docs/validation/{i}.yaml. Feche com "
                         f"`cepa-plan finish {q} {i} --status done --evidence "
                         f"\"...\" --repo {repo} --commit`.")
        else:
            lines.append(f"- {i} (fila {q}): delegue ao validation-lead, que "
                         f"grava {repo}/docs/validation/{i}.yaml, e feche com "
                         f"`cepa-plan finish {q} {i} --status done`. Se o "
                         "validador não puder rodar, feche como `blocked` com "
                         "o motivo. Se o item não foi construído nesta "
                         f"sessão, apague {path}.")
    return "\n".join(lines)


def main():
    if os.environ.get("CEPA_MODO", "").lower() == "off":
        return 0
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict) or data.get("stop_hook_active"):
        return 0
    sid = str(data.get("session_id") or "")
    if not sid:
        return 0
    entries = owed(sid)
    if not entries:
        return 0
    print(json.dumps({"decision": "block", "reason": message(entries)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
