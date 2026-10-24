#!/usr/bin/env python3
"""Divergence detector among the 5 copies of the path-locks (P0-3, review 2026-08-17).

No dependencies — run with `python3 tests/test_lock_copies_drift.py`.
Exits non-zero on failure.

## The problem this file exists to catch

`path-lock.py` and `bash-path-lock.py` are the two hooks that sustain the product's
central guarantee: a worker writes only in its own lane, a lead delegates instead of
coding. They exist in **five copies**, one per topology with a hook, and the
maintenance rule is human — "every fix lands in all 5". It has already failed: the fix
of the `>=` false positive (the hook read the `>` of `>=` as a redirection and
blocked a legitimate command) had to be propagated by hand, and the project's memory
records the episode of the copy that was left behind.

The failure mode is silent, which is what makes it expensive: the lagging copy does not
break anything — it **allows** what the other four block, and the agent's report
reads as success.

## What is compared: code, not prose

The comparison is made over the **syntax tree** (AST) of each function, with
docstrings removed. This is a decision, made after the first version of
this test (textual comparison) reported six divergences that all turned out to be
cosmetic: rewritten comments, docstrings of different styles and
`list[str]` versus `list` in an annotation. None changed behavior.

A detector that shouts over a comma teaches people to ignore it, and the day it shouts
over a `>=` turning into `>` is the day someone presses "ignore". So:

- **Comments, docstrings and type annotations are not compared.** Per-topology
  prose is legitimate — `build-hex` carries the real incident that originated the
  hook, and it makes sense that it does.
- **Everything else is.** Comparing the body in AST catches exactly the class that
  matters: a condition altered in one copy only, which is how the `>=` false positive
  survived in four copies and not in the fifth.

Coverage per file:

- **`bash-path-lock.py`: the whole module**, including the module-level regex
  tables — which is where the `>=` bug lived.
- **`common/hooks/_shellscan.py` against `bash-path-lock`**: the command-line
  reading engine (quote mask, split into segments, redirection regex) exists in two
  sources — the template of the 5 copies and this module, from which the
  `enforcement-guard` and the `maven-reactor-guard` import. Two sources
  because a hook of another plugin does not import from `common`. Before 2026-08-23 there were
  **seven manual copies** and this detector knew five: the `>=` false positive
  went 2 months unfixed in the `enforcement-guard`, and the multi-line commit
  (WEGO-2087) repeated the story.
- **`path-lock.py`: the shared core** (`detect_agent`,
  `is_own_expertise_file`, `path_matches`) plus the `main` of the topologies without their own
  YAML. The `main` of `build-hex` and `debug_log` legitimately differ, and
  are declared in `EXEMPT` **with the reason** — a declared exception is a decision;
  a silent exception is the disease this file treats.

## Perturbation (how to know this test proves something)

Edit any compared function in ONE copy — for example swap a `>=` for
`>` in `build-hex/hooks/bash-path-lock.py` — and this test turns red
naming the divergent copy. If it stays green, it is proving nothing.
"""

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

# This test cites a telemetry emitter hook. Today it does not get to execute it,
# but citing and executing are one step apart, and that distance is what
# left 7 tests polluting the real ledger for a month. See
# tests/_isolated_telemetry.py.
from _isolated_telemetry import isolate

isolate()


REPO = Path(__file__).resolve().parent.parent

# Topology directory → the tokens that copy legitimately carries.
# All become <T> before the comparison. Maintaining this table is the price of having 5
# copies; when automatic generation exists (2nd half of the BACKLOG item),
# it reads from here.
TOPOLOGIES = {
    "build-team": ["build-team", "multiteam"],
    "build-hex": ["build-hex", "hex", "HEX_PATHLOCK_DEBUG"],
    "discovery": ["discovery"],
    "design": ["design"],
    "docs-topology": ["docs-topology", "docs"],
    "marketing": ["marketing"],
}

# Functions of path-lock.py that MUST be identical in the copies where they exist.
PATHLOCK_CORE = ["detect_agent", "is_own_expertise_file", "path_matches"]

# Legitimate divergences, with the reason. Without a written reason, it does not go in here.
EXEMPT = {
    ("path-lock.py", "main"):
        "build-hex resolve papéis→módulos via build-hex.yaml (load_roles + "
        "build_allowed_writes) antes de gatear; as outras topologias têm o mapa "
        "de globs fixo no módulo. O fluxo de decisão é o mesmo; o preâmbulo não.",
    ("bash-path-lock.py", "main"):
        "mesmo motivo do path-lock:main — o build-hex resolve papéis→módulos "
        "pelo build-hex.yaml antes de gatear, e o main é onde esse preâmbulo "
        "acontece. A extração de alvos de escrita (_segment_targets, "
        "extract_write_targets) e as tabelas de regex, que é onde mora o risco, "
        "seguem comparadas nas 5.",
    ("path-lock.py", "debug_log"):
        "existe só em build-hex e docs-topology, e a do build-hex recebe o mapa "
        "de papéis (`roles`) para logar qual módulo cada papel virou — dado que "
        "só existe onde há build-hex.yaml. É função de diagnóstico, fora do "
        "caminho de decisão do gate: divergir aqui não permite nem bloqueia nada.",
}

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def normalize(src: str) -> str:
    """Erases what is legitimately per-topology, preserves the rest.

    Only MECHANICAL substitutions go in here. If one day it is necessary to normalize
    logic for two files to match, the answer is to fix the copy, not to
    widen this function — normalizing a behavior difference is how a
    divergence detector stops detecting.
    """
    # The alias of the imported module (`hex_path_lock`, `design_path_lock`, ...):
    # `_` is a word character, so the \b substitution below does not
    # reach it. It must come first, and explicitly.
    src = re.sub(r"\b\w+_path_lock\b", "<T>_path_lock", src)
    words = sorted({w for ws in TOPOLOGIES.values() for w in ws}, key=len, reverse=True)
    for w in words:
        src = re.sub(rf"\b{re.escape(w)}\b", "<T>", src)
    # The noun of what the topology writes: build-* writes `source`,
    # design/discovery/docs write `artifacts`. A declared difference, not an
    # accidental one.
    src = re.sub(r"Writing (?:source|artifacts) via Bash", "Writing <NOUN> via Bash", src)
    src = re.sub(r"Escrever (?:código|artefatos) por Bash", "Escrever <NOUN> por Bash", src)
    # Trailing whitespace on a line is not a divergence.
    return "\n".join(line.rstrip() for line in src.splitlines()).strip()


def _is_docstring(node) -> bool:
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def _strip_docstrings(tree):
    """Strips the docstring of the module and of each function, recursively.

    Comments no longer exist in the AST — that is precisely why the comparison
    is made here and not on the text.
    """
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and _is_docstring(body[0]):
            node.body = body[1:] or [ast.Pass()]
    return tree


def module_constants(src: str) -> str:
    """Module-level statements that are NOT a function, import or the final guard.

    This is where `_REDIR_RE`, `_UNCOVERED_RE`, `_SEP_RE` and `_PSEUDO` live — the
    tables that decide what counts as a write. `PLUGIN_NAME` leaves the count
    because it is precisely what each topology has of its own.
    """
    tree = _strip_docstrings(ast.parse(normalize(src)))
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.Import, ast.ImportFrom, ast.If)):
            continue
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "PLUGIN_NAME" in names:
                continue
        out.append(ast.dump(node))
    return "\n".join(out)


def code_of(src: str) -> str:
    """The AST of the whole module, without docstrings, as a comparable string.

    One line per top-level statement, so that the first divergence reported
    is locatable instead of a wall of text.
    """
    tree = _strip_docstrings(ast.parse(normalize(src)))
    return "\n".join(ast.dump(node) for node in tree.body)


def _is_diagnostic_call(node) -> bool:
    """A bare `debug_log(...)` — diagnostics, outside the decision path.

    Only two of the five copies have `debug_log` (build-hex and docs-topology), and
    its call in `main` would make the `main`s diverge over a line that neither
    allows nor blocks anything. Removing ONLY that call keeps the rest of `main`
    under comparison — exempting the whole `main` would blind the check precisely
    on the function that decides.
    """
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "debug_log")


def functions_of(src: str) -> dict:
    """name → AST of the function BODY (no docstring, no signature).

    Without the signature on purpose: `list[str]` versus `list` is annotation
    style, not behavior, and one of them is just newer than the other.
    """
    tree = _strip_docstrings(ast.parse(normalize(src)))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            body = [b for b in node.body if not _is_diagnostic_call(b)]
            out[node.name] = "\n".join(ast.dump(b) for b in body)
    return out


def copies(filename: str) -> dict:
    out = {}
    for top in TOPOLOGIES:
        p = REPO / top / "hooks" / filename
        if p.exists():
            out[top] = p.read_text(encoding="utf-8")
    return out


# ── cases ────────────────────────────────────────────────────────────────────

def test_all_copies_exist():
    for filename in ("path-lock.py", "bash-path-lock.py"):
        found = copies(filename)
        check(f"{filename}: as 5 cópias existem",
              len(found) == len(TOPOLOGIES),
              f"achei {sorted(found)}")


def test_bash_path_lock_identical():
    """Every function and every module-level table, in the 5 copies.

    The tables go in because that is where the `>=` bug lived: `_REDIR_RE` is a
    module constant, not a function, and a regression there would not show up in a
    comparison that only looked at functions.
    """
    found = copies("bash-path-lock.py")
    if not found:
        check("bash-path-lock.py: cópias encontradas", False)
        return

    # 1. module-level tables / constants
    consts = {t: module_constants(s) for t, s in found.items()}
    ref_topo = "build-hex"
    ref = consts[ref_topo]
    divergent = [t for t, s in consts.items() if s != ref]
    check("bash-path-lock.py: tabelas de módulo idênticas nas 5 cópias",
          not divergent, f"divergem de {ref_topo}: {divergent}")
    for t in divergent:
        _report_first_diff(ref_topo, ref, t, consts[t])

    # 2. functions, one by one
    funcs = {t: functions_of(s) for t, s in found.items()}
    names = sorted({n for f in funcs.values() for n in f})
    for name in names:
        if ("bash-path-lock.py", name) in EXEMPT:
            continue
        present = {t: f[name] for t, f in funcs.items() if name in f}
        if len(present) < 2:
            continue
        ref = present[ref_topo] if ref_topo in present else present[sorted(present)[0]]
        base = ref_topo if ref_topo in present else sorted(present)[0]
        divergent = [t for t, s in present.items() if s != ref]
        check(f"bash-path-lock.py:{name} idêntico em {len(present)} cópias",
              not divergent, f"divergem de {base}: {divergent}")
        for t in divergent:
            _report_first_diff(f"{base}:{name}", ref, t, present[t])


def test_path_lock_core_identical():
    """The shared core must match; the rest is declared in EXEMPT."""
    found = copies("path-lock.py")
    if not found:
        check("path-lock.py: cópias encontradas", False)
        return
    funcs = {t: functions_of(s) for t, s in found.items()}
    for name in PATHLOCK_CORE:
        present = {t: f[name] for t, f in funcs.items() if name in f}
        if len(present) < 2:
            continue  # function in one copy only — nothing to compare
        ref_topo = "build-hex" if "build-hex" in present else sorted(present)[0]
        ref = present[ref_topo]
        divergent = [t for t, s in present.items() if s != ref]
        check(f"path-lock.py:{name} idêntico em {len(present)} cópias",
              not divergent,
              f"divergem de {ref_topo}: {divergent}")
        if divergent:
            for t in divergent:
                _report_first_diff(f"{ref_topo}:{name}", ref, t, present[t])


def test_exemptions_have_reason():
    """An exception without a written reason is a divergence that disguised itself."""
    for key, reason in EXEMPT.items():
        check(f"exceção {key[0]}:{key[1]} declara motivo",
              isinstance(reason, str) and len(reason.strip()) > 40,
              "motivo ausente ou vago demais para auditar")


def test_pathlock_main_matches_outside_the_hex():
    """The 4 topologies without module YAML share the whole `main`.

    `build-hex` is in EXEMPT; the other four have no excuse — if one
    of them diverges, it is exactly the "4 of 5 fixed" case.
    """
    found = {t: s for t, s in copies("path-lock.py").items() if t != "build-hex"}
    mains = {t: fs["main"] for t, fs in ((t, functions_of(s)) for t, s in found.items())
             if "main" in fs}
    if len(mains) < 2:
        check("path-lock.py:main comparável fora do build-hex", False)
        return
    ref_topo = sorted(mains)[0]
    ref = mains[ref_topo]
    divergent = [t for t, s in mains.items() if s != ref]
    check(f"path-lock.py:main idêntico nas {len(mains)} topologias sem build-hex.yaml",
          not divergent,
          f"divergem de {ref_topo}: {divergent}")
    if divergent:
        for t in divergent:
            _report_first_diff(f"{ref_topo}:main", ref, t, mains[t])


# The command-line reading engine, in the two sources that remained: the template
# of the 5 copies (represented by build-hex's) and common/hooks/_shellscan.py,
# from which the two common guards import.
SHELLSCAN_FUNCS = ["_quoted_mask", "_split_segments", "_strip_redirections",
                   "_unquoted_view", "_unquote", "_is_flag"]
SHELLSCAN_CONSTS = ["_REDIR_RE", "_REDIR_STRIP_RE", "_SEP_PAIRS", "_SEP_CHARS",
                    "_PSEUDO", "_UNCOVERED_RE"]

# The step above parsing: which files the command line WRITES. It entered
# `_shellscan` on 2026-08-26 for the `write-mode-gate`, ported from
# bash-path-lock. It stays OUT of SHELLSCAN_FUNCS on purpose: the
# `enforcement-guard` keeps its own, poorer version of these two (it does not
# know `git mv`, does not count the source of a `mv`), and the case
# `test_common_guards_do_not_recopy_the_engine` would turn red over a debt
# that is not this detector's to resolve — it is recorded in the BACKLOG.
SHELLSCAN_TARGET_FUNCS = ["_segment_targets", "extract_write_targets"]


def named_constants(src: str, names: list) -> dict:
    """name → AST of the assignment, for the requested constants."""
    tree = _strip_docstrings(ast.parse(normalize(src)))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    out[t.id] = ast.dump(node.value)
    return out


def test_shellscan_engine_matches_bash_path_lock():
    """The two sources of the parsing engine must say the same thing.

    Perturbation: swap `(?![&=])` for `(?!&)` in the `_REDIR_RE` of
    `common/hooks/_shellscan.py` — the `>=` false positive, exactly as it
    survived in the enforcement-guard — and this case turns red naming the
    constant. If it stays green, it is proving nothing.
    """
    ref_p = REPO / "build-hex" / "hooks" / "bash-path-lock.py"
    scan_p = REPO / "common" / "hooks" / "_shellscan.py"
    check("common/hooks/_shellscan.py existe", scan_p.exists())
    if not (ref_p.exists() and scan_p.exists()):
        return
    ref_src, scan_src = ref_p.read_text(encoding="utf-8"), scan_p.read_text(encoding="utf-8")

    ref_c, scan_c = (named_constants(ref_src, SHELLSCAN_CONSTS),
                     named_constants(scan_src, SHELLSCAN_CONSTS))
    for name in SHELLSCAN_CONSTS:
        check(f"_shellscan:{name} presente nas duas fontes",
              name in ref_c and name in scan_c,
              f"bash-path-lock={name in ref_c} _shellscan={name in scan_c}")
        if name in ref_c and name in scan_c:
            check(f"_shellscan:{name} idêntico ao bash-path-lock",
                  ref_c[name] == scan_c[name],
                  "a tabela divergiu entre as duas fontes do motor")

    ref_f, scan_f = functions_of(ref_src), functions_of(scan_src)
    for name in SHELLSCAN_FUNCS + SHELLSCAN_TARGET_FUNCS:
        check(f"_shellscan:{name} presente nas duas fontes",
              name in ref_f and name in scan_f,
              f"bash-path-lock={name in ref_f} _shellscan={name in scan_f}")
        if name in ref_f and name in scan_f:
            equal = ref_f[name] == scan_f[name]
            check(f"_shellscan:{name} idêntico ao bash-path-lock", equal,
                  "o corpo divergiu entre as duas fontes do motor")
            if not equal:
                _report_first_diff(f"bash-path-lock:{name}", ref_f[name],
                                   "_shellscan", scan_f[name])


def test_common_guards_do_not_recopy_the_engine():
    """The two guards import the engine; they cannot go back to defining their own.

    Redefining `_quoted_mask` or `_REDIR_RE` in a guard is exactly how the
    duplication started the first time — and the new copy would not be seen by
    any of the cases above, because they compare the two DECLARED sources.
    """
    for name in ("enforcement-guard.py", "maven-reactor-guard.py"):
        p = REPO / "common" / "hooks" / name
        check(f"{name} existe", p.exists())
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        check(f"{name} importa _shellscan", "import _shellscan" in src,
              "o guard precisa importar o motor em vez de copiá-lo")
        tree = ast.parse(src)
        redefined = [n.name for n in tree.body
                       if isinstance(n, ast.FunctionDef)
                       and n.name in SHELLSCAN_FUNCS]
        redefined += [t.id for n in tree.body if isinstance(n, ast.Assign)
                        for t in n.targets
                        if isinstance(t, ast.Name) and t.id in SHELLSCAN_CONSTS
                        and not (isinstance(n.value, ast.Attribute))]
        check(f"{name} não redefine nada do motor", not redefined,
              f"redefinido localmente: {sorted(set(redefined))}")


def _report_first_diff(ref_label, ref, other_label, other):
    """Shows the SNIPPET that differs — not the start of the line, which is equal.

    The comparison is over AST dumps, which are long and start identical:
    printing the first 100 characters would show two equal lines and send
    the reader hunting for the difference by hand. Here the window is centered on the first
    divergent character.
    """
    a, b = ref.splitlines(), other.splitlines()
    for i in range(max(len(a), len(b))):
        la = a[i] if i < len(a) else ""
        lb = b[i] if i < len(b) else ""
        if la == lb:
            continue
        j = next((k for k in range(min(len(la), len(lb))) if la[k] != lb[k]),
                 min(len(la), len(lb)))
        lo, hi = max(0, j - 40), j + 70
        pre = "…" if lo else ""
        print(f"       1ª divergência (statement {i + 1}, caractere {j}):")
        print(f"         {ref_label}: {pre}{la[lo:hi] or '<ausente>'}")
        print(f"         {other_label}: {pre}{lb[lo:hi] or '<ausente>'}")
        return


def test_bash_path_lock_comes_from_template():
    """The 5 copies must be exactly the rendered template.

    This is the STRONG guarantee, and it replaces the comparison between copies for
    this file: comparing copies with each other proves they agree; comparing
    with the template proves they come from a single place. The difference matters when
    someone edits the five by hand in a consistent and wrong way.

    Building the generator yielded a finding that the comparison between copies had
    not given: `discovery` and `docs-topology` said "Writing source via Bash"
    in the block message, though their agents write documents, not
    code — they came copied from build-team without adjusting the word. The comparison
    between copies treated that noun as a legitimate per-topology difference;
    the template forces declaring which is the right one for each.
    """
    gen = REPO / "bin" / "gen-locks.py"
    check("bin/gen-locks.py existe", gen.exists())
    if not gen.exists():
        return
    r = subprocess.run([sys.executable, str(gen), "--check"],
                       capture_output=True, text=True, cwd=str(REPO))
    check("as 5 cópias são exatamente o molde renderizado",
          r.returncode == 0, (r.stdout + r.stderr).strip()[:300])


def _gen_locks_topologies():
    """Loads bin/gen-locks.py as a module and returns its TOPOLOGIES.

    `importlib` because the file name has a hyphen (`gen-locks.py`) and a direct
    `import` is not possible. Loading the module executes nothing: the generator only
    acts inside `if __name__ == "__main__"`, and this test is never called
    as `__main__`.
    """
    path_ = REPO / "bin" / "gen-locks.py"
    spec = importlib.util.spec_from_file_location("gen_locks_drift_check", str(path_))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TOPOLOGIES


def test_topology_list_matches_the_disk():
    """The 3 sources of the list of topologies with a hook must say the same thing.

    The gap the proof-gate found: deleting the `marketing` line only from
    `bin/gen-locks.py` (or only from the `TOPOLOGIES` of this file) left the two
    corresponding tests green, because each compared only against its
    own list — none compared the list against the disk. A topology
    could vanish from one source without anyone detecting it, because the other source
    was never consulted as arbiter.

    The three sources:

      1. the disk — every directory that actually has `hooks/bash-path-lock.py`;
      2. `bin/gen-locks.py`'s `TOPOLOGIES` — what the generator writes;
      3. the `TOPOLOGIES` of this file — what the other cases of this file
         compare.

    The three must be exactly the same set of directories. A
    divergence is reported naming which set has what, not just "did not
    match" — that is what makes the test, and not just the reading of the code, the one who
    decides whether a new (or deleted) topology is registered everywhere.

    Perturbation (how to know this case proves something): delete the `marketing`
    line from ONE of the two lists (`bin/gen-locks.py` or the `TOPOLOGIES`
    of this file) and run this file — it must turn red naming
    the list from which it vanished. If it stays green, it is proving nothing.
    """
    from_disk = {p.parent.parent.name
                for p in REPO.glob("*/hooks/bash-path-lock.py")}
    from_generator = {t["dir"] for t in _gen_locks_topologies()}
    this_file = set(TOPOLOGIES)

    check("disco e bin/gen-locks.py: mesmo conjunto de topologias",
          from_disk == from_generator,
          f"só no disco: {sorted(from_disk - from_generator) or '—'}; "
          f"só no gen-locks: {sorted(from_generator - from_disk) or '—'}")

    check("disco e TOPOLOGIES deste arquivo: mesmo conjunto de topologias",
          from_disk == this_file,
          f"só no disco: {sorted(from_disk - this_file) or '—'}; "
          f"só no TOPOLOGIES do teste: {sorted(this_file - from_disk) or '—'}")

    check("bin/gen-locks.py e TOPOLOGIES deste arquivo: mesmo conjunto de topologias",
          from_generator == this_file,
          f"só no gen-locks: {sorted(from_generator - this_file) or '—'}; "
          f"só no TOPOLOGIES do teste: {sorted(this_file - from_generator) or '—'}")


def main():
    test_all_copies_exist()
    test_topology_list_matches_the_disk()
    test_bash_path_lock_comes_from_template()
    test_bash_path_lock_identical()
    test_path_lock_core_identical()
    test_pathlock_main_matches_outside_the_hex()
    test_shellscan_engine_matches_bash_path_lock()
    test_common_guards_do_not_recopy_the_engine()
    test_exemptions_have_reason()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        print("\nUma cópia saiu da linha. Propague o conserto para TODAS antes de "
              "seguir — é exatamente a classe de falha que este teste existe para "
              "pegar (ver o item P0-3 no BACKLOG).")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
