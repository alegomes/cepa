#!/usr/bin/env python3
"""Regression tests: Maestro wave that finished and nobody landed.

## The defect

The /maestro:run merge train only runs with the maestro session alive. In wave 1
of WEGO-paralelo (2026-08-24) it died before getting there: five slices
DONE, `landed: []` in wave-state.yaml, and nothing on disk distinguished "wave
running" from "wave waiting for you". The branches were merged by hand, hours and
half a day later, by whoever happened to notice.

## What these tests hold

- the wave-state separates "the daughter finished" (DONE) from "the branch is in the
  integration" (LANDED), and `aguardando-merge` lists the first without the second;
- the item's done criterion: session dead right after the last daughter, and the next
  session hears "5 finished slices waiting for merge" without opening
  wave-state.yaml. The sentence comes from `maestro-programs --aguardando-merge`, which is
  what /common:next calls, and from cepa-doctor;
- `landed` refuses a slice that is not DONE: marking FAIL as landed would erase the
  state that sends the slice to re-fork;
- an old wave-state (merge only in the `landed:` list) is still read correctly;
- a retry registered with `set-slice` in the middle of the wave enters the finish
  boundary right away, not in the next wave.

Run: python3 tests/test_maestro_pending_merge.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WAVE_STATE = REPO / "maestro" / "bin" / "maestro-wave-state"
PROGRAMS = REPO / "maestro" / "bin" / "maestro-programs"
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

SLICES = ["S-2050", "S-2059", "S-2067", "S-2070", "S-2107"]

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def ws(progdir, *args):
    return subprocess.run([sys.executable, str(WAVE_STATE)] + list(args[:1])
                          + [str(progdir)] + list(args[1:]),
                          capture_output=True, text=True)


def build(tmp, name="WEGO-paralelo"):
    """Git repo with a wave program whose wave 1 was started."""
    root = Path(tmp)
    progdir = root / ".claude" / "programs" / name
    progdir.mkdir(parents=True)
    (progdir / "plan.yaml").write_text(yaml.safe_dump({
        "schema_version": 2, "mode": "parallel-waves", "program": name,
        "waves": [{"id": 1, "slices": SLICES, "status": "pending"}],
    }))
    (root / "README.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    r = ws(progdir, "init", "--plan", str(progdir / "plan.yaml"), "--wave", "1")
    assert r.returncode == 0, r.stderr
    return root, progdir


def finish_all(progdir):
    """The last daughter finished; the maestro session dies here."""
    for s in SLICES:
        r = ws(progdir, "set-slice", s, "DONE")
        assert r.returncode == 0, r.stderr


def waiting(progdir):
    r = ws(progdir, "aguardando-merge", "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["aguardando_merge"]


def test_dead_session_next_session_hears_what_is_waiting(tmp):
    root, progdir = build(tmp)
    finish_all(progdir)
    r = subprocess.run([sys.executable, str(PROGRAMS), str(root),
                        "--aguardando-merge"], capture_output=True, text=True)
    check("maestro-programs --aguardando-merge sai 0", r.returncode == 0, r.stderr)
    check("...e diz '5 slice(s) terminada(s) esperando merge'",
          "5 slice(s) terminada(s) esperando merge" in r.stdout, r.stdout)
    check("...nomeando as slices", all(s in r.stdout for s in SLICES), r.stdout)
    check("...e a rota /maestro:resume <programa>",
          "/maestro:resume WEGO-paralelo" in r.stdout, r.stdout)
    listing = subprocess.run([sys.executable, str(PROGRAMS), str(root)],
                              capture_output=True, text=True)
    check("a listagem normal também mostra a espera",
          "esperando merge" in listing.stdout, listing.stdout)


def test_doctor_charges_for_the_stalled_wave(tmp):
    root, progdir = build(tmp)
    finish_all(progdir)
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"], cwd=str(root),
                       capture_output=True, text=True, timeout=120)
    out = p.stdout + p.stderr
    check("doctor avisa na área [maestro]", "[maestro]" in out and "⚠" in out, out)
    check("...com a contagem e a rota",
          "5 slice(s) terminada(s) esperando merge" in out
          and "/maestro:resume WEGO-paralelo" in out, out)


def test_landed_removes_from_waiting_and_silences(tmp):
    root, progdir = build(tmp)
    finish_all(progdir)
    for s in SLICES[:3]:
        r = ws(progdir, "landed", s)
        check(f"landed {s} sai 0", r.returncode == 0, r.stderr)
    state = yaml.safe_load((progdir / "wave-state.yaml").read_text())
    check("slice aterrissada vira LANDED",
          state["slices"]["S-2050"]["status"] == "LANDED", state)
    check("sobram as 2 não aterrissadas, na ordem",
          waiting(progdir) == SLICES[3:], waiting(progdir))
    for s in SLICES[3:]:
        ws(progdir, "landed", s)
    check("tudo aterrissado: nada espera", waiting(progdir) == [])
    r = subprocess.run([sys.executable, str(PROGRAMS), str(root),
                        "--aguardando-merge"], capture_output=True, text=True)
    check("...e o maestro-programs fica calado", r.stdout.strip() == "", r.stdout)
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"], cwd=str(root),
                       capture_output=True, text=True, timeout=120)
    check("...e o doctor também", "[maestro]" not in p.stdout + p.stderr)
    check("LANDED conta como terminal na fronteira de término",
          ws(progdir, "check-terminal").returncode == 0)


def test_landed_refuses_slice_that_did_not_finish_well(tmp):
    _, progdir = build(tmp)
    ws(progdir, "set-slice", "S-2067", "FAIL")
    r = ws(progdir, "landed", "S-2067")
    check("landed de slice FAIL sai 2", r.returncode == 2, r.stdout + r.stderr)
    check("...dizendo o que registrar antes", "set-slice" in r.stderr, r.stderr)
    state = yaml.safe_load((progdir / "wave-state.yaml").read_text())
    check("...e o FAIL continua lá",
          state["slices"]["S-2067"]["status"] == "FAIL"
          and "S-2067" not in state["landed"], state)


def test_old_wave_state_with_landed_list(tmp):
    _, progdir = build(tmp)
    finish_all(progdir)
    file = progdir / "wave-state.yaml"
    state = yaml.safe_load(file.read_text())
    state["landed"] = ["S-2050", "S-2059", "S-2070"]  # merged by hand, old format
    file.write_text(yaml.safe_dump(state, sort_keys=False))
    check("nome na lista `landed:` conta como aterrissado",
          waiting(progdir) == ["S-2067", "S-2107"], waiting(progdir))


def test_slice_still_running_is_not_charged(tmp):
    _, progdir = build(tmp)
    ws(progdir, "set-slice", "S-2050", "DONE")
    ws(progdir, "set-slice", "S-2059", "running")
    check("só a DONE espera merge; a running não é dívida sua",
          waiting(progdir) == ["S-2050"], waiting(progdir))


def test_registered_retry_enters_the_boundary(tmp):
    _, progdir = build(tmp)
    finish_all(progdir)
    r = ws(progdir, "set-slice", "S-2067R", "running",
           "--detail", "retentativa de S-2067")
    check("set-slice registra a retentativa nova", r.returncode == 0, r.stderr)
    check("...e a fronteira de término a enxerga na hora (exit 2)",
          ws(progdir, "check-terminal").returncode == 2)


def test_commands_call_the_check(tmp):
    nxt = (REPO / "common" / "commands" / "next.md").read_text()
    check("/common:next roda maestro-programs --aguardando-merge",
          "maestro-programs . --aguardando-merge" in nxt)
    res = (REPO / "maestro" / "commands" / "resume.md").read_text()
    check("/maestro:resume vai ao merge train quando a onda terminou sem merge",
          "aguardando-merge" in res and "Step 9" in res)
    run = (REPO / "maestro" / "commands" / "run.md").read_text()
    check("/maestro:run registra a retentativa no instante do fork",
          "Retry under a new name" in run
          and "set-slice PROGDIR <slice>R running" in run)


def main():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        with tempfile.TemporaryDirectory() as tmp:
            t(tmp)
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print(f"\n{len(tests)} testes ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
