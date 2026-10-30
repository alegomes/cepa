#!/usr/bin/env python3
"""Tests: `cepa-until` records the version of the `twg` CLI in each `item_start`.

Run with `python3 tests/test_cepa_until_twg_version.py` (needs PyYAML).

## Why this record exists

`twg` (Atlassian) installs a `launchd` scheduler
(`com.atlassian.twg.upkeep.plist`) that checks for updates on its own every 12
minutes — the version may change BETWEEN two cards of the SAME unattended run, with no
signal at all. `cepa-until` reads the installed version at EACH item (never
cached at `run_start`) and records it in the `item_start` event of the run's `.jsonl` — it is
the concrete proof of which tool produced which item.

The test that matters most here is the one that swaps IN THE MIDDLE of the run: the fake `claude`
rewrites the fake `twg` script during the processing of the first item, and
the ledger's two `item_start`s must carry different versions.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def build_repo(tmp, item_list):
    root = Path(tmp) / "repo"
    root.mkdir(parents=True, exist_ok=True)
    d = root / ".claude" / "programs" / "fila"
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "program": "fila",
             "source": "teste", "items": item_list}
    (d / "plan.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                 encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root


def item(ident, status="pending", human_pending=None):
    return {"id": ident, "title": f"item {ident}", "why": "porque",
            "status": status, "blocked_by": [], "human_pending": human_pending,
            "evidence": None}


def fake_claude(tmp, body):
    """Identical to the helper in test_cepa_until.py: a fake `claude` on the PATH."""
    binv = Path(tmp) / "bin"
    binv.mkdir(exist_ok=True)
    script = binv / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import os, sys, yaml, json, time\n"
        "PLANO = os.environ['FAKE_PLANO']\n"
        "ARGS = sys.argv[1:]\n"
        "def carrega():\n"
        "    return yaml.safe_load(open(PLANO, encoding='utf-8'))\n"
        "def grava(p):\n"
        "    open(PLANO, 'w', encoding='utf-8').write("
        "yaml.safe_dump(p, allow_unicode=True))\n"
        "def marca(ident, **campos):\n"
        "    p = carrega()\n"
        "    for it in p['items']:\n"
        "        if it['id'] == ident:\n"
        "            it.update(campos)\n"
        "    grava(p)\n"
        "def primeiro_pendente():\n"
        "    for it in carrega()['items']:\n"
        "        if it['status'] == 'pending' and not it.get('human_pending'):\n"
        "            return it['id']\n"
        "    return None\n"
        "with open(os.environ['FAKE_CHAMADAS'], 'a') as f:\n"
        "    f.write(json.dumps(ARGS) + '\\n')\n"
        + body + "\n",
        encoding="utf-8")
    script.chmod(0o755)
    return binv


def fake_twg(binv, version):
    """Fake `twg`: sh script that echoes `version` in free text (the same free
    form as the real CLI, which the doctor/until regex extracts)."""
    script = binv / "twg"
    script.write_text(f"#!/bin/sh\necho 'twg version {version}'\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def essential_paths(tmp):
    """A directory with only symlinks to git/python3 — used when the test wants to
    guarantee that NO real `twg` of the machine of whoever runs the test enters the
    PATH (this machine has a real installation, see docs/env-manifest.md)."""
    d = Path(tmp) / "minpath"
    d.mkdir(exist_ok=True)
    for given_name in ("git", "python3"):
        real = shutil.which(given_name)
        if real:
            target = d / given_name
            if not target.exists():
                target.symlink_to(real)
    return d


def run_until(root, binv, plan, args, timeout=120, extra_env=None, path=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    env["PATH"] = f"{binv}:{path}" if path is not None else f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plan)
    env.setdefault("CEPA_WORKTREE_HOME", str(Path(root).parent / "worktrees"))
    calls = Path(root).parent / "chamadas.jsonl"
    env["FAKE_CHAMADAS"] = str(calls)
    args = list(args)
    if "--verify" not in args and "--no-verify" not in args:
        args.append("--no-verify")
    if "--no-analysis" not in args:
        args.append("--no-analysis")
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root)]
                       + args, capture_output=True, text=True, env=env,
                       timeout=timeout)
    lines = []
    if calls.exists():
        lines = [json.loads(l) for l in calls.read_text().splitlines() if l.strip()]
    return p, lines


def ledger_of(root):
    d = Path(root) / ".claude" / "programs" / "fila" / "until"
    events = []
    for f in sorted(d.glob("*.jsonl")):
        events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return events


def item_starts(root):
    return [e for e in ledger_of(root) if e.get("evento") == "item_start"]


def test_item_start_brings_the_installed_twg_version():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        fake_twg(binv, "1.3.1")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        run_until(root, binv, plan, ["--for", "2h"])
        starts = item_starts(root)
        check("houve 1 item_start", len(starts) == 1, json.dumps(starts))
        check("...com twg_version 1.3.1",
              starts and starts[0].get("twg_version") == "1.3.1",
              json.dumps(starts))


def test_without_twg_on_path_writes_null():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        # no fake `twg` created, and the PATH is restricted to git/python3 — the CLI
        # simply does not exist (not even the real one of the machine running the test).
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        run_until(root, binv, plan, ["--for", "2h"], path=str(essential_paths(tmp)))
        starts = item_starts(root)
        check("houve 1 item_start", len(starts) == 1, json.dumps(starts))
        check("...com twg_version null (twg ausente do PATH)",
              starts and starts[0].get("twg_version") is None,
              json.dumps(starts))


def test_version_changing_mid_run_shows_in_both_item_starts():
    """The case that matters: the fake `claude` rewrites the fake `twg` during the
    processing of the FIRST item (simulating the `upkeep` scheduler updating
    the CLI by itself in the middle of the night). The two `item_start`s must carry
    DIFFERENT versions — the version is read at each item, never cached."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(
            tmp,
            "if primeiro_pendente() == 'a1':\n"
            "    open(os.environ['FAKE_TWG'], 'w').write("
            "\"#!/bin/sh\\necho 'twg version 1.4.0'\\n\")\n"
            "marca(primeiro_pendente(), status='done')")
        twg_path = fake_twg(binv, "1.3.1")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        run_until(root, binv, plan, ["--for", "2h"],
             extra_env={"FAKE_TWG": str(twg_path)})
        starts = item_starts(root)
        check("houve 2 item_start", len(starts) == 2, json.dumps(starts))
        if len(starts) == 2:
            v1 = starts[0].get("twg_version")
            v2 = starts[1].get("twg_version")
            check("1º item_start com a versão de ANTES da troca (1.3.1)",
                  v1 == "1.3.1", json.dumps(starts))
            check("2º item_start com a versão de DEPOIS da troca (1.4.0)",
                  v2 == "1.4.0", json.dumps(starts))
            check("as duas versões são diferentes entre si",
                  v1 != v2, json.dumps(starts))


def main():
    print("cepa-until — twg_version em cada item_start\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
