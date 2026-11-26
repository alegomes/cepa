#!/usr/bin/env python3
"""cepa-run — with `tests/run-all.sh` as the build, the full suite runs once per
pair of `done` items (O1, owner, 2026-11-26).

In run reforma-de-nomes/2026-11-25-2108 the suite took 393 of 495 min, one
48-min run per item. Contract guarded here:

  - the 1st item is checked alone (its time sizes the window check); then
    the next `done` item is deferred and checked together with the one after it;
  - red on the pair: the failed files run on the commit between the two items;
    green there means the 2nd item broke it (only it leaves the branch), red
    there means the 1st broke it (it leaves, and the 2nd goes back to
    `pending` with no red return of its own);
  - an item still waiting for its pair when the queue ends is checked on its
    own commit before the run closes;
  - an item that changed a plugin hook is never deferred.

No third-party deps beyond PyYAML — run with `python3 tests/test_cepa_run_pair_verify.py`.
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

# Fake run-all.sh: notes (cwd, argv) of each call; red, with a "com falha:"
# list, when the tree it runs in has `quebra.txt`.
FAKE_SUITE = (
    "#!/usr/bin/env python3\n"
    "import json, os, sys\n"
    "from pathlib import Path\n"
    "calls = Path({calls!r})\n"
    "broken = Path('quebra.txt').exists()\n"
    "files = sorted(p.name for p in Path('.').glob('a*.txt'))\n"
    "with calls.open('a') as f:\n"
    "    f.write(json.dumps({{'argv': sys.argv[1:], 'files': files,\n"
    "                        'red': broken}}) + '\\n')\n"
    "if broken:\n"
    "    print('com falha: 1')\n"
    "    print('  - tests/test_q.py')\n"
    "    sys.exit(1)\n"
    "print('tudo verde')\n")

# WORKS plus a plugin hook for the item named in FAKE_HOOK.
WORKS_HOOK = WORKS.replace(
    "subprocess.run(['git', 'add', '-A'], check=True)\n",
    "if ident == os.environ.get('FAKE_HOOK'):\n"
    "    os.makedirs('p/hooks', exist_ok=True)\n"
    "    os.makedirs('p/.claude-plugin', exist_ok=True)\n"
    "    open('p/.claude-plugin/plugin.json', 'w').write('{}')\n"
    "    open('p/hooks/h.py', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n", 1)


def run(tmp, ids, breaks="", hook=""):
    root = build_repo(tmp, [item(i) for i in ids])
    calls = Path(tmp) / "suite-calls"
    (root / "tests").mkdir(exist_ok=True)
    suite = root / "tests" / "run-all.sh"
    suite.write_text(FAKE_SUITE.format(calls=str(calls)))
    suite.chmod(0o755)
    _commits(root, "suite")
    binv = fake_claude(tmp, WORKS_HOOK)
    p, _ = run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", SUITE],
                     extra_env={"FAKE_QUEBRA": breaks, "FAKE_HOOK": hook})
    seen = ([json.loads(l) for l in calls.read_text().splitlines()]
            if calls.exists() else [])
    return root, p, seen, ledger_of(root)


def ev(ledger, kind, **match):
    return [e for e in ledger if e.get("evento") == kind
            and all(e.get(k) == v for k, v in match.items())]


def test_green_queue_runs_one_suite_per_pair():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2", "a3"])
        check("3 itens done", all(status(root, i)["status"] == "done"
                                  for i in ("a1", "a2", "a3")), p.stdout[-800:])
        check("a suíte rodou 2 vezes para 3 itens (a1 sozinho, a2+a3 juntos)",
              len(seen) == 2, str(seen))
        check("a 2ª rodada já tem os commits de a2 e a3",
              len(seen) == 2 and {"a2.txt", "a3.txt"} <= set(seen[1]["files"]),
              str(seen))
        check("o registro grava verify_adiado para a2",
              len(ev(led, "verify_adiado", id="a2")) == 1, str(led))
        check("o registro dá a2 como verde junto com a3",
              ev(led, "verify", id="a2", verde=True, par="a3"), str(led))


def test_red_pair_with_green_middle_takes_off_only_the_second():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2", "a3"], breaks="a3")
        mid = ev(led, "verify", id="a2", no_meio=True)
        check("o par vermelho roda os arquivos com falha no commit do meio",
              len(mid) == 1 and mid[0]["verde"] is True
              and mid[0].get("arquivos") == ["tests/test_q.py"], str(mid))
        check("o meio roda só o arquivo com falha",
              any(c["argv"] == ["tests/test_q.py"] and c["files"] == ["a1.txt", "a2.txt"]
                  for c in seen), str(seen))
        check("a2 fica done", status(root, "a2")["status"] == "done",
              str(status(root, "a2")))
        check("só a3 tem volta vermelha",
              ev(led, "volta_vermelha", id="a3") and not ev(led, "volta_vermelha", id="a2"),
              str(led))


def test_red_middle_takes_off_the_first_and_the_second_goes_back_clean():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2", "a3"], breaks="a2")
        mid = ev(led, "verify", id="a2", no_meio=True)
        check("o meio fica vermelho", len(mid) >= 1 and mid[0]["verde"] is False,
              str(mid))
        check("a2 tem volta vermelha", ev(led, "volta_vermelha", id="a2"), str(led))
        check("a3 não tem volta vermelha própria",
              not ev(led, "volta_vermelha", id="a3"), str(led))
        check("a3 termina done (voltou para pending e refez)",
              status(root, "a3")["status"] == "done", str(status(root, "a3")))
        check("a1 fica done", status(root, "a1")["status"] == "done",
              str(status(root, "a1")))
        check("a2 não fica done (quebra a suíte toda vez)",
              status(root, "a2")["status"] != "done", str(status(root, "a2")))


def test_item_waiting_for_its_pair_is_checked_before_the_run_closes():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2"])
        check("a2 adiado", ev(led, "verify_adiado", id="a2"), str(led))
        check("a2 conferido no próprio commit antes de fechar",
              ev(led, "verify", id="a2", adiado=True, verde=True), str(led))
        check("a suíte rodou 2 vezes", len(seen) == 2, str(seen))
        ends = [i for i, e in enumerate(led) if e.get("evento") == "run_end"]
        checks = [i for i, e in enumerate(led)
                  if e.get("evento") == "verify" and e.get("adiado")]
        check("a conferência vem antes do run_end",
              ends and checks and checks[-1] < ends[0], str(led))


def test_deferred_red_at_the_end_takes_the_item_off():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2"], breaks="a2")
        check("a2 tem volta vermelha", ev(led, "volta_vermelha", id="a2"), str(led))
        check("a2 não fica done", status(root, "a2")["status"] != "done",
              str(status(root, "a2")))
        branch = [e for e in led if e["evento"] == "run_start"][0]["branch"]
        import subprocess
        log = subprocess.run(["git", "log", "--format=%s", branch], cwd=root,
                             capture_output=True, text=True).stdout.split()
        check("a2 sai da branch do run", "a2" not in log, str(log))


def test_item_that_changes_a_hook_is_not_deferred():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2", "a3"], hook="a2")
        check("a2 mexe em hook e não é adiado",
              not ev(led, "verify_adiado", id="a2"), str(led))
        check("a2 tem a própria suíte",
              ev(led, "verify", id="a2", verde=True) and
              not ev(led, "verify", id="a2", par="a3"), str(led))


def main():
    print("cepa-run — suíte por par de itens\n")
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
