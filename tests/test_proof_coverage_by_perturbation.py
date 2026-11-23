#!/usr/bin/env python3
"""L2 coverage measured by perturbation, and an owner-signed waiver that holds.

Origin (BACKLOG.md § "A dispensa de cobertura aceita pelo dono não é lida pelo
esquema de prova...", fb-20261123-8, fb-20261020-1, fb-20261028-2): this repo has
no Python coverage tool, so `l2_coverage` was always `assumed` and 28 of 33 items
of run all/2026-11-21-1244 came back NEEDS-HUMAN, even when every deliberate break
turned a test red and even when the owner had already signed a waiver.

  A. `l2_coverage.technique: perturbation` + `status: pass` is valid only with
     `l3_load_bearing.perturbation.status: pass` and no `uncovered_lines`;
     `assumed` next to a passing perturbation with nothing uncovered is blocked
     under ANY verdict (the perturbation already measured coverage).
  B. `l2_coverage.status: waived` + `waivers: [...]` is valid only when every
     file it must cover has a valid, unexpired, owner-signed `nada-a-provar`
     waiver (looked up in the repo and in the main clone of a linked worktree).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "build-hex" / "hooks" / "proof-verdict-guard.py"
sys.path.insert(0, str(REPO / "board-flow" / "bin"))
FAILURES = []

TMP = Path(tempfile.mkdtemp(prefix="proof-cov-")).resolve()
PAST = (date.today() - timedelta(days=30)).isoformat()
FUTURE = (date.today() + timedelta(days=300)).isoformat()


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def make_repo(name):
    root = TMP / name
    (root / "docs" / "proof").mkdir(parents=True)
    (root / ".claude" / "waivers").mkdir(parents=True)
    return root


def waiver(root, scope, status=None, drop=None, trigger=None, motivo="nada-a-provar",
           escopo=None, fname=None):
    d = {"motivo": motivo, "escopo": escopo or scope, "razao": "no coverage tool",
         "autor": "alegomes", "criado_em": "2026-11-10",
         "revisit_trigger": trigger or "when the repo gains a coverage tool"}
    if status:
        d["status"] = status
    if drop:
        d.pop(drop)
    import yaml
    path = Path(root) / ".claude" / "waivers" / (fname or f"nada-a-provar--{scope.replace('/', '-')}.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))
    return path


def scope_yaml(classes):
    body = "scope:\n  changed_classes:\n"
    for c in classes:
        body += (f'    - class: "{c}"\n      module: bin\n'
                 "      external_observable: false\n      substituted_by_double: none\n")
    return body


def artifact(verdict="proven", l2=None, perturbation="pass", classes=("common/bin/cepa-plan",)):
    l2 = l2 if l2 is not None else ("  l2_coverage:\n    status: pass\n"
                                    "    technique: perturbation\n    uncovered_lines: []\n"
                                    '    run: "no coverage tool; 3 perturbations went red"\n')
    return (f"schema_version: 2\ncard: X-1\nverdict: {verdict}\n{scope_yaml(classes)}"
            "levels:\n  l3_load_bearing:\n    pit:\n      status: absent\n"
            f"    perturbation:\n      status: {perturbation}\n"
            f"{l2}  l4_adversarial_input:\n    status: clean\n")


def l2_block(status, technique=None, uncovered=None, waivers=None):
    s = f"  l2_coverage:\n    status: {status}\n"
    if technique:
        s += f"    technique: {technique}\n"
    if uncovered is not None:
        s += "    uncovered_lines: " + json.dumps(uncovered) + "\n"
    if waivers is not None:
        s += "    waivers: " + json.dumps(waivers) + "\n"
    return s + '    run: "r"\n'


def run(root, content, name="X-1.yaml"):
    fp = str(Path(root) / "docs" / "proof" / name)
    payload = json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": fp, "content": content},
                          "cwd": str(root)})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True)


def blocked(r, *needles):
    return r.returncode == 2 and all(n in r.stderr for n in needles)


# ── A. coverage measured by perturbation ───────────────────────────────────
a = make_repo("a")
r = run(a, artifact())
check("proven + l2 pass/perturbation + L3 pass + nothing uncovered -> allowed",
      r.returncode == 0, r.stderr[:300])

r = run(a, artifact(perturbation="skipped"))
check("...with L3 perturbation skipped -> blocked by the L2 perturbation rule",
      blocked(r, "technique: perturbation"), r.stderr[:300])

r = run(a, artifact(l2=l2_block("pass", "perturbation", ["common/bin/cepa-plan:10-12"])))
check("...with non-empty uncovered_lines -> blocked, names uncovered_lines",
      blocked(r, "uncovered_lines"), r.stderr[:300])

r = run(a, artifact(perturbation="survived"))
check("...with perturbation survived -> blocked", r.returncode == 2, r.stderr[:300])

r = run(a, artifact("needs-human", l2_block("assumed", uncovered=[])))
check("needs-human + assumed + perturbation pass + nothing uncovered -> blocked",
      blocked(r, "technique: perturbation"), r.stderr[:300])

r = run(a, artifact("needs-human", "  l2_coverage:\n    status: assumed\n    run: r\n"))
check("...uncovered_lines absent -> blocked too", blocked(r, "technique: perturbation"),
      r.stderr[:300])

r = run(a, artifact("needs-human", l2_block("assumed", uncovered=["common/bin/cepa-plan:10-12"])))
check("needs-human + assumed + uncovered listing X, no waiver -> allowed",
      r.returncode == 0, r.stderr[:300])

r = run(a, artifact("needs-human", l2_block("assumed", uncovered=["common/bin/cepa-plan:10-12"]),
                    perturbation="skipped"))
check("needs-human + assumed + perturbation skipped -> allowed (nothing was measured)",
      r.returncode == 0, r.stderr[:300])

# ── B. waivers ─────────────────────────────────────────────────────────────
WV = [".claude/waivers/nada-a-provar--common-bin-cepa-plan.yaml"]
b = make_repo("b")
waiver(b, "common/bin/cepa-plan")
UNC = ["common/bin/cepa-plan:10-12"]

r = run(b, artifact("needs-human", l2_block("assumed", uncovered=UNC)))
check("assumed + uncovered X + valid waiver for X -> blocked, says write `waived`",
      blocked(r, "status: waived", "waivers:"), r.stderr[:300])

r = run(b, artifact("needs-human", "  l2_coverage:\n    status: assumed\n    run: r\n",
                    perturbation="skipped"))
check("assumed + valid waiver for every changed class -> blocked (rule 4)",
      blocked(r, "status: waived"), r.stderr[:300])

r = run(b, artifact(l2=l2_block("waived", waivers=WV)))
check("proven + l2 waived + valid waiver for every changed class -> allowed",
      r.returncode == 0, r.stderr[:300])

r = run(b, artifact(l2=l2_block("waived", uncovered=UNC, waivers=WV)))
check("proven + l2 waived + uncovered_lines resolving to the waived file -> allowed",
      r.returncode == 0, r.stderr[:300])

r = run(b, artifact("needs-human", l2_block("waived", uncovered=UNC, waivers=WV)))
check("needs-human + l2 waived + valid waiver -> allowed", r.returncode == 0, r.stderr[:300])

# waiver that does not count
for label, kw in (("status proposta", dict(status="proposta")),
                  ("status recusada", dict(status="recusada")),
                  ("missing autor", dict(drop="autor")),
                  ("expired date", dict(trigger=f"on {PAST} or when it changes")),
                  ("wrong motivo", dict(motivo="teste-cego")),
                  ("other file", dict(escopo="common/bin/outro"))):
    d = make_repo("bad-" + label.replace(" ", "-"))
    waiver(d, "common/bin/cepa-plan", **kw)
    r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
    check(f"proven + waived + waiver with {label} -> blocked", blocked(r, "cepa-plan"),
          r.stderr[:300])
    r = run(d, artifact("needs-human", l2_block("waived", waivers=WV)))
    check(f"needs-human + waived + waiver with {label} -> blocked", r.returncode == 2,
          r.stderr[:300])

r = run(b, artifact(l2=l2_block("waived", waivers=WV),
                    classes=("common/bin/cepa-plan", "common/bin/other")))
check("waived but only one of two changed classes has a waiver -> blocked, names the other",
      blocked(r, "common/bin/other"), r.stderr[:300])

f = make_repo("future")
waiver(f, "common/bin/cepa-plan", trigger=f"until {FUTURE}")
r = run(f, artifact(l2=l2_block("waived", waivers=WV)))
check("waiver with a future date holds", r.returncode == 0, r.stderr[:300])

n = make_repo("none")
r = run(n, artifact("needs-human", l2_block("waived", waivers=WV)))
check("needs-human + waived with no waiver at all -> blocked", r.returncode == 2,
      r.stderr[:300])

e = make_repo("empty")
waiver(e, "common/bin/cepa-plan")
r = run(e, artifact(l2=l2_block("waived", waivers=WV), classes=()).replace(
    "  changed_classes:\n", "  changed_classes: []\n"))
check("waived with nothing to cover (no classes, no uncovered) -> blocked", r.returncode == 2,
      r.stderr[:300])

# loose scope key
lo = make_repo("loose")
waiver(lo, "common/bin/cepa-plan", escopo="Common Bin CepaPlan")
r = run(lo, artifact(l2=l2_block("waived", uncovered=UNC, waivers=WV)))
check("loose scope key matches the file of an uncovered_lines entry", r.returncode == 0,
      r.stderr[:300])

# main-clone lookup from a linked worktree
main = TMP / "mainclone"
main.mkdir()
G = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
subprocess.run(G + ["init", "-q", "-b", "main", str(main)], check=True)
(main / "README").write_text("x")
subprocess.run(G + ["-C", str(main), "add", "README"], check=True)
subprocess.run(G + ["-C", str(main), "commit", "-q", "-m", "i"], check=True)
wt = TMP / "linked-wt"
subprocess.run(G + ["-C", str(main), "worktree", "add", "-q", "-b", "wt", str(wt)], check=True)
(wt / "docs" / "proof").mkdir(parents=True)
waiver(main, "common/bin/cepa-plan")        # only in the main clone
r = run(wt, artifact(l2=l2_block("waived", waivers=WV)))
check("waiver only in the main clone is found from a linked worktree", r.returncode == 0,
      r.stderr[:300])
r = run(wt, artifact("needs-human", "  l2_coverage:\n    status: assumed\n    run: r\n",
                     perturbation="skipped"))
check("...and the assumed -> waived rule sees it too", blocked(r, "status: waived"),
      r.stderr[:300])

# top-level WAIVER_KEYS block stays; the nested `waivers:` is not caught by it
r = run(b, artifact(l2=l2_block("waived", waivers=WV)))
check("nested l2_coverage.waivers is not the top-level waiver key", r.returncode == 0,
      r.stderr[:300])
r = run(b, "waiver_proposto: .claude/waivers/x.yaml\n" + artifact(l2=l2_block("waived", waivers=WV)))
check("top-level waiver_proposto still blocks proven", blocked(r, "waiver_proposto"),
      r.stderr[:300])

# fallback without PyYAML: structure invisible, `waived` cannot be verified
broken = artifact(l2=l2_block("waived", waivers=WV)) + "broken: [unclosed\n"
r = run(b, broken)
check("fallback: proven + waived -> blocked, waiver could not be verified",
      blocked(r, "could not be verified"), r.stderr[:300])
r = run(b, broken.replace("verdict: proven", "verdict: needs-human"))
check("fallback: needs-human + waived -> allowed (rules 2 and 4 do not fire)",
      r.returncode == 0, r.stderr[:300])

# old behavior intact
r = run(a, artifact(l2="  l2_coverage:\n    status: assumed\n    uncovered_lines: ['common/bin/cepa-plan:1']\n    run: r\n",
                    perturbation="skipped"))
check("proven + assumed + perturbation skipped -> still blocked, needs-human",
      blocked(r, "needs-human"), r.stderr[:300])
r = run(a, artifact(l2="  l2_coverage:\n    status: pass\n    run: r\n"))
check("proven + plain l2 pass (no technique) -> allowed", r.returncode == 0, r.stderr[:300])
r = run(a, artifact(l2="  l2_coverage:\n    status: pass\n    run: r\n", perturbation="skipped"))
check("proven + plain pass + perturbation skipped -> still blocked by the old rule",
      r.returncode == 2, r.stderr[:300])

# ── review fixes: malformed uncovered_lines, relative path, partial waived ──
for label, val in (("string", "'c/D:1-9'"), ("dict", "{a: 1}")):
    r = run(a, artifact(l2=f"  l2_coverage:\n    status: pass\n    technique: perturbation\n"
                           f"    uncovered_lines: {val}\n    run: r\n"))
    check(f"proven + perturbation pass + uncovered_lines as a {label} -> blocked",
          blocked(r, "technique: perturbation"), r.stderr[:300])

rel = make_repo("rel")
waiver(rel, "common/bin/cepa-plan")
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": "docs/proof/X-1.yaml",
                                     "content": artifact(l2=l2_block("waived", waivers=WV))},
                      "cwd": str(rel)})
r = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True)
check("relative file_path: waiver under payload cwd is found", r.returncode == 0, r.stderr[:300])

pw = make_repo("partial")
waiver(pw, "a/B")
PC = ("a/B", "c/D")
r = run(pw, artifact(l2=l2_block("waived", uncovered=["a/B:1"], waivers=WV), classes=PC))
check("waived + partial uncovered_lines + perturbation pass -> allowed", r.returncode == 0,
      r.stderr[:300])
r = run(pw, artifact("needs-human", l2_block("waived", uncovered=["a/B:1"], waivers=WV),
                     perturbation="skipped", classes=PC))
check("waived + partial uncovered_lines + perturbation skipped -> blocked",
      blocked(r, "perturbation did not pass"), r.stderr[:300])
r = run(pw, artifact(l2=l2_block("waived", uncovered=[], waivers=WV), classes=PC))
check("waived + empty uncovered_lines + waiver only for a/B of two -> blocked, names c/D",
      blocked(r, "c/D"), r.stderr[:300])

# telemetry: distinct blocked= per new block
tele = os.environ.get("CEPA_TELEMETRY_DIR")
events = ""
if tele:
    for p in Path(tele).glob("events-*.jsonl"):
        events += p.read_text()
for tag in ("l2_perturbation_unbacked", "l2_assumed_but_perturbed",
            "l2_waived_unbacked", "l2_assumed_but_waived"):
    check(f"telemetry blocked={tag}", f'"blocked": "{tag}"' in events)

# ── twin agreement with board-flow/bin/waivers.py ──────────────────────────
spec = importlib.util.spec_from_file_location("guard", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
import waivers as W  # noqa: E402

CASES = {
    "valid": dict(),
    "proposta": dict(status="proposta"),
    "recusada": dict(status="recusada"),
    "missing-field": dict(drop="razao"),
    "expired": dict(trigger=f"until {PAST}"),
    "future": dict(trigger=f"until {FUTURE}"),
    "loose-key": dict(escopo="Common  Bin/Cepa_Plan"),
    "wrong-motivo": dict(motivo="teste-cego"),
}
for label, kw in CASES.items():
    t = make_repo("twin-" + label)
    waiver(t, "common/bin/cepa-plan", **kw)
    real = W.applicable(W.load(str(t)), "nada-a-provar", "common/bin/cepa-plan")
    twin = guard.applicable_waiver(guard.load_waivers([t / ".claude" / "waivers"]),
                                   "common/bin/cepa-plan")
    check(f"twin agrees with waivers.py: {label}", bool(real) == bool(twin),
          f"real={bool(real)} twin={bool(twin)}")

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all proof coverage-by-perturbation tests passed")
