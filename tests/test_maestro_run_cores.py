#!/usr/bin/env python3
"""Regression tests for the deterministic cores of /maestro:run (passo 3).

Cobre maestro-fork-settings (camada 1), maestro-poll (event loop 2a) e
maestro-wave-state (estado/recuperação 2c). Sem deps além de PyYAML.
Run: python3 tests/test_maestro_run_cores.py
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
    # Regressão WEGO-paralelo 2026-08-24: o Claude Code RECUSA regra Write(path)
    # ("only Edit(path) rules are matched"); Edit(path) já cobre toda escrita.
    check("nenhuma regra Write(path) — só Edit(path) é aceita",
          not [x for x in perms["allow"] + perms["deny"] if x.startswith("Write(")],
          perms["allow"] + perms["deny"])
    check("identidade do slice vai na URL do porteiro (achado spike)",
          "slice=S1" in s["mcpServers"]["gatekeeper"]["url"], s["mcpServers"])
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
    sh([BIN / "maestro-wave-state", "landed", pd, "S1"])
    r = sh([BIN / "maestro-wave-state", "get", pd, "--json"])
    check("landed registra o merge", "S1" in json.loads(r.stdout)["landed"], r.stdout)


def test_check_terminal(tmp):
    """A8 — a onda não aterrissa com slice sem estado terminal."""
    pd = Path(tmp) / "prog3"
    pd.mkdir()
    plan = pd / "plan.yaml"
    plan.write_text(PLAN)
    sh([BIN / "maestro-wave-state", "init", pd, "--plan", plan, "--wave", "1"])

    # recém-inicializada: as duas slices em pending → NÃO aterrissa
    r = sh([BIN / "maestro-wave-state", "check-terminal", pd])
    check("onda toda pending → exit 2", r.returncode == 2, r.stdout + r.stderr)
    check("nomeia as slices penduradas",
          "S1" in r.stderr and "S2" in r.stderr, r.stderr)

    # uma terminal, outra rodando → ainda NÃO aterrissa (o caso perigoso:
    # parece progresso, e é exatamente onde uma slice some do radar)
    sh([BIN / "maestro-wave-state", "set-slice", pd, "S1", "DONE"])
    sh([BIN / "maestro-wave-state", "set-slice", pd, "S2", "running"])
    r = sh([BIN / "maestro-wave-state", "check-terminal", pd])
    check("uma DONE + uma running → exit 2", r.returncode == 2, r.stdout + r.stderr)
    check("não acusa a slice que já terminou",
          "S2" in r.stderr and "S1" not in r.stderr, r.stderr)

    # os quatro estados terminais contam como término (não só DONE):
    # FAIL/TIMEOUT/ESCALATED são resultados, e re-forkam na onda seguinte
    for st in ("FAIL", "TIMEOUT", "ESCALATED"):
        sh([BIN / "maestro-wave-state", "set-slice", pd, "S2", st])
        r = sh([BIN / "maestro-wave-state", "check-terminal", pd])
        check(f"S2={st} conta como terminal → exit 0",
              r.returncode == 0, r.stdout + r.stderr)

    r = sh([BIN / "maestro-wave-state", "check-terminal", pd, "--json"])
    check("--json lista os não-terminais (vazio quando tudo terminou)",
          r.returncode == 0 and json.loads(r.stdout)["non_terminal"] == {}, r.stdout)

    # regressão para o caminho de status ausente: slice no wave-state sem a
    # chave status não pode passar por omissão
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
    # o ÚLTIMO marcador vale
    pd = _prog_with_running(tmp + "/d", marker="MAESTRO-EXIT:ESCALATED:x\nMAESTRO-EXIT:0\n")
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "5000"]).stdout)
    check("último marcador vence", out["transitions"][0]["to"] == "DONE", out)
    # TIMEOUT: started há mais de timeout_min, sem marcador
    pd = _prog_with_running(tmp + "/e", marker=None, started=1000, timeout_min=1)
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", str(1000 + 61)]).stdout)
    check("sem MAESTRO-EXIT após T_slice → TIMEOUT",
          out["transitions"][0]["to"] == "TIMEOUT", out)
    # ainda rodando: sem marcador, dentro do prazo → alive
    pd = _prog_with_running(tmp + "/f", marker="progride...\n", started=1000, timeout_min=45)
    os.utime(pd / "slices" / "S1" / "resultado.txt", (1000, 1050))
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "1100", "--heartbeat-s", "300"]).stdout)
    check("dentro do prazo e com progresso → alive, sem transição",
          out["alive"] == ["S1"] and not out["transitions"], out)
    # stalled: mtime velho além do heartbeat
    out = json.loads(sh([BIN / "maestro-poll", pd, "--now", "2000", "--heartbeat-s", "300"]).stdout)
    check("mtime velho > heartbeat → stalled",
          any(s["slice"] == "S1" for s in out["stalled"]), out)
    # escalações pendentes na fila
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
