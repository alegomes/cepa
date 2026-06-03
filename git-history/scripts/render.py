#!/usr/bin/env python3
"""git-history renderer — turn a datapack.json into PNG charts.

Deterministic: no interpretation, just visualization of the numbers the
collector produced. Requires matplotlib; if it's missing this script exits
non-zero with a clear message so the caller can fall back to text/Mermaid.

Usage:
    render.py [--datapack PATH] [--outdir DIR] [--metric commits|churn|est_hours]
"""

import argparse
import json
import sys

METRIC_LABELS = {
    "commits": "Commits",
    "churn": "Line churn (insertions + deletions)",
    "est_hours": "Estimated work hours",
}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def metric_matrix(pack, metric):
    """Return (repo_names, periods, rows) where rows[i][j] is repo i's value
    for period j."""
    periods = pack["periods"]
    repos = [r for r in pack["repos"] if not r.get("empty")]
    names = [r["name"] for r in repos]
    rows = []
    for r in repos:
        ebp = r["effort_by_period"]
        rows.append([float(ebp.get(p, {}).get(metric, 0) or 0) for p in periods])
    return names, periods, rows


def thin_ticks(periods, max_ticks=24):
    """Return (indices, labels) thinned so the x-axis stays legible."""
    n = len(periods)
    if n <= max_ticks:
        return list(range(n)), periods
    step = (n // max_ticks) + 1
    idx = list(range(0, n, step))
    return idx, [periods[i] for i in idx]


def render_stacked_area(pack, metric, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names, periods, rows = metric_matrix(pack, metric)
    if not names:
        return None
    x = list(range(len(periods)))
    fig, ax = plt.subplots(figsize=(max(10, len(periods) * 0.4), 6))
    ax.stackplot(x, *rows, labels=names, alpha=0.85)
    ax.set_title(f"Effort over time by project — {METRIC_LABELS[metric]}")
    ax.set_ylabel(METRIC_LABELS[metric])
    ax.set_xlabel(f"Time ({pack['granularity']})")
    idx, labels = thin_ticks(periods)
    ax.set_xticks(idx)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.legend(loc="upper left", fontsize=8, ncol=max(1, len(names) // 6))
    ax.margins(x=0)
    fig.tight_layout()
    path = f"{outdir}/effort-stacked-area.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def render_heatmap(pack, metric, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names, periods, rows = metric_matrix(pack, metric)
    if not names:
        return None
    fig, ax = plt.subplots(
        figsize=(max(10, len(periods) * 0.35), max(3, len(names) * 0.6)))
    data = rows if rows else [[0]]
    im = ax.imshow(data, aspect="auto", cmap="viridis")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    idx, labels = thin_ticks(periods)
    ax.set_xticks(idx)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_title(f"Activity heatmap — {METRIC_LABELS[metric]}")
    fig.colorbar(im, ax=ax, label=METRIC_LABELS[metric], fraction=0.025, pad=0.01)
    fig.tight_layout()
    path = f"{outdir}/activity-heatmap.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def render_milestones(pack, outdir):
    """Timeline scatter of tags + structural/keyword signals per repo."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from datetime import datetime

    repos = [r for r in pack["repos"] if not r.get("empty")]
    if not repos:
        return None

    def to_num(iso):
        return datetime.fromisoformat(iso).timestamp()

    fig, ax = plt.subplots(figsize=(12, max(3, len(repos) * 0.9)))
    markers = {
        "tag": ("*", "Release tag", 180),
        "structural": ("s", "Structural shift", 70),
        "keyword": ("o", "Pivot/learning keyword", 50),
        "revert": ("x", "Revert", 60),
    }
    plotted = set()
    for i, r in enumerate(repos):
        for t in r.get("tags", []):
            ax.scatter(to_num(t["date"]), i, marker=markers["tag"][0],
                       s=markers["tag"][2], color="#d62728",
                       label=markers["tag"][1] if "tag" not in plotted else None)
            plotted.add("tag")
        sig = r.get("signals", {})
        for s in sig.get("structural", []):
            ax.scatter(to_num(s["date"]), i, marker=markers["structural"][0],
                       s=markers["structural"][2], color="#1f77b4",
                       label=markers["structural"][1] if "structural" not in plotted else None)
            plotted.add("structural")
        for s in sig.get("keyword", []):
            ax.scatter(to_num(s["date"]), i, marker=markers["keyword"][0],
                       s=markers["keyword"][2], color="#2ca02c", alpha=0.7,
                       label=markers["keyword"][1] if "keyword" not in plotted else None)
            plotted.add("keyword")
        for s in sig.get("reverts", []):
            ax.scatter(to_num(s["date"]), i, marker=markers["revert"][0],
                       s=markers["revert"][2], color="#ff7f0e",
                       label=markers["revert"][1] if "revert" not in plotted else None)
            plotted.add("revert")

    ax.set_yticks(range(len(repos)))
    ax.set_yticklabels([r["name"] for r in repos], fontsize=9)
    ax.set_title("Milestones & narrative signals over time")

    # Human-readable date ticks
    span = pack["span"]
    lo, hi = to_num(span["start"]), to_num(span["end"])
    # Day-granular labels for short spans, month-granular for long ones, so
    # ticks don't collapse to the same repeated label.
    date_fmt = "%Y-%m-%d" if span["days"] <= 150 else "%Y-%m"
    n_ticks = 8
    ticks = [lo + (hi - lo) * k / (n_ticks - 1) for k in range(n_ticks)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([datetime.fromtimestamp(t).strftime(date_fmt) for t in ticks],
                       rotation=45, ha="right", fontsize=8)
    if plotted:
        ax.legend(loc="upper left", fontsize=8)
    ax.margins(y=0.2)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    path = f"{outdir}/milestones-timeline.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser(description="Render charts from a datapack.")
    ap.add_argument("--datapack", default="git-history-report/datapack.json")
    ap.add_argument("--outdir", default="git-history-report")
    ap.add_argument("--metric", default="est_hours",
                    choices=["commits", "churn", "est_hours"])
    args = ap.parse_args()

    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("✗ matplotlib not installed. Install it (`pip install matplotlib`) "
              "or fall back to Mermaid/ASCII charts in the report.", file=sys.stderr)
        sys.exit(3)

    import os
    os.makedirs(args.outdir, exist_ok=True)
    pack = load(args.datapack)

    produced = []
    for fn in (lambda: render_stacked_area(pack, args.metric, args.outdir),
               lambda: render_heatmap(pack, args.metric, args.outdir),
               lambda: render_milestones(pack, args.outdir)):
        p = fn()
        if p:
            produced.append(p)
            print(f"✔ {p}", file=sys.stderr)

    if not produced:
        print("⚠ Nothing to render (no non-empty repos).", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
