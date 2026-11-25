#!/usr/bin/env python3
"""CS-6 of docs/spec/reforma-de-nomes-dos-comandos.md: every environment variable
Cepa owns has the `CEPA_` prefix and an English name, and the old one is still read.

  - a scan of `common/bin/` and `common/hooks/` (Python through the AST, the `cepa`
    launcher as shell text) fails on a variable that is READ without the `CEPA_`
    prefix (and is not on the short list of names that belong to someone else), on
    a name in the old-names table, or on a Portuguese word in a `CEPA_` name,
    outside the one place that reads the old name as a fallback;
  - the scan is load-bearing: it flags fabricated snippets (self-check);
  - `CEPA_MODE=off cepa --help` and `CEPA_MODO=off cepa --help` both exit 0, and the
    "environment" part of `cepa --help` cites the new forms and none of the old;
  - old name alone still works (CEPA_MODO, CEPA_ENCADEAR, CEPA_PERMISSOES=classificador,
    one CEPA_UNTIL_*, one CLAUDE_WT_*, one CCW_*), and with new and old both set to
    different values the new one wins;
  - Cepa sets the NEW name for the processes it launches;
  - the Python table and the launcher's shell table agree;
  - the living docs and the slash-command markdown show only the new names, except on
    a line that declares the compatibility.

Run with `python3 -m pytest tests/test_env_names_in_english.py -q`.
"""
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# This test runs a hook that emits telemetry (write-mode-gate); without this the
# events would land in ~/.claude/cepa-telemetry/ and enter the /common:metrics
# report as if they were real use. See tests/_isolated_telemetry.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin"
HOOKS = REPO / "common" / "hooks"
CEPA = BIN / "cepa"

# The contract of the spec ("Decided without asking"): old name -> new name.
OLD_TO_NEW = {
    "CEPA_MODO": "CEPA_MODE",
    "CEPA_MODO_DEFAULT": "CEPA_MODE_DEFAULT",
    "CEPA_ENCADEAR": "CEPA_CHAIN",
    "CEPA_PERMISSOES": "CEPA_PERMISSIONS",
    "CEPA_PROMPT_MODO": "CEPA_PROMPT_MODE",
    "CEPA_COR": "CEPA_COLOR",
    "CEPA_UNTIL_RUN": "CEPA_RUN",
    "CEPA_UNTIL_TETO_LEITURA": "CEPA_RUN_READER_CEILING",
    "CEPA_UNTIL_SONDA_REDE": "CEPA_RUN_NETWORK_PROBE",
    "CEPA_UNTIL_SONDA_INTERVALO": "CEPA_RUN_PROBE_INTERVAL",
    "CEPA_UNTIL_MODELO_LEITOR": "CEPA_RUN_READER_MODEL",
    "CEPA_UNTIL_MARGEM_RESET": "CEPA_RUN_RESET_MARGIN",
    "CEPA_UNTIL_LINHA_VIVA": "CEPA_RUN_LIVE_LINE",
    "CEPA_UNTIL_LIMITE_ANALISE": "CEPA_RUN_ANALYSIS_LIMIT",
    "CEPA_UNTIL_LEITOR": "CEPA_RUN_READER",
    "CEPA_UNTIL_HEARTBEAT": "CEPA_RUN_HEARTBEAT",
    "CEPA_UNTIL_GRACA_SIGTERM": "CEPA_RUN_SIGTERM_GRACE",
    "CEPA_UNTIL_ESPERA_RESPOSTA": "CEPA_RUN_ANSWER_WAIT",
    "CEPA_UNTIL_COR": "CEPA_RUN_COLOR",
    "CEPA_HEARTBEAT_ORFA": "CEPA_HEARTBEAT_ORPHAN",
    "CLAUDE_AUTONOMOUS_RUN_ID": "CEPA_AUTONOMOUS_RUN_ID",
    "CLAUDE_WT_CLAIM": "CEPA_WT_CLAIM",
    "CLAUDE_WT_CLAUDE_BIN": "CEPA_WT_CLAUDE_BIN",
    "CLAUDE_WT_NUDGE": "CEPA_WT_NUDGE",
    "CLAUDE_WT_ROOT": "CEPA_WT_ROOT",
    "CLAUDE_WT_SESSION_SOFTCAP": "CEPA_WT_SESSION_SOFTCAP",
    "CLAUDE_WT_SLICE": "CEPA_WT_SLICE",
    "CLAUDE_WT_SUBJECT": "CEPA_WT_SUBJECT",
    "CLAUDE_WT_SUBJECT_MINPROMPTS": "CEPA_WT_SUBJECT_MINPROMPTS",
    "CLAUDE_WT_SUBJECT_THRESHOLD": "CEPA_WT_SUBJECT_THRESHOLD",
    "CCW_SEED": "CEPA_SEED",
    "CCW_WORKTREE_HOME": "CEPA_WORKTREE_HOME",
    "CAPTURE_BUILD_DEBUG": "CEPA_CAPTURE_BUILD_DEBUG",
    "CAPTURE_BUILD_DEBUG_LOG": "CEPA_CAPTURE_BUILD_DEBUG_LOG",
    "LEAD_WORKTREE_DEBUG": "CEPA_LEAD_WORKTREE_DEBUG",
    "LEAD_WORKTREE_DEBUG_LOG": "CEPA_LEAD_WORKTREE_DEBUG_LOG",
}
# Other plugins: Cepa-owned too, only the prefix was missing.
OTHER_PLUGINS_OLD_TO_NEW = {
    "HEX_PATHLOCK_DEBUG": "CEPA_HEX_PATHLOCK_DEBUG",
    "HEX_PATHLOCK_DEBUG_LOG": "CEPA_HEX_PATHLOCK_DEBUG_LOG",
    "DOCS_PATHLOCK_DEBUG": "CEPA_DOCS_PATHLOCK_DEBUG",
    "DOCS_PATHLOCK_DEBUG_LOG": "CEPA_DOCS_PATHLOCK_DEBUG_LOG",
    "REVIEW_GATE_ALLOW_DIRECT": "CEPA_REVIEW_GATE_ALLOW_DIRECT",
    "REVIEW_GATE_NUDGE": "CEPA_REVIEW_GATE_NUDGE",
}
OLD_VALUES = {"CEPA_PERMISSIONS": {"classificador": "classifier"},
              "CEPA_PROMPT_MODE": {"substitui": "replace"}}

OLD_FAMILIES = ("CLAUDE_WT_", "CCW_", "CEPA_UNTIL", "CAPTURE_BUILD", "LEAD_WORKTREE",
                "CLAUDE_AUTONOMOUS", "HEX_PATHLOCK", "DOCS_PATHLOCK", "REVIEW_GATE_")
PT_TOKENS = {"MODO", "ENCADEAR", "PERMISSOES", "COR", "ORFA", "LEITOR", "ESPERA",
             "RESPOSTA", "SONDA", "REDE", "INTERVALO", "MARGEM", "LINHA", "VIVA",
             "LIMITE", "ANALISE", "GRACA", "TETO", "LEITURA", "MODELO", "DONO",
             "SUBSTITUI", "CLASSIFICADOR"}

# Names that belong to someone else and are read as-is. Each one says whose it is.
FOREIGN = {
    # the operating system and the terminal
    "HOME": "operating system", "USER": "operating system", "PATH": "operating system",
    "TERM": "terminal", "TMPDIR": "operating system", "NO_COLOR": "no-color.org convention",
    "EDITOR": "operating system", "VISUAL": "operating system",
    "COLUMNS": "terminal", "LINES": "terminal", "OLDPWD": "shell", "PWD": "shell",
    "SHELL": "operating system",
    # Claude Code (it sets them; Cepa only reads, or hands one down to claude -p)
    "CLAUDE_PROJECT_DIR": "Claude Code", "CLAUDE_PLUGIN_ROOT": "Claude Code",
    "CLAUDE_SESSION_ID": "Claude Code", "CLAUDE_CODE_SESSION_ID": "Claude Code",
    "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "Claude Code (Cepa sets it for a child claude -p)",
    # herdr
    "HC_TERMINAL_ID": "herdr", "HERDR_PANE_ID": "herdr", "HERDR_BIN_PATH": "herdr",
    "HERDR_ENV": "herdr",
}


# --- the scan ---------------------------------------------------------------

def _is_old(name):
    return name in OLD_TO_NEW or name in OTHER_PLUGINS_OLD_TO_NEW \
        or name.startswith(OLD_FAMILIES)


def _problem(name, assigned=()):
    """Why a variable read under this name is not allowed, or None."""
    if _is_old(name):
        return f"{name}: old name (table CS-6)"
    if name.startswith("CEPA_"):
        bad = PT_TOKENS & set(name.split("_"))
        return f"{name}: Portuguese word {sorted(bad)}" if bad else None
    if name in FOREIGN or name in assigned:
        return None
    return f"{name}: no CEPA_ prefix and not on the foreign list"


NEW_NAMES = set(OLD_TO_NEW.values())


def _direct_problem(name):
    """A read of a renamed variable's NEW name that does not go through the
    fallback: `CEPA_MODO=off` would silently stop working there."""
    if name in NEW_NAMES:
        return f"{name}: direct read of a renamed variable (use the _cepaenv helper)"
    return None


def _env_text(node):
    return ast.unparse(node) if node is not None else ""


def _looks_like_env(node):
    t = _env_text(node)
    return t.endswith("environ") or t in ("env", "environ", "environment")


HELPER_NAMES = ("E", "_cepaenv")


def scan_python(source, fallback_funcs=(), fallback_calls=()):
    """Every problem found in one Python source. `fallback_funcs`: function names
    where reading the old name is the point (the fallback); `fallback_calls`: helper
    functions whose arguments are `(new, old)` name pairs."""
    # the generator template marks: a line of its own becomes a statement
    source = re.sub(r"^@@\w+@@$", "    pass", source, flags=re.M)
    source = re.sub(r"@@(\w+)@@", r"\1", source)
    tree = ast.parse(source)
    consts = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = n.value.value
    out = []

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        return None

    def visit(node, func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in fallback_calls:
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node.name
        names = []
        direct = []   # names read straight from the environment
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ("get", "is_set") \
                    and isinstance(f.value, ast.Name) and f.value.id in HELPER_NAMES \
                    and node.args:
                # a read THROUGH the helper: the name must be a CEPA_ one
                nm = literal(node.args[0])
                if nm and not nm.startswith("CEPA_") and func not in fallback_funcs:
                    p = f"{nm}: read through the helper without the CEPA_ prefix"
                    if p not in out:
                        out.append(p)
            elif isinstance(f, ast.Attribute) and f.attr in ("get", "pop", "setdefault") \
                    and _looks_like_env(f.value) and node.args:
                names.append(literal(node.args[0]))
                direct.append(literal(node.args[0]))
            elif isinstance(f, ast.Attribute) and f.attr == "getenv" and node.args:
                names.append(literal(node.args[0]))
                direct.append(literal(node.args[0]))
            elif isinstance(f, ast.Name) and f.id == "getenv" and node.args:
                names.append(literal(node.args[0]))
                direct.append(literal(node.args[0]))
        elif isinstance(node, ast.Subscript) and _looks_like_env(node.value):
            names.append(literal(node.slice))
            if isinstance(node.ctx, ast.Load):   # `environ[X] = v` sets, it does not read
                direct.append(literal(node.slice))
        elif isinstance(node, ast.Compare) and any(_looks_like_env(c) for c in node.comparators):
            names.append(literal(node.left))
            direct.append(literal(node.left))
        # an exact string equal to an old name, anywhere (a tuple of names, a table...)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and _is_old(node.value) and re.fullmatch(r"[A-Z][A-Z0-9_]+", node.value):
            names.append(node.value)
        for nm in names:
            if not nm or (func in fallback_funcs):
                continue
            p = _problem(nm) or (_direct_problem(nm) if nm in direct else None)
            if p and p not in out:
                out.append(p)
        for c in ast.iter_child_nodes(node):
            visit(c, func)

    visit(tree, None)
    return out


_SH_READ = re.compile(r"\$\{?([A-Z][A-Z0-9_]*)")
_SH_CALL = re.compile(r"\bcepa_env\s+([A-Z][A-Z0-9_]*)")
# an assignment sits at command position (line start, after `;`, `&&`, `||`, `$(`, `(` or a case label `)`,
# or after another assignment of the same command), never inside a quoted message
_SH_ASSIGN = re.compile(
    r"(?:^|;|&&|\|\||\$\(|\(|\))[ \t]*(?:export\s+|local\s+)?"
    r"(?:[A-Za-z_]\w*=(?:\"[^\"]*\"|[^\s$(]*)[ \t]+)*([A-Z][A-Z0-9_]*)=", re.M)
_SH_EXPORT = re.compile(r"^\s*export\s+([A-Z][A-Z0-9_]*)", re.M)


def _strip_sh_comments(text):
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def _drop_shell_function(text, fname):
    """The text without the body of `fname() { ... }` (the fallback place)."""
    m = re.search(rf"^{fname}\(\)\s*\{{.*?^\}}", text, re.M | re.S)
    return text[:m.start()] + text[m.end():] if m else text


def scan_shell(text, fallback_funcs=()):
    """Problems in a shell script. A variable the script assigns itself is not a read
    of the user's setting. Two precisions: a non-CEPA_ name assigned anywhere in the
    script is a local (and one that is exported is still flagged); a CEPA_ renamed
    name is exempt from the "direct read" rule only AFTER its first assignment in the
    text (the launcher sets CEPA_WT_CLAIM and exports it), so the same `$NAME` read
    before any assignment is an environment read and is flagged."""
    text = _strip_sh_comments(text)
    for f in fallback_funcs:
        text = _drop_shell_function(text, f)
    first_assign = {}
    for m in _SH_ASSIGN.finditer(text):
        first_assign.setdefault(m.group(1), m.start(1))
    exported = set(_SH_EXPORT.findall(text))
    out = []

    def add(p):
        if p and p not in out:
            out.append(p)
    for m in _SH_READ.finditer(text):
        nm = m.group(1)
        mine = nm in first_assign and first_assign[nm] < m.start()
        if nm.startswith("CEPA_") or _is_old(nm):
            add(_problem(nm))
            if not mine:
                add(_direct_problem(nm))
        else:
            add(_problem(nm, set(first_assign) - exported))
    for m in _SH_CALL.finditer(text):
        nm = m.group(1)
        add(_problem(nm))
        if not nm.startswith("CEPA_"):
            add(f"{nm}: read through cepa_env without the CEPA_ prefix")
    for nm in exported:
        add(_problem(nm))
    for nm in first_assign:
        if _is_old(nm):
            add(_problem(nm))
    return out


def _bin_is_shell(path):
    return open(path, "rb").readline().startswith((b"#!/bin/sh", b"#!/usr/bin/env bash",
                                                   b"#!/bin/bash", b"#!/usr/bin/env sh"))


def scan_tree():
    """{file: [problems]} for common/bin and common/hooks."""
    found = {}
    files = [p for p in sorted(BIN.iterdir()) if p.is_file()]
    files += sorted(HOOKS.glob("*.py")) + sorted((HOOKS / "_templates").glob("*.tmpl"))
    for p in files:
        rel = str(p.relative_to(REPO))
        if p.name == "_cepaenv.py":
            continue  # the table and the fallback read: the single place
        if p.suffix not in ("", ".py", ".tmpl"):
            continue
        if _bin_is_shell(p):
            probs = scan_shell(p.read_text(encoding="utf-8"), ("_cepa_old_name", "cepa_env"))
        else:
            probs = scan_python(p.read_text(encoding="utf-8"), ("_run_card",))
        if probs:
            found[rel] = probs
    return found


# --- 1. the scan ------------------------------------------------------------

def test_no_old_or_unprefixed_variable_is_read_in_common():
    found = scan_tree()
    assert not found, "variables read outside the CEPA_ English names:\n" + "\n".join(
        f"  {f}: {', '.join(p)}" for f, p in found.items())


def test_scan_flags_fabricated_python():
    assert scan_python('import os\nx = os.environ.get("CEPA_MODO", "on")\n')
    assert scan_python('import os\nx = os.environ["CCW_SEED"]\n')
    assert scan_python('import os\nx = os.getenv("MY_THING")\n')
    assert scan_python('import os\nok = "CEPA_ESPERA_X" in os.environ\n')
    assert scan_python('import os\nENV = "CLAUDE_WT_CLAIM"\nx = os.environ.get(ENV)\n')
    assert scan_python('UNATTENDED = ("CEPA_UNTIL_RUN", "X")\n')
    assert scan_python('def f(env):\n    return env.get("CEPA_COR")\n')
    # a direct read of a NEW name bypasses the fallback: CEPA_MODO would stop working
    assert scan_python('import os\nx = os.environ.get("CEPA_MODE", "on")\n')
    assert scan_python('import os\nx = os.environ["CEPA_MODE"]\n')
    assert scan_python('import os\nx = "CEPA_CHAIN" in os.environ\n')
    assert scan_python('def f(env):\n    return env.get("CEPA_RUN")\n')
    assert scan_python('import os\nx = os.getenv("CEPA_COLOR")\n')
    # setting it for a child is fine; so is reading through the helper
    assert not scan_python('import os\nos.environ["CEPA_RUN"] = "1"\n')
    assert not scan_python('import _cepaenv as E\nx = E.get("CEPA_MODE", "on")\n')
    assert not scan_python('import os\nx = os.environ.get("CEPA_FEEDBACK_DIR")\n')
    # a read through the helper with a name that is not CEPA_
    assert scan_python('import _cepaenv as E\nx = E.get("MY_THING")\n')
    assert scan_python('import _cepaenv as E\nx = E.is_set("HOME")\n')
    assert scan_python('import _cepaenv\nx = _cepaenv.get("DEBUG")\n')
    # clean ones
    assert not scan_python('import os\nx = os.environ.get("HOME")\n')
    assert not scan_python('import os\nx = os.environ.get(name)\n')
    # the fallback function is the one place allowed to read the old name
    src = 'import os\ndef _run_card():\n    return os.environ.get("CLAUDE_AUTONOMOUS_RUN_ID")\n'
    assert scan_python(src)
    assert not scan_python(src, ("_run_card",))


def test_scan_flags_fabricated_shell():
    assert scan_shell('[ "${CEPA_MODO:-on}" = off ] && exit\n')
    assert scan_shell('x="$MY_THING"\n')
    assert scan_shell('export CLAUDE_WT_CLAIM\n')
    assert scan_shell('RES=$(CLAUDE_WT_ROOT="$R" python3 x)\n')
    assert scan_shell('v=$(cepa_env CEPA_UNTIL_RUN)\n')
    assert scan_shell('echo "$CEPA_PROMPT_MODO"\n')
    # a direct read of a NEW name bypasses the fallback
    assert scan_shell('[ "${CEPA_MODE:-on}" = off ] && exit\n')
    assert scan_shell('echo "$CEPA_MODE"\n')
    assert scan_shell('x=$(cepa_env MY_THING)\n')
    # what the script assigns itself, then reads or exports to a child, is not the
    # user's setting; the same read BEFORE the assignment still is
    assert not scan_shell('C=1\nCEPA_WT_CLAIM="$C"\nexport CEPA_WT_CLAIM\necho "$CEPA_WT_CLAIM"\n')
    assert scan_shell('echo "$CEPA_WT_CLAIM"\nCEPA_WT_CLAIM=1\n')
    # a message that merely contains `CEPA_MODE=off` is not an assignment
    assert scan_shell("printf 'turn off with CEPA_MODE=off'\necho \"$CEPA_MODE\"\n")
    assert not scan_shell('ROOT=/r\nR=$(CEPA_WT_ROOT="$ROOT" python3 x)\n')
    assert not scan_shell('[ "$(cepa_env CEPA_MODE on)" = off ] && exit\n')
    assert not scan_shell('ROOT=1\necho "$ROOT" "$HOME" "${CEPA_PREFLIGHT:-on}"\n')
    src = '_cepa_old_name() {\n  case "$1" in CEPA_MODE) echo CEPA_MODO;; esac\n}\n'
    assert not scan_shell(src, ("_cepa_old_name",))


def test_foreign_list_says_whose_each_name_is():
    assert all(FOREIGN.values())
    assert not any(k.startswith("CEPA_") or _is_old(k) for k in FOREIGN)


# --- 2. the table: one place, agreed by the two languages -------------------

def _env_module():
    spec = importlib.util.spec_from_file_location("_cepaenv", HOOKS / "_cepaenv.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_python_table_is_the_contract():
    m = _env_module()
    assert dict(m.RENAMED) == OLD_TO_NEW
    assert {k: dict(v) for k, v in m.OLD_VALUES.items()} == OLD_VALUES


def test_shell_table_agrees_with_python():
    m = _env_module()
    text = CEPA.read_text(encoding="utf-8")
    body = re.search(r"^_cepa_old_name\(\)\s*\{(.*?)^\}", text, re.M | re.S)
    assert body, "cepa has no _cepa_old_name function"
    pairs = dict(re.findall(r"\b(CEPA_[A-Z_]+)\)\s*echo\s+([A-Z_]+)", body.group(1)))
    assert pairs, "the shell table is empty"
    for new, old in pairs.items():
        assert m.RENAMED.get(old) == new, f"shell says {old} -> {new}"
    # and every variable the launcher reads or sets has its old name in the table
    launcher_new = set(re.findall(r"cepa_env\s+(CEPA_[A-Z_]+)", text))
    missing = {n for n in launcher_new if n in OLD_TO_NEW.values() and n not in pairs}
    assert not missing, f"the launcher reads {sorted(missing)} without an old-name line"


# --- 3. help ----------------------------------------------------------------

def _cepa(args, env_extra, cwd=None):
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("CEPA_") or k.startswith("CLAUDE_WT_") or k.startswith("CCW_")
                   or k == "CLAUDE_AUTONOMOUS_RUN_ID")}
    env.update(NO_COLOR="1", CEPA_PREFLIGHT="off")
    env.update(env_extra)
    return subprocess.run([str(CEPA)] + args, capture_output=True, text=True,
                          env=env, cwd=str(cwd or REPO), timeout=60)


def test_help_exits_zero_under_both_names():
    for var in ("CEPA_MODE", "CEPA_MODO"):
        r = _cepa(["--help"], {var: "off"})
        assert r.returncode == 0, (var, r.stderr)


def test_help_environment_section_cites_only_the_new_forms():
    out = _cepa(["--help"], {}).stdout
    sec = out[out.index("environment:"):]
    for form in ("CEPA_MODE=off", "CEPA_CHAIN=off", "CEPA_PERMISSIONS=classifier"):
        assert form in sec, (form, sec)
    for name in list(OLD_TO_NEW) + ["classificador"]:
        assert not re.search(rf"(?<![A-Z_]){name}(?![A-Z_])", out), name


# --- 4. old alone works; new wins -------------------------------------------

def test_helper_old_alone_new_wins_and_values():
    m = _env_module()
    for old, new in OLD_TO_NEW.items():
        assert m.get(new, env={old: "A"}) == "A", old
        assert m.get(new, env={new: "N", old: "O"}) == "N", old
        assert m.get(new, "d", env={}) == "d", old
        assert m.get(new, "d", env={new: ""}) == "d", old
    for new, table in OLD_VALUES.items():
        old = {v: k for k, v in OLD_TO_NEW.items()}[new]
        for oldv, newv in table.items():
            assert m.get(new, env={new: oldv}) == newv   # old value, new name
            assert m.get(new, env={old: oldv}) == newv   # old value, old name
            assert m.get(new, env={new: newv}) == newv


def _load_script(path, name):
    from importlib.machinery import SourceFileLoader
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load_hook(fname):
    sys.path.insert(0, str(HOOKS))
    try:
        spec = importlib.util.spec_from_file_location(fname.replace("-", "_"), HOOKS / fname)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(HOOKS))


def _with_env(env, fn):
    saved = dict(os.environ)
    try:
        for k in list(os.environ):
            if k in OLD_TO_NEW or k in OLD_TO_NEW.values():
                del os.environ[k]
        os.environ.update(env)
        return fn()
    finally:
        os.environ.clear()
        os.environ.update(saved)


class _Reached(BaseException):
    """The hook went past the on/off switch."""


def _gate_reaches_work(fname, patch, env, argv=(), stdin=""):
    """True when `main()` of the hook goes past its on/off switch under `env`."""
    import io
    mod = _load_hook(fname)
    patch(mod)

    def go():
        old_stdin, old_argv = sys.stdin, sys.argv
        sys.stdin, sys.argv = io.StringIO(stdin), [fname, *argv]
        try:
            try:
                mod.main()
            except SystemExit:
                return False
            except _Reached:
                return True
            return False
        finally:
            sys.stdin, sys.argv = old_stdin, old_argv
    return _with_env(env, go)


def _boom(*a, **k):
    raise _Reached()


def test_mode_switch_old_alone_and_new_wins_in_write_mode_gate():
    def patch(mod):
        mod._wtlib.session_root = _boom
    payload = json.dumps({"cwd": "/tmp", "tool_name": "Edit", "tool_input": {}})

    def reaches(env):
        return _gate_reaches_work("write-mode-gate.py", patch, env, stdin=payload)
    assert reaches({})
    assert not reaches({"CEPA_MODO": "off"})
    assert not reaches({"CEPA_MODE": "off"})
    assert reaches({"CEPA_MODE": "on", "CEPA_MODO": "off"})
    assert not reaches({"CEPA_MODE": "off", "CEPA_MODO": "on"})


def test_chain_switch_old_alone_and_new_wins_in_session_chain():
    def patch(mod):
        mod.L.main_root = _boom

    def reaches(env):
        return _gate_reaches_work("session-chain.py", patch, env, argv=("lid", "cepa", "0"))
    assert reaches({})
    assert not reaches({"CEPA_ENCADEAR": "off"})
    assert not reaches({"CEPA_CHAIN": "off"})
    assert reaches({"CEPA_CHAIN": "on", "CEPA_ENCADEAR": "off"})


def test_validation_owed_gate_mode_switch():
    def patch(mod):
        json.load = _boom
    real = json.load
    try:
        def reaches(env):
            return _gate_reaches_work("validation-owed-gate.py", patch, env, stdin="{}")
        assert reaches({})
        assert not reaches({"CEPA_MODO": "off"})
        assert not reaches({"CEPA_MODE": "off"})
        assert reaches({"CEPA_MODE": "on", "CEPA_MODO": "off"})
    finally:
        json.load = real


def test_launcher_old_mode_name_alone_skips_the_mode():
    """In a git repo without a mode, `cepa` asks for one; with the mode off (by the old
    name alone) it just launches claude; the new name wins over the old."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        fake = td / "fake-claude"
        fake.write_text('#!/bin/sh\nprintf "CLAUDE_ARGS:%s\\n" "$*"\n')
        fake.chmod(0o755)
        repo = td / "repo"
        repo.mkdir()
        g = ["git", "-C", str(repo)]
        subprocess.run(g + ["init", "-q", "-b", "main"], check=True)
        subprocess.run(g + ["-c", "user.name=t", "-c", "user.email=t@t", "commit",
                            "-q", "--allow-empty", "-m", "i"], check=True)
        base = {"HOME": str(td), "CEPA_WT_CLAUDE_BIN": str(fake),
                "CEPA_WORKTREE_HOME": str(td / "wt")}

        def run(extra, args=()):
            return _cepa(["-p", "x", *args], dict(base, **extra), cwd=repo)
        old = run({"CEPA_MODO": "off", "CEPA_PERMISSOES": "classificador"})
        assert old.returncode == 0, old.stderr
        assert "CLAUDE_ARGS:" in old.stdout and "dangerously-skip" not in old.stdout, old.stdout
        new = run({"CEPA_MODE": "off", "CEPA_PERMISSIONS": "classifier"})
        assert new.returncode == 0, new.stderr
        assert "dangerously-skip" not in new.stdout, new.stdout
        # new wins: old says classifier, new says bypass
        both = run({"CEPA_MODE": "off", "CEPA_PERMISSIONS": "bypass",
                    "CEPA_PERMISSOES": "classificador"})
        assert "dangerously-skip-permissions" in both.stdout, both.stdout
        # old claude binary override still works (the fake printed above)
        legacy_bin = _cepa(["-p", "x"], {"HOME": str(td), "CLAUDE_WT_CLAUDE_BIN": str(fake),
                                         "CEPA_MODE": "off",
                                         "CEPA_WORKTREE_HOME": str(td / "wt")}, cwd=repo)
        assert "CLAUDE_ARGS:" in legacy_bin.stdout, (legacy_bin.stdout, legacy_bin.stderr)
        # the old values of the prompt mode, under either name
        prompt = td / "p.md"
        prompt.write_text("hello")
        r = run({"CEPA_MODE": "off", "CEPA_PROMPT": str(prompt), "CEPA_PROMPT_MODO": "substitui"})
        assert "--system-prompt" in r.stdout and "--append-system-prompt" not in r.stdout, r.stdout
        r = run({"CEPA_MODE": "off", "CEPA_PROMPT": str(prompt), "CEPA_PROMPT_MODE": "replace"})
        assert "--system-prompt" in r.stdout and "--append-system-prompt" not in r.stdout, r.stdout


def test_cepa_run_reads_old_run_names_and_new_wins():
    run = _load_script(BIN / "cepa-run", "cepa_run_cs6")
    helper = _env_module()
    assert run.ENV_WINDOW == "CEPA_RUN"
    env = _with_env({}, run.item_environment)
    assert env.get("CEPA_RUN") == "1" and "CEPA_UNTIL_RUN" not in env
    assert helper.get("CEPA_RUN_ANSWER_WAIT", "600", env={"CEPA_UNTIL_ESPERA_RESPOSTA": "5"}) == "5"


def test_wtlib_seed_and_worktree_home_old_and_new():
    sys.path.insert(0, str(HOOKS))
    try:
        import _wtlib
    finally:
        sys.path.remove(str(HOOKS))
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        (repo / ".claude").mkdir(parents=True)
        for f in ("a.txt", "b.txt"):
            (repo / f).write_text(f)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        old = _with_env({"CCW_SEED": "a.txt"}, lambda: _wtlib.seed_globs(str(repo)))
        new = _with_env({"CEPA_SEED": "b.txt"}, lambda: _wtlib.seed_globs(str(repo)))
        both = _with_env({"CEPA_SEED": "b.txt", "CCW_SEED": "a.txt"},
                         lambda: _wtlib.seed_globs(str(repo)))
        assert list(old) == ["a.txt"] and list(new) == ["b.txt"] and list(both) == ["b.txt"]


def test_session_launch_reads_old_wt_names():
    src = (HOOKS / "session-launch.py").read_text(encoding="utf-8")
    assert "CEPA_WT_ROOT" in src and "CEPA_WT_SLICE" in src
    m = _env_module()
    assert m.get("CEPA_WT_ROOT", env={"CLAUDE_WT_ROOT": "/r"}) == "/r"
    assert m.get("CEPA_WT_ROOT", env={"CLAUDE_WT_ROOT": "/r", "CEPA_WT_ROOT": "/n"}) == "/n"


def test_cepa_sets_the_new_names_for_what_it_launches():
    text = CEPA.read_text(encoding="utf-8")
    assert re.search(r"CEPA_WT_ROOT=", text) and re.search(r"CEPA_WT_SLICE=", text)
    assert re.search(r"export CEPA_WT_CLAIM", text)
    for old in ("CLAUDE_WT_ROOT=", "CLAUDE_WT_CLAIM"):
        assert old not in re.sub(r"_cepa_old_name\(\).*?^\}", "", text, flags=re.M | re.S)


# --- 5. other plugins read the new names too --------------------------------

def test_other_plugins_read_new_names_with_old_as_fallback():
    waivers = _load_script(REPO / "board-flow" / "bin" / "waivers.py", "waivers_cs6")
    assert waivers.in_autonomous_run({"CEPA_RUN": "1"})
    assert waivers.in_autonomous_run({"CEPA_UNTIL_RUN": "1"})
    assert waivers.in_autonomous_run({"CEPA_AUTONOMOUS_RUN_ID": "r"})
    assert waivers.in_autonomous_run({"CLAUDE_AUTONOMOUS_RUN_ID": "r"})
    assert not waivers.in_autonomous_run({})
    # every generated bash-path-lock copy reads the card through the one fallback function
    for plug in ("build-team", "build-hex", "discovery", "design", "docs-topology", "marketing"):
        p = REPO / plug / "hooks" / "bash-path-lock.py"
        probs = scan_python(p.read_text(encoding="utf-8"), ("_run_card",))
        assert not probs, (plug, probs)
    for p in [REPO / "build-hex/hooks/path-lock.py", REPO / "docs-topology/hooks/path-lock.py",
              REPO / "review-gate/hooks/no-direct-main.py", REPO / "review-gate/hooks/push-nudge.py"]:
        probs = scan_python(p.read_text(encoding="utf-8"), (), ("_env",))
        probs = [x for x in probs if not x.startswith(("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME"))]
        assert not probs, (p.name, probs)


# --- 6. text: live docs show only the new names -----------------------------

LIVE_TEXT = (["README.md", "agents-overview.md", "docs/commands.md", "docs/cepa-cli.md",
              "docs/autonomous-mode.md", "docs/cepa-until.md", "docs/handoff.md",
              "docs/loop-engineering.md", "docs/modos-de-trabalho.md",
              "docs/system-prompt-customizado.md", "docs/troubleshooting.md",
              "docs/internals/cc-quirks.md", "docs/internals/hooks.md",
              "docs/internals/path-lock.md", "docs/internals/gauntlet-pilot-bash-path-lock.md"]
             + [str(p.relative_to(REPO)) for p in sorted(REPO.glob("*/commands/*.md"))]
             + [str(p.relative_to(REPO)) for p in sorted(REPO.glob("*/skills/**/SKILL.md"))]
             + [str(p.relative_to(REPO)) for p in sorted(REPO.glob("*/agents/*.md"))])
COMPAT_WORDS = re.compile(r"\b(old|older|legacy|still (read|accepted)|antiga|antigo)\b", re.I)


def test_live_text_shows_only_new_names_outside_compatibility_lines():
    names = sorted(list(OLD_TO_NEW) + list(OTHER_PLUGINS_OLD_TO_NEW), key=len, reverse=True)
    rx = re.compile(r"(?<![A-Z0-9_])(" + "|".join(names) + r")(?![A-Z0-9_])")
    offenders = []
    for rel in LIVE_TEXT:
        p = REPO / rel
        if not p.exists():
            continue
        in_table = False
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if rel == "docs/cepa-cli.md" and line.startswith("## "):
                # the one table that declares the compatibility
                in_table = line == "## Environment variables"
            if rx.search(line) and not COMPAT_WORDS.search(line) and not in_table:
                offenders.append(f"{rel}:{i}: {rx.search(line).group(1)}")
    assert not offenders, "old names in live text:\n  " + "\n  ".join(offenders[:40])


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
