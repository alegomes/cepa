#!/usr/bin/env python3
"""O validation-lead grava o próprio veredito em docs/validation/, e só lá.

No third-party deps — run with `python3 tests/test_path_lock_validation_lead.py`.
Exits non-zero on the first failure.

O agente validation-lead (build-hex e build-team) tem a instrução de gravar
`.claude/validation/<KEY>.yaml`, e o `cepa-plan finish --status done` recusa
fechar item sem esse arquivo. Mas o ALLOWED_WRITES dele era `[]`: o path-lock
barrava a escrita, e o orquestrador transcrevia o veredito à mão. Aconteceu nos
3 itens entregues do run cepa-until 2026-09-27-0832 do wego-acessos-backend
(WEGO-2323, 2324, 2325). O veredito gravado por outro agente deixa de ser
independente de quem validou.

O destino é docs/validation/ (27/09/2026), e não .claude/validation/: nos
projetos que rodam o portão `.claude/*` é ignorado pelo git, então o veredito
morria com a worktree descartável do run. É o mesmo motivo que levou o
proof-reviewer para docs/proof/.

Dirige cada cópia do hook como subprocesso, como test_path_lock_out_of_root.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(
    h for h in REPO.glob("*/hooks/path-lock.py")
    if '"validation-lead"' in h.read_text()
)


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
        print("FAIL: nenhum */hooks/path-lock.py com validation-lead em", REPO)
        return 1

    failures = 0
    for hook in HOOKS:
        topo = hook.parent.parent.name
        agent = f"{plugin_name(hook)}:validation-lead"
        proj = Path(tempfile.mkdtemp())

        cases = [
            # (label, file_path, expected_exit, why)
            ("veredito em docs/validation  -> allow",
             proj / "docs/validation/WEGO-1.yaml", 0,
             "é o arquivo que o agente tem ordem de gravar e o finish exige"),
            ("caminho antigo .claude/validation -> block",
             proj / ".claude/validation/WEGO-1.yaml", 2,
             ".claude/ é ignorado pelo git nos projetos: o veredito gravado lá "
             "some com a worktree, como acontecia com .claude/proof/"),
            ("código de produção           -> block",
             proj / "src/main/java/Foo.java", 2,
             "a liberação não pode abrir o código para quem só valida"),
            ("veredito de outro portão     -> block",
             proj / ".claude/acceptance/WEGO-1.yaml", 2,
             "o aceite é do completion-auditor, não do validation-lead"),
        ]
        for label, fp, want, why in cases:
            got = run(hook, agent, fp, proj)
            if got == want:
                print(f"PASS [{topo:11}] {label} -> exit {got}")
            else:
                failures += 1
                print(f"FAIL [{topo:11}] {label} -> exit {got} (want {want}: {why})")

    print()
    if failures:
        print(f"{failures} failure(s) across {len(HOOKS)} hook copies")
        return 1
    print(f"All checks passed across {len(HOOKS)} hook copies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
