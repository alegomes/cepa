#!/usr/bin/env python3
"""git-history collector — deterministic extraction of effort + narrative
signals from one or more Git repositories into a single datapack.json.

This is the *facts* half of the plugin: it runs `git log`/`for-each-ref` and
computes proxies and signals. It makes NO interpretive claims — pivots and
learning episodes are emitted as raw *signals*, and it is the narrator agent's
job (downstream) to turn them into a story, clearly labelled as inference.

No third-party dependencies — Python stdlib + the `git` CLI only.

Usage:
    collect.py REPO [REPO ...] [--since DATE] [--until DATE]
               [--granularity auto|week|month|quarter]
               [--output PATH] [--session-gap MIN] [--gap-days N]

Output schema: see build_datapack() / the `schema_version` field.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = 1

# Unit separator — safe field delimiter inside git --pretty format strings.
US = "\x1f"
RS = "@@C@@"  # record separator marking the start of each commit block

# --- Heuristic knobs (overridable via CLI) ---
DEFAULT_SESSION_GAP_MIN = 120     # commits farther apart start a new work session
DEFAULT_FIRST_COMMIT_BONUS_MIN = 60  # assumed work before a session's first commit
DEFAULT_GAP_DAYS = 21             # silence longer than this is a "gap" signal
MERGE_RATIO_THRESHOLD = 0.08      # merge-commit share suggesting a merge workflow
SQUASH_RATIO_THRESHOLD = 0.15     # "(#123)"-style subject share suggesting squash
SIGNAL_CAP = 400                  # per-category cap; we log what we drop

# Files whose churn is noise, not effort. Counted as a "touch" but excluded
# from line-churn so a regenerated lockfile doesn't read as a week of work.
GENERATED_PATTERNS = [
    r"(^|/)package-lock\.json$", r"(^|/)yarn\.lock$", r"(^|/)pnpm-lock\.yaml$",
    r"(^|/)poetry\.lock$", r"(^|/)Cargo\.lock$", r"(^|/)Gemfile\.lock$",
    r"(^|/)go\.sum$", r"(^|/)composer\.lock$", r"(^|/)Pipfile\.lock$",
    r"\.min\.(js|css)$", r"\.map$", r"_pb2\.py$", r"\.pb\.go$",
    r"(^|/)node_modules/", r"(^|/)dist/", r"(^|/)build/", r"(^|/)vendor/",
    r"(^|/)\.next/", r"(^|/)__generated__/",
]
GENERATED_RE = re.compile("|".join(GENERATED_PATTERNS))

# Dependency / build manifests — a change here is a stack-direction signal.
MANIFESTS = {
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts",
    "requirements.txt", "pyproject.toml", "Pipfile", "go.mod", "Cargo.toml",
    "Gemfile", "composer.json", "pubspec.yaml", "setup.py", "build.sbt",
}
MANIFEST_SUFFIXES = (".csproj", ".fsproj")

# Commit-subject keywords grouped by what they hint at. Word-boundary matched,
# case-insensitive. These are *hints*, not verdicts.
KEYWORD_CATEGORIES = {
    "rewrite": [r"rewrite", r"rewrote", r"from scratch", r"start over",
                r"ground up", r"redo", r"re-?implement"],
    "migration": [r"migrat", r"port(ed|ing)? to", r"switch(ed|ing)? to",
                  r"replace[d]? .* with", r"upgrade"],
    "abandon": [r"abandon", r"drop(ped|ping)?", r"deprecat", r"remove[d]? .*support",
                r"kill(ed)?", r"retire"],
    "learning": [r"\boops\b", r"actually", r"turns out", r"learned",
                 r"realiz", r"mistake", r"should have", r"my bad", r"whoops"],
    "experiment": [r"experiment", r"\bspike\b", r"\bpoc\b", r"proof of concept",
                   r"prototype", r"\btry(ing)?\b", r"\bwip\b"],
}
KEYWORD_RES = {
    cat: re.compile("|".join(rf"\b{p}\b" if not p.startswith(r"\b") else p
                            for p in pats), re.IGNORECASE)
    for cat, pats in KEYWORD_CATEGORIES.items()
}
REVERT_RE = re.compile(r"^revert\b|\brevert(s|ed|ing)?\b", re.IGNORECASE)


def run_git(repo, args, timeout=120):
    """Run a git command in `repo`, return stdout as text. Raises on failure."""
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True, text=True, check=True, timeout=timeout,
    ).stdout


def is_git_repo(path):
    try:
        out = run_git(path, ["rev-parse", "--is-inside-work-tree"], timeout=20)
        return out.strip() == "true"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def repo_name(path):
    """Prefer the remote 'origin' repo name; fall back to the directory name."""
    try:
        url = run_git(path, ["remote", "get-url", "origin"], timeout=20).strip()
        if url:
            base = url.rstrip("/").split("/")[-1]
            return base[:-4] if base.endswith(".git") else base
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return os.path.basename(os.path.abspath(path.rstrip("/"))) or path


def parse_iso(s):
    """Parse git's strict-ISO author date into an aware datetime."""
    try:
        return datetime.fromisoformat(s.strip())
    except ValueError:
        # Fallback for environments without offset support.
        return datetime.fromisoformat(s.strip()[:19]).replace(tzinfo=timezone.utc)


def top_level(path):
    """First path segment — the 'area' a file belongs to ('' for repo root)."""
    path = path.strip()
    if "/" not in path:
        return "(root)"
    return path.split("/", 1)[0]


def normalize_numstat_path(path):
    """numstat rename forms: 'a => b', '{old => new}/x', 'dir/{a => b}'.
    Return the *new* path."""
    if "=>" not in path:
        return path
    # Brace form: foo/{old => new}/bar  -> foo/new/bar
    m = re.search(r"\{(.*?) => (.*?)\}", path)
    if m:
        return path[:m.start()] + m.group(2) + path[m.end():]
    # Plain form: old => new
    parts = path.split("=>")
    return parts[-1].strip()


def is_generated(path):
    return bool(GENERATED_RE.search(path))


def is_manifest(path):
    base = path.rsplit("/", 1)[-1]
    return base in MANIFESTS or base.endswith(MANIFEST_SUFFIXES)


# ---------------------------------------------------------------------------
# Per-repo extraction
# ---------------------------------------------------------------------------

def collect_commits(repo, since, until):
    """Stream the landed history (HEAD) with per-file numstat.

    We use HEAD (not --all) on purpose: the landed history is the defensible
    record of what the project actually became. Branch/merge topology is
    captured separately via collect_merges().
    """
    fmt = US.join(["%H", "%an", "%ae", "%aI", "%s"])
    args = ["log", "--no-merges", "--date=iso-strict",
            f"--pretty=format:{RS}{fmt}", "--numstat"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    out = run_git(repo, args, timeout=300)

    commits = []
    cur = None
    for line in out.split("\n"):
        if line.startswith(RS):
            if cur is not None:
                commits.append(cur)
            fields = line[len(RS):].split(US)
            if len(fields) < 5:
                cur = None
                continue
            h, an, ae, ai, subj = fields[0], fields[1], fields[2], fields[3], fields[4]
            cur = {
                "hash": h, "author": an, "email": ae,
                "date": parse_iso(ai), "subject": subj,
                "files": [], "churn": 0, "touched_areas": set(),
                "manifests": [], "generated_only": True,
            }
        elif line.strip() and cur is not None:
            # numstat row:  <added>\t<removed>\t<path>
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            added, removed, path = parts
            path = normalize_numstat_path(path)
            cur["files"].append(path)
            cur["touched_areas"].add(top_level(path))
            if is_manifest(path):
                cur["manifests"].append(path.rsplit("/", 1)[-1])
            if not is_generated(path):
                cur["generated_only"] = False
                a = int(added) if added.isdigit() else 0
                r = int(removed) if removed.isdigit() else 0
                cur["churn"] += a + r
    if cur is not None:
        commits.append(cur)
    commits.sort(key=lambda c: c["date"])
    return commits


def collect_merges(repo, since, until):
    fmt = US.join(["%aI", "%s", "%P"])
    args = ["log", "--merges", "--date=iso-strict", f"--pretty=format:{fmt}"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    out = run_git(repo, args, timeout=120)
    merges = []
    for line in out.split("\n"):
        if not line.strip():
            continue
        f = line.split(US)
        if len(f) < 2:
            continue
        merges.append({"date": parse_iso(f[0]).isoformat(), "subject": f[1]})
    return merges


def collect_tags(repo):
    try:
        out = run_git(repo, [
            "for-each-ref", "--sort=creatordate",
            f"--format=%(refname:short){US}%(creatordate:iso-strict)",
            "refs/tags",
        ], timeout=60)
    except subprocess.CalledProcessError:
        return []
    tags = []
    for line in out.split("\n"):
        if not line.strip():
            continue
        f = line.split(US)
        if len(f) < 2 or not f[1].strip():
            continue
        try:
            tags.append({"name": f[0], "date": parse_iso(f[1]).isoformat()})
        except ValueError:
            continue
    return tags


def detect_workflow(repo, total_commits, merge_count, commits):
    """Classify the repo's predominant workflow so the narrator can adapt.
    Returns (label, evidence dict)."""
    squash_markers = sum(1 for c in commits if re.search(r"\(#\d+\)\s*$", c["subject"]))
    merge_ratio = merge_count / total_commits if total_commits else 0.0
    squash_ratio = squash_markers / total_commits if total_commits else 0.0
    if merge_ratio >= MERGE_RATIO_THRESHOLD:
        label = "merge-based"
    elif squash_ratio >= SQUASH_RATIO_THRESHOLD:
        label = "squash"
    else:
        label = "linear/rebase"
    return label, {
        "merge_ratio": round(merge_ratio, 3),
        "squash_marker_ratio": round(squash_ratio, 3),
        "merge_count": merge_count,
        "squash_markers": squash_markers,
    }


# ---------------------------------------------------------------------------
# Time bucketing
# ---------------------------------------------------------------------------

def choose_granularity(span_days):
    if span_days <= 120:
        return "week"
    if span_days <= 760:
        return "month"
    return "quarter"


def bucket_key(dt, gran):
    if gran == "week":
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"
    if gran == "quarter":
        return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
    return f"{dt.year}-{dt.month:02d}"  # month


def enumerate_periods(start, end, gran):
    """Ordered, gap-free list of bucket keys covering [start, end]."""
    keys = []
    if gran == "week":
        # Step weekly from the Monday of the start week.
        d = start - timedelta(days=start.weekday())
        last = end + timedelta(days=7)
        seen = set()
        while d <= last:
            k = bucket_key(d, "week")
            if k not in seen:
                seen.add(k)
                keys.append(k)
            d += timedelta(days=7)
    elif gran == "quarter":
        y, q = start.year, (start.month - 1) // 3 + 1
        ey, eq = end.year, (end.month - 1) // 3 + 1
        while (y, q) <= (ey, eq):
            keys.append(f"{y}-Q{q}")
            q += 1
            if q > 4:
                q = 1
                y += 1
    else:  # month
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            keys.append(f"{y}-{m:02d}")
            m += 1
            if m > 12:
                m = 1
                y += 1
    return keys


# ---------------------------------------------------------------------------
# Effort, areas, signals
# ---------------------------------------------------------------------------

def estimate_sessions(commits, gap_min, bonus_min):
    """git-hours heuristic: cluster commits into work sessions by author-date
    proximity; a session's effort is its span plus a bonus for the unrecorded
    work before its first commit. Returns {period_dt_of_session_start: minutes}
    keyed by the session's first commit datetime."""
    if not commits:
        return []
    gap = timedelta(minutes=gap_min)
    sessions = []
    start = prev = commits[0]["date"]
    for c in commits[1:]:
        if c["date"] - prev > gap:
            sessions.append((start, prev))
            start = c["date"]
        prev = c["date"]
    sessions.append((start, prev))
    out = []
    for s_start, s_end in sessions:
        minutes = (s_end - s_start).total_seconds() / 60.0 + bonus_min
        out.append((s_start, minutes))
    return out


def build_repo_record(repo, path, since, until, gran_holder, knobs):
    commits = collect_commits(path, since, until)
    merges = collect_merges(path, since, until)
    tags = collect_tags(path)

    if not commits:
        return {
            "name": repo, "path": os.path.abspath(path),
            "empty": True, "total_commits": 0,
            "note": "No commits in range (HEAD history).",
            "merges": merges, "tags": tags,
        }

    total_commits = len(commits)
    workflow, wf_evidence = detect_workflow(path, total_commits, len(merges), commits)

    # Per-period effort
    effort = defaultdict(lambda: {"commits": 0, "churn": 0, "est_hours": 0.0})
    for c in commits:
        k = bucket_key(c["date"], gran_holder["gran"])
        effort[k]["commits"] += 1
        effort[k]["churn"] += c["churn"]

    for s_start, minutes in estimate_sessions(
            commits, knobs["session_gap"], knobs["first_bonus"]):
        k = bucket_key(s_start, gran_holder["gran"])
        effort[k]["est_hours"] += minutes / 60.0

    for k in effort:
        effort[k]["est_hours"] = round(effort[k]["est_hours"], 2)

    # Area attribution + structural first/last-seen
    area = defaultdict(lambda: {"churn": 0, "commits": 0, "first": None, "last": None})
    for c in commits:
        for a in c["touched_areas"]:
            rec = area[a]
            rec["commits"] += 1
            d = c["date"]
            if rec["first"] is None or d < rec["first"]:
                rec["first"] = d
            if rec["last"] is None or d > rec["last"]:
                rec["last"] = d
        # churn split evenly across the non-generated areas it touched
        real_areas = [a for a in c["touched_areas"] if a != "(root)"] or list(c["touched_areas"])
        if real_areas and c["churn"]:
            per = c["churn"] / len(real_areas)
            for a in real_areas:
                area[a]["churn"] += per

    area_effort = sorted(
        ({"area": a, "churn": round(v["churn"]), "commits": v["commits"],
          "first": v["first"].isoformat(), "last": v["last"].isoformat()}
         for a, v in area.items()),
        key=lambda x: x["churn"], reverse=True,
    )

    # --- Signals ---
    signals = {"keyword": [], "reverts": [], "gaps": [], "stack_changes": [],
               "structural": []}
    dropped = defaultdict(int)

    def add(bucket, item):
        if len(signals[bucket]) < SIGNAL_CAP:
            signals[bucket].append(item)
        else:
            dropped[bucket] += 1

    for c in commits:
        subj = c["subject"]
        if REVERT_RE.search(subj):
            add("reverts", {"date": c["date"].isoformat(), "hash": c["hash"][:10],
                            "subject": subj})
        for cat, rx in KEYWORD_RES.items():
            if rx.search(subj):
                add("keyword", {"date": c["date"].isoformat(), "hash": c["hash"][:10],
                                "subject": subj, "category": cat})
                break
        if c["manifests"]:
            add("stack_changes", {"date": c["date"].isoformat(), "hash": c["hash"][:10],
                                  "subject": subj, "manifests": sorted(set(c["manifests"]))})

    # Time gaps in landed history
    gap_delta = timedelta(days=knobs["gap_days"])
    for prev, nxt in zip(commits, commits[1:]):
        if nxt["date"] - prev["date"] > gap_delta:
            add("gaps", {
                "start": prev["date"].isoformat(), "end": nxt["date"].isoformat(),
                "days": (nxt["date"] - prev["date"]).days,
            })

    # Structural: areas that were abandoned (last-seen well before repo end) or
    # introduced well after repo start.
    repo_start = commits[0]["date"]
    repo_end = commits[-1]["date"]
    span = (repo_end - repo_start) or timedelta(days=1)
    for a, v in area.items():
        if a == "(root)":
            continue
        late_intro = (v["first"] - repo_start) > span * 0.33
        early_abandon = (repo_end - v["last"]) > max(span * 0.33, timedelta(days=60))
        if late_intro:
            add("structural", {"area": a, "event": "introduced-late",
                               "date": v["first"].isoformat(),
                               "churn": round(v["churn"])})
        if early_abandon and v["churn"] > 0:
            add("structural", {"area": a, "event": "abandoned",
                               "date": v["last"].isoformat(),
                               "churn": round(v["churn"])})

    truncated = {k: n for k, n in dropped.items() if n}

    return {
        "name": repo,
        "path": os.path.abspath(path),
        "empty": False,
        "workflow": workflow,
        "workflow_evidence": wf_evidence,
        "first_commit": repo_start.isoformat(),
        "last_commit": repo_end.isoformat(),
        "total_commits": total_commits,
        "total_churn": sum(c["churn"] for c in commits),
        "authors": len({c["email"] for c in commits}),
        "effort_by_period": dict(effort),
        "area_effort": area_effort[:25],
        "tags": tags,
        "merges": merges[:SIGNAL_CAP],
        "signals": signals,
        "signals_truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def build_datapack(repos, since, until, requested_gran, knobs):
    # First pass: collect commits to find the global span, so granularity is
    # chosen once across all repos (single shared timeline).
    raw = []
    used_names = {}
    for path in repos:
        if not is_git_repo(path):
            print(f"  ⚠ skipping (not a git repo): {path}", file=sys.stderr)
            continue
        name = repo_name(path)
        # Disambiguate repos that resolve to the same name (e.g. two clones).
        if name in used_names:
            used_names[name] += 1
            name = f"{name} ({used_names[name]})"
        else:
            used_names[name] = 1
        commits = collect_commits(path, since, until)
        raw.append((name, path, commits))

    if not raw:
        raise SystemExit("✗ No analysable git repositories among the given paths.")

    all_dates = [c["date"] for _, _, cs in raw for c in cs]
    if not all_dates:
        raise SystemExit("✗ No commits found in the given range across all repos.")
    start, end = min(all_dates), max(all_dates)
    span_days = (end - start).days or 1
    gran = requested_gran if requested_gran != "auto" else choose_granularity(span_days)
    gran_holder = {"gran": gran}

    periods = enumerate_periods(start, end, gran)

    repo_records = []
    for name, path, _ in raw:
        print(f"  • {name}: extracting…", file=sys.stderr)
        repo_records.append(
            build_repo_record(name, path, since, until, gran_holder, knobs))

    # Cross-repo timeline matrix
    by_period = {p: {} for p in periods}
    for rec in repo_records:
        if rec.get("empty"):
            continue
        for p, v in rec["effort_by_period"].items():
            by_period.setdefault(p, {})[rec["name"]] = v

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_args": {
            "repos": [os.path.abspath(p) for p in repos],
            "since": since, "until": until,
            "granularity_requested": requested_gran,
            "session_gap_min": knobs["session_gap"],
            "gap_days": knobs["gap_days"],
        },
        "granularity": gran,
        "span": {"start": start.isoformat(), "end": end.isoformat(),
                 "days": span_days},
        "periods": periods,
        "repos": repo_records,
        "timeline": {"by_period": by_period},
    }


def main():
    ap = argparse.ArgumentParser(description="Collect Git history into a datapack.")
    ap.add_argument("repos", nargs="+", help="paths to git repositories")
    ap.add_argument("--since", help="only commits since DATE (git --since syntax)")
    ap.add_argument("--until", help="only commits until DATE")
    ap.add_argument("--granularity", default="auto",
                    choices=["auto", "week", "month", "quarter"])
    ap.add_argument("--output", default="git-history-report/datapack.json")
    ap.add_argument("--session-gap", type=int, default=DEFAULT_SESSION_GAP_MIN,
                    help="minutes between commits that start a new work session")
    ap.add_argument("--first-bonus", type=int, default=DEFAULT_FIRST_COMMIT_BONUS_MIN,
                    help="assumed minutes of work before a session's first commit")
    ap.add_argument("--gap-days", type=int, default=DEFAULT_GAP_DAYS,
                    help="days of silence counted as a gap signal")
    args = ap.parse_args()

    knobs = {"session_gap": args.session_gap, "first_bonus": args.first_bonus,
             "gap_days": args.gap_days}

    print(f"▶ Collecting history from {len(args.repos)} repo(s)…", file=sys.stderr)
    pack = build_datapack(args.repos, args.since, args.until,
                          args.granularity, knobs)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, ensure_ascii=False)

    n_repos = sum(1 for r in pack["repos"] if not r.get("empty"))
    print(f"✔ Wrote {args.output}", file=sys.stderr)
    print(f"  {n_repos} repo(s) · granularity={pack['granularity']} · "
          f"{len(pack['periods'])} periods · "
          f"span {pack['span']['start'][:10]}…{pack['span']['end'][:10]}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
