#!/usr/bin/env python3
"""The build-hex leads call the workers with the plugin prefix (`<plugin>:<name>`).

No external dependency — run with `python3 tests/test_leads_prefix_workers.py`.

## Why it exists

Installed as a plugin, agents are addressed as `<plugin>:<name>` (e.g.:
`build-hex:epic-author`). The three build-hex leads ordered delegating by the short name, so
the first call to Task failed with 'Agent type not found' and was redone: a lost
turn per item. Measurement (feedback fb-20261016-2, run `until/2026-10-16-0822`, item
`S3-clientes-provedor-unificados`, build-hex 1.4.1): the planning-lead's 3 calls failed
and were redone, 3 turns thrown away on a single item. Worse: `product-manager`,
`qa-engineer` and `security-reviewer` also exist in build-team, so a short name may
even resolve to the wrong plugin, with no error at all.

The fix was applied to 3 copies; copy N+1 (a new lead, or a new worker cited
without a prefix) would be born broken in silence. This test is the radar. The rule is mechanical and
derived from disk, not from a fixed list: the set of agent names comes from
`*/agents/*.md`; every name in backticks in a lead must come prefixed with the owning plugin, and
every `<plugin>:<name>` must point to a file that exists.
"""

import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Only the build-hex for now. The leads of the other topologies still use a short name;
# prefixing them is a follow-up, and they enter here when they are fixed.
PLUGINS_COVERED = ["build-hex"]

# Delegation verb: on the line that has it, an agent name in prose (without backticks) is also
# an instruction and needs a prefix. References on other lines are free.
DELEGATION_VERB = re.compile(
    r"delegat|route (to|back)|hand(s)? (off|to)|proceed to", re.I)

TOKEN = re.compile(r"`([a-z][a-z0-9-]*(?::[a-z][a-z0-9-]*)?)`")


def agent_map(repo: Path) -> dict:
    """name -> set of plugins that have `<plugin>/agents/<name>.md`."""
    mapping = {}
    for p in repo.glob("*/agents/*.md"):
        mapping.setdefault(p.stem, set()).add(p.parent.parent.name)
    return mapping


def verify(repo: Path, plugins: list) -> list:
    """Returns the violation messages in the `*-lead.md` of the given plugins."""
    mapping = agent_map(repo)
    leads = [p for pl in plugins for p in sorted((repo / pl / "agents").glob("*-lead.md"))]
    if not leads:
        return ["nenhum */agents/*-lead.md encontrado — o detector quebrou, não o repo"]
    if not mapping:
        return ["nenhum nome de agente encontrado em */agents/*.md — o detector "
                "quebrou, não o repo"]

    known_plugins = {d for names in mapping.values() for d in names}
    errors = []
    for lead in leads:
        rel = lead.relative_to(repo)
        owner = lead.parent.parent.name  # lead's plugin: <owner>/agents/<lead>.md
        for n, line in enumerate(lead.read_text(encoding="utf-8").splitlines(), 1):
            for m in TOKEN.finditer(line):
                tok = m.group(1)
                if ":" in tok:
                    plugin, name = tok.split(":", 1)
                    # it is only an agent reference if the plugin exists or the name is an
                    # agent's; otherwise it is something else (e.g.: `file:line`)
                    if plugin not in known_plugins and name not in mapping:
                        continue
                    if not (repo / plugin / "agents" / f"{name}.md").is_file():
                        errors.append(f"{rel}:{n}: `{tok}` aponta para "
                                     f"{plugin}/agents/{name}.md, que não existe")
                    elif plugin not in (owner, "common"):
                        # exists, but in another plugin: the lead only delegates to itself
                        # (same plugin) or to `common`
                        if owner in mapping.get(name, ()):
                            correct = f"`{owner}:{name}`"
                        elif "common" in mapping.get(name, ()):
                            correct = f"`common:{name}`"
                        else:
                            correct = None
                        msg = (f"{rel}:{n}: `{tok}` em lead do {owner}: plugin errado; ")
                        msg += (f"o dono aqui é {correct}" if correct else
                                f"`{name}` não existe em {owner} nem em common")
                        errors.append(msg)
                elif tok in mapping:
                    owners = sorted(mapping[tok])
                    if len(owners) == 1:
                        errors.append(f"{rel}:{n}: `{tok}` sem prefixo; use "
                                     f"`{owners[0]}:{tok}`")
                    else:
                        options = ", ".join(f"`{d}:{tok}`" for d in owners)
                        errors.append(f"{rel}:{n}: `{tok}` sem prefixo e existe em "
                                     f"vários plugins ({options}); o lead deve "
                                     f"escolher o dono")
            if DELEGATION_VERB.search(line):
                without_backticks = re.sub(r"`[^`]*`", " ", line)
                for m in re.finditer(r"(?<![:\w-])([a-z][a-z0-9-]*)(?![:\w-])",
                                     without_backticks):
                    if m.group(1) in mapping and not line.startswith("description:"):
                        errors.append(f"{rel}:{n}: nome curto em prosa de delegação "
                                     f"(`{m.group(1)}`); use `<plugin>:<nome>`")
            # frontmatter `description:` — text the orchestrator reads when choosing
            if re.match(r"description:", line):
                m = re.search(r"Delegates to (.*)", line)
                if m:
                    for word in re.findall(r"(?<![:\w-])([a-z][a-z0-9-]*)(?![:\w-])",
                                              m.group(1)):
                        if word in mapping:
                            errors.append(f"{rel}:{n}: description cita `{word}` "
                                         f"sem prefixo "
                                         f"({', '.join(sorted(mapping[word]))})")
    return errors


def selftest() -> list:
    """Proves the verifier is able to turn red (and to turn green)."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        ag = t / "x" / "agents"
        ag.mkdir(parents=True)
        (ag / "foo.md").write_text("---\nname: foo\n---\n", encoding="utf-8")
        lead = ag / "y-lead.md"

        lead.write_text("---\nname: y-lead\n---\nDelegue a `foo`.\n", encoding="utf-8")
        if not any("y-lead.md:4" in e and "x:foo" in e for e in verify(t, ["x"])):
            failures.append("autoteste: nome curto `foo` não foi detectado")

        lead.write_text("---\nname: y-lead\n---\nDelegue a `x:foo`.\n", encoding="utf-8")
        if verify(t, ["x"]):
            failures.append("autoteste: `x:foo` válido foi reprovado")

        lead.write_text("---\nname: y-lead\n---\nDelegue a `x:fo`.\n", encoding="utf-8")
        if not verify(t, ["x"]):
            failures.append("autoteste: `x:fo` (typo) não foi detectado")

        # wrong plugin: `z` also has `foo`, but the lead is from `x`
        zag = t / "z" / "agents"
        zag.mkdir(parents=True)
        (zag / "foo.md").write_text("---\nname: foo\n---\n", encoding="utf-8")
        lead.write_text("---\nname: y-lead\n---\nDelegue a `z:foo`.\n", encoding="utf-8")
        if not any("plugin errado" in e and "x:foo" in e for e in verify(t, ["x"])):
            failures.append("autoteste: `z:foo` em lead de `x` não foi detectado")

        cag = t / "common" / "agents"
        cag.mkdir(parents=True)
        (cag / "bar.md").write_text("---\nname: bar\n---\n", encoding="utf-8")
        lead.write_text("---\nname: y-lead\n---\n`common:bar` e `file:line`.\n",
                        encoding="utf-8")
        if verify(t, ["x"]):
            failures.append("autoteste: `common:bar` / `file:line` foram reprovados")

        lead.write_text("---\nname: y-lead\n---\nDelegate to foo now.\n", encoding="utf-8")
        if not any("prosa de delegação" in e for e in verify(t, ["x"])):
            failures.append("autoteste: nome curto em prosa de delegação não detectado")

        lead.write_text("---\nname: y-lead\n---\nfoo reads TASK.md.\n", encoding="utf-8")
        if verify(t, ["x"]):
            failures.append("autoteste: referência `foo reads TASK.md` foi reprovada")

        lead.write_text("---\ndescription: Delegates to foo, bar\n---\n", encoding="utf-8")
        if not verify(t, ["x"]):
            failures.append("autoteste: nome curto na description não foi detectado")
    return failures


def main():
    failures = selftest()
    print("ok   autoteste" if not failures else "FAIL autoteste")

    errors = verify(REPO, PLUGINS_COVERED)
    leads = [p for pl in PLUGINS_COVERED for p in (REPO / pl / "agents").glob("*-lead.md")]
    for e in errors:
        print("FAIL", e, file=sys.stderr)
    if not errors:
        print(f"ok   {len(leads)} leads de {', '.join(PLUGINS_COVERED)}: workers todos "
              "com prefixo do plugin dono")

    all_items = failures + errors
    for f in failures:
        print("FAIL", f, file=sys.stderr)
    if all_items:
        print(f"\n{len(all_items)} falha(s). Nos leads, chame o worker como "
              "`<plugin>:<nome>` (ex.: `build-hex:epic-author`).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
