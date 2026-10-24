#!/usr/bin/env python3
"""End to end for the item `until-build-longo-sem-trava`: a real `claude -p`,
inside a `cepa-until` window, collects a build that runs past 10 minutes.

It is NOT part of the suite (`tests/run-all.sh` only runs `test_*.py`): it calls
the real `claude`, costs money (about US$ 0.20 with sonnet) and takes the
build's time plus a few minutes. Run it by hand when touching
`no-background-build` or when `claude` changes version:

    python3 tests/e2e_long_build_claude_p.py            # 700s build
    python3 tests/e2e_long_build_claude_p.py --seconds 660 --model haiku

## Why it exists

The hook's unit test (`test_no_background_build.py`) proves the hook's DECISION
on a hand-built payload. It does not prove that an agent, receiving only the
request "run the build and collect the result", comes out the other side with
the result collected. That depends on two things only a real `claude -p`
shows, and which on 2026-09-27 (claude 2.1.283) were:

  - `claude -p` kills the background when the turn ends, with
    `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` at 0, absent or 120000;
  - an armed `Monitor` does not hold the turn.

If `claude` ever starts waiting for the background, this script stays green; if
the hook stops steering the agent, it goes red.

The request does not teach the recipe on purpose: the hook is the one that has
to teach it. The loaded hooks are ONLY this tree's (`--setting-sources local`
turns off the user's plugins), to measure the code here and not the installed one.

Exits 0 with the result collected, 1 without it.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"

REQUEST = ("Neste diretório, rode `make verify` (é o build do projeto; leva uns "
          "{minutos} minutos) e colha o resultado: grave em resultado.txt a "
          "última linha que o build imprimiu e o código de saída dele. Só isso.")


def settings():
    bg = f"python3 {HOOKS / 'no-background-build.py'}"
    busy = f"python3 {HOOKS / 'no-busy-wait.py'}"
    return {"hooks": {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": bg},
                                          {"type": "command", "command": busy}]},
            {"matcher": "Monitor", "hooks": [{"type": "command", "command": bg}]},
        ],
        "Stop": [{"hooks": [{"type": "command", "command": bg}]}],
    }}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=700,
                    help="duração do build sintético (default 700: passa do "
                         "teto de 10 min do Bash, que é o caso do item)")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--dir", help="onde montar o cenário (default: tmp novo)")
    a = ap.parse_args()

    d = Path(a.dir or tempfile.mkdtemp(prefix="e2e-build-longo-"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "Makefile").write_text(
        f"verify:\n\tsleep {a.seconds}\n\t@echo \"BUILD SUCCESS\"\n")
    (d / "settings.json").write_text(json.dumps(settings(), indent=1))

    env = dict(os.environ)
    env["CEPA_UNTIL_RUN"] = "1"
    env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"] = "0"  # what cepa-until exports
    request = REQUEST.format(minutos=max(1, round(a.seconds / 60)))
    print(f"cenário em {d}; build de {a.seconds}s; modelo {a.model}")
    started_at = time.time()
    p = subprocess.run(
        ["claude", "-p", request, "--model", a.model,
         "--dangerously-skip-permissions", "--setting-sources", "local",
         "--settings", str(d / "settings.json"), "--output-format", "json"],
        cwd=d, env=env, capture_output=True, text=True)
    elapsed = time.time() - started_at
    (d / "saida.json").write_text(p.stdout)
    (d / "stderr.txt").write_text(p.stderr)

    result_file = d / "resultado.txt"
    lines = result_file.read_text().split() if result_file.exists() else []
    collected = "SUCCESS" in " ".join(lines) and "0" in lines
    try:
        cost = json.loads(p.stdout).get("total_cost_usd")
    except (json.JSONDecodeError, AttributeError):
        cost = None
    print(f"claude saiu {p.returncode} em {elapsed:.0f}s (custo {cost})")
    print(f"resultado.txt: {lines or 'ausente'}")
    if elapsed < a.seconds:
        print("FAIL  o claude saiu antes de o build terminar: o build morreu "
              "com o turno")
        return 1
    if not collected:
        print("FAIL  o build não foi colhido")
        return 1
    print("ok  build de mais de 10 min colhido dentro da janela")
    return 0


if __name__ == "__main__":
    sys.exit(main())
