#!/usr/bin/env python3
"""Regression tests of common/hooks/write-mode-gate.py.

A session's mode was prose: `session-mode.py` injects on every turn "an action
outside this mode does NOT become a question and does NOT become work now", and nothing blocked. In
session `session/drain-plan-speed` (2026-08-26) the agent broke the mode seven times
in a row — turned each deviation into a closed question with "Recomendo sim",
harvested the yes, and built. No deviation capture was recorded.

This gate is the sibling of `refactor-gate.py`: a whitelist of DESTINATIONS per mode,
applied to Edit/Write/MultiEdit/NotebookEdit and also to Bash.

Contracts guarded here:
  - a mode with a whitelist: a destination outside it blocks (rc=2) with the reason;
  - a destination inside the list passes;
  - `construction` and `refactor` are silent — whoever charges there are the
    completion-auditor/proof-reviewer and the refactor-gate;
  - with no declared mode, silent;
  - Bash is not an escape route: `>`, `>>`, `sed -i`, `tee` and `git mv` block
    the same (blocking only Write has already let agents escape through sed in this repo);
  - `>=` in a condition does not become a redirect (a real false block of the
    bash-path-lock, which silenced perturbations for 2 months);
  - a write OUTSIDE the session root passes — the perturbation worktree in /tmp and the
    session's scratchpad are not governed by mode (path-lock-out-of-root);
  - a python/node inline script (`-c`, `-e`, heredoc) has its script read: a
    known write call whose path is readable is judged like any target, so a
    write outside the mode BLOCKS (fb-20261106-1); a script that only reads passes;
  - what still cannot be read (`patch`, a computed path, a script with no
    known write call) does NOT block and
    WARNS — blocking would take every heredoc along, which is how this repo runs
    scripts; the silence of before let the line break the mode without a trace;
  - the message says what to do (record through off-mode-capture, or end the
    mode) and does NOT announce the kill switch: a cheap escape is the same escape again;
  - CEPA_MODO=off turns the gate off.

No third-party deps — run with `python3 tests/test_write_mode_gate.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The hook emits `modo_escrita_indecidivel`, and this suite executes it: without isolating, the
# rehearsal becomes a line in the /common:metrics report of whoever runs the tests.
from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "common" / "hooks" / "write-mode-gate.py"

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Repo:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        (self.path / ".claude").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "."], cwd=self.path, check=True)
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def mode(self, name):
        (self.path / ".claude" / "session-mode").write_text(
            f"mode: {name}\nbudget: null\n", encoding="utf-8")

    def call(self, tool, tool_input, env=None):
        e = {**os.environ}
        e.update(env or {})
        return subprocess.run(
            [sys.executable, str(GATE)],
            input=json.dumps({"cwd": str(self.path), "tool_name": tool,
                              "tool_input": tool_input}),
            capture_output=True, text=True, timeout=15, env=e,
        )

    def edit(self, path, **kw):
        return self.call("Edit", {"file_path": path}, **kw)

    def bash(self, cmd, **kw):
        return self.call("Bash", {"command": cmd}, **kw)


# One case per mode: what it PRODUCES (passes) and what it does not produce (blocks).
ALLOWED = {
    "exploration": ["docs/estrategia-x.md", ".claude/programs/p/plan.yaml",
                   "BACKLOG.md"],
    "discovery": ["docs/discovery/c/framing.md", "docs/spec/x.md",
                   ".claude/acceptance/x.yaml", "BACKLOG.md"],
    "design": ["docs/design/fluxos.md", ".claude/x", "BACKLOG.md"],
    "reflection": [".claude/reflection/r.md", "docs/qualquer.md", "BACKLOG.md"],
    "documentation": ["docs/tutorial/primeiro-dia.md", "docs/reference/api.md",
                     ".claude/x", "BACKLOG.md", "README.md"],
}
BLOCKED = {
    "exploration": ["common/hooks/novo.py", "common/commands/x.md",
                   "tests/test_x.py", "common/agents/lead.md", "src/App.java"],
    "discovery": ["docs/estrategia-x.md", "common/hooks/novo.py",
                   "tests/test_x.py"],
    "design": ["docs/how-to/x.md", "common/hooks/novo.py"],
    "reflection": ["common/hooks/novo.py", "tests/test_x.py"],
    "documentation": ["common/hooks/novo.py", "tests/test_x.py",
                     "common/commands/x.md", "common/README.md"],
}


def test_whitelist_per_mode():
    for mode, targets in ALLOWED.items():
        with Repo() as r:
            r.mode(mode)
            for target in targets:
                p = r.edit(target)
                check(f"{mode}: libera {target}", p.returncode == 0, p.stderr[:160])
    for mode, targets in BLOCKED.items():
        with Repo() as r:
            r.mode(mode)
            for target in targets:
                p = r.edit(target)
                check(f"{mode}: bloqueia {target}", p.returncode == 2, p.stderr[:160])


def test_modes_without_list_are_silent():
    for mode in ("construction", "refactor"):
        with Repo() as r:
            r.mode(mode)
            for target in ("common/hooks/novo.py", "tests/test_x.py",
                         "src/main/java/App.java"):
                p = r.edit(target)
                check(f"{mode}: gate é mudo em {target}", p.returncode == 0,
                      p.stderr[:160])


def test_session_mode_in_old_format_applies():
    """`modo: exploracao` (the old `cepa`) is still read as `exploration`."""
    for old, new in (("exploracao", "exploration"), ("descoberta", "discovery"),
                        ("documentacao", "documentation"), ("reflexao", "reflection")):
        with Repo() as r:
            (r.path / ".claude" / "session-mode").write_text(
                f"modo: {old}\nrotina: null\norcamento: null\naberto_em: 2026-10-19T13:46:36Z\n",
                encoding="utf-8")
            p = r.edit("src/App.java")
            check(f"antigo: modo: {old} bloqueia como {new}",
                  p.returncode == 2 and f"mode {new}" in p.stderr, p.stderr[:200])
    with Repo() as r:
        (r.path / ".claude" / "session-mode").write_text("modo: construcao\n", encoding="utf-8")
        p = r.edit("src/App.java")
        check("antigo: modo: construcao é mudo (como construction)", p.returncode == 0, p.stderr[:200])
    with Repo() as r:
        (r.path / ".claude" / "session-mode").write_text("modo: exploracao\n", encoding="utf-8")
        p = r.edit("docs/estrategia-x.md")
        check("antigo: modo: exploracao libera docs/**", p.returncode == 0, p.stderr[:200])


def test_without_mode_is_silent():
    with Repo() as r:
        p = r.edit("common/hooks/novo.py")
        check("sem modo declarado: gate é mudo", p.returncode == 0, p.stderr[:160])


def test_all_write_tools():
    with Repo() as r:
        r.mode("exploration")
        for tool, ti in (("Write", {"file_path": "common/hooks/n.py"}),
                         ("MultiEdit", {"file_path": "common/hooks/n.py"}),
                         ("NotebookEdit", {"notebook_path": "analise/n.ipynb"})):
            p = r.call(tool, ti)
            check(f"exploration: {tool} bloqueado", p.returncode == 2, p.stderr[:120])


def test_bash_is_not_an_escape_route():
    with Repo() as r:
        r.mode("exploration")
        for cmd in ('echo x > common/hooks/novo.py',
                    'cat foo >> common/commands/run.md',
                    "sed -i '' 's/a/b/' common/bin/cepa",
                    'tee tests/test_x.py < /dev/null',
                    'git mv common/hooks/a.py common/hooks/b.py',
                    # Downloading/creating/syncing also writes, and the destination is
                    # explicit in the argv — finding of the proof-reviewer.
                    'curl -o common/hooks/novo.py https://e.com/f',
                    'wget -O tests/test_x.py https://e.com/f',
                    'touch common/hooks/novo.py',
                    'rsync -a /tmp/x/ common/hooks/',
                    # Reverting a locked file to an old version is
                    # writing to it — the same tool as the watched `git mv`.
                    'git checkout main -- common/hooks/novo.py',
                    'git restore tests/test_x.py'):
            p = r.bash(cmd)
            check(f"bash bloqueado: {cmd[:30]}", p.returncode == 2, p.stderr[:120])


def test_bash_allows_what_the_mode_produces():
    with Repo() as r:
        r.mode("exploration")
        for cmd in ('echo x > docs/estrategia.md',
                    'git commit -m "docs(estrategia): dois caminhos\n\nA -> B"',
                    'grep -rn "modo" common/hooks/',
                    # The BSD form of sed leaves `''` as an operand: without filtering
                    # the empty token, the SCRIPT `s/a/b/` was counted as a written file
                    # and this legitimate command was blocked.
                    "sed -i '' 's/a/b/' docs/estrategia.md",
                    'curl -o docs/baixado.md https://e.com/f',
                    'touch docs/nota.md',
                    'git checkout main -- docs/estrategia.md',
                    # Switching branches is not a path-directed write: if it
                    # became a target, the mode would block every `git checkout`.
                    'git checkout main'):
            p = r.bash(cmd)
            check(f"bash liberado: {cmd[:30]}", p.returncode == 0, p.stderr[:160])


def test_undecidable_construct_warns_without_blocking():
    """`python3 -c`, `patch` and heredoc write where the gate cannot see.

    Finding of the proof-reviewer (2026-08-26): the signal existed in `_shellscan` and the
    gate discarded it, so these lines passed without a block AND without a trace.
    The decision was to warn, not to block — the list includes heredoc, and a mode that
    blocks every `python3 - <<PY` is a mode nobody uses.
    """
    with Repo() as r:
        r.mode("exploration")
        for cmd in ('python3 -c "import sys; print(sys.argv)"',
                    'patch common/bin/cepa < /tmp/p.diff',
                    "python3 - <<'PY'\nprint(1)\nPY"):
            p = r.bash(cmd)
            check(f"indecidível não barra: {cmd[:26]}", p.returncode == 0,
                  p.stderr[:160])
            check(f"indecidível avisa: {cmd[:26]}", "WARNING" in p.stderr,
                  p.stderr[:160] or "(stderr vazio)")
            check(f"aviso diz que não conferiu: {cmd[:22]}",
                  "did not check" in p.stderr, p.stderr[:200])


def test_readable_command_does_not_warn():
    """The warning is only worth anything if it is rare — one that always shouts teaches people to ignore it."""
    with Repo() as r:
        r.mode("exploration")
        for cmd in ('echo x > docs/estrategia.md', 'grep -rn modo common/'):
            p = r.bash(cmd)
            check(f"sem aviso em comando legível: {cmd[:24]}",
                  "WARNING" not in p.stderr, p.stderr[:160])


def test_undecidable_is_silent_in_mode_without_list():
    with Repo() as r:
        r.mode("construction")
        p = r.bash('python3 -c "open(\'x.py\',\'w\')"')
        check("construction: nem aviso", p.returncode == 0 and "WARNING" not in p.stderr,
              p.stderr[:160])


def test_undecidable_does_not_swallow_a_block():
    """A readable target outside the list blocks even when the line is also opaque."""
    with Repo() as r:
        r.mode("exploration")
        p = r.bash('echo x > common/hooks/n.py && python3 -c "pass"')
        check("alvo legível fora da lista ainda barra", p.returncode == 2,
              p.stderr[:160])


def test_ge_is_not_a_redirect():
    with Repo() as r:
        r.mode("exploration")
        p = r.bash('if [ "$n" >= 3 ]; then echo common/hooks/x.py; fi')
        check(">= não vira redirecionamento", p.returncode == 0, p.stderr[:160])


def test_outside_the_root_passes():
    """The perturbation worktree in /tmp and the scratchpad do not belong to the mode.

    Narrowing the gate to outside the root is what locked the proof-reviewer on
    2026-06-18 (memory path-lock-out-of-root) and left 5 cards stuck in
    NEEDS-HUMAN. Here the mode governs the session's repo, and only it.
    """
    with Repo() as r:
        r.mode("exploration")
        for target in ("/tmp/perturba/App.java", "/tmp/scratch/nota.py"):
            p = r.edit(target)
            check(f"fora da raiz passa: {target}", p.returncode == 0, p.stderr[:160])


def test_message_says_what_to_do():
    with Repo() as r:
        r.mode("exploration")
        p = r.edit("common/hooks/novo.py")
        check("mensagem nomeia o modo ativo", "exploration" in p.stderr, p.stderr[:200])
        check("mensagem nomeia o alvo", "common/hooks/novo.py" in p.stderr,
              p.stderr[:200])
        check("mensagem oferece a captura do desvio",
              "off-mode-capture" in p.stderr, p.stderr[:200])
        check("mensagem oferece encerrar o modo",
              "end this mode" in p.stderr.lower(), p.stderr[:300])
        check("mensagem NÃO anuncia o kill switch",
              "CEPA_MODO" not in p.stderr, p.stderr[:300])


def test_kill_switch():
    with Repo() as r:
        r.mode("exploration")
        p = r.edit("common/hooks/novo.py", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off desliga o gate", p.returncode == 0, p.stderr[:160])


def test_table_comes_from_modes_py():
    """The whitelist lives in _modes.py, together with the rest of the modes table.

    A second table of modes in the hook is the disease that _modes.py treats.
    """
    sys.path.insert(0, str(REPO / "common" / "hooks"))
    from _modes import MODES
    for name, d in MODES.items():
        check(f"_modes: {name} declara `write`", "write" in d,
              "modo sem lista branca declarada — nem 'tudo' nem os globs")
    src = GATE.read_text(encoding="utf-8") if GATE.exists() else ""
    check("o hook importa a tabela em vez de copiá-la", "_modes" in src)


def test_heredoc_body_is_not_a_target():
    """Episodes 2 and 3 of the item portao-modo-escrita-le-heredoc (2026-09-02).

    The gate treated the text INSIDE the heredoc as shell: a backtick quoted
    in the body became a target, and a `>` of an example quoted in the prose became the
    destination of the write. The attempt to record the very BACKLOG section
    that described the defect was blocked by it. The body is data, not a command.
    """
    with Repo() as r:
        r.mode("exploration")
        cases = {
            "crase no corpo":
                f"cat > {r.path}/docs/nota.md <<'EOF'\n"
                "veja `common/hooks/x.py` e `\n"
                "EOF",
            "redirecionamento no corpo":
                f"cat >> {r.path}/BACKLOG.md <<'EOF'\n"
                "o comando fazia echo x > common/hooks/novo.py\n"
                "EOF",
            "redirecionamento no corpo, delimitador sem aspas":
                f"cat >> {r.path}/BACKLOG.md <<EOF\n"
                "echo x > common/hooks/novo.py\n"
                "EOF",
        }
        for name, cmd in cases.items():
            p = r.bash(cmd)
            check(f"heredoc liberado: {name}", p.returncode == 0, p.stderr[:200])
        # The body being data cannot open a hole: the REAL destination of the command
        # is still checked.
        p = r.bash("cat > common/hooks/novo.py <<'EOF'\nconteudo\nEOF")
        check("heredoc para destino fora do modo ainda barra",
              p.returncode == 2, p.stderr[:200])


def test_variable_of_the_command_itself_is_expanded():
    """Episode 1: the target assembled by a variable assigned in the command itself.

    The gate reported the literal `$D/x.md`, which matches no list, and
    blocked saying "you are outside the mode". The same path written out in full
    passed. The simple assignment is on the line: it can be read without executing.
    """
    with Repo() as r:
        r.mode("exploration")
        for cmd in (f'D={r.path}/.claude/notas; cat > "$D/x.md" <<EOF\noi\nEOF',
                    f'D={r.path}/.claude/notas && echo oi > ${{D}}/x.md',
                    f'export D="{r.path}/docs"; echo oi >> $D/y.md',
                    'D=docs; E=$D/sub; echo oi > $E/z.md'):
            p = r.bash(cmd)
            check(f"variável do comando expandida: {cmd[-24:]!r}",
                  p.returncode == 0, p.stderr[:200])
        # Expanding is not loosening: the expanded destination outside the mode blocks.
        p = r.bash('D=common/hooks; echo x > "$D/novo.py"')
        check("variável expandida para fora do modo barra", p.returncode == 2,
              p.stderr[:200])
        check("o bloqueio mostra o alvo já expandido",
              "common/hooks/novo.py" in p.stderr, p.stderr[:300])


def test_unresolvable_target_does_not_blame_the_mode():
    """The net of the item: when the target cannot be read, say so.

    The two failures were indistinguishable to whoever reads — the parsing one came out with the
    "outside the mode" message, which orders ending the mode, and whoever takes
    the block believes it. A target with a variable the command does not assign (or assigns
    through command substitution) is an unresolved target, not a verdict.
    """
    with Repo() as r:
        r.mode("exploration")
        for cmd in ('echo x > "$DESTINO_QUE_NINGUEM_DEFINIU/a.md"',
                    'D=$(pwd)/docs; echo x > $D/a.md',
                    'echo x > "${D:-docs}/a.md"'):
            p = r.bash(cmd)
            check(f"não resolvido barra: {cmd[:28]}", p.returncode == 2,
                  p.stderr[:200])
            check(f"diz que não resolveu: {cmd[:28]}",
                  "could not resolve" in p.stderr, p.stderr[:300])
            check(f"não culpa o modo: {cmd[:28]}",
                  "outside what that mode produces" not in p.stderr
                  and "end this mode" not in p.stderr.lower(), p.stderr[:300])
        # A command that touches the variable without a simple assignment invalidates the value
        # the gate kept: `unset D` leaves `$D` empty in the shell, and releasing
        # `docs/y` would be releasing a target that is not the real one.
        for cmd in ('D=docs; unset D; echo x > $D/y.md',
                    'D=docs; read D < /tmp/entrada; echo x > $D/y.md',
                    'D=docs; ((D+=1)); echo x > $D/y.md'):
            p = r.bash(cmd)
            check(f"mutação invalida o valor: {cmd[8:22]}",
                  p.returncode == 2 and "could not resolve" in p.stderr,
                  p.stderr[:200])
        # A real environment variable remains valid (os.path.expandvars).
        p = r.bash('echo x > "$RAIZ_TESTE/docs/a.md"',
                   env={"RAIZ_TESTE": str(r.path)})
        check("variável de ambiente definida resolve", p.returncode == 0,
              p.stderr[:200])


def test_git_dir_is_checkout_preparation_in_every_mode():
    """fb-20261105-1: `.git/info/**` is checkout preparation outside versioning.

    A `discovery` session was blocked from `echo '.playwright-mcp/' >>
    .git/info/exclude`. `.git/info/` passes in every mode; `.git/hooks/*` and
    `.git/config` do not (git runs code from them later), nor `.gitignore`
    (versioned) or anything that normalizes out of `.git/info/`.
    """
    for mode in ("discovery", "exploration", "design", "reflection",
                 "documentation"):
        with Repo() as r:
            r.mode(mode)
            p = r.edit(".git/info/exclude")
            check(f"{mode}: Edit em .git/info/exclude passa", p.returncode == 0,
                  p.stderr[:160])
            p = r.call("Write", {"file_path": ".git/info/exclude"})
            check(f"{mode}: Write em .git/info/exclude passa",
                  p.returncode == 0, p.stderr[:160])
            p = r.edit(".git/info/sparse-checkout")
            check(f"{mode}: Edit em .git/info/sparse-checkout passa",
                  p.returncode == 0, p.stderr[:160])
            p = r.bash("echo x >> .git/info/sparse-checkout")
            check(f"{mode}: bash em .git/info/sparse-checkout passa",
                  p.returncode == 0, p.stderr[:160])
            p = r.edit(".git/info/attributes")
            check(f"{mode}: Edit em .git/info/attributes passa",
                  p.returncode == 0, p.stderr[:160])
            for target in (".git/hooks/pre-commit", ".git/config"):
                p = r.edit(target)
                check(f"{mode}: Edit em {target} bloqueia (executa código depois)",
                      p.returncode == 2, p.stderr[:160])
                p = r.bash(f"echo x >> {target}")
                check(f"{mode}: bash em {target} bloqueia (executa código depois)",
                      p.returncode == 2, p.stderr[:160])
            for label, cmd in (
                    ("relativo", "echo '.playwright-mcp/' >> .git/info/exclude"),
                    ("absoluto",
                     f"echo '.playwright-mcp/' >> {r.path}/.git/info/exclude")):
                p = r.bash(cmd)
                check(f"{mode}: bash {label} em .git/info/exclude passa",
                      p.returncode == 0, p.stderr[:160])
            p = r.edit("common/hooks/x.py")
            check(f"{mode}: common/hooks/x.py segue bloqueado",
                  p.returncode == 2, p.stderr[:160])
            p = r.edit(".git/../common/hooks/x.py")
            check(f"{mode}: .git/../common/hooks/x.py segue bloqueado",
                  p.returncode == 2, p.stderr[:160])
            p = r.bash("echo x >> .git/../common/hooks/x.py")
            check(f"{mode}: bash .git/../common/hooks/x.py segue bloqueado",
                  p.returncode == 2, p.stderr[:160])
    with Repo() as r:
        r.mode("discovery")
        p = r.edit(".gitignore")
        check("discovery: .gitignore (versionado) segue bloqueado",
              p.returncode == 2, p.stderr[:160])
        p = r.bash("echo '.playwright-mcp/' >> .gitignore")
        check("discovery: bash em .gitignore segue bloqueado",
              p.returncode == 2, p.stderr[:160])


# fb-20261106-1 (2026-11-06): in an `exploration` session five files outside
# docs/ and .claude/ were edited by `python3` with a heredoc, and the gate only
# warned. The shape of those edits, which is how this repo patches a file:
INTERP_WRITES_OUTSIDE = [
    # heredoc, the variable holding a literal path
    "python3 - <<'PY'\nfrom pathlib import Path\np = Path('common/hooks/_modes.py')\n"
    "s = p.read_text()\np.write_text(s.replace('a', 'b'))\nPY",
    # heredoc without the dash, open() in write mode
    'python3 <<EOF\nwith open("common/bin/cepa-intent", "w") as f:\n    f.write("x")\nEOF',
    # python -c
    'python3 -c "open(\'common/hooks/evil.py\',\'w\').write(\'1\')"',
    # node -e and node heredoc
    "node -e \"require('fs').writeFileSync('compass/hooks/a.tsx', 'x')\"",
    "node <<'JS'\nconst fs = require('fs');\nfs.appendFileSync(`compass/hooks/b.ts`, 'x');\nJS",
    # a loop over literal paths
    "python3 - <<'PY'\nimport pathlib\nfor f in ['docs/a.md', 'common/bin/cepa-metrics']:\n"
    "    pathlib.Path(f).write_text('x')\nPY",
    # absolute path inside the session root is resolved like a relative one
    "python3 - <<'PY'\nopen('{root}/tests/test_x.py', 'a').write('x')\nPY",
]


def test_interpreter_write_outside_mode_blocks():
    """A python/node script that writes a readable path outside the mode BLOCKS."""
    with Repo() as r:
        r.mode("exploration")
        for cmd in INTERP_WRITES_OUTSIDE:
            cmd = cmd.replace("{root}", str(r.path))
            p = r.bash(cmd)
            check(f"interpretador fora do modo barra: {cmd[:40]!r}",
                  p.returncode == 2, p.stderr[:200] or "(stderr vazio)")
            check(f"mensagem é a de fora do modo: {cmd[:30]!r}",
                  "outside what that mode" in p.stderr, p.stderr[:200])


def test_interpreter_block_names_the_script_target():
    with Repo() as r:
        r.mode("exploration")
        p = r.bash(INTERP_WRITES_OUTSIDE[0])
        check("o alvo barrado é o caminho do script",
              "common/hooks/_modes.py" in p.stderr, p.stderr[:200])


def test_interpreter_write_inside_mode_passes():
    """Writing what the mode produces through a script stays allowed, without noise."""
    with Repo() as r:
        r.mode("exploration")
        for cmd in ("python3 - <<'PY'\nfrom pathlib import Path\n"
                    "Path('docs/estrategia.md').write_text('x')\nPY",
                    "python3 -c \"open('.claude/x.yaml','w').write('1')\"",
                    "node -e \"require('fs').writeFileSync('BACKLOG.md','x')\""):
            p = r.bash(cmd)
            check(f"interpretador dentro do modo passa: {cmd[:36]!r}",
                  p.returncode == 0, p.stderr[:200])
            check(f"sem aviso quando o alvo foi lido: {cmd[:30]!r}",
                  "WARNING" not in p.stderr, p.stderr[:200])


def test_interpreter_reading_outside_mode_passes():
    """Reading a file outside the mode is not writing it: the script that only reads passes."""
    with Repo() as r:
        r.mode("exploration")
        for cmd in ("python3 - <<'PY'\nfrom pathlib import Path\n"
                    "print(Path('common/hooks/_modes.py').read_text()[:10])\nPY",
                    "python3 -c \"print(open('common/bin/cepa').read())\"",
                    # reads outside, writes inside
                    "python3 - <<'PY'\nfrom pathlib import Path\n"
                    "src = Path('common/hooks/_modes.py').read_text()\n"
                    "Path('docs/notas.md').write_text(src)\nPY"):
            p = r.bash(cmd)
            check(f"leitura fora do modo passa: {cmd[:40]!r}",
                  p.returncode == 0, p.stderr[:200])


def test_interpreter_write_outside_root_passes():
    """Decision 2 holds for scripts too: /tmp belongs to no mode."""
    with Repo() as r:
        r.mode("exploration")
        p = r.bash("python3 - <<'PY'\nopen('/tmp/cepa-scratch.txt', 'w').write('x')\nPY")
        check("script gravando em /tmp passa", p.returncode == 0, p.stderr[:200])


def test_interpreter_unreadable_target_still_warns():
    """A write whose path the script computes is not guessed: warning, as before."""
    with Repo() as r:
        r.mode("exploration")
        p = r.bash("python3 - <<'PY'\nimport sys\nopen(sys.argv[1], 'w').write('x')\nPY")
        check("alvo computado não barra", p.returncode == 0, p.stderr[:200])
        check("alvo computado avisa", "WARNING" in p.stderr, p.stderr[:200])


def test_interpreter_in_construction_is_silent():
    for mode in ("construction", "refactor"):
        with Repo() as r:
            r.mode(mode)
            p = r.bash(INTERP_WRITES_OUTSIDE[0])
            check(f"{mode}: script livre", p.returncode == 0 and not p.stderr.strip(),
                  p.stderr[:160])


def test_interpreter_reads_which_argument_writes():
    """The source of a copy is read, the destination is written."""
    with Repo() as r:
        r.mode("exploration")
        ok = r.bash("python3 - <<'PY'\nimport shutil\n"
                    "shutil.copy('common/hooks/_modes.py', 'docs/modes-copia.py')\nPY")
        check("copiar DE fora para docs passa", ok.returncode == 0, ok.stderr[:200])
        bad = r.bash("python3 - <<'PY'\nimport shutil\n"
                     "shutil.copy('docs/a.md', 'common/hooks/a.md')\nPY")
        check("copiar PARA fora barra", bad.returncode == 2, bad.stderr[:200])
        # `move` deletes its source: both ends are writes
        for src, dst in (("docs/a.md", "common/hooks/a.md"),
                         ("common/hooks/a.md", "docs/a.md")):
            mv = r.bash(f"python3 -c \"import shutil; shutil.move('{src}','{dst}')\"")
            check(f"mover {src} -> {dst} barra", mv.returncode == 2, mv.stderr[:200])
        mv_ok = r.bash("python3 -c \"import shutil; shutil.move('docs/a.md','docs/b.md')\"")
        check("mover dentro de docs passa", mv_ok.returncode == 0, mv_ok.stderr[:200])
        env = r.bash("CEPA_X=1 python3 -c \"open('tests/t.py','w').write('x')\"")
        check("prefixo de variável não esconde o -c", env.returncode == 2,
              env.stderr[:200])


def test_heredoc_to_a_script_file_is_data():
    """`python3 tool.py <<EOF` feeds DATA to a script: the body is not the program."""
    with Repo() as r:
        r.mode("exploration")
        p = r.bash("python3 tool.py <<'EOF'\nopen('common/x.py', 'w')\nEOF")
        check("stdin de script não vira programa", p.returncode == 0, p.stderr[:200])


def main():
    print("test_write_mode_gate")
    if not GATE.exists():
        print(f"  FAIL hook ausente: {GATE}")
        return 1
    for fn in (test_whitelist_per_mode, test_modes_without_list_are_silent,
               test_session_mode_in_old_format_applies,
               test_without_mode_is_silent, test_all_write_tools,
               test_bash_is_not_an_escape_route, test_bash_allows_what_the_mode_produces,
               test_undecidable_construct_warns_without_blocking,
               test_readable_command_does_not_warn,
               test_undecidable_is_silent_in_mode_without_list,
               test_undecidable_does_not_swallow_a_block,
               test_ge_is_not_a_redirect, test_outside_the_root_passes,
               test_message_says_what_to_do, test_kill_switch,
               test_table_comes_from_modes_py,
               test_heredoc_body_is_not_a_target,
               test_variable_of_the_command_itself_is_expanded,
               test_unresolvable_target_does_not_blame_the_mode,
               test_git_dir_is_checkout_preparation_in_every_mode,
               test_interpreter_write_outside_mode_blocks,
               test_interpreter_block_names_the_script_target,
               test_interpreter_write_inside_mode_passes,
               test_interpreter_reading_outside_mode_passes,
               test_interpreter_write_outside_root_passes,
               test_interpreter_unreadable_target_still_warns,
               test_interpreter_in_construction_is_silent,
               test_interpreter_reads_which_argument_writes,
               test_heredoc_to_a_script_file_is_data):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
