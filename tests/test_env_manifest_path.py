#!/usr/bin/env python3
"""Regression test for the environment manifest reader (`common/hooks/_wtlib.py`).

No dependencies — run with `python3 tests/test_env_manifest_path.py`.
Exits non-zero on failure.

## What this file exists to hold

The environment manifest declares the project's runtime: ports, how to start the app,
healthcheck, and the `seed:` list of gitignored files that a new worktree
needs to receive in order to work (`.env`, local credentials). Whoever reads it is the
worktree seeding (`seed-worktree.py`, `/common:worktree-start`) and the screen
gate, when its `up:` says `env.yaml`.

It lived in `.claude/env.yaml` until 2026-08-22 — and `.claude/` is gitignored in the
projects that use the harness, so the manifest was invisible to git and vanished
with the session's disposable worktree. Now the place is `docs/env.yaml`, and the
old one is still read.

**There is no hook here to lock the destination, and that is a real difference** from
the proof verdict and the UI proof manifest: those two are
written by an agent, so a hook can block the write in the wrong place.
This one is declared by hand by the project owner — there is no write to block. The
read order tested below is the ONLY mechanics that moves the convention, which
makes it the only thing that can break it silently: if the preference inverts, the
project that moved the file starts being seeded by the old declaration, and a
worktree is born without the files the new `seed:` listed.

## Perturbation (how to know this test proves something)

Invert the order of `ENV_MANIFEST_PATHS` and the case "both → docs wins" turns
red.
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("wtlib", REPO / "common" / "hooks" / "_wtlib.py")
wtlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wtlib)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def repo_with(**manifests):
    """Creates a temporary repo with the requested manifests: docs=..., claude=..."""
    root = tempfile.mkdtemp()
    for where, content in manifests.items():
        d = os.path.join(root, "docs" if where == "docs" else ".claude")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "env.yaml"), "w") as fh:
            fh.write(content)
    return root


NEW = "ports:\n  - 8083\nseed:\n  - .env\n  - novo.local\n"
OLD = "ports:\n  - 9999\nseed:\n  - .env\n  - antigo.local\n"

# ── precedence ────────────────────────────────────────────────────────────
r = repo_with(docs=NEW, claude=OLD)
check("os dois no disco → docs/env.yaml ganha",
      wtlib.env_manifest_list(r, "seed") == [".env", "novo.local"],
      wtlib.env_manifest_list(r, "seed"))
check("…e o caminho devolvido é o de docs/",
      str(wtlib.env_manifest_path(r)).endswith("docs/env.yaml"),
      str(wtlib.env_manifest_path(r)))

r = repo_with(claude=OLD)
check("só o antigo → segue sendo lido (repo que ainda não moveu)",
      wtlib.env_manifest_list(r, "seed") == [".env", "antigo.local"],
      wtlib.env_manifest_list(r, "seed"))

r = repo_with(docs=NEW)
check("só o novo → lido", wtlib.env_manifest_list(r, "seed") == [".env", "novo.local"],
      wtlib.env_manifest_list(r, "seed"))

# ── absence and garbage: fail-silent, like the whole seeding path ─────────
r = tempfile.mkdtemp()
check("nenhum manifesto → lista vazia, sem exceção",
      wtlib.env_manifest_list(r, "seed") == [], wtlib.env_manifest_list(r, "seed"))
check("nenhum manifesto → caminho None", wtlib.env_manifest_path(r) is None)

r = repo_with(docs=":::: isto não é yaml ::::\n")
check("manifesto ilegível → lista vazia, nunca estoura",
      wtlib.env_manifest_list(r, "seed") == [], wtlib.env_manifest_list(r, "seed"))

r = repo_with(docs=NEW)
check("chave ausente → lista vazia",
      wtlib.env_manifest_list(r, "inexistente") == [])

# ── the two list forms that the tolerant parser accepts ───────────────────
r = repo_with(docs="seed: [.env, cred.local]\n")
check("lista inline → lida", wtlib.env_manifest_list(r, "seed") == [".env", "cred.local"],
      wtlib.env_manifest_list(r, "seed"))

r = repo_with(docs="ports:\n  - 8083\nseed:\n  - .env   # comentário\n")
check("comentário no fim da linha → removido",
      wtlib.env_manifest_list(r, "seed") == [".env"], wtlib.env_manifest_list(r, "seed"))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all env-manifest path tests passed")
