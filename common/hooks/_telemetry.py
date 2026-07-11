#!/usr/bin/env python3
"""Cepa telemetry — append-only event ledger for the harness itself.

The harness audits cards, builds, and proofs, but until now collected nothing
about its OWN behavior: how often gates block (and whether legitimately), how
builds trend per repo, which proof verdicts dominate, how sessions start and
end. Every improvement was anecdotal. This module closes the loop.

Design:
  - One JSONL file per month at ~/.claude/cepa-telemetry/events-YYYY-MM.jsonl
    (global, cross-project — the interesting questions span repos).
  - Every event: {"ts": ISO-UTC, "event": str, "repo": str|None, ...fields}.
    `repo` is the basename of the git root when resolvable from cwd.
  - Strictly fail-silent as a library: telemetry must NEVER break a hook or a
    gate. Any error is swallowed (stderr note only under CEPA_TELEMETRY_DEBUG=1).
  - No PII / no payloads: events carry categories, statuses, and short labels —
    never command lines, file contents, or Jira descriptions.

Library use (from other hooks):
    import _telemetry as T
    T.emit("gate_block", tier="sharing", status="FAILURE")

CLI use (from commands / skills that want to log an outcome):
    python3 _telemetry.py emit drain_done cards=5 outcome=ok
    (values are strings; ints parse when they look like ints)

Aggregation lives in bin/cepa-metrics; this module only writes.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

TELEMETRY_DIR = Path(os.environ.get("CEPA_TELEMETRY_DIR", "")) if os.environ.get(
    "CEPA_TELEMETRY_DIR"
) else Path.home() / ".claude" / "cepa-telemetry"


def _debug(msg: str) -> None:
    if os.environ.get("CEPA_TELEMETRY_DEBUG") == "1":
        print(f"[cepa-telemetry] {msg}", file=sys.stderr)


def _repo_name(cwd: str = None) -> str:
    """Basename of the git main root for cwd, or the cwd basename. Best-effort."""
    try:
        d = cwd or os.getcwd()
        out = subprocess.run(
            ["git", "-C", d, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            common = out.stdout.strip()
            if common.endswith("/.git"):
                return Path(common).parent.name
            return Path(common).name  # bare/odd layouts: better than nothing
        return Path(d).name
    except Exception:
        return ""


def emit(event: str, cwd: str = None, **fields) -> None:
    """Append one event. Fail-silent by contract — never raises."""
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "repo": _repo_name(cwd),
        }
        # Keep values JSON-safe and short; telemetry is categories, not payloads.
        for k, v in fields.items():
            if isinstance(v, str) and len(v) > 200:
                v = v[:200]
            entry[k] = v
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        fname = TELEMETRY_DIR / f"events-{entry['ts'][:7]}.jsonl"
        with open(fname, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # noqa: BLE001 — fail-silent is the contract
        _debug(f"emit failed: {e}")


def _parse_val(raw: str):
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return int(raw)
    return raw


def main(argv):
    if len(argv) < 2 or argv[0] != "emit":
        print("usage: _telemetry.py emit <event> [key=value ...]", file=sys.stderr)
        return 1
    event = argv[1]
    fields = {}
    for pair in argv[2:]:
        if "=" in pair:
            k, _, v = pair.partition("=")
            fields[k] = _parse_val(v)
    emit(event, **fields)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
