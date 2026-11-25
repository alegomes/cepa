#!/usr/bin/env python3
"""CS-5 of docs/spec/reforma-de-nomes-dos-comandos.md: the flags of the slash
commands and the verdict values are shown in English, and the old Portuguese
forms are still accepted.

  - the mode menu prints `/common:spec --continue <slug>`, never `--continuar`;
  - the `argument-hint` of the slash commands has the English flags and none of
    the Portuguese ones, and the body of each command says the old form is still
    accepted (a slash command is prose an agent executes);
  - `cepa queue verdict` takes kept|vetoed|refined and writes the very marker
    that mantida|vetada|refinada write (the marker in the document stays);
  - `cepa queue finish` takes --open-point / --resolve-open-point and still
    takes --pendencia / --resolve-pendencia;
  - a prompt typed with the old `/common:spec --continuar x` is still the menu
    action `/common:spec --continue`.

Run with `python3 -m pytest tests/test_slash_flags_in_english.py -q`.
"""
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin"
CEPA = BIN / "cepa"
CEPA_QUEUE = BIN / "cepa-queue"
COMMANDS = REPO / "common" / "commands"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import build_repo, item  # noqa: E402

ENV = dict(os.environ, CEPA_PREFLIGHT="off", NO_COLOR="1", GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for _v in ("CEPA_RUN", "CEPA_UNTIL_RUN", "CEPA_AUTONOMOUS_RUN_ID", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(_v, None)


def _run(argv, cwd):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                          cwd=str(cwd), env=ENV, timeout=120)


def _hint(name):
    text = (COMMANDS / name).read_text(encoding="utf-8")
    m = re.search(r"^argument-hint:(.*)$", text, re.M)
    assert m, f"{name} has no argument-hint"
    return m.group(1), text


# --- 1. the mode menu -------------------------------------------------------

def test_menu_prints_continue_not_continuar():
    r = _run([CEPA, "modes", "--menu", "discovery"], REPO)
    assert r.returncode == 0, r.stderr
    assert "/common:spec --continue <slug>" in r.stdout, r.stdout
    assert "--continuar" not in r.stdout, r.stdout


# --- 2 and 5. argument-hint and the compatibility line ----------------------

OLD_IN_HINT = ["--continuar", "--fechar", "--lista", "--lentes", "--angulos",
               "--na-branch", "--fila", "seguranca", "api-contrato", "dados",
               "arquitetura", "--plan"]

# command file -> (English forms in the hint, old forms the body says it accepts)
HINTS = {
    "spec.md": (["--continue", "--close", "--list"],
                ["--continuar", "--fechar", "--lista"]),
    "advisors.md": (["--lenses", "security", "api-contract", "data", "ux",
                     "architecture"],
                    ["--lentes", "seguranca", "api-contrato", "dados",
                     "arquitetura"]),
    "gauntlet.md": (["--angles"], ["--angulos"]),
    "queue-run.md": (["--on-branch"], ["--na-branch"]),
    "run-review.md": (["--queue"], ["--fila"]),
    "next.md": (["--queue"], ["--plan"]),
}


def test_argument_hints_are_english_only():
    for name, (new, _old) in HINTS.items():
        hint, _ = _hint(name)
        for word in new:
            assert word in hint, (name, word, hint)
        for word in OLD_IN_HINT:
            assert word not in hint, (name, word, hint)


def test_each_command_body_says_the_old_form_is_still_accepted():
    for name, (_new, old) in HINTS.items():
        _, text = _hint(name)
        body = text.split("---", 2)[2]
        for word in old:
            rows = body.splitlines()
            near = " ".join(" ".join(" ".join(rows[max(0, i - 1):i + 3]).split())
                            for i, row in enumerate(rows) if word in row)
            assert near and "still accepted" in near, (name, word)


def test_queue_run_and_epic_say_the_old_finish_flags_are_accepted():
    body = (COMMANDS / "queue-run.md").read_text(encoding="utf-8")
    assert "--open-point" in body and "--resolve-open-point" in body
    flat = " ".join(body.split())
    assert "`--pendencia` is still accepted" in flat
    assert "`--resolve-pendencia` is still accepted" in flat
    for name in ("spec.md", "epic.md"):
        t = " ".join((COMMANDS / name).read_text(encoding="utf-8").split())
        assert "kept|vetoed|refined" in t, name
        assert "`mantida`, `vetada` and `refinada` are still accepted" in t, name


# --- 3. verdict -------------------------------------------------------------

SPEC = """# Spec

**Status:** draft

## Decided without asking

- Primeira decisao.
- Segunda decisao.
- Terceira decisao.
"""

TYPED = [("kept", "mantida", []), ("vetoed", "vetada", ["--reason", "fora do ciclo"]),
         ("refined", "refinada", ["--text", "Texto novo"])]


def _verdict(typed, extra):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "-C", tmp, "init", "-q"], check=True)
        spec = root / "spec.md"
        spec.write_text(SPEC, encoding="utf-8")
        r = _run([CEPA_QUEUE, "verdict", spec, "1", typed, *extra, "--repo", tmp], root)
        return r, spec.read_text(encoding="utf-8")


def test_verdict_english_values_write_the_same_marker_as_the_old_ones():
    for new, old, extra in TYPED:
        rn, fn = _verdict(new, extra)
        ro, fo = _verdict(old, extra)
        assert rn.returncode == 0, (new, rn.stderr)
        assert ro.returncode == 0, (old, ro.stderr)
        assert fn == fo, (new, old, fn, fo)
        assert f"· {old} em " in fn, fn


def test_verdict_errors_name_the_value_typed():
    for typed, needs in (("vetoed", "--reason"), ("refined", "--text"),
                         ("vetada", "--reason"), ("refinada", "--text")):
        r, _ = _verdict(typed, [])
        assert r.returncode == 2, (typed, r.stdout, r.stderr)
        assert f"{typed} exige {needs}" in r.stderr, (typed, r.stderr)


def test_verdict_help_shows_english_values():
    r = _run([CEPA_QUEUE, "verdict", "--help"], REPO)
    assert r.returncode == 0
    assert "kept" in r.stdout and "vetoed" in r.stdout and "refined" in r.stdout
    assert " 2 kept" in r.stdout and " 2 mantida" not in r.stdout


# --- 4. finish --------------------------------------------------------------

def _finish(open_flag, resolve_flag):
    """Opens two points with `open_flag`, resolves point 1 with `resolve_flag`;
    returns the item as recorded."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])

        def cli(*args):
            return subprocess.run([sys.executable, str(CEPA_QUEUE), *args,
                                   "--repo", str(root)], capture_output=True,
                                  text=True, cwd=root, env=ENV, timeout=60)

        def commit():
            subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=ENV)
            subprocess.run(["git", "commit", "-qm", "x", "--allow-empty"], cwd=root,
                           check=True, env=ENV, capture_output=True)

        assert cli("start", "fila", "a1").returncode == 0
        commit()
        p = cli("finish", "fila", "a1", "--status", "pending", "--evidence", "e",
                open_flag, "x um", open_flag, "x dois")
        assert p.returncode == 0, p.stderr + p.stdout
        commit()
        assert cli("start", "fila", "a1").returncode == 0
        commit()
        p = cli("finish", "fila", "a1", "--status", "pending", "--evidence", "feito",
                resolve_flag, "1")
        assert p.returncode == 0, p.stderr + p.stdout
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        it = {i["id"]: i for i in yaml.safe_load(plan.read_text())["items"]}["a1"]
        return [(x["texto"], bool(x.get("resolvida_em")), x.get("como"))
                for x in it["pendencias"]]


def test_finish_open_point_records_the_same_as_pendencia():
    new = _finish("--open-point", "--resolve-open-point")
    old = _finish("--pendencia", "--resolve-pendencia")
    assert new == old == [("x um", True, "feito"), ("x dois", False, None)], (new, old)


def test_finish_resolve_point_alias_still_accepted():
    assert _finish("--open-point", "--resolve-point")[0][1] is True


def test_finish_help_shows_english_flags_first():
    r = _run([CEPA_QUEUE, "finish", "--help"], REPO)
    assert r.returncode == 0
    assert "--open-point" in r.stdout and "--resolve-open-point" in r.stdout
    usage = r.stdout.split("\n\n", 1)[0]
    assert "--pendencia" not in usage and "--resolve-pendencia" not in usage, usage


# --- the hook: a prompt with the old flag is still the menu action ----------

def _session_mode():
    spec = importlib.util.spec_from_file_location(
        "session_mode_cs5", REPO / "common" / "hooks" / "session-mode.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO / "common" / "hooks"))
    spec.loader.exec_module(mod)
    return mod


def test_old_flag_prompt_is_recognised_as_the_menu_action():
    sm = _session_mode()
    pending = {"actions": [
        {"n": 1, "commands": ["/common:spec <the idea>"]},
        {"n": 2, "commands": ["/common:spec --continue <slug>"]}]}
    assert sm.menu_choice(pending, "/common:spec --continuar x") == (
        2, "/common:spec --continue")
    assert sm.menu_choice(pending, "/common:spec --continue x") == (
        2, "/common:spec --continue")


def test_menu_saved_before_the_rename_still_matches():
    """A `.claude/mode-menu-pending` written before CS-5 carries `--continuar`;
    the choice still matches and is recorded with the English flag."""
    sm = _session_mode()
    pending = {"actions": [
        {"n": 1, "commands": ["/common:spec"]},
        {"n": 2, "commands": ["/common:spec --continuar <slug>"]},
    ]}
    assert sm.menu_choice(pending, "/common:spec --continue x") == (2, "/common:spec --continue")
    assert sm.menu_choice(pending, "/common:spec --continuar x") == (2, "/common:spec --continue")
    assert sm.menu_choice(pending, "2") == (2, "/common:spec --continue")
