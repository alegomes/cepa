#!/usr/bin/env python3
"""Tests for the mode menu section of `cepa-metrics` (CS-8 of modos-opinativos).

The session-mode hook records `mode_menu.shown` when the opening turn shows the
mode menu and `mode_menu.chosen` when the next reply picks one of its actions
(CS-7). This report is what turns those two events into the number the spec
asked for: per mode, choices ÷ showings, with the arithmetic in the line, so the
owner can decide whether the turn the menu costs at every opening pays for itself
(docs/spec/modos-opinativos.md, "Riscos").

The ledger is a throwaway directory (CEPA_TELEMETRY_DIR); the expected values
were counted by hand over it.

Run: python3 tests/test_cepa_metrics_mode_menu.py
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
METRICS = REPO / "common" / "bin" / "cepa-metrics"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def write_ledger(tmp, events):
    base = datetime.now(timezone.utc) - timedelta(days=1)
    lines = []
    for i, e in enumerate(events):
        lines.append(json.dumps({"ts": (base + timedelta(minutes=i)).isoformat(),
                                 "repo": "cepa", **e}))
    (Path(tmp) / f"events-{base.strftime('%Y-%m')}.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def run(tmp, *args):
    env = {**os.environ, "CEPA_TELEMETRY_DIR": tmp}
    return subprocess.run([sys.executable, str(METRICS), *args], capture_output=True,
                          text=True, env=env, timeout=60)


def section(out, title):
    """The lines of the report section that starts with `## <title>`."""
    lines = out.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and title in ln:
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith("## "):
                    break
                body.append(nxt)
            return body
    return None


def test_menu_rate_per_mode():
    """The declared red test: 4 showings and 1 choice of discovery give the
    discovery line with "1 ÷ 4 = 25%". Construction (2 shown, 2 chosen) is there
    so the count is per mode, not one total; exploration was shown and never
    chosen, and must say 0, not disappear."""
    with tempfile.TemporaryDirectory() as tmp:
        ev = [{"event": "mode_menu.shown", "mode": "discovery"} for _ in range(4)]
        ev.append({"event": "mode_menu.chosen", "mode": "discovery", "action": 1,
                   "command": "/common:spec"})
        ev += [{"event": "mode_menu.shown", "mode": "construction"} for _ in range(2)]
        ev += [{"event": "mode_menu.chosen", "mode": "construction", "action": 2,
                "command": "/common:drain-plan"} for _ in range(2)]
        ev.append({"event": "mode_menu.shown", "mode": "exploration"})
        ev.append({"event": "session_start"})
        write_ledger(tmp, ev)
        r = run(tmp)
        check("cepa-metrics exits 0", r.returncode == 0, r.stderr[-400:])
        body = section(r.stdout, "Menu do modo")
        check("the report has a mode menu section", body is not None, r.stdout[-1500:])
        body = body or []
        disc = [ln for ln in body if ln.strip().startswith("discovery")]
        check("discovery line carries 1 ÷ 4 = 25%",
              len(disc) == 1 and "1 ÷ 4 = 25%" in disc[0], "\n".join(body))
        cons = [ln for ln in body if ln.strip().startswith("construction")]
        check("construction line carries 2 ÷ 2 = 100%",
              len(cons) == 1 and "2 ÷ 2 = 100%" in cons[0], "\n".join(body))
        expl = [ln for ln in body if ln.strip().startswith("exploration")]
        check("exploration shown and never chosen says 0 ÷ 1 = 0%",
              len(expl) == 1 and "0 ÷ 1 = 0%" in expl[0], "\n".join(body))
        check("the section explains the calculation",
              any("memória de cálculo" in ln for ln in body), "\n".join(body))
        custom = section(r.stdout, "Eventos custom") or []
        check("menu events are not listed again as custom events",
              not any("mode_menu" in ln for ln in custom), "\n".join(custom))


def test_menu_json():
    with tempfile.TemporaryDirectory() as tmp:
        ev = [{"event": "mode_menu.shown", "mode": "discovery"} for _ in range(4)]
        ev.append({"event": "mode_menu.chosen", "mode": "discovery", "action": 1,
                   "command": "/common:spec"})
        write_ledger(tmp, ev)
        r = run(tmp, "--json")
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            data = {}
        menu = data.get("mode_menu", {})
        check("--json carries mode_menu per mode",
              menu.get("discovery", {}).get("shown") == 4
              and menu.get("discovery", {}).get("chosen") == 1, r.stdout[-800:])
        check("--json does not list menu events as custom",
              "mode_menu.shown" not in data.get("custom_events", {}), r.stdout[-800:])


def test_choice_without_showing_in_the_window():
    """A choice whose showing fell before the window start (the reply came right
    at the window edge) has no denominator: the line says so
    instead of dividing by zero or printing a rate over 100%."""
    with tempfile.TemporaryDirectory() as tmp:
        write_ledger(tmp, [{"event": "mode_menu.chosen", "mode": "discovery",
                            "action": 1, "command": "/common:spec"}])
        r = run(tmp)
        check("choice without showing exits 0", r.returncode == 0, r.stderr[-400:])
        body = section(r.stdout, "Menu do modo") or []
        disc = [ln for ln in body if ln.strip().startswith("discovery")]
        check("choice without showing says there is no showing",
              len(disc) == 1 and "sem exibição" in disc[0], "\n".join(body))


def test_no_menu_events_no_section():
    with tempfile.TemporaryDirectory() as tmp:
        write_ledger(tmp, [{"event": "session_start"}])
        r = run(tmp)
        check("without menu events there is no menu section",
              section(r.stdout, "Menu do modo") is None, r.stdout[-800:])


def main():
    for fn in (test_menu_rate_per_mode, test_menu_json,
               test_choice_without_showing_in_the_window, test_no_menu_events_no_section):
        fn()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
