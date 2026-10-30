#!/usr/bin/env python3
"""Regression tests for the deterministic cores of /maestro:run (step 3).

Covers maestro-fork-settings (layer 1), maestro-poll (event loop 2a) and
maestro-wave-state (state/recovery 2c). No deps beyond PyYAML.
Run: python3 tests/test_maestro_run_colors.py
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "maestro" / "bin"
FAILS = []


def sh(argv, **kw):
    return subprocess.run([sys.executable] + [str(x) for x in argv],
                          capture_output=True, text=True, **kw)


def check(name, cond, detail=""):
    print(("  ok  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILS.append(name)


PLAN = """\
schema_version: 1
program: t
waves:
  - id: 1
    slices: [S1, S2]
    status: pending
slices:
  S1:
    demanda: A
    surface: ["src/a.py", "docs/*.md"]
    bash_extra: ["./run-x.sh"]
    timeout_min: 30
  S2:
    demanda: B
    surface: ["src/b.py"]
"""


def test_fork_settings(tmp):
    plan = Path(tmp) / "plan.yaml"
    plan.write_text(PLAN)
    r = sh([BIN / "maestro-fork-settings", plan, "S1", "--port", "9001"])
    check("fork-settings emite JSON válido", r.returncode == 0, r.stderr)
    s = json.loads(r.stdout)
    perms = s["permissions"]
    check("allow inclui a superfície declarada",
          "Edit(src/a.py)" in perms["allow"] and "Edit(docs/*.md)" in perms["allow"],
          perms["allow"])
    check("allow inclui bash_extra do slice",
          "Bash(./run-x.sh:*)" in perms["allow"], perms["allow"])
    check("ACHADO DO SPIKE: ask catch-all roteia ao porteiro",
          set(["Bash", "Write", "Edit"]).issubset(set(perms["ask"])), perms["ask"])
    check("deny cobre a zona de enforcement",
          any("hooks/**" in d for d in perms["deny"]) and
          any(".claude/settings.json" in d for d in perms["deny"]), perms["deny"])
    # WEGO-paralelo regression 2026-08-24: Claude Code REFUSES a Write(path) rule
    # ("only Edit(path) rules are matched"); Edit(path) already covers every write.
    check("nenhuma regra Write(path) — só Edit(path) é aceita",
          not [x for x in perms["allow"] + perms["deny"] if x.startswith("Write(")],
          perms["allow"] + perms["deny"])
    # Regression of the SAME wave: mcpServers in settings.json is ignored — the daughter
    # started without the gatekeeper's tool and died with exit 1 at launch.
    check("settings.json NÃO declara mcpServers (não é lido para MCP)",
          "mcpServers" not in s, list(s))
    rm = sh([BIN / "maestro-fork-settings", plan, "S1", "--port", "9001",
             "--emit", "mcp"])
    m = json.loads(rm.stdout)
    check("identidade do slice vai na URL do porteiro (achado spike)",
          "slice=S1" in m["mcpServers"]["gatekeeper"]["url"], m)
    wt = Path(tmp) / "wt"
    wt.mkdir()
    rw = sh([BIN / "maestro-fork-settings", plan, "S1", "--port", "9001",
             "--out-dir", wt])
    check("--out-dir grava o PAR settings.json + .mcp.json no worktree",
          rw.returncode == 0 and (wt / ".claude" / "settings.json").is_file()
          and (wt / ".mcp.json").is_file(), rw.stdout + rw.stderr)
    r2 = sh([BIN / "maestro-fork-settings", plan, "NAO-EXISTE"])
    check("slice inexistente → erro", r2.returncode == 2, r2.stdout)


def test_wave_state(tmp):
    pd = Path(tmp) / "prog"
    pd.mkdir()
    plan = pd / "plan.yaml"
    plan.write_text(PLAN)
    r = sh([BIN / "maestro-wave-state", "init", pd, "--plan", plan, "--wave", "1"])
    check("wave-state init cria 2 slices", r.returncode == 0 and "2 slice" in r.stdout, r.stdout)
    r = sh([BIN / "maestro-wave-state", "get", pd, "--json"])
    ws = json.loads(r.stdout)
    check("S1 herda timeout_min do plano (30)", ws["slices"]["S1"]["timeout_min"] == 30, ws)
    sh([BIN / "maestro-wave-state", "set-slice", pd, "S1", "running",
        "--pane", "p1", "--worktree", "/wt/S1", "--started-epoch", "1000"])
    r = sh([BIN / "maestro-wave-state", "get", pd, "--json"])
    ws = json.loads(r.stdout)
    check("set-slice persiste pane/worktree/epoch",
          ws["slices"]["S1"]["status"] == "running" and
          ws["slices"]["S1"]["pane"] == "p1" and
          ws["slices"]["S1"]["started_epoch"] == 1000, ws["slices"]["S1"])
    r = sh([BIN / "maestro-wave-state", "set-slice", pd, "S1", "GARBAGE"])
    check("status inválido é recusado", r.returncode == 2, r.stdout)
    # The merge train only lands DONE (landed of running is refused; see
    # tests/test_maestro_pending_merge.py).
    sh([BIN / "maestro-wave-state", "set-slice", pd, "S1", "DONE"])
    sh([BIN / "maestro-wave-state", "landed", pd, "S1"])
    r = sh([BIN / "maestro-wave-state", "get", pd, "--json"])
    ws = json.loads(r.stdout)
    check("landed registra o merge",
          "S1" in ws["landed"] and ws["slices"]["S1"]["status"] == "LANDED", r.stdout)


def test_check_terminal(tmp):
    """A8 — the wave does not land with a slice that has no terminal state."""
    pd = Path(tmp) / "prog3"
    pd.mkdir()
    plan = pd / "plan.yaml"
    plan.write_text(PLAN)
    sh([BIN / "maestro-wave-state", "init", pd, "--plan", plan, "--wave", "1"])

    # freshly initialized: both slices pending → does NOT land
    r = sh([BIN / "maestro-wave-state", "check-terminal", pd])
    check("onda toda pending → exit 2", r.returncode == 2, r.stdout + r.stderr)
    check("nomeia as slices penduradas",
          "S1" in r.stderr and "S2" in r.stderr, r.stderr)

    # one terminal, another running → still does NOT land (the dangerous case:
    # it looks like progress, and it is exactly where a slice vanishes from the radar)
    sh([BIN / "maestro-wave-state", "set-slice", pd, "S1", "DONE"])
    sh([BIN / "maestro-wave-state", "set-slice", pd, "S2", "running"])
    r = sh([BIN / "maestro-wave-state", "check-terminal", pd])
    check("uma DONE + uma running → exit 2", r.returncode == 2, r.stdout + r.stderr)
    check("não acusa a slice que já terminou",
          "S2" in r.stderr and "S1" not in r.stderr, r.stderr)

    # the four terminal states count as finished (not only DONE):
    # FAIL/TIMEOUT/ESCALATED are results, and re-fork in the next wave
    for st in ("FAIL", "TIMEOUT", "ESCALATED"):
        sh([BIN / "maestro-wave-state", "set-slice", pd, "S2", st])
        r = sh([BIN / "maestro-wave-state", "check-terminal", pd])
        check(f"S2={st} conta como terminal → exit 0",
              r.returncode == 0, r.stdout + r.stderr)

    r = sh([BIN / "maestro-wave-state", "check-terminal", pd, "--json"])
    check("--json lista os não-terminais (vazio quando tudo terminou)",
          r.returncode == 0 and json.loads(r.stdout)["non_terminal"] == {}, r.stdout)

    # regression for the missing status path: a slice in the wave-state without the
    # status key must not pass by omission
    import yaml
    ws = yaml.safe_load((pd / "wave-state.yaml").read_text())
    ws["slices"]["S3"] = {"timeout_min": 45}
    (pd / "wave-state.yaml").write_text(yaml.safe_dump(ws, allow_unicode=True))
    r = sh([BIN / "maestro-wave-state", "check-terminal", pd])
    check("slice sem chave status → exit 2 (não passa por omissão)",
          r.returncode == 2 and "S3" in r.stderr, r.stdout + r.stderr)


def _prog_with_running(tmp, marker=None, mtime_age=0, started=None, timeout_min=45):
    pd = Path(tmp) / "prog2"
    (pd / "slices" / "S1").mkdir(parents=True, exist_ok=True)
    ws = {"program": "t", "wave": 1, "timeout_min_default": 45,
          "slices": {"S1": {"status": "running", "timeout_min": timeout_min,
                            "started_epoch": started}}}
    import yaml
    (pd / "wave-state.yaml").write_text(yaml.safe_dump(ws))
    if marker is not None:
        res = pd / "slices" / "S1" / "resultado.txt"
        res.write_text(marker)
    return pd


def test_poll(tmp):
    import os
    # DONE
    pd = _prog_with_running(tmp + "/a", marker="log...\nMAESTRO-EXIT:0\n")
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "5000"]).stdout)
    check("MAESTRO-EXIT:0 → DONE",
          out["transitions"] == [{"slice": "S1", "to": "DONE", "detail": 0}], out)
    # FAIL
    pd = _prog_with_running(tmp + "/b", marker="MAESTRO-EXIT:1\n")
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "5000"]).stdout)
    check("MAESTRO-EXIT:1 → FAIL", out["transitions"][0]["to"] == "FAIL", out)
    # ESCALATED
    pd = _prog_with_running(tmp + "/c", marker="MAESTRO-EXIT:ESCALATED:abc123\n")
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "5000"]).stdout)
    check("MAESTRO-EXIT:ESCALATED → ESCALATED + id",
          out["transitions"][0]["to"] == "ESCALATED" and
          out["transitions"][0]["detail"] == "abc123", out)
    # the LAST marker counts
    pd = _prog_with_running(tmp + "/d", marker="MAESTRO-EXIT:ESCALATED:x\nMAESTRO-EXIT:0\n")
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "5000"]).stdout)
    check("último marcador vence", out["transitions"][0]["to"] == "DONE", out)
    # TIMEOUT: started more than timeout_min ago, without a marker
    pd = _prog_with_running(tmp + "/e", marker=None, started=1000, timeout_min=1)
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", str(1000 + 61)]).stdout)
    check("sem MAESTRO-EXIT após T_slice → TIMEOUT",
          out["transitions"][0]["to"] == "TIMEOUT", out)
    # WEGO-paralelo regression 2026-08-24: the wrapper tees the resultado.txt AT THE ROOT
    # OF THE WORKTREE (--cwd), not in <progdir>/slices/<S>/. Looking only under slices/
    # left 5 finished slices eternally "running" until they turned TIMEOUT.
    pdw = _prog_with_running(tmp + "/g", marker=None, started=1000, timeout_min=45)
    wt = Path(tmp + "/g") / "worktree-S1"
    wt.mkdir(parents=True, exist_ok=True)
    (wt / "resultado.txt").write_text("trabalho...\nMAESTRO-EXIT:0\n")
    import yaml as _y
    _ws = _y.safe_load((pdw / "wave-state.yaml").read_text())
    _ws["slices"]["S1"]["worktree"] = str(wt)
    (pdw / "wave-state.yaml").write_text(_y.safe_dump(_ws))
    out = json.loads(sh([BIN / "maestro-poll", pdw, "--now", "1100"]).stdout)
    check("lê o resultado.txt na raiz do worktree do slice",
          out["transitions"] == [{"slice": "S1", "to": "DONE", "detail": 0}], out)
    # still running: no marker, within the deadline → alive
    pd = _prog_with_running(tmp + "/f", marker="progride...\n", started=1000, timeout_min=45)
    os.utime(pd / "slices" / "S1" / "resultado.txt", (1000, 1050))
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "1100", "--heartbeat-s", "300"]).stdout)
    check("dentro do prazo e com progresso → alive, sem transição",
          out["alive"] == ["S1"] and not out["transitions"], out)
    # stalled: stale mtime beyond the heartbeat
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "2000", "--heartbeat-s", "300"]).stdout)
    check("mtime velho > heartbeat → stalled",
          any(s["slice"] == "S1" for s in out["stalled"]), out)
    # pending escalations in the queue
    pd = _prog_with_running(tmp + "/g", marker="x\n", started=1, timeout_min=45)
    esc = pd / "gatekeeper" / "escalations"
    esc.mkdir(parents=True)
    (esc / "e1.yaml").write_text("id: e1\nslice: S1\nestado: pending\n")
    (esc / "e2.yaml").write_text("id: e2\nslice: S1\nestado: answered\n")
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "2"]).stdout)
    check("poll drena só escalações pending",
          len(out["escalations"]) == 1 and out["escalations"][0]["id"] == "e1", out)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for sub in "a b c d e f g".split():
            (Path(tmp) / sub).mkdir()
        test_fork_settings(tmp)
        test_wave_state(tmp)
        test_check_terminal(tmp)
        test_poll(tmp)
    print()
    if FAILS:
        print(f"{len(FAILS)} failure(s): {FAILS}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
