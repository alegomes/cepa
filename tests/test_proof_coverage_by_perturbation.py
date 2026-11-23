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


def tagged(label, r, tag, verdict=None):
    """This call appended exactly one `proof_verdict` event, and its `blocked` is `tag`
    (None: an allowed call, the hook emits no `blocked` key). With `verdict`, the event
    also records that declared verdict."""
    ev = r.events
    ok = (len(ev) == 1 and ev[0].get("event") == "proof_verdict"
          and ev[0].get("blocked") == tag
          and (verdict is None or ev[0].get("verdict") == verdict))
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
tagged("pass/perturbation + uncovered_lines", r, "l2_perturbation_unbacked", "proven")

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
tagged("no-PyYAML fallback", r, "l2_waived_unverifiable", "proven")
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

# ── fourth-round survivors + sweep of the waiver code ──────────────────────
# A. the scope is compared for EQUALITY (through the loose key), never containment
for label, esc, fpath in (("waiver scope contains the file", "pkg/a/Service.py", "Service.py"),
                          ("file contains the waiver scope", "Service.py", "pkg/a/Service.py")):
    d = make_repo("scope-" + label.split()[0] + "-" + label.split()[-1])
    waiver(d, "scope-x", escopo=esc, fname="nada-a-provar--scope-x.yaml")
    r = run(d, artifact("needs-human", l2_block("waived", uncovered=[fpath + ":1"], waivers=WV),
                        classes=(fpath,)))
    check(f"waived + {label} (not equal) -> blocked", blocked(r, fpath), r.stderr[:300])
    tagged(f"waived, {label}", r, "l2_waived_unbacked")
    r = run(d, artifact("needs-human", l2_block("assumed", uncovered=[fpath + ":1"]),
                        classes=(fpath,)))
    check(f"assumed + {label} -> not 'already waived' -> allowed", r.returncode == 0,
          r.stderr[:300])

# B. only `*.yaml` files are waivers
for ext in (".yaml.bak", ".yml", ".yaml~"):
    d = make_repo("ext-" + ext.strip(".~").replace(".", "-") + str(len(ext)))
    waiver(d, "common/bin/cepa-plan", fname="nada-a-provar--svc" + ext)
    r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
    check(f"valid waiver saved as *{ext} does not count -> blocked", blocked(r, "cepa-plan"),
          r.stderr[:300])
    tagged(f"waiver file *{ext}", r, "l2_waived_unbacked")
d = make_repo("ext-yaml")
waiver(d, "common/bin/cepa-plan", fname="nada-a-provar--svc.yaml")
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("the same content saved as .yaml counts -> allowed", r.returncode == 0, r.stderr[:300])

# motivo is compared for equality
for mot in ("nada-a-provar-x", "nada", "Nada-a-provar"):
    d = make_repo("motivo-" + mot.replace("-", ""))
    waiver(d, "common/bin/cepa-plan", motivo=mot)
    r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
    check(f"waiver with motivo {mot!r} (not equal to nada-a-provar) -> blocked",
          blocked(r, "cepa-plan"), r.stderr[:300])

# motivo is compared EXACTLY: no trimming, no case folding (same as waivers.matches)
for label, mot in (("padded", " nada-a-provar "), ("mixed case", "Nada-A-Provar")):
    d = make_repo("motivo-exact-" + label.replace(" ", ""))
    waiver(d, "a/B.py", motivo=mot)
    r = run(d, artifact(l2=l2_block("waived", uncovered=[], waivers=WV), classes=("a/B.py",)))
    check(f"waived + waiver with motivo {mot!r} ({label}) -> blocked, names a/B.py",
          blocked(r, "no owner-signed waiver covers: a/B.py"), r.stderr[:300])
    tagged(f"waiver motivo {label}", r, "l2_waived_unbacked")

# status is compared EXACTLY too: only the literal `proposta`/`recusada` void a waiver,
# so a padded or capitalised status is NOT a no-effect status and the waiver counts
for idx, st in enumerate((" proposta ", "Proposta", " Recusada", "recusada\t")):
    d = make_repo(f"status-exact-{idx}")
    waiver(d, "common/bin/cepa-plan", status=st)
    r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
    check(f"waived + waiver with status {st!r} (not a literal no-effect status) -> allowed",
          r.returncode == 0, r.stderr[:300])
    tagged(f"waiver status {st!r}", r, None)

# only a perturbation that PASSED measures coverage: any other word, even a
# good-looking one, leaves `assumed` + empty uncovered_lines allowed
for st in ("ran", "clean", "n/a"):
    r = run(a, artifact("needs-human", l2_block("assumed", uncovered=[]), perturbation=st))
    check(f"needs-human + assumed + empty uncovered + perturbation {st!r} -> allowed",
          r.returncode == 0, r.stderr[:300])
    tagged(f"assumed next to perturbation {st!r}", r, None)

# the first APPLICABLE waiver wins: an unusable one sorted first does not end the search
d = make_repo("sorted")
waiver(d, "common/bin/cepa-plan", trigger=f"until {PAST}", fname="a-expired.yaml")
waiver(d, "other/File", fname="b-other-file.yaml")
waiver(d, "common/bin/cepa-plan", status="proposta", fname="c-proposta.yaml")
waiver(d, "common/bin/cepa-plan", fname="z-valid.yaml")
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("expired + other-file + proposta waivers sorted before a valid one -> still waived",
      r.returncode == 0, r.stderr[:300])
r = run(d, artifact("needs-human", l2_block("assumed", uncovered=UNC)))
check("...and assumed there is told to write `waived`", blocked(r, "status: waived"),
      r.stderr[:300])

# a bare repo's git-common-dir is not `<main>/.git`: its parent is not a main clone
bp = TMP / "bare-parent"
(bp / ".claude" / "waivers").mkdir(parents=True)
waiver(bp, "common/bin/cepa-plan")
bare = bp / "repo.git"
subprocess.run(G + ["init", "-q", "--bare", str(bare)], check=True)
(bare / "docs" / "proof").mkdir(parents=True)
r = run(bare, artifact(l2=l2_block("waived", waivers=WV)))
check("bare repo: the waiver in its PARENT dir is not a main-clone waiver -> blocked",
      blocked(r, "cepa-plan"), r.stderr[:300])
tagged("bare repo common dir", r, "l2_waived_unbacked")

# uncovered_lines shapes
r = run(a, artifact(l2=l2_block("pass", "perturbation").replace(
    '    run: "r"\n', '    uncovered_lines: ""\n    run: "r"\n')))
check("uncovered_lines: '' (empty string) is empty -> proven + pass/perturbation allowed",
      r.returncode == 0, r.stderr[:300])
r = run(a, artifact(l2=l2_block("pass", "perturbation").replace(
    '    run: "r"\n', '    uncovered_lines: "  "\n    run: "r"\n')))
check("uncovered_lines: '  ' (blank string, not null) is NOT empty -> blocked",
      blocked(r, "uncovered_lines"), r.stderr[:300])
d = make_repo("nocolon")
waiver(d, "a/B.py")
r = run(d, artifact("needs-human", l2_block("waived", uncovered=["a/B.py"], waivers=WV),
                    classes=("a/B.py",)))
check("uncovered_lines entry without a colon is the file itself -> waiver found -> allowed",
      r.returncode == 0, r.stderr[:300])
r = run(pw, artifact("needs-human", l2_block("assumed", uncovered=["a/B:1", "c/D:2"]),
                     classes=PC))
check("assumed + two uncovered files, waiver for only one -> allowed (not 'already waived')",
      r.returncode == 0, r.stderr[:300])

# no l2_coverage mapping at all: no L2 rule fires (old behavior)
nol2 = ("schema_version: 2\ncard: X-1\nverdict: needs-human\n"
        + scope_yaml(("common/bin/cepa-plan",))
        + "levels:\n  l3_load_bearing:\n    perturbation:\n      status: pass\n")
r = run(b, nol2)
check("no l2_coverage + a signed waiver + perturbation pass -> allowed (no L2 rule fires)",
      r.returncode == 0, r.stderr[:300])
tagged("no l2_coverage", r, None)
r = run(b, nol2 + "  l2_coverage: waived\n")
check("l2_coverage as a scalar -> allowed (no L2 rule fires)", r.returncode == 0,
      r.stderr[:300])

# ── malformed / edge input: the L2 code must decide, not an exception swallowed ──
L3_PERT = ("  l3_load_bearing:\n    pit:\n      status: absent\n"
           "    perturbation:\n      status: pass\n")
L3_SCALAR = "  l3_load_bearing: pass\n"
PERT_SCALAR = "  l3_load_bearing:\n    pit:\n      status: absent\n    perturbation: pass\n"
ASSUMED_BARE = "  l2_coverage:\n    status: assumed\n    run: r\n"
for label, l3 in (("l3_load_bearing as a bare scalar", L3_SCALAR),
                  ("perturbation as a bare scalar", PERT_SCALAR)):
    assert L3_PERT in artifact()
    r = run(a, artifact().replace(L3_PERT, l3))
    check(f"proven + pass/perturbation + {label} -> blocked (the perturbation did not pass)",
          blocked(r, "technique: perturbation"), r.stderr[:300])
    tagged(f"pass/perturbation with {label}", r, "l2_perturbation_unbacked")
    r = run(b, artifact("needs-human", ASSUMED_BARE).replace(L3_PERT, l3))
    check(f"assumed + signed waiver for every class + {label} -> blocked by rule 4",
          blocked(r, "status: waived"), r.stderr[:300])
    tagged(f"assumed with a waiver, {label}", r, "l2_assumed_but_waived")

NO_SCOPE = artifact("needs-human", l2_block("waived", waivers=WV)).replace(
    scope_yaml(("common/bin/cepa-plan",)), "")
assert "scope:" not in NO_SCOPE
r = run(b, NO_SCOPE)
check("waived + empty uncovered_lines + no `scope` key -> blocked (nothing to cover)",
      blocked(r, "no file to cover"), r.stderr[:300])
tagged("waived, no scope key", r, "l2_waived_unbacked")
NULL_CLASSES = artifact("needs-human", l2_block("waived", waivers=WV), classes=())
assert "changed_classes:\n" in NULL_CLASSES and "- class" not in NULL_CLASSES
r = run(b, NULL_CLASSES)
check("waived + empty uncovered_lines + `changed_classes:` null -> blocked (nothing to cover)",
      blocked(r, "no file to cover"), r.stderr[:300])
tagged("waived, changed_classes null", r, "l2_waived_unbacked")

# The hook only PARSES file_path (it writes nothing): an absolute path whose proof dir
# sits at index 0 has root `/`, so the waiver under the payload cwd is NOT the one used.
rootp = make_repo("root-slash")
waiver(rootp, "common/bin/cepa-plan")
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": "/docs/proof/X-1.yaml",
                                     "content": artifact(l2=l2_block("waived", waivers=WV))},
                      "cwd": str(rootp)})
r = hook(payload, cwd=str(neutral))
check("absolute /docs/proof/X-1.yaml: root is `/`, the waiver under the payload cwd does not count",
      blocked(r, "cepa-plan"), r.stderr[:300])
tagged("absolute path with the proof dir at index 0", r, "l2_waived_unbacked")

# project in a SUBDIRECTORY of the repo: git-common-dir is `../.git` unless absolute
sr = TMP / "subrepo"
sr.mkdir()
subprocess.run(G + ["init", "-q", "-b", "main", str(sr)], check=True)
(sr / "sub" / "docs" / "proof").mkdir(parents=True)
waiver(sr, "common/bin/cepa-plan")          # in <repo>/.claude/waivers, not <repo>/sub/
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": str(sr / "sub" / "docs" / "proof" / "X.yaml"),
                                     "content": artifact(l2=l2_block("waived", waivers=WV))},
                      "cwd": str(sr / "sub")})
r = hook(payload, cwd=str(neutral))
check("project in <repo>/sub: the waiver in <repo>/.claude/waivers is found (process cwd elsewhere)",
      r.returncode == 0, r.stderr[:300])
tagged("project in a repo subdirectory", r, None)

# ── sweep: the enum line, the message each branch prints, absent/blank status ──
r = run(a, artifact(l2="  l2_coverage:\n    status: gap\n    run: r\n"))
check("proven + l2 gap -> blocked by the forbidding-status rule (gap is in the l2 enum)",
      blocked(r, "forbid") and "closed enum" not in r.stderr, r.stderr[:300])
check("...and the event is a proof_block, not an unknown_status",
      len(r.events) == 1 and r.events[0].get("event") == "proof_block", str(r.events))
r = run(a, artifact(l2="  l2_coverage:\n    status: ran\n    run: r\n"))
check("proven + l2 `ran` (a status of ANOTHER level) -> blocked, outside the l2 enum",
      blocked(r, "closed enum"), r.stderr[:300])
tagged("l2 status from another level's enum", r, "unknown_status", "proven")

SKIP_L3 = "    perturbation:\n      status: skipped\n"
r = run(a, artifact(l2=l2_block("pass", "perturbation", UNC)))
check("pass/perturbation + passing perturbation + uncovered: the message lists the uncovered",
      blocked(r, "is not empty: common/bin/cepa-plan:10-12")
      and "perturbation.status is not `pass`" not in r.stderr, r.stderr[:300])
for label, unc in (("nothing uncovered", []), ("something uncovered", UNC)):
    r = run(a, artifact(l2=l2_block("pass", "perturbation", unc), perturbation="skipped"))
    check(f"pass/perturbation + perturbation skipped + {label}: the message blames the perturbation",
          blocked(r, "perturbation.status is not `pass`") and "is not empty" not in r.stderr,
          r.stderr[:300])
    tagged(f"pass/perturbation, perturbation skipped, {label}", r,
           "l2_perturbation_unbacked", "proven")

# an l2_coverage with NO status (or a blank one) matches no status rule
NOSTATUS = "  l2_coverage:\n    run: r\n"
n_ = make_repo("nostatus-none")
for label, repo_, art in (
        ("perturbation pass + signed waiver for the class", b, artifact("needs-human", NOSTATUS)),
        ("no class and nothing uncovered", b, artifact("needs-human", NOSTATUS, classes=())),
        ("uncovered + perturbation skipped, no waiver", n_,
         artifact("needs-human", NOSTATUS.replace("run: r", "uncovered_lines: " + json.dumps(UNC)),
                  perturbation="skipped")),
        ("a signed waiver for the class + perturbation skipped", b,
         artifact("needs-human", NOSTATUS, perturbation="skipped")),
        ("an unwaived class + perturbation skipped", n_,
         artifact("needs-human", NOSTATUS, perturbation="skipped"))):
    for st in ("", "    status: ''\n"):
        r = run(repo_, art.replace("  l2_coverage:\n", "  l2_coverage:\n" + st))
        check(f"l2_coverage with {'a blank' if st else 'no'} status + {label} -> allowed",
              r.returncode == 0, r.stderr[:300])

r = run(a, artifact(l2=l2_block("pass", uncovered=UNC)))
check("proven + l2 pass WITHOUT a technique + uncovered_lines -> allowed (not perturbation)",
      r.returncode == 0, r.stderr[:300])

# five unwaived files are named in sorted order, whichever way they were declared
ORDER = ["m/E", "m/B", "m/D", "m/A", "m/C"]
SORTED = "m/A, m/B, m/C, m/D, m/E"
r = run(n, artifact(l2=l2_block("waived", waivers=WV), classes=ORDER))
check("waived + five unwaived changed classes: named sorted", blocked(r, SORTED), r.stderr[:300])
r = run(n, artifact(l2=l2_block("waived", uncovered=[f"{c}:1" for c in ORDER], waivers=WV)))
check("waived + five unwaived uncovered files: named sorted", blocked(r, SORTED), r.stderr[:300])

# a bare-`pass`/null/uppercase perturbation status
r = run(b, artifact("needs-human", ASSUMED_BARE, perturbation="PASS"))
check("assumed + perturbation status `PASS` (any case) + nothing uncovered -> blocked by rule 3",
      blocked(r, "technique: perturbation"), r.stderr[:300])
tagged("PASS in capitals", r, "l2_assumed_but_perturbed")
r = run(b, artifact("needs-human", ASSUMED_BARE, perturbation="null"))
check("assumed + perturbation status null + signed waiver -> blocked by rule 4 (not a pass)",
      blocked(r, "status: waived"), r.stderr[:300])
tagged("perturbation status null", r, "l2_assumed_but_waived")
r = run(b, artifact("needs-human", ASSUMED_BARE, classes=()).replace(
    "    perturbation:\n      status: pass\n", "    perturbation:\n      run: r\n"))
check("assumed + perturbation mapping WITHOUT a status + nothing to cover -> allowed",
      r.returncode == 0, r.stderr[:300])
r = run(b, artifact("needs-human", ASSUMED_BARE.replace("assumed\n", "assumed\n    technique: 5\n")))
check("assumed + technique as a number + perturbation pass -> still blocked by rule 3",
      blocked(r, "technique: perturbation"), r.stderr[:300])
for label, val in (("blank", '"  "'), ("empty", '""')):
    r = run(a, artifact(l2=l2_block("pass", "perturbation").replace(
        '    run: "r"\n', f'    uncovered_lines: [{val}, ""]\n    run: "r"\n')))
    check(f"uncovered_lines holding only {label} strings is empty -> proven allowed",
          r.returncode == 0, r.stderr[:300])

# technique perturbation with no status at all is not `pass`
r = run(a, artifact(l2="  l2_coverage:\n    technique: perturbation\n"
                       "    uncovered_lines: " + json.dumps(UNC) + "\n    run: r\n"))
check("proven + technique perturbation WITHOUT a status + uncovered_lines -> allowed (not `pass`)",
      r.returncode == 0, r.stderr[:300])

# uncovered_lines is reported as written, trimmed; odd shapes still count as uncovered
r = run(a, artifact(l2=l2_block("pass", "perturbation", ["  common/bin/cepa-plan:10-12 "])))
check("a padded entry is listed trimmed", blocked(r, "is not empty: common/bin/cepa-plan:10-12."),
      r.stderr[:300])
for label, val, listed in (("string", '"  common/bin/cepa-plan:10-12  "', "common/bin/cepa-plan:10-12."),
                           ("blank string", '"   "', "   ."),
                           ("number", "5", "5.")):
    r = run(a, artifact(l2=f"  l2_coverage:\n    status: pass\n    technique: perturbation\n"
                           f"    uncovered_lines: {val}\n    run: r\n"))
    check(f"uncovered_lines as a {label}: blocked and listed as written",
          blocked(r, "is not empty: " + listed), r.stderr[:300])
r = run(a, artifact(l2="  l2_coverage:\n    status: pass\n    technique: perturbation\n"
                       "    uncovered_lines: [5]\n    run: r\n"))
check("uncovered_lines holding a number is uncovered -> blocked", blocked(r, "is not empty: 5."),
      r.stderr[:300])

# changed_classes entries of odd shape
ODD = (scope_yaml(("common/bin/cepa-plan",))
       + "    - module: bin\n      substituted_by_double: none\n"
       + "    - class: null\n      substituted_by_double: none\n")
r = run(b, artifact("needs-human", l2_block("waived", waivers=WV)).replace(
    scope_yaml(("common/bin/cepa-plan",)), ODD))
check("changed_classes entries without a class (missing / null) are not files to cover -> allowed",
      r.returncode == 0, r.stderr[:300])
r = run(n, artifact("needs-human", l2_block("waived", waivers=WV)).replace(
    '"common/bin/cepa-plan"', "7"))
check("a numeric class is still a file to cover -> waived without a waiver is blocked",
      blocked(r, "no owner-signed waiver covers: 7"), r.stderr[:300])

# an entry whose class is empty or falsy is not a file to cover; a real class still is
ew = make_repo("empty-class-waived")
waiver(ew, "a/B.py")
en = make_repo("empty-class-unwaived")
for label, extra in (("an empty string", '    - class: ""\n      module: bin\n'),
                     ("the number 0", "    - class: 0\n      module: bin\n")):
    art = artifact("needs-human", l2_block("waived", uncovered=[], waivers=WV),
                   classes=("a/B.py",))
    art = art.replace("levels:\n", extra + "levels:\n", 1)
    r = hook(json.dumps({"tool_name": "Write",
                         "tool_input": {"file_path": str(ew / "docs" / "proof" / "X-1.yaml"),
                                        "content": art},
                         "cwd": str(ew)}))
    check(f"changed_classes with a real class (waived) and {label} as a class -> allowed",
          r.returncode == 0, r.stderr[:300])
    tagged(f"real class waived + {label} class", r, None)
    r = run(en, art)
    check(f"same without a waiver for a/B.py ({label} entry) -> blocked, names a/B.py only",
          blocked(r, "no owner-signed waiver covers: a/B.py.\n"), r.stderr[:300])
    tagged(f"real class unwaived + {label} class", r, "l2_waived_unbacked")

# the printed name of a missing file is trimmed (file part of an uncovered entry; class name)
r = run(en, artifact("needs-human", l2_block("waived", uncovered=["  a/B.py :3"], waivers=WV)))
check("uncovered entry '  a/B.py :3' with no waiver -> printed file name is trimmed",
      blocked(r, "no owner-signed waiver covers: a/B.py.\n"), r.stderr[:300])
r = run(en, artifact("needs-human", l2_block("waived", uncovered=[], waivers=WV),
                     classes=(" a/B.py ",)))
check("class ' a/B.py ' with no waiver -> printed class name is trimmed",
      blocked(r, "no owner-signed waiver covers: a/B.py.\n"), r.stderr[:300])

# waiver files of odd shape must be skipped or compared, never crash the hook
d = make_repo("odd-files")
(d / ".claude" / "waivers" / "a-broken.yaml").write_text("[unclosed\n")
(d / ".claude" / "waivers" / "b-list.yaml").write_text("- just\n- a list\n")
waiver(d, "other/File", escopo=123, fname="c-int-escopo.yaml")
waiver(d, "common/bin/cepa-plan", fname="z-valid.yaml")
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("broken YAML, a list and a numeric escopo sorted before a valid waiver -> allowed",
      r.returncode == 0, r.stderr[:300])
d = make_repo("date-trigger")
waiver(d, "common/bin/cepa-plan", trigger=date.today() - timedelta(days=30))
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("revisit_trigger as an unquoted YAML date in the past -> expired -> blocked (no crash)",
      blocked(r, "cepa-plan"), r.stderr[:300])
d = make_repo("date-trigger-future")
waiver(d, "common/bin/cepa-plan", trigger=date.today() + timedelta(days=300))
r = run(d, artifact(l2=l2_block("waived", waivers=WV)))
check("revisit_trigger as an unquoted YAML date in the future -> allowed", r.returncode == 0,
      r.stderr[:300])
d = make_repo("no-escopo")
waiver(d, "none-x", drop="escopo", fname="no-escopo.yaml")
r = run(d, artifact(l2=l2_block("waived", waivers=WV), classes=("None",)))
check("a waiver WITHOUT escopo does not cover a file called `None` -> blocked",
      blocked(r, "None"), r.stderr[:300])
d = make_repo("blank-file")
waiver(d, "x", fname="x.yaml")
r = run(d, artifact(l2=l2_block("waived", uncovered=[":3"], waivers=WV)))
check("uncovered entry with an empty file part is not covered by a waiver for `x` -> blocked",
      r.returncode == 2, r.stderr[:300])

# payload cwd that is not a string: the guard must still decide, not crash
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": "docs/proof/X-1.yaml",
                                     "content": artifact("needs-human",
                                                         l2_block("waived", waivers=WV))},
                      "cwd": 5})
r = hook(payload, cwd=str(neutral))
check("payload cwd as a number + relative path + waived -> blocked, no traceback",
      blocked(r, "cepa-plan") and "Traceback" not in r.stderr, r.stderr[:300])

payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": str(b / "docs" / "proof" / "X-1.yaml"),
                                     "content": artifact("needs-human",
                                                         l2_block("waived", waivers=WV))},
                      "cwd": 5})
r = hook(payload, cwd=str(neutral))
check("payload cwd as a number + ABSOLUTE path: the waiver at the artifact's root is found",
      r.returncode == 0, r.stderr[:300])

# a git that fails contributes nothing, whatever it printed
fake = TMP / "fakebin"
fake.mkdir()
fmain = make_repo("fake-main")
waiver(fmain, "common/bin/cepa-plan")
fg = make_repo("fake-git-repo")
(fake / "git").write_text(f'#!/bin/sh\necho "{fmain}/.git"\nexit 1\n')
(fake / "git").chmod(0o755)
old_path = os.environ["PATH"]
os.environ["PATH"] = f"{fake}{os.pathsep}{old_path}"
try:
    r = run(fg, artifact(l2=l2_block("waived", waivers=WV)))
finally:
    os.environ["PATH"] = old_path
check("git exits non-zero printing a .git path: that dir is not a waiver dir -> blocked",
      blocked(r, "cepa-plan"), r.stderr[:300])

# a NUL byte in the path: glob cannot list the dir, which must read as "no waivers"
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": "/tmp/x\u0000y/docs/proof/X-1.yaml",
                                     "content": artifact("needs-human",
                                                         l2_block("waived", waivers=WV))},
                      "cwd": str(TMP)})
r = hook(payload, cwd=str(neutral))
check("a NUL byte in the path -> no waiver dir can be listed -> blocked, no traceback",
      blocked(r, "cepa-plan") and "Traceback" not in r.stderr, r.stderr[:300])

# a git slower than the 5 s guard is abandoned, even if it would have answered later
slow = TMP / "slowbin"
slow.mkdir()
sg = make_repo("slow-git-repo")
# slow only for the waiver lookup (cwd = the repo); the telemetry's own git call (cwd = TMP) is fast
(slow / "git").write_text("#!/usr/bin/env python3\nimport sys, time\n"
                          f"if sys.argv[2] != {str(sg)!r}:\n    sys.exit(1)\n"
                          f'time.sleep(5.3)\nprint("{fmain}/.git")\n')
(slow / "git").chmod(0o755)
payload = json.dumps({"tool_name": "Write",
                      "tool_input": {"file_path": str(sg / "docs" / "proof" / "X-1.yaml"),
                                     "content": artifact(l2=l2_block("waived", waivers=WV))},
                      "cwd": str(TMP)})
os.environ["PATH"] = f"{slow}{os.pathsep}{old_path}"
try:
    r = hook(payload, cwd=str(neutral))
finally:
    os.environ["PATH"] = old_path
check("git slower than 5 s is abandoned: its late answer is not a waiver dir -> blocked",
      blocked(r, "cepa-plan"), r.stderr[:300])

# fallback / no-l2 shapes under `proven`
r = run(b, nol2.replace("verdict: needs-human", "verdict: proven"))
check("proven + no l2_coverage mapping -> allowed (nothing to check, nothing crashes)",
      r.returncode == 0, r.stderr[:300])
tagged("proven, no l2_coverage", r, None)
FB = artifact(l2=l2_block("pass", "perturbation", [])) + "broken: [unclosed\n"
r = run(b, FB)
check("fallback: proven with no `waived` anywhere -> allowed", r.returncode == 0, r.stderr[:300])
tagged("fallback, nothing waived", r, None)
r = run(b, FB.replace("status: clean", "status: d"))
check("fallback: a status that is a substring of `waived` is just unknown -> blocked as such",
      blocked(r, "closed enum"), r.stderr[:300])
tagged("fallback, status `d`", r, "unknown_status", "proven")

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
    # fourth-round sweep: scope / motivo / status / date shapes / file extension
    "escopo-contains-file": dict(escopo="pkg/common/bin/cepa-plan"),
    "file-contains-escopo": dict(escopo="bin/cepa-plan"),
    "motivo-superstring": dict(motivo="nada-a-provar-x"),
    "motivo-substring": dict(motivo="nada"),
    "motivo-capitalised": dict(motivo="Nada-a-provar"),
    "status-Proposta": dict(status="Proposta"),
    "status-padded": dict(status="proposta "),
    "status-other": dict(status="aceita"),
    "status-leading-padded": dict(status=" proposta "),
    "status-Recusada": dict(status="Recusada"),
    "motivo-padded": dict(motivo=" nada-a-provar "),
    "motivo-mixed-case": dict(motivo="Nada-A-Provar"),
    "two-dates-expired-first": dict(trigger=f"from {PAST} until {FUTURE}"),
    "two-dates-future-first": dict(trigger=f"from {FUTURE} until {PAST}"),
    "invalid-month-past": dict(trigger="until 2020-13-45"),
    "invalid-month-future": dict(trigger="until 2099-13-45"),
    "short-date": dict(trigger="until 2020-1-5"),
    "bak-file": dict(fname="nada-a-provar--svc.yaml.bak"),
    "yml-file": dict(fname="nada-a-provar--svc.yml"),
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


# direct assertions on the inline twin's helpers
check("_wkey(None) is the empty key", guard._wkey(None) == "" and guard._wkey("") == "")
check("_wkey keeps only lowercase alphanumerics (no replacement text)",
      guard._wkey("A/b-C 1") == "abc1", guard._wkey("A/b-C 1"))
check("_waiver_expired takes `today` (before / after the date)",
      not guard._waiver_expired({"revisit_trigger": "until 2020-01-01"}, today=date(2019, 12, 31))
      and guard._waiver_expired({"revisit_trigger": "until 2020-01-01"}, today=date(2020, 1, 2)))
check("an absolute path with the proof dir at index 0 has root `/`",
      guard.waiver_dirs("/docs/proof/X-1.yaml", "/some/cwd")[0] == Path("/.claude/waivers"),
      str(guard.waiver_dirs("/docs/proof/X-1.yaml", "/some/cwd")))
check("a relative path with a prefix is joined to the payload cwd",
      guard.waiver_dirs("pkg/docs/proof/X-1.yaml", str(TMP))[0] == TMP / "pkg" / ".claude" / "waivers")
loaded = guard.load_waivers([TMP / "ext-yaml" / ".claude" / "waivers"])
check("load_waivers records the file it read in `_path`",
      len(loaded) == 1 and loaded[0].get("_path", "").endswith("nada-a-provar--svc.yaml"),
      str(loaded))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all proof coverage-by-perturbation tests passed")
