#!/usr/bin/env python3
"""cepa-run — on a red `tests/run-all.sh`, the repetition runs only the failed files.

In run reforma-de-nomes/2026-11-25-2108, CS-8 and CS-10 went red, the supervisor
ran the whole suite again (about 48 min each) and the same file failed again:
98 min with no new information. Contract guarded here:

  - when the verify is `tests/run-all.sh` and its output lists files under
    "com falha:", the 2nd run is `tests/run-all.sh <those files>`;
  - a red without that list (the suite did not get to the summary) repeats
    the whole suite, as before;
  - any other build (`--verify <cmd>`) keeps repeating the whole command,
    which test_cepa_until_run_branch.test_4a already pins.

No third-party deps beyond PyYAML — run with `python3 tests/test_cepa_run_repeat_failed.py`.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_run_branch import WORKS, _commits, plan_of, status  # noqa: E402

SUITE = "tests/run-all.sh"


def suite_script(calls, first_output, first_rc, second_rc):
    """Fake run-all.sh: notes its argv on each call; the 1st call prints
    `first_output` and exits `first_rc`, the next ones exit `second_rc`."""
    return (
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        f"calls = Path({str(calls)!r})\n"
        "seen = calls.read_text().splitlines() if calls.exists() else []\n"
        "with calls.open('a') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if not seen:\n"
        f"    print({first_output!r})\n"
        f"    sys.exit({first_rc})\n"
        f"sys.exit({second_rc})\n")


def run_with_suite(tmp, first_output, first_rc=1, second_rc=0):
    root = build_repo(tmp, [item("a1")])
    calls = Path(tmp) / "suite-calls"
    (root / "tests").mkdir(exist_ok=True)
    suite = root / "tests" / "run-all.sh"
    suite.write_text(suite_script(calls, first_output, first_rc, second_rc))
    suite.chmod(0o755)
    _commits(root, "suite")
    binv = fake_claude(tmp, WORKS)
    p, _ = run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", SUITE])
    argv = ([json.loads(l) for l in calls.read_text().splitlines()]
            if calls.exists() else [])
    return root, p, argv


SUMMARY = (
    "FALHA   tests/test_b.py  (saída 1)  (12s)\n"
    "─────────────────────────────────────────\n"
    "arquivos rodados: 3 de 3\n"
    "mais lentos:\n"
    "  40s  tests/test_c.py\n"
    "  12s  tests/test_b.py\n"
    "com falha: 2\n"
    "  - tests/test_b.py\n"
    "  - tests/test_c.py  [TIMEOUT 900s]")


def test_red_suite_repeats_only_the_failed_files():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, argv = run_with_suite(tmp, SUMMARY)
        check("a suíte rodou duas vezes", len(argv) == 2, f"{argv} {p.stdout[-600:]}")
        check("a 1ª rodada é a suíte inteira", argv[:1] == [[]], str(argv))
        check("a 2ª rodada leva só os arquivos de 'com falha:', sem o [TIMEOUT]",
              argv[1:2] == [["tests/test_b.py", "tests/test_c.py"]], str(argv))
        check("verde na 2ª: o item fecha done",
              status(root, "a1")["status"] == "done", str(status(root, "a1")))
        rep = [e for e in ledger_of(root)
               if e["evento"] == "verify" and e.get("repeticao") == 2]
        check("o registro da repetição nomeia os arquivos",
              len(rep) == 1 and rep[0].get("arquivos")
              == ["tests/test_b.py", "tests/test_c.py"], str(rep))


def test_red_suite_without_failure_list_repeats_the_whole_suite():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, argv = run_with_suite(tmp, "ERRO: pytest ausente", first_rc=2)
        check("sem 'com falha:' a 2ª rodada é a suíte inteira",
              argv == [[], []], f"{argv} {p.stdout[-600:]}")
        check("o item fecha done", status(root, "a1")["status"] == "done",
              str(status(root, "a1")))


def test_red_again_on_the_failed_files_gives_the_item_back():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, argv = run_with_suite(tmp, SUMMARY, second_rc=1)
        check("2ª rodada só com os arquivos",
              argv[1:2] == [["tests/test_b.py", "tests/test_c.py"]], str(argv))
        check("vermelho de novo: o item sai de done",
              status(root, "a1")["status"] != "done", str(status(root, "a1")))


def test_real_run_all_feeds_the_real_parser_and_takes_its_list():
    """The pair the fake suite above stands in for: the real run-all.sh writes
    "com falha:", cepa-run's parser reads it, and the real run-all.sh accepts
    the list back as its filter."""
    import importlib.machinery
    import importlib.util
    import os
    import shutil
    import subprocess
    here = Path(__file__).resolve().parent
    loader = importlib.machinery.SourceFileLoader(
        "cepa_run_mod", str(here.parent / "common" / "bin" / "cepa-run"))
    spec = importlib.util.spec_from_loader("cepa_run_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as tmp:
        tests = Path(tmp) / "tests"
        tests.mkdir()
        for f in ("run-all.sh", "_run_with_timeout.py"):
            shutil.copy(here / f, tests / f)
        (tests / "test_good.py").write_text("print('ok')\n")
        (tests / "test_bad.py").write_text("import sys\nsys.exit(1)\n")
        env = dict(os.environ, SKIP_PYTEST="1")
        log = Path(tmp) / "run.log"
        log.write_text("antes\n")
        offset = mod.log_size(log)
        r = subprocess.run(["bash", str(tests / "run-all.sh")], env=env,
                           capture_output=True, text=True, timeout=60)
        with log.open("a") as f:
            f.write(r.stdout + r.stderr)
        failed = mod.failed_suite_files(log, offset)
        check("o parser lê a lista do run-all.sh real",
              failed == ["tests/test_bad.py"], f"{failed} {r.stdout[-400:]}")
        r2 = subprocess.run(["bash", str(tests / "run-all.sh")] + failed, env=env,
                            capture_output=True, text=True, timeout=60)
        out = r2.stdout
        check("o run-all.sh real aceita a lista e roda só esse arquivo",
              "→ 1 arquivo(s)" in out and "test_good.py" not in out
              and "  - tests/test_bad.py" in out, out)


def main():
    print("cepa-run — repetir só os arquivos com falha\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
