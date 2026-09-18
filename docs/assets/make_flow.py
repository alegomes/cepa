#!/usr/bin/env python3
"""Draws docs/assets/flow.svg from docs/assets/flow-data.csv.

The CSV holds one line per tracker card with dates only (created, outcome,
resolved). No keys, titles or client names. Run: python3 docs/assets/make_flow.py
"""
import csv
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = list(csv.DictReader(open(HERE / "flow-data.csv")))
d = lambda s: date.fromisoformat(s)
start = min(d(r["created"]) for r in rows)
end = max([d(r["created"]) for r in rows] + [d(r["resolved"]) for r in rows if r["resolved"]])
days = [start + timedelta(n) for n in range((end - start).days + 1)]
# discarded cards leave the scope on the day they are discarded
scope = [sum(1 for r in rows if d(r["created"]) <= t and not (r["outcome"] == "discarded" and d(r["resolved"]) <= t)) for t in days]
done = [sum(1 for r in rows if r["outcome"] == "done" and d(r["resolved"]) <= t) for t in days]

W, H, L, R, T, B = 860, 380, 52, 20, 44, 40
top = (max(scope) // 50 + 1) * 50
x = lambda i: L + (W - L - R) * i / (len(days) - 1)
y = lambda v: H - B - (H - T - B) * v / top
def area(vals, fill):
    pts = [f"{x(0):.1f},{y(0):.1f}"]
    for i, v in enumerate(vals):  # step chart
        if i: pts.append(f"{x(i):.1f},{y(vals[i-1]):.1f}")
        pts.append(f"{x(i):.1f},{y(v):.1f}")
    pts.append(f"{x(len(vals)-1):.1f},{y(0):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'

o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="system-ui,sans-serif" font-size="12">',
     f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
for v in range(0, top + 1, 50):
    o.append(f'<line x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#e5e7eb"/>')
    o.append(f'<text x="{L-8}" y="{y(v)+4:.1f}" text-anchor="end" fill="#6b7280">{v}</text>')
o.append(area(scope, "#f59e0b"))
o.append(area(done, "#2f855a"))
for i, t in enumerate(days):
    if t.day in (1, 16):
        o.append(f'<text x="{x(i):.1f}" y="{H-B+18}" text-anchor="middle" fill="#6b7280">{t.strftime("%b %-d")}</text>')
o.append(f'<text x="{L}" y="20" font-size="14" font-weight="600" fill="#111827">Cards in scope vs. cards done, one engineer, one project</text>')
o.append(f'<rect x="{L}" y="28" width="10" height="10" fill="#f59e0b"/><text x="{L+15}" y="37" fill="#374151">open</text>')
o.append(f'<rect x="{L+60}" y="28" width="10" height="10" fill="#2f855a"/><text x="{L+75}" y="37" fill="#374151">done</text>')
cepa = days.index(date(2026, 8, 12))
o.append(f'<line x1="{x(cepa):.1f}" x2="{x(cepa):.1f}" y1="{T}" y2="{H-B}" stroke="#111827" stroke-dasharray="4 3"/>')
o.append(f'<text x="{x(cepa)-6:.1f}" y="{T+12}" text-anchor="end" fill="#111827">Cepa starts on this board</text>')
o.append(f'<text x="{W-R-6}" y="{y(done[-1])+18:.1f}" text-anchor="end" fill="#ffffff" font-weight="600">{done[-1]} done</text>')
o.append("</svg>")
(HERE / "flow.svg").write_text("\n".join(o))
print(f"{start}..{end} scope={scope[-1]} done={done[-1]} done_on_aug12={done[cepa]} done_before={done[cepa-1]}")
