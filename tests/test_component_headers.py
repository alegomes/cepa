#!/usr/bin/env python3
"""Every command, agent and skill the repo publishes has a header Claude Code reads,
and every `plugin:name` it cites exists.

No third-party dependency — run with `python3 tests/test_component_headers.py`.
Exits non-zero when any check fails.

The pain (gap E3 of docs/estrategia-lacunas-ecc.md): 2 of the 21 `SKILL.md`
files of the repo had no header block (`---` with `name:` and `description:`).
Claude Code does not load a skill without it, and nothing flickered: two agents
of the same plugin kept telling the agent to apply a skill that was never
there. Fixing those two files fixes today's symptom; this test stops the next
one. It is a test in the suite, not a hook (risk R1 of the same document).

What it checks, per component kind:

- skill   `<plugin>/skills/<dir>/SKILL.md`: header present and closed, `name`
          equal to `<dir>`, `description` not empty;
- agent   `<plugin>/agents/<stem>.md`: header present and closed, `name` equal
          to `<stem>`, `description` not empty;
- command `<plugin>/commands/<stem>.md`: header present and closed,
          `description` not empty;
- every `plugin:name` or `/plugin:name` written in any of those files, where
  `plugin` is a published plugin name (the `name` of `.claude-plugin/plugin.json`,
  so the `docs-topology/` folder publishes `docs:`), names an agent, command or
  skill that exists in that plugin.

An exception lives in this file with its reason, never as a silent skip. Each
exception is a ratchet: the test fails when the exception stops being true
(the file got fixed, the reference got resolved or removed), so the list only
shrinks.
"""

import json
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Repo-relative path → why it is still broken. The ratchet fails as soon as the
# file passes, which is the cue to delete the line.
KNOWN_BROKEN = {
}

# "plugin:name" → why citing it while it does not exist is on purpose.
DANGLING_OK = {
    "discovery:investigate":
        "common/commands/autonomous-start.md cita o fluxo futuro com '(when/if it exists)'",
}

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# --- header ----------------------------------------------------------------

def header(text):
    """The header block as {key: value}, or None when absent or unclosed.

    A block scalar (`description: |` or `>`) takes the indented lines below it.
    Lenient on purpose, line by line and not strict YAML: about 45 components
    carry an unquoted `: ` inside `description`, strict YAML rejects them, and
    Claude Code loads them today. Failing them would be a red with no defect.
    """
    if not text.startswith("---\n"):
        return None
    close = re.search(r"\n---[ \t]*(\n|$)", text[3:])
    if close is None:
        return None
    end = 3 + close.start()
    fields, key = {}, None
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            fields[key] = "" if value in ("|", ">", "|-", ">-", "|+", ">+") else value
        elif key and line.startswith((" ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields


def header_problems(kind, path, expected_name):
    """The list of reasons this component's header would not load. Empty = fine."""
    fields = header(path.read_text(encoding="utf-8"))
    if fields is None:
        return ["sem bloco de cabeçalho '---' fechado na primeira linha"]
    problems = []
    if not fields.get("description", "").strip("'\" "):
        problems.append("description vazio ou ausente")
    if kind in ("skill", "agent"):
        name = fields.get("name", "").strip("'\" ")
        if name != expected_name:
            problems.append(f"name={name!r}, esperado {expected_name!r}")
    return problems


# --- inventory -------------------------------------------------------------

def plugins(repo):
    """{published plugin name: plugin folder}."""
    found = {}
    for manifest in sorted(repo.glob("*/.claude-plugin/plugin.json")):
        found[json.loads(manifest.read_text())["name"]] = manifest.parent.parent
    return found


def components(repo):
    """[(kind, published plugin name, component name, path)] of the whole repo."""
    found = []
    for plugin, folder in plugins(repo).items():
        for path in sorted(folder.glob("skills/*/SKILL.md")):
            found.append(("skill", plugin, path.parent.name, path))
        for path in sorted(folder.glob("agents/*.md")):
            found.append(("agent", plugin, path.stem, path))
        for path in sorted(folder.glob("commands/*.md")):
            found.append(("command", plugin, path.stem, path))
    return found


def dangling(repo):
    """{"plugin:name": [file:line, ...]} for every citation that resolves to nothing."""
    names = plugins(repo)
    comps = components(repo)
    known = {f"{plugin}:{name}" for _, plugin, name, _ in comps}
    cite = re.compile(
        r"(?<![\w./-])/?(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True))
        + r"):([a-z][a-z0-9-]*[a-z0-9])"
    )
    found = {}
    for _, _, _, path in comps:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in cite.finditer(line):
                ref = f"{m.group(1)}:{m.group(2)}"
                if ref not in known:
                    found.setdefault(ref, []).append(f"{path.relative_to(repo)}:{number}")
    return found


def broken(repo):
    """{repo-relative path: [problems]} for every component whose header fails."""
    found = {}
    for kind, _, name, path in components(repo):
        problems = header_problems(kind, path, name)
        if problems:
            found[str(path.relative_to(repo))] = problems
    return found


# --- the validator goes red on the defects it exists for ------------------

def self_test():
    """Build a tiny repo with one defect of each kind and require the validator to see it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def write(rel, text):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        write("p/.claude-plugin/plugin.json", json.dumps({"name": "pp"}))
        write("p/skills/good/SKILL.md", "---\nname: good\ndescription: ok\n---\nbody\n")
        write("p/skills/bare/SKILL.md", "# bare\n\nno header, the lot-0 defect\n")
        write("p/skills/renamed/SKILL.md", "---\nname: other\ndescription: ok\n---\n")
        write("p/skills/folded/SKILL.md", "---\nname: folded\ndescription: >\n  two\n  lines\n---\n")
        write("p/agents/a.md", "---\nname: a\ndescription:\n---\nSee `pp:good` and `pp:ghost`.\n")
        write("p/agents/b.md", "---\nname: b\ndescription: ok\n---\nRun /pp:c, never /pp:gone. file:line\n")
        write("p/commands/c.md", "---\ndescription: ok\n---\n")
        write("p/commands/open.md", "---\ndescription: ok\nnever closed\n")

        got = broken(root)
        check("self-test: SKILL.md sem cabeçalho é pego", "p/skills/bare/SKILL.md" in got, got)
        check("self-test: name diferente da pasta é pego", "p/skills/renamed/SKILL.md" in got, got)
        check("self-test: description vazio é pego", "p/agents/a.md" in got, got)
        check("self-test: cabeçalho não fechado é pego", "p/commands/open.md" in got, got)
        check("self-test: description em bloco dobrado passa", "p/skills/folded/SKILL.md" not in got, got)
        check("self-test: componente correto passa",
              not {"p/skills/good/SKILL.md", "p/agents/b.md", "p/commands/c.md"} & set(got), got)

        refs = dangling(root)
        check("self-test: referência pendurada é pega", set(refs) == {"pp:ghost", "pp:gone"}, refs)


# --- the real repo ---------------------------------------------------------

def main():
    self_test()

    check("o repo publica componentes", len(components(REPO)) > 100, len(components(REPO)))

    got = broken(REPO)
    for path, problems in sorted(got.items()):
        if path in KNOWN_BROKEN:
            continue
        check(f"cabeçalho de {path}", False, "; ".join(problems))
    new = sorted(set(got) - set(KNOWN_BROKEN))
    check(f"todo comando, agente e skill tem cabeçalho válido ({len(new)} novo(s) quebrado(s))", not new, new)
    for path, reason in sorted(KNOWN_BROKEN.items()):
        check(f"exceção ainda verdadeira: {path}", path in got,
              f"o arquivo passou; apague a linha de KNOWN_BROKEN ({reason})")

    refs = dangling(REPO)
    for ref, where in sorted(refs.items()):
        if ref in DANGLING_OK:
            continue
        check(f"referência {ref} existe", False, ", ".join(where))
    unexpected = sorted(set(refs) - set(DANGLING_OK))
    check(f"toda citação plugin:nome resolve ({len(unexpected)} pendurada(s))", not unexpected, unexpected)
    for ref, reason in sorted(DANGLING_OK.items()):
        check(f"exceção ainda verdadeira: {ref}", ref in refs,
              f"a citação sumiu ou passou a resolver; apague a linha de DANGLING_OK ({reason})")

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\nall ok")


if __name__ == "__main__":
    main()
