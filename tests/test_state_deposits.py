#!/usr/bin/env python3
"""DUR-4: the single reader of the five state deposits (`common/hooks/_state.py`).

Run with `python3 tests/test_state_deposits.py` (needs nothing installed).

What it proves:
  (a) a writer that touches `.claude/<name>` without declaring `<name>` in the
      catalogue turns this test red (it scans the code of `common/`), and a stray
      entry in a `.claude/` is reported by `unknown_entries`;
  (b) the one liveness rule: a `rodando` record is alive only with a fresh
      heartbeat (and a live pid on the same host); no heartbeat is never `vivo`;
  (c) the four commands' bins import and use the module, and `cepa-plan` has no
      copy of the heartbeat constant any more;
  (d) `cepa-doctor` warns in the `estado` area when `.claude/` has a stray entry.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _state  # noqa: E402
import _wtlib  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def test_every_writer_is_catalogued():
    names = {}
    files = list((REPO / "common" / "hooks").glob("*.py")) + [
        p for p in (REPO / "common" / "bin").iterdir() if p.is_file()]
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in re.finditer(r"\.claude/([A-Za-z0-9_][A-Za-z0-9_.-]*)", text):
            names.setdefault(m.group(1).rstrip("."), f.name)
        # segment form: root / ".claude" / "x", os.path.join(root, ".claude", "x")
        for m in re.finditer(r"""["']\.claude["']\s*[,/]\s*["']([^"'/]+)["']""", text):
            names.setdefault(m.group(1).rstrip("."), f.name)
    # prefixes of globs written in prose (`.claude/settings*`) and bare words
    prefixes = {"settings"}
    missing = sorted(n for n in names
                     if n not in prefixes and not _state.catalogued(n))
    check("todo `.claude/<nome>` citado no código de common/ está no catálogo",
          not missing, "; ".join(f"{n} (em {names[n]})" for n in missing))
    check("a varredura achou os depósitos conhecidos",
          {"queues", "sessions", "handoffs"} <= set(names), str(sorted(names))[:200])


def test_segment_form_is_scanned():
    probe = REPO / "common" / "hooks" / "_tmp_probe_segment.py"
    probe.write_text('p = root / ".claude" / "zzz-segmento"\n', encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, str(Path(__file__)), "--only-scan"],
                           capture_output=True, text=True)
    finally:
        probe.unlink()
    check("um escritor em forma de segmentos sem catálogo deixa a varredura vermelha",
          r.returncode != 0 and "zzz-segmento" in r.stdout, r.stdout[-300:])


def test_unknown_entries():
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / ".claude"
        (c / "queues").mkdir(parents=True)
        (c / "sessions").mkdir()
        (c / "handoffs").mkdir()
        (c / "last-build.json").write_text("{}")
        (c / "sessions" / "k.json").write_text("{}")
        (c / "sessions" / "k.next.json").write_text("{}")
        (c / "handoffs" / "b.md").write_text("x")
        check("sem estranhos, nada é reportado", _state.unknown_entries(tmp) == [],
              str(_state.unknown_entries(tmp)))
        (c / "foo.json").write_text("{}")
        (c / "sessions" / "x.weird").write_text("")
        got = _state.unknown_entries(tmp)
        check("um foo.json estranho em .claude/ é reportado", "foo.json" in got, str(got))
        check("um tipo de arquivo estranho em sessions/ é reportado",
              "sessions/x.weird" in got, str(got))
    real = REPO / ".claude"
    for name in ("acceptance", "deviations.md", "doctor-last-run", "expertise",
                 "feedback-nudge", "handoffs", "last-build.json", "no-build",
                 "programs", "queues", "reflection", "rescued", "session-intent",
                 "session-log.md", "session-mode", "sessions", "topology", "waivers",
                 "env.yaml", "proof", "prove", "prompts", "cepa-prompts",
                 "loop-state.json", "last-root-install.json", "editorial-lint",
                 "worktree-seed", "worktrees", "validation", "external-tests",
                 "ui-proof", "board-flow.lifecycle.yaml", "settings.json",
                 "settings.local.json", "reflexao"):
        if not _state.catalogued(name):
            check(f"a entrada real {name} está no catálogo", False)
            break
    else:
        check("todas as entradas reais e as citadas pelos escritores estão no catálogo", True)
    check("o .claude/ do próprio repo não tem estranhos",
          _state.unknown_entries(REPO) == [] or not real.is_dir(),
          str(_state.unknown_entries(REPO)))


def beat(seconds_ago):
    return (datetime.now().astimezone() - timedelta(seconds=seconds_ago)).isoformat(
        timespec="seconds")


def test_liveness():
    me = _wtlib.host()
    base = {"estado": "rodando", "host": me, "pid": os.getpid()}
    s, d = _state.run_liveness({**base, "heartbeat": beat(5)})
    check("rodando + heartbeat fresco + pid vivo + mesmo host = vivo", s == "vivo", f"{s} {d}")
    s, d = _state.run_liveness({**base, "heartbeat": beat(7200)})
    check("heartbeat velho = morto", s == "morto" and "MORTO" in d, f"{s} {d}")
    s, d = _state.run_liveness(dict(base))
    check("rodando sem heartbeat = desconhecido, nunca vivo", s == "desconhecido", f"{s} {d}")
    s, _ = _state.run_liveness({**base, "pid": 2 ** 22 + 12345, "heartbeat": beat(1)})
    check("pid morto no mesmo host = morto mesmo com heartbeat fresco", s == "morto", s)
    s, _ = _state.run_liveness({**base, "estado": "esperando-dono", "heartbeat": beat(1)})
    check("esperando-dono não está vivo", s == "esperando-dono", s)
    other = {"estado": "rodando", "host": me + "-outro", "pid": 2 ** 22 + 12345}
    s, _ = _state.run_liveness({**other, "heartbeat": beat(5)})
    check("outro host com heartbeat fresco = vivo (pid não é sondado)", s == "vivo", s)
    s, _ = _state.run_liveness({**other, "heartbeat": beat(7200)})
    check("outro host com heartbeat velho = morto", s == "morto", s)
    s, _ = _state.run_liveness({**base, "heartbeat": datetime.now().isoformat(timespec="seconds")})
    check("heartbeat sem fuso (arquivo antigo) é lido como hora local", s == "vivo", s)
    s, d = _state.run_liveness({**other, "heartbeat": beat(-7200)})
    check("heartbeat no futuro (relógio adiantado) = desconhecido, nunca vivo",
          s == "desconhecido" and "futuro" in d, f"{s} {d}")
    s, _ = _state.run_liveness({**base, "heartbeat": "lixo"})
    check("heartbeat ilegível = desconhecido", s == "desconhecido", s)


def test_runs_reader():
    with tempfile.TemporaryDirectory() as tmp:
        for layout, fname in ((".claude/queues", "q"), (".claude/programs", "p")):
            d = Path(tmp) / layout / fname / "until"
            d.mkdir(parents=True)
            (d / "r.estado.json").write_text(json.dumps(
                {"run": fname, "estado": "aterrissado", "arvore": "/x"}))
        rs = _state.runs(tmp)
        check("runs lê os dois layouts", sorted(r["estado"]["run"] for r in rs) == ["p", "q"],
              str(rs))
        check("run_of acha pelo id", _state.run_of(tmp, run_id="q")["estado"]["run"] == "q")
        snap = _state.snapshot(tmp)
        check("snapshot traz os cinco depósitos e os estranhos",
              set(snap) == {"fila", "run", "handoff", "sessao", "autonomo", "unknown"},
              str(set(snap)))


def test_bins_use_the_module():
    for name in ("cepa-plan", "cepa-doctor", "cepa-until-digest", "cepa-intent"):
        text = (REPO / "common" / "bin" / name).read_text(encoding="utf-8")
        used = len(re.findall(r"_state\.\w+|from _state import", text))
        check(f"{name} importa e usa _state", "import _state" in text and used >= 1,
              f"usos={used}")
    plan = (REPO / "common" / "bin" / "cepa-plan").read_text(encoding="utf-8")
    check("cepa-plan não define mais HEARTBEAT_STALE_SEC",
          not re.search(r"^HEARTBEAT_STALE_SEC\s*=", plan, re.M))


def run_doctor(root):
    return subprocess.run([sys.executable, str(REPO / "common" / "bin" / "cepa-doctor"),
                           "--projeto"], cwd=root, capture_output=True, text=True,
                          env={**os.environ, "CEPA_NO_COLOR": "1", "NO_COLOR": "1"})


def test_doctor_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".claude").mkdir()
        (root / "README.md").write_text("x\n")
        subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
        r = run_doctor(root)
        check("sem entrada estranha o doctor não avisa em estado",
              "não conhece" not in r.stdout, r.stdout[-400:])
        (root / ".claude" / "foo.json").write_text("{}")
        r = run_doctor(root)
        out = r.stdout + r.stderr
        check("o doctor avisa na área estado e nomeia a entrada estranha",
              "foo.json" in out and "_state.py" in out, out[-600:])


if "--only-scan" in sys.argv:
    test_every_writer_is_catalogued()
    sys.exit(1 if FAILURES else 0)

for t in (test_every_writer_is_catalogued, test_segment_form_is_scanned, test_unknown_entries, test_liveness,
          test_runs_reader, test_bins_use_the_module, test_doctor_warns):
    t()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("todos os testes passaram")
