#!/usr/bin/env python3
"""Zero-token replay of a hand-written hook-payload corpus against hook versions.

Replays tests/replay/<hook-id>/*.json against the hooks in the working tree and,
optionally, against the same hooks at one or more git refs, then prints one
comparison row per hook x version and the calls whose decision differs between
versions. See tests/replay/README.md for the scenario format.

Stdlib only. Exit 0 on a successful run even with mismatches (it is a measuring
instrument); non-zero only on usage or infrastructure errors.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parent.parent
HOOK_DIRS = ("common/hooks", "build-hex/hooks")
WORKTREE = "worktree"
# Env vars that change hook behavior and must not leak in from the caller.
SCRUBBED_ENV = ("CEPA_BASHLOCK_ENFORCE", "CEPA_HEX_PATHLOCK_DEBUG", "CEPA_RUN",
                "CEPA_AUTONOMOUS_RUN_ID", "CEPA_SEED",
                # the names these had before CS-6 are still read, so they leak too
                "HEX_PATHLOCK_DEBUG", "CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID", "CCW_SEED",
                # path-lock.py:detect_agent falls back to these when the payload
                # has no agent_type, so a caller running as a subagent would
                # turn a "main session" call into a gated one.
                "CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME",
                "CEPA_HEX_PATHLOCK_DEBUG_LOG", "CEPA_CAPTURE_BUILD_DEBUG", "CAPTURE_BUILD_DEBUG",
                "CEPA_TELEMETRY_DEBUG")


def scrubbed(environ):
    """Caller env minus hook-altering vars and GIT_* (a git hook running the
    replay would otherwise point the fixtures' git at the caller's repo)."""
    return {k: v for k, v in environ.items()
            if k not in SCRUBBED_ENV and not k.startswith("GIT_")}


def die(msg):
    print(f"run.py: error: {msg}", file=sys.stderr)
    sys.exit(2)


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()}")
    return r


def load_scenarios(hook_ids):
    out = []
    for hid in hook_ids:
        d = HERE / hid
        if not d.is_dir():
            die(f"no corpus directory for hook id {hid!r} ({d})")
        for f in sorted(d.glob("*.json")):
            sc = json.loads(f.read_text(encoding="utf-8"))
            sc["_file"] = f"{hid}/{f.name}"
            sc["_id"] = hid
            out.append(sc)
    return out


def subst(obj, root):
    if isinstance(obj, str):
        return obj.replace("{root}", root)
    if isinstance(obj, list):
        return [subst(x, root) for x in obj]
    if isinstance(obj, dict):
        return {k: subst(v, root) for k, v in obj.items()}
    return obj


def build_fixture(setup, root):
    Path(root).mkdir(parents=True, exist_ok=True)
    for rel, content in (setup.get("files") or {}).items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if setup.get("git"):
        def g(*a):
            subprocess.run(["git", "-C", root, *a], capture_output=True, check=True)
        g("init", "-q", "-b", "main")
        g("config", "user.email", "replay@example.invalid")
        g("config", "user.name", "replay")
        g("config", "commit.gpgsign", "false")
        g("add", "-A")
        g("commit", "-q", "--allow-empty", "-m", "seed")


def materialize(repo, ref, dest):
    """Extract hook dirs at `ref` into dest. Returns None or an error string."""
    if git(repo, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False).returncode != 0:
        die(f"unknown ref {ref!r} in {repo}")
    arch = subprocess.run(["git", "-C", str(repo), "archive", ref, *HOOK_DIRS],
                          capture_output=True)
    if arch.returncode != 0:
        # some dirs may not exist at that ref: retry one by one
        for d in HOOK_DIRS:
            a = subprocess.run(["git", "-C", str(repo), "archive", ref, d], capture_output=True)
            if a.returncode == 0:
                subprocess.run(["tar", "-x", "-C", str(dest)], input=a.stdout, check=True)
        return None
    subprocess.run(["tar", "-x", "-C", str(dest)], input=arch.stdout, check=True)
    return None


def run_scenario(sc, hooks_root, telemetry_dir):
    """Run one scenario in a fresh temp dir. Returns a list of call result dicts."""
    hook_rel = sc["hook"]
    hook_path = Path(hooks_root) / hook_rel
    results = []
    if not hook_path.is_file():
        for c in sc["calls"]:
            results.append({"scenario": sc["_file"], "call": c["name"], "decision": "missing",
                            "stderr": "", "ms": 0.0, "call_def": c})
        return results
    with tempfile.TemporaryDirectory(prefix="cepa-replay-") as td:
        root = os.path.join(os.path.realpath(td), "demo")
        build_fixture(subst(sc.get("setup") or {}, root), root)
        env = scrubbed(os.environ)
        env["CEPA_TELEMETRY_DIR"] = telemetry_dir
        env.update(subst(sc.get("env") or {}, root))
        for c in sc["calls"]:
            payload = subst(c["payload"], root)
            t0 = time.perf_counter()
            r = subprocess.run([sys.executable, str(hook_path)], input=json.dumps(payload),
                               capture_output=True, text=True, env=env, cwd=root)
            ms = (time.perf_counter() - t0) * 1000
            # Exit 2 means deny only when the hook itself said why: Python exits 2
            # with "can't open file" on stderr when the script is unreadable.
            if r.returncode == 2 and "can't open file" in r.stderr:
                dec = "error2"
            else:
                dec = "deny" if r.returncode == 2 else ("allow" if r.returncode == 0 else f"error{r.returncode}")
            results.append({"scenario": sc["_file"], "call": c["name"], "decision": dec,
                            "stderr": r.stderr if dec == "deny" else "", "ms": ms, "call_def": c})
    return results


def summarize(results):
    s = {"calls": len(results), "denials": 0, "redundant_denials": 0, "holes": 0,
         "mismatches": 0, "deny_tokens_est": 0, "mean_ms": 0.0, "missing": 0, "errors": 0}
    chars = 0
    for r in results:
        d, c = r["decision"], r["call_def"]
        if d == "missing":
            s["missing"] += 1
            continue
        if d.startswith("error"):
            s["errors"] += 1
        if d == "deny":
            s["denials"] += 1
            chars += len(r["stderr"])
            if c.get("redundant"):
                s["redundant_denials"] += 1
        if c.get("must_deny") and d != "deny":
            s["holes"] += 1
        if d != c["expect"]:
            s["mismatches"] += 1
    s["deny_tokens_est"] = round(chars / 4)
    ran = [r for r in results if r["decision"] != "missing"]
    s["mean_ms"] = round(sum(r["ms"] for r in ran) / len(ran), 1) if ran else 0.0
    return s


def main():
    ap = argparse.ArgumentParser(
        description="Replay a hand-written corpus of hook payloads against the working-tree "
                    "hooks and against the same hooks at git refs; print a comparison table. "
                    "Costs zero tokens.")
    ap.add_argument("--hook", action="append", metavar="ID",
                    help="hook id to replay (corpus directory name); repeatable; default: all")
    ap.add_argument("--ref", action="append", default=[], metavar="REF",
                    help="git ref to compare against the working tree; repeatable")
    ap.add_argument("--repo", default=str(DEFAULT_REPO), metavar="PATH",
                    help="repo providing the worktree hooks and the refs (default: the repo "
                         "containing this script)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of tables")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        die(f"--repo {repo} is not a directory")
    all_ids = sorted(p.name for p in HERE.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    ids = args.hook or all_ids
    for h in ids:
        if h not in all_ids:
            die(f"unknown hook id {h!r}; available: {', '.join(all_ids)}")
    scenarios = load_scenarios(ids)

    versions = [WORKTREE] + args.ref
    report = {"versions": versions, "hooks": {}, "diffs": []}
    with tempfile.TemporaryDirectory(prefix="cepa-replay-tel-") as tel, \
            tempfile.TemporaryDirectory(prefix="cepa-replay-refs-") as refs:
        roots = {WORKTREE: str(repo)}
        for i, ref in enumerate(args.ref):
            d = os.path.join(refs, str(i))
            os.makedirs(d)
            materialize(repo, ref, d)
            roots[ref] = d
        per = {}  # (hook, version) -> results
        for v in versions:
            for sc in scenarios:
                per.setdefault((sc["_id"], v), []).extend(run_scenario(sc, roots[v], tel))
        for hid in ids:
            report["hooks"][hid] = {v: summarize(per[(hid, v)]) for v in versions}
        for hid in ids:
            base = {(r["scenario"], r["call"]): r["decision"] for r in per[(hid, WORKTREE)]}
            for v in versions[1:]:
                for r in per[(hid, v)]:
                    k = (r["scenario"], r["call"])
                    if r["decision"] != base.get(k):
                        report["diffs"].append({"hook": hid, "scenario": r["scenario"],
                                                "call": r["call"], WORKTREE: base.get(k),
                                                "version": v, "decision": r["decision"]})

    if args.json:
        print(json.dumps(report, indent=2))
        return
    print("Replay of hand-written hook payloads (zero tokens). "
          "tokens = estimated denial-message tokens (stderr chars / 4).")
    cols = ["calls", "denials", "redundant_denials", "holes", "mismatches", "deny_tokens_est", "mean_ms"]
    hdr = ["hook", "version", "calls", "denials", "redundant", "holes", "mismatch", "tokens", "ms"]
    rows = [hdr]
    for hid in ids:
        for v in versions:
            s = report["hooks"][hid][v]
            note = " (hook file missing)" if s["missing"] else ""
            rows.append([hid, v + note] + [str(s[c]) for c in cols])
    w = [max(len(r[i]) for r in rows) for i in range(len(hdr))]
    for i, r in enumerate(rows):
        print("  ".join(x.ljust(w[j]) for j, x in enumerate(r)).rstrip())
        if i == 0:
            print("  ".join("-" * x for x in w))
    print()
    if not args.ref:
        print("No --ref given: nothing to compare against.")
    elif not report["diffs"]:
        print("No call changed decision between versions.")
    else:
        print("Calls whose decision differs from the working tree:")
        for d in report["diffs"]:
            print(f"  {d['scenario']} :: {d['call']}: worktree={d[WORKTREE]} {d['version']}={d['decision']}")


if __name__ == "__main__":
    main()
