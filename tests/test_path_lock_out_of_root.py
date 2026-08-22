#!/usr/bin/env python3
"""Regression tests for the path-lock out-of-root carve-out.

No third-party deps — run with `python3 tests/test_path_lock_out_of_root.py`.
Exits non-zero on the first failure.

Guards the /tmp-perturbation block: path_matches() does
`Path(file_path).resolve().relative_to(project_root)`, which raises ValueError
for any path outside the project tree → returns False → the write falls through
to BLOCKED (exit 2). That made proof-reviewer's throwaway /tmp perturbation
worktree (where it breaks code to prove a test goes RED) structurally
un-writable, even though the hook's own comments say out-of-root is "never
gated". The fix: main() fails open when the resolved target is outside
project_root — the same carve-out bash-path-lock.py already applies. See memory
and the proof-reviewer note in build_allowed_writes.

The hook ships in every topology, so we drive every copy as a subprocess and
assert exit codes end-to-end — a fix that misses one topology is still a bug.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/path-lock.py"))


def plugin_name(path):
    spec = importlib.util.spec_from_file_location(
        f"pl_{path.parent.parent.name}", str(path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PLUGIN_NAME


def run(hook, agent_type, file_path, cwd):
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(file_path)},
        "agent_type": agent_type,
        "cwd": str(cwd),
    }
    p = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return p.returncode


def main():
    if not HOOKS:
        print("FAIL: no */hooks/path-lock.py found under", REPO)
        return 1

    failures = 0
    for hook in HOOKS:
        topo = hook.parent.parent.name
        pname = plugin_name(hook)
        proj = Path(tempfile.mkdtemp())   # project root
        other = Path(tempfile.mkdtemp())  # disjoint tree — stands in for /tmp/proof-*

        cases = [
            # (label, agent_type, file_path, expected_exit, why)
            ("out-of-root unknown -> allow",
             f"{pname}:zzz-nonexistent-agent", other / "src/main/java/Foo.java", 0,
             "a write outside the project tree is not this lock's business"),
            ("in-root unknown   -> block",
             f"{pname}:zzz-nonexistent-agent", proj / "src/main/java/Foo.java", 2,
             "carve-out must stay scoped: in-root unknown agent is still gated"),
        ]
        # The exact bug that drove this fix: a KNOWN proof-reviewer perturbing
        # source in its /tmp worktree. Only build-hex ships that agent.
        if "proof-reviewer" in hook.read_text():
            cases.append(
                ("out-of-root proof-reviewer -> allow",
                 f"{pname}:proof-reviewer", other / "src/main/java/Foo.java", 0,
                 "proof-reviewer must be able to break code in its /tmp worktree")
            )
            # O destino do veredito (22/08/2026). Nos projetos que rodam o
            # portão `.claude/` é gitignored, então o veredito gravado lá some
            # junto com a worktree descartável da sessão — sobrevivia só porque
            # alguém copiava o arquivo para docs/ depois de cada card, e é o
            # passo que se esquece ao fechar a sessão. Travar a escrita em
            # docs/proof/ é o que torna isso mecânico em vez de disciplina: se o
            # caminho velho continuasse liberado, o esquecimento voltaria calado.
            cases += [
                ("proof-reviewer docs/proof   -> allow",
                 f"{pname}:proof-reviewer", proj / "docs/proof/WEGO-1.yaml", 0,
                 "docs/proof/ é versionado — é onde o veredito sobrevive"),
                ("proof-reviewer .claude/proof-> block",
                 f"{pname}:proof-reviewer", proj / ".claude/proof/WEGO-1.yaml", 2,
                 "o caminho antigo tem de BLOQUEAR, senão o veredito volta a "
                 "morrer com a worktree sem ninguém notar"),
            ]

        for label, agent_type, fp, want, why in cases:
            got = run(hook, agent_type, fp, proj)
            if got == want:
                print(f"PASS [{topo:11}] {label:34} -> exit {got}")
            else:
                failures += 1
                print(f"FAIL [{topo:11}] {label:34} -> exit {got} (want {want}: {why})")

    print()
    if failures:
        print(f"{failures} failure(s) across {len(HOOKS)} hook copies")
        return 1
    print(f"All checks passed across {len(HOOKS)} hook copies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
