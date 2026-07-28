#!/usr/bin/env python3
"""Regression tests for the negative-example priming defect (2026-07-28).

No third-party deps — run with `python3 tests/test_prompt_placeholder_hosts.py`.

The incident: `atlassian-expert`'s rule forbidding site inference spelled the
forbidden value out by name — a *plausible*, repo-specific host. The agent read
the prohibition and used exactly the host quoted inside it, then asked the user
to authorize OAuth for a domain that does not exist. A negative example that is
plausible and specific to the repo in front of the agent works as a suggestion,
not as a prohibition.

Guards, over every file that is loaded into an agent's context (agent prompts,
slash commands, skills — NOT docs/ or the changelog, which humans read):
  - every `<x>.atlassian.net` host is from the fictional placeholder set;
  - the atlassian-expert prompt still carries both halves of the fix — the
    "placeholder, never a value" caveat and the "missing site is BLOCKED, never
    an auth request" rule.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Obviously fictional hosts. Anything else reads as a real, usable value.
ALLOWED_HOSTS = {"example", "acme", "your-site", "seu-site"}

HOST_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9.-]*)\.atlassian\.net")

# Directories whose content is prompt context for an agent, not human prose.
PROMPT_DIRS = ("agents", "commands", "skills", "hooks")

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def prompt_files():
    """Every plugin file that lands in an agent's context window."""
    for plugin_dir in sorted(REPO.iterdir()):
        if not plugin_dir.is_dir() or plugin_dir.name.startswith("."):
            continue
        if plugin_dir.name in {"docs", "tests", "bin", "archive"}:
            continue
        for sub in PROMPT_DIRS:
            root = plugin_dir / sub
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix in {".md", ".yaml", ".yml"}:
                    yield path


def main():
    print("prompt placeholder hosts")

    scanned = 0
    offenders = []
    for path in prompt_files():
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for host in HOST_RE.findall(line):
                label = host.split(".")[0]
                if label not in ALLOWED_HOSTS:
                    rel = path.relative_to(REPO)
                    offenders.append(f"{rel}:{lineno} → {host}.atlassian.net")

    check("varreu arquivos de prompt", scanned > 0, f"scanned={scanned}")
    check(
        "nenhum host plausível em prompt de agente",
        not offenders,
        "; ".join(offenders),
    )

    expert = REPO / "board-flow" / "agents" / "atlassian-expert.md"
    text = expert.read_text(encoding="utf-8")

    check(
        "atlassian-expert marca hostnames como placeholder",
        "placeholder illustrating the *prohibition*" in text,
        "caveat removido do prompt",
    )
    check(
        "atlassian-expert proíbe pedir auth para site inventado",
        "never an auth request" in text,
        "regra do pedido de OAuth removida",
    )

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
