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

# This test runs `cepa-intent`, `cepa-doctor` and `cepa-until-digest` for real,
# and cites the `session-log` deposit; without this the events would fall in
# ~/.claude/cepa-telemetry/ and enter the /common:metrics report as if they were
# real use (tests/test_isolated_telemetry.py went red on 2026-11-05 for exactly
# this file). See tests/_isolated_telemetry.py.
from _isolated_telemetry import isolate

isolate()

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


def test_slash_form_is_scanned():
    probe = REPO / "common" / "hooks" / "_tmp_probe_slash.py"
    probe.write_text('p = root + "/.claude/zzz-barra"\n', encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, str(Path(__file__)), "--only-scan"],
                           capture_output=True, text=True)
    finally:
        probe.unlink()
    check("um escritor em forma de barra sem catálogo deixa a varredura vermelha",
          r.returncode != 0 and "zzz-barra" in r.stdout, r.stdout[-300:])


def test_liveness_thresholds():
    saved = _state.HEARTBEAT_STALE_SEC
    _state.HEARTBEAT_STALE_SEC = 900.0
    try:
        me = _wtlib.host()
        base = {"estado": "rodando", "host": me, "pid": os.getpid()}
        other = {"estado": "rodando", "host": me + "-outro", "pid": 1}
        check("idade 800s (abaixo do limite de 900s) = vivo",
              _state.run_liveness({**base, "heartbeat": beat(800)})[0] == "vivo")
        check("idade 1000s (acima do limite) = morto",
              _state.run_liveness({**base, "heartbeat": beat(1000)})[0] == "morto")
        check("heartbeat 60s no futuro (relógio levemente adiantado) = vivo",
              _state.run_liveness({**other, "heartbeat": beat(-60)})[0] == "vivo")
        s, d = _state.run_liveness({**other, "heartbeat": beat(-901)})
        check("heartbeat 901s no futuro = desconhecido, e o detalhe diz futuro",
              s == "desconhecido" and "futuro" in d, f"{s} {d}")
        s, _ = _state.run_liveness({"estado": "rodando", "pid": 2 ** 22 + 12345,
                                    "heartbeat": beat(1)})
        check("registro sem a chave host e pid morto = morto", s == "morto", s)
    finally:
        _state.HEARTBEAT_STALE_SEC = saved


def test_stray_in_handoffs_and_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        c = Path(tmp) / ".claude"
        (c / "handoffs").mkdir(parents=True)
        (c / "sessions").mkdir()
        (c / "handoffs" / "x.weird").write_text("")
        (c / "sessions" / "x.weird").write_text("")
        (c / "handoffs" / "ok.md").write_text("x")
        (c / "handoffs" / "ok.claim").write_text("{}")
        (c / "handoffs" / "archive").mkdir()
        got = _state.unknown_entries(tmp)
        check("handoffs/x.weird é reportado", "handoffs/x.weird" in got, str(got))
        check("sessions/x.weird é reportado", "sessions/x.weird" in got, str(got))
        check("os tipos conhecidos de handoffs/ não são reportados",
              sorted(got) == ["handoffs/x.weird", "sessions/x.weird"], str(got))


def test_readers_with_content():
    import _handoff
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _wtlib.write_entry(str(root), "vivo-1", {"session_id": "vivo-1",
                           "pid": os.getpid(), "hostname": _wtlib.host(),
                           "started_at": _wtlib.now_iso()})
        _wtlib.write_entry(str(root), "morto-1", {"session_id": "morto-1",
                           "pid": 2 ** 22 + 12345, "hostname": _wtlib.host(),
                           "started_at": _wtlib.now_iso()})
        ss = {x["entry"]["session_id"]: x["live"] for x in _state.sessions(root)}
        check("sessions classifica a viva e a morta",
              ss == {"vivo-1": True, "morto-1": False}, str(ss))

        _handoff.write(_handoff.handoff_path(str(root), "feat/x"),
                       {"branch": "feat/x", "updated_at": _wtlib.now_iso()},
                       auto="a", note="n")
        hs = _state.handoffs(root)
        check("handoffs lista o arquivo com o branch do meta",
              len(hs) == 1 and hs[0]["path"].name == "feat-x.md"
              and hs[0]["meta"].get("branch") == "feat/x", str(hs))

        check("autonomous_runs sem docs/autonomous devolve lista vazia",
              _state.autonomous_runs(root) == [])
        d = root / "docs" / "autonomous" / "run-9"
        d.mkdir(parents=True)
        (d / "state.yaml").write_text("run_id: run-9\nlog: []\n")
        ar = _state.autonomous_runs(root)
        check("autonomous_runs traz o run e o conteúdo do state.yaml",
              len(ar) == 1 and ar[0]["run"] == "run-9"
              and (ar[0]["state"] or {}).get("run_id") == "run-9", str(ar))

        u = root / ".claude" / "queues" / "q" / "until"
        u.mkdir(parents=True)
        (u / "r.estado.json").write_text(json.dumps(
            {"run": "r1", "estado": "aterrissado", "arvore": "/noite/x"}))
        r = _state.run_of(root, run_id="nao-existe", tree="/noite/x")
        check("run_of cai para a árvore quando o id não acha",
              r is not None and r["estado"]["run"] == "r1", str(r))
        check("run_of sem id nem árvore que casem = None",
              _state.run_of(root, run_id="nao", tree="/outra") is None)
        (root / ".claude" / "estranho.bin").write_text("")
        snap = _state.snapshot(root)
        check("snapshot['unknown'] lista o estranho", "estranho.bin" in snap["unknown"],
              str(snap["unknown"]))
        check("snapshot traz sessões e handoffs reais",
              len(snap["sessao"]) == 2 and len(snap["handoff"]) == 1)


def _digest_fixture(tmp, estado):
    until = Path(tmp) / ".claude" / "programs" / "F" / "until"
    until.mkdir(parents=True)
    ledger = until / "r.jsonl"
    ledger.write_text("\n".join(json.dumps(e) for e in [
        {"evento": "run_start", "fila": "F", "branch": "until/r", "base": "dead00"},
        {"evento": "run_end", "motivo": "fim-da-fila", "detalhe": "x"}]) + "\n")
    if estado is not None:
        (until / "r.estado.json").write_text(json.dumps(estado))
    return ledger


def test_digest_shows_run_liveness_line():
    digest = REPO / "common" / "bin" / "cepa-until-digest"
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _digest_fixture(tmp, {"run": "r", "estado": "rodando",
                                       "host": _wtlib.host(), "pid": os.getpid(),
                                       "heartbeat": beat(7200)})
        r = subprocess.run([sys.executable, str(digest), str(ledger)],
                           capture_output=True, text=True)
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("- run:")), "")
        check("o digest traz a linha `- run:` dizendo MORTO", "MORTO" in line,
              r.stdout[:400] + r.stderr[-200:])
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _digest_fixture(tmp, None)
        r = subprocess.run([sys.executable, str(digest), str(ledger)],
                           capture_output=True, text=True)
        check("sem .estado.json o digest não traz a linha `- run:`",
              r.returncode == 0 and "- run:" not in r.stdout, r.stdout[:300] + r.stderr[-200:])


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=cwd, check=True, capture_output=True)


def test_intent_state_inside_a_run_says_if_it_is_alive():
    intent = REPO / "common" / "bin" / "cepa-intent"
    with tempfile.TemporaryDirectory() as tmp:
        main = Path(tmp).resolve() / "main"
        main.mkdir()
        _git(main, "init", "-q", ".")
        (main / "README.md").write_text("x\n")
        _git(main, "add", "-A")
        _git(main, "commit", "-qm", "base")
        wtree = Path(tmp).resolve() / "noite"
        _git(main, "worktree", "add", "-q", "-b", "until/r", str(wtree))
        u = main / ".claude" / "queues" / "q" / "until"
        u.mkdir(parents=True)

        def state_out(heartbeat):
            (u / "r.estado.json").write_text(json.dumps(
                {"run": "r1", "estado": "rodando", "host": _wtlib.host(),
                 "pid": os.getpid(), "arvore": str(wtree), "heartbeat": heartbeat}))
            env = {**os.environ, "CEPA_UNTIL_RUN": "r1"}
            return subprocess.run([sys.executable, str(intent), "state"], cwd=wtree,
                                  capture_output=True, text=True, env=env).stdout

        out = state_out(beat(7200))
        check("dentro do run: as linhas antigas continuam",
              "state: empty" in out and "delegate: /common:next" in out, out)
        check("heartbeat velho: `run: r1 (morto)`", "run: r1 (morto)" in out, out)
        out = state_out(beat(3))
        check("heartbeat fresco e pid vivo: `run: r1 (vivo)`", "run: r1 (vivo)" in out, out)


def test_doctor_stray_is_a_warning_not_ok():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".claude").mkdir()
        (root / "README.md").write_text("x\n")
        subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
        (root / ".claude" / "foo.json").write_text("{}")
        out = run_doctor(root).stdout
        lines = [ln for ln in out.splitlines() if "[estado]" in ln]
        warns = [ln for ln in lines if ln.lstrip().startswith("⚠")]
        oks = [ln for ln in lines if ln.lstrip().startswith("✓")]
        check("a linha [estado] com o estranho é ⚠ e não ✓",
              len(warns) == 1 and "foo.json" in warns[0] and not oks, str(lines))
        (root / ".claude" / "foo.json").unlink()
        lines = [ln for ln in run_doctor(root).stdout.splitlines() if "[estado]" in ln]
        check("sem estranho a linha [estado] é ✓ e não há ⚠",
              len(lines) == 1 and lines[0].lstrip().startswith("✓"), str(lines))


def test_non_dict_estado_files_are_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        u = Path(tmp) / ".claude" / "queues" / "q" / "until"
        u.mkdir(parents=True)
        (u / "a.estado.json").write_text("[]")
        (u / "b.estado.json").write_text("null")
        (u / "c.estado.json").write_text(json.dumps({"run": "c", "estado": "aterrissado"}))
        rs = _state.runs(tmp)
        check("`[]` e `null` não entram em runs", [r["estado"]["run"] for r in rs] == ["c"],
              str(rs))
        try:
            got = _state.run_of(tmp, run_id="zzz", tree="/x")
        except Exception as e:  # noqa: BLE001
            got = f"EXC {e!r}"
        check("run_of não quebra nem devolve os arquivos que não são objeto", got is None,
              str(got))


def test_digest_ignores_a_non_dict_estado():
    digest = REPO / "common" / "bin" / "cepa-until-digest"
    with tempfile.TemporaryDirectory() as tmp:
        ledger = _digest_fixture(tmp, [])
        r = subprocess.run([sys.executable, str(digest), str(ledger)],
                           capture_output=True, text=True)
        check("`.estado.json` com `[]`: sem linha `- run:` e saída 0",
              r.returncode == 0 and "- run:" not in r.stdout, r.stdout[:200] + r.stderr[-300:])


def test_intent_run_lookup_by_each_key_alone():
    intent = REPO / "common" / "bin" / "cepa-intent"
    with tempfile.TemporaryDirectory() as tmp:
        main = Path(tmp).resolve() / "main"
        main.mkdir()
        _git(main, "init", "-q", ".")
        (main / "README.md").write_text("x\n")
        _git(main, "add", "-A")
        _git(main, "commit", "-qm", "base")
        wtree = Path(tmp).resolve() / "noite"
        _git(main, "worktree", "add", "-q", "-b", "until/r", str(wtree))
        u = main / ".claude" / "queues" / "q" / "until"
        u.mkdir(parents=True)

        def out_with(arvore, env_run):
            (u / "r.estado.json").write_text(json.dumps(
                {"run": "r1", "estado": "rodando", "host": _wtlib.host(),
                 "pid": os.getpid(), "arvore": arvore, "heartbeat": beat(3)}))
            env = {**os.environ, "CEPA_UNTIL_RUN": env_run}
            return subprocess.run([sys.executable, str(intent), "state"], cwd=wtree,
                                  capture_output=True, text=True, env=env).stdout

        out = out_with(str(wtree), "id-que-nao-casa")
        check("só a árvore casa (o id não): a linha `run:` aparece", "run: r1 (vivo)" in out, out)
        out = out_with("/outra/arvore", "r1")
        check("só o id casa (a árvore é outra): a linha `run:` aparece", "run: r1 (vivo)" in out, out)


if "--only-scan" in sys.argv:
    test_every_writer_is_catalogued()
    sys.exit(1 if FAILURES else 0)

for t in (test_every_writer_is_catalogued, test_segment_form_is_scanned,
          test_slash_form_is_scanned, test_unknown_entries, test_liveness_thresholds,
          test_stray_in_handoffs_and_sessions, test_readers_with_content,
          test_digest_shows_run_liveness_line,
          test_intent_state_inside_a_run_says_if_it_is_alive,
          test_doctor_stray_is_a_warning_not_ok, test_liveness,
          test_non_dict_estado_files_are_ignored, test_digest_ignores_a_non_dict_estado,
          test_intent_run_lookup_by_each_key_alone,
          test_runs_reader, test_bins_use_the_module, test_doctor_warns):
    t()

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("todos os testes passaram")
