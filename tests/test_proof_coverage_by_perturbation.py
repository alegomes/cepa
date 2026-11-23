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
# `isolate()` points at a FIXED ledger dir that is never emptied, so a tag assertion
# would read events of earlier executions. This file takes a fresh dir per execution.
TELE = Path(tempfile.mkdtemp(prefix="proof-cov-tele-")).resolve()
os.environ["CEPA_TELEMETRY_DIR"] = str(TELE)

REPO = Path(__file__).resolve().parent.parent
HOOK = Path(os.environ.get("CEPA_PROOF_GUARD_HOOK")
            or REPO / "build-hex" / "hooks" / "proof-verdict-guard.py")
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


def ledger():
    """Every line of the (fresh) telemetry ledger, in file order."""
    out = []
    for p in sorted(TELE.glob("events-*.jsonl")):
        out += p.read_text().splitlines()
    return out


def hook(payload, cwd=None):
    """Runs the hook once; `.events` holds exactly what THIS call appended to the ledger."""
    before = ledger()
    r = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                       text=True, cwd=cwd, env=dict(os.environ, CEPA_TELEMETRY_DIR=str(TELE)))
    r.events = [json.loads(line) for line in ledger()[len(before):]]
    return r


def run(root, content, name="X-1.yaml"):
    fp = str(Path(root) / "docs" / "proof" / name)
    payload = json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": fp, "content": content},
                          "cwd": str(root)})
    return hook(payload)


def tagged(label, r, tag):
    """This call appended exactly one `proof_verdict` event, and its `blocked` is `tag`
    (None: an allowed call, the hook emits no `blocked` key)."""
    ev = r.events
    ok = (len(ev) == 1 and ev[0].get("event") == "proof_verdict"
          and ev[0].get("blocked") == tag)
    check(f"telemetry [{tag}]: {label}", ok, f"events={ev}")


def blocked(r, *needles):
    return r.returncode == 2 and all(n in r.stderr for n in needles)


# ── A. coverage measured by perturbation ───────────────────────────────────
a = make_repo("a")
r = run(a, artifact())
check("proven + l2 pass/perturbation + L3 pass + nothing uncovered -> allowed",
      r.returncode == 0, r.stderr[:300])
tagged("allowed proven", r, None)

r = run(a, artifact(perturbation="skipped"))
check("...with L3 perturbation skipped -> blocked by the L2 perturbation rule",
      blocked(r, "technique: perturbation"), r.stderr[:300])

r = run(a, artifact(l2=l2_block("pass", "perturbation", ["common/bin/cepa-plan:10-12"])))
check("...with non-empty uncovered_lines -> blocked, names uncovered_lines",
      blocked(r, "uncovered_lines"), r.stderr[:300])
tagged("pass/perturbation + uncovered_lines", r, "l2_perturbation_unbacked")

r = run(a, artifact(perturbation="survived"))
check("...with perturbation survived -> blocked", r.returncode == 2, r.stderr[:300])

r = run(a, artifact("needs-human", l2_block("assumed", uncovered=[])))
check("needs-human + assumed + perturbation pass + nothing uncovered -> blocked",
      blocked(r, "technique: perturbation"), r.stderr[:300])
tagged("assumed next to a passing perturbation", r, "l2_assumed_but_perturbed")

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
tagged("assumed with a valid waiver", r, "l2_assumed_but_waived")

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
tagged("waived, one of two classes unwaived (missing-waiver site)", r, "l2_waived_unbacked")

f = make_repo("future")
waiver(f, "common/bin/cepa-plan", trigger=f"until {FUTURE}")
r = run(f, artifact(l2=l2_block("waived", waivers=WV)))
check("waiver with a future date holds", r.returncode == 0, r.stderr[:300])

n = make_repo("none")
r = run(n, artifact("needs-human", l2_block("waived", waivers=WV)))
check("needs-human + waived with no waiver at all -> blocked", r.returncode == 2,
      r.stderr[:300])
tagged("waived, no waiver at all (missing-waiver site)", r, "l2_waived_unbacked")

e = make_repo("empty")
waiver(e, "common/bin/cepa-plan")
r = run(e, artifact(l2=l2_block("waived", waivers=WV), classes=()).replace(
    "  changed_classes:\n", "  changed_classes: []\n"))
check("waived with nothing to cover (no classes, no uncovered) -> blocked", r.returncode == 2,
      r.stderr[:300])
tagged("waived, nothing to cover (site 1)", r, "l2_waived_unbacked")

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
tagged("no-PyYAML fallback", r, "l2_waived_unverifiable")
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

# The process cwd is a neutral dir outside any git repo, so the REAL repo's
# `.claude/waivers` can never decide these outcomes; the scope exists only in the temp repo.
neutral = TMP / "neutral-cwd"
neutral.mkdir()
UNIQ = "zz/only-in-temp/Thing.py"
rel = make_repo("rel")
UWV = [str(waiver(rel, UNIQ).relative_to(rel))]
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": "docs/proof/X-1.yaml",
                                     "content": artifact(l2=l2_block("waived", waivers=UWV),
                                                         classes=(UNIQ,))},
                      "cwd": str(rel)})
r = hook(payload, cwd=str(neutral))
check("relative file_path, no prefix: waiver under payload cwd is found (process cwd elsewhere)",
      r.returncode == 0, r.stderr[:300])
rel_none = make_repo("rel-none")
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": "docs/proof/X-1.yaml",
                                     "content": artifact(l2=l2_block("waived", waivers=UWV),
                                                         classes=(UNIQ,))},
                      "cwd": str(rel_none)})
r = hook(payload, cwd=str(neutral))
check("...and a payload cwd without that waiver -> blocked (the lookup is not satisfied elsewhere)",
      r.returncode == 2, r.stderr[:300])

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
tagged("waived + uncovered_lines, perturbation not passing (site 2)", r, "l2_waived_unbacked")
r = run(pw, artifact(l2=l2_block("waived", uncovered=[], waivers=WV), classes=PC))
check("waived + empty uncovered_lines + waiver only for a/B of two -> blocked, names c/D",
      blocked(r, "c/D"), r.stderr[:300])
tagged("waived, c/D unwaived (missing-waiver site)", r, "l2_waived_unbacked")

# ── mutation-survivor cases (each pins one rule of the L2 block) ───────────
TODAY = date.today()
sv = make_repo("surv")
waiver(sv, "common/bin/cepa-plan")
UNC1 = ["common/bin/cepa-plan:10-12"]
NO_CLASSES = lambda c: c.replace("  changed_classes:\n", "  changed_classes: []\n")  # noqa: E731

# 1. rule 1 fires only for technique: perturbation
r = run(sv, artifact(l2=l2_block("pass", uncovered=UNC1)))
check("proven + plain l2 pass (no technique) + uncovered_lines + perturbation pass -> allowed",
      r.returncode == 0, r.stderr[:300])

# 2. waived + empty uncovered_lines does not need the perturbation to pass
r = run(sv, artifact("needs-human", l2_block("waived", uncovered=[], waivers=WV),
                     perturbation="skipped"))
check("waived + empty uncovered_lines + every class waived + perturbation skipped -> allowed",
      r.returncode == 0, r.stderr[:300])

# 3. assumed with nothing to cover is not "already waived"
r = run(sv, artifact("needs-human", "  l2_coverage:\n    status: assumed\n    run: r\n",
                     perturbation="skipped", classes=()).replace(
    "  changed_classes:\n", "  changed_classes: []\n"))
check("assumed + nothing to cover + perturbation skipped -> allowed (no waiver rule)",
      r.returncode == 0, r.stderr[:300])
r = run(sv, "schema_version: 2\ncard: X-1\nverdict: needs-human\n"
            "levels:\n  l3_load_bearing:\n    perturbation:\n      status: skipped\n"
            "  l2_coverage:\n    status: assumed\n    run: r\n")
check("...same with no scope at all -> allowed", r.returncode == 0, r.stderr[:300])

# 4. every field of WAIVER_REQUIRED counts
for fld in ("revisit_trigger", "criado_em"):
    d = make_repo("req-" + fld)
    waiver(d, "common/bin/cepa-plan", drop=fld)
    r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
    check(f"proven + waived + waiver missing {fld} -> blocked", blocked(r, "cepa-plan"),
          r.stderr[:300])

# 5. a waiver whose date is TODAY still holds
d = make_repo("today")
waiver(d, "common/bin/cepa-plan", trigger=f"until {TODAY.isoformat()}")
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("waiver whose revisit_trigger date is today still holds", r.returncode == 0,
      r.stderr[:300])

# 6. non-mapping YAML files in .claude/waivers/ never crash the hook
d = make_repo("junk")
(d / ".claude" / "waivers" / "empty.yaml").write_text("")
(d / ".claude" / "waivers" / "list.yaml").write_text("- a\n- b\n")
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("empty + list yaml next to no valid waiver -> exit 2, no crash",
      r.returncode == 2 and "Traceback" not in r.stderr, f"{r.returncode} {r.stderr[:300]}")
waiver(d, "common/bin/cepa-plan")
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("empty + list yaml next to a valid waiver -> the valid one is found (exit 0)",
      r.returncode == 0 and "Traceback" not in r.stderr, f"{r.returncode} {r.stderr[:300]}")

# 7. relative file_path resolves against the PAYLOAD cwd, not the process cwd
rr = make_repo("relroot")
proj = rr / "proj"
(proj / "docs" / "proof").mkdir(parents=True)
waiver(proj, "common/bin/cepa-plan")
elsewhere = TMP / "elsewhere"
elsewhere.mkdir()
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": "proj/docs/proof/X-1.yaml",
                                     "content": artifact(l2=l2_block("waived", waivers=WV))},
                      "cwd": str(rr)})
r = hook(payload, cwd=str(elsewhere))
check("relative file_path with a prefix: waiver found via payload cwd, process cwd elsewhere",
      r.returncode == 0, r.stderr[:300])

# 8. status / technique are compared case-insensitively
r = run(sv, artifact("needs-human", l2_block("Assumed", uncovered=[])))
check("status: Assumed (capitalised) + perturbation pass + nothing uncovered -> blocked",
      blocked(r, "technique: perturbation"), r.stderr[:300])
r = run(sv, artifact(l2=l2_block("pass", "Perturbation", UNC1)))
check("technique: Perturbation + pass + uncovered_lines + proven -> blocked by rule 1",
      blocked(r, "uncovered_lines"), r.stderr[:300])
r = run(n, artifact("needs-human", l2_block("Waived", waivers=WV)))
check("status: Waived (capitalised) with no waiver -> blocked", blocked(r, "waived"),
      r.stderr[:300])

# 9. blank uncovered_lines entries are not uncovered hunks
r = run(sv, artifact(l2=l2_block("pass", "perturbation", ["", "  "])))
check("uncovered_lines of blank strings is empty -> proven + pass/perturbation allowed",
      r.returncode == 0, r.stderr[:300])

# 10. the file part of an uncovered_lines entry is split at the LAST colon
for fpart in ("pkg:mod/a.py", "C:/proj/a/B.py"):
    d = make_repo("colon-" + fpart.replace(":", "_").replace("/", "_"))
    waiver(d, fpart, fname="nada-a-provar--colon.yaml")
    r = run(d, artifact(l2=l2_block("waived", uncovered=[fpart + ":10-12"], waivers=WV)))
    check(f"uncovered_lines entry with a colon in the file ({fpart}) + waiver for it -> allowed",
          r.returncode == 0, r.stderr[:300])

# 11. non-dict entries of changed_classes are ignored
d = make_repo("junkclasses")
waiver(d, "common/bin/cepa-plan")
c = artifact("needs-human", l2_block("waived", uncovered=[], waivers=WV))
c = c.replace("  changed_classes:\n", "  changed_classes:\n    - bare-string\n    - null\n", 1)
r = run(d, c)
check("changed_classes with a bare string and null next to a waived dict -> allowed, no crash",
      r.returncode == 0 and "Traceback" not in r.stderr, f"{r.returncode} {r.stderr[:300]}")

# a malformed sibling must not switch the L2 rules off (the guard swallows the error)
r = run(n, c)
check("...and with no waiver for the dict's class -> still blocked (rules not silently off)",
      blocked(r, "cepa-plan"), r.stderr[:300])

# 12. a perturbation that did not PASS backs nothing
r = run(a, artifact("unproven", l2_block("assumed", uncovered=[]), perturbation="survived"))
check("unproven + assumed + empty uncovered + perturbation survived -> allowed",
      r.returncode == 0, r.stderr[:300])
r = run(sv, artifact("unproven", l2_block("waived", uncovered=UNC1, waivers=WV),
                     perturbation="survived"))
check("unproven + waived + uncovered_lines + perturbation survived -> blocked",
      blocked(r, "perturbation did not pass"), r.stderr[:300])
tagged("unproven waived + uncovered_lines, perturbation survived (site 2)", r,
       "l2_waived_unbacked")

# 13. rule 1 is about status `pass` only (not "anything but gap", not pass-or-waived)
bw = make_repo("rule1-waived")
BWV = [str(waiver(bw, "a/B.py").relative_to(bw))]
r = run(bw, artifact(l2=l2_block("waived", "perturbation", ["a/B.py:1-3"], BWV),
                     classes=("a/B.py",)))
check("proven + waived/perturbation + uncovered_lines + signed waiver + perturbation pass -> allowed",
      r.returncode == 0, r.stderr[:300])
bn = make_repo("rule1-assumed")
r = run(bn, artifact("needs-human", l2_block("assumed", "perturbation", ["a/B.py:1-3"]),
                     classes=("a/B.py",)))
check("needs-human + assumed/perturbation + uncovered_lines + no waiver + perturbation pass -> allowed",
      r.returncode == 0, r.stderr[:300])

# 14. surrounding whitespace in QUOTED values is stripped before the comparison
#     (`collect_statuses`, the older enum check, strips + lowercases too: it never objects)
r = run(a, artifact("needs-human", l2_block('" assumed "', uncovered=[])))
check("l2 status ' assumed ' (padded) + perturbation pass + nothing uncovered -> blocked",
      blocked(r, "technique: perturbation"), r.stderr[:300])
tagged("padded l2 status", r, "l2_assumed_but_perturbed")
r = run(a, artifact(l2=l2_block("pass", '" perturbation "', UNC1)))
check("technique ' perturbation ' (padded) + pass + uncovered_lines + proven -> blocked by rule 1",
      blocked(r, "uncovered_lines"), r.stderr[:300])
tagged("padded technique", r, "l2_perturbation_unbacked")
r = run(a, artifact("needs-human", l2_block("assumed", uncovered=[]), perturbation='" pass "'))
check("perturbation status ' pass ' (padded) + assumed + nothing uncovered -> blocked by rule 2",
      blocked(r, "technique: perturbation"), r.stderr[:300])
tagged("padded perturbation status", r, "l2_assumed_but_perturbed")

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
    "missing-revisit_trigger": dict(drop="revisit_trigger"),
    "missing-criado_em": dict(drop="criado_em"),
    "today": dict(trigger=f"until {date.today().isoformat()}"),
}
for label, kw in CASES.items():
    t = make_repo("twin-" + label)
    waiver(t, "common/bin/cepa-plan", **kw)
    real = W.applicable(W.load(str(t)), "nada-a-provar", "common/bin/cepa-plan",
                        today=date.today())
    twin = guard.applicable_waiver(guard.load_waivers([t / ".claude" / "waivers"]),
                                   "common/bin/cepa-plan", today=date.today())
    check(f"twin agrees with waivers.py: {label}", bool(real) == bool(twin),
          f"real={bool(real)} twin={bool(twin)}")

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all proof coverage-by-perturbation tests passed")
