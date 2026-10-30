#!/usr/bin/env python3
"""gen-locks — generates the per-topology copies of bash-path-lock from a template.

## Why it exists

`bash-path-lock.py` lives in five copies, one per topology with a hook. Until
2026-08-17 the maintenance rule was human: "every fix lands in all 5". It
failed twice in a verifiable way:

- the fix for the `>=` false positive (the hook read the `>` of `>=` as a
  redirection and blocked a legitimate command) had to be propagated by hand;
- the treatment of `git mv` as a write stayed only in the `docs-topology` copy.
  In the other four, an agent moved a file out of its own lane with `git mv`
  and the lock saw nothing. Nobody noticed until a test compared the copies.

The failure mode is silent — the lagging copy does not break, it **allows** what
the others block, and the agent's report reads as success.

`tests/test_lock_copies_drift.py` detects the divergence **after** it happens.
This generator makes it impossible: there is one template, and the five copies
are a function of it.

## Why only bash-path-lock, and not path-lock

`path-lock.py` carries `ALLOWED_WRITES` — the map of who writes where, which is
**topology data**, not engine. Centralizing it here would take the permission
list away from the agents it governs, which is where it needs to be so someone
can check it against the agent's `Writes:`. `bash-path-lock` does not have that
problem: it imports the allowlist from its sibling and is 100% mechanical.

For `path-lock`, the guarantee remains the detector — declared, with the
reason, instead of a centralization that would worsen readability.

## Usage

    python3 bin/gen-locks.py --check    # do the copies on disk match the template?
    python3 bin/gen-locks.py --write    # regenerates the five
    python3 bin/gen-locks.py --diff     # shows what would change

`--check` is what the test calls. Exits non-zero when some copy diverged.
"""

import argparse
import difflib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "common" / "hooks" / "_templates" / "bash-path-lock.py.tmpl"
TARGET = "hooks/bash-path-lock.py"

# Per-topology table. It is the ONLY thing that legitimately varies between the
# copies — and, being here, it is auditable at a glance. Adding a new topology
# with a hook is adding a line and running --write.
#
#   dir     the topology's directory in the repo
#   plugin  plugin name (the prefix that arrives in agent_type)
#   alias   prefix of the module imported via importlib (must not collide)
#   noun    what the topology writes — changes the block sentence: the build
#           topologies write `código`; design/discovery/docs write
#           `artefatos`. Saying "source" to someone who only writes documents
#           makes the message sound wrong to whoever reads it.
TOPOLOGIES = [
    {"dir": "build-team",    "plugin": "build-team", "alias": "multiteam", "noun": "código"},
    {"dir": "build-hex",     "plugin": "build-hex",  "alias": "hex",       "noun": "código"},
    {"dir": "discovery",     "plugin": "discovery",  "alias": "discovery", "noun": "artefatos"},
    {"dir": "design",        "plugin": "design",     "alias": "design",    "noun": "artefatos"},
    {"dir": "docs-topology", "plugin": "docs",       "alias": "docs",      "noun": "artefatos"},
    {"dir": "marketing",     "plugin": "marketing",  "alias": "marketing", "noun": "artefatos"},
]

# How each copy obtains the allowlist from the sibling path-lock. build-hex is
# the only one that resolves architectural roles (domain/api/adapter…) to module
# names, reading the project's `build-hex.yaml`; the others read the module's
# fixed dict.
HEX_RESOLUTION = """    roles, extra = pl.load_config(project_root)
    allowed_writes = pl.build_allowed_writes(roles, extra)
    agent = pl.detect_agent(payload)
    allowed = allowed_writes.get(agent)"""

PLAIN_RESOLUTION = """    agent = pl.detect_agent(payload)
    allowed = pl.ALLOWED_WRITES.get(agent)"""


def render(topo: dict) -> str:
    src = TEMPLATE.read_text(encoding="utf-8")
    # The template header explains the template, not the copy. The copy gets its own.
    body = src.split("\n#!/usr/bin/env python3\n", 1)
    if len(body) == 2:
        src = "#!/usr/bin/env python3\n" + body[1]
    else:  # is the shebang the template's 1st line? then drop only the comment block
        lines = src.splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("#!"))
        src = "\n".join(lines[start:])

    resolution = HEX_RESOLUTION if topo["dir"] == "build-hex" else PLAIN_RESOLUTION
    marks = {
        "@@PLUGIN@@": topo["plugin"],
        "@@ALIAS@@": topo["alias"],
        "@@NOUN@@": topo["noun"],
        "@@ALLOWLIST_RESOLUTION@@": resolution,
    }
    for mark, value in marks.items():
        src = src.replace(mark, value)
    leftover = [m for m in marks if m in src]
    assert not leftover, f"marca não substituída em {topo['dir']}: {leftover}"
    return src


def main():
    ap = argparse.ArgumentParser(description="Gera as cópias do bash-path-lock.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="as cópias batem com o molde?")
    g.add_argument("--write", action="store_true", help="regenera as cinco cópias")
    g.add_argument("--diff", action="store_true", help="mostra o que mudaria")
    args = ap.parse_args()

    if not TEMPLATE.exists():
        print(f"✗ molde ausente: {TEMPLATE}", file=sys.stderr)
        return 2

    divergent = []
    for topo in TOPOLOGIES:
        path = REPO / topo["dir"] / TARGET
        want = render(topo)
        have = path.read_text(encoding="utf-8") if path.exists() else ""

        if args.write:
            if have != want:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(want, encoding="utf-8")
                print(f"  regenerado  {path.relative_to(REPO)}")
            else:
                print(f"  já em dia   {path.relative_to(REPO)}")
            continue

        if have != want:
            divergent.append(topo["dir"])
            if args.diff:
                print(f"\n=== {path.relative_to(REPO)} ===")
                for line in difflib.unified_diff(
                        have.splitlines(), want.splitlines(),
                        fromfile="no disco", tofile="do molde", lineterm="", n=2):
                    print(line)

    if args.write:
        return 0

    if divergent:
        print(f"\n✗ {len(divergent)} cópia(s) divergem do molde: {', '.join(divergent)}")
        print("  Edite common/hooks/_templates/bash-path-lock.py.tmpl e rode")
        print("  `python3 bin/gen-locks.py --write`. Editar a cópia direto não")
        print("  propaga — é exatamente assim que o `git mv` ficou anos faltando")
        print("  em quatro das cinco.")
        return 1
    print(f"✓ as {len(TOPOLOGIES)} cópias são exatamente o molde renderizado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
