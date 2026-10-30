#!/usr/bin/env python3
"""The marketing topology exists, is registered and the path-lock works.

No dependencies — run with `python3 tests/test_marketing_topology.py`.
Exits non-zero on the first batch of failures.

Covers behavior, not just existence:

  - `plugin.json` and the entry in `marketplace.json` parse and point
    to the right directory;
  - every agent has valid frontmatter; the lead has `Task` in its tools, the
    workers/gates do not;
  - the GENERATED path-lock (`marketing/hooks/path-lock.py`) allows an agent of the
    topology to write `docs/marketing/x/pecas/a.md` and denies the same write
    outside the tree, e.g. `common/hooks/x.py`.

Mirrors the style of `tests/test_path_lock_out_of_root.py` (invokes the hook via
subprocess with a JSON payload on stdin) and `tests/test_commands_catalog.py`
(the plugin name comes from the manifest, not from the folder).
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO / "marketing"

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}  {detail}")


# ── plugin.json + marketplace entry ─────────────────────────────────────────

def test_plugin_json():
    manifest = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
    check("marketing/.claude-plugin/plugin.json existe", manifest.is_file())
    if not manifest.is_file():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    check("plugin.json: name == 'marketing'", data.get("name") == "marketing")
    check("plugin.json: description menciona os 5 agentes",
          all(a in data.get("description", "") for a in
              ("content-lead", "content-strategist", "copywriter",
               "brand-style-critic", "fact-checker")),
          data.get("description", "")[:120])
    hooks = data.get("hooks", {}).get("PreToolUse", [])
    matchers = {h.get("matcher") for h in hooks}
    check("plugin.json: hook de Edit/Write/MultiEdit/NotebookEdit declarado",
          "Edit|Write|MultiEdit|NotebookEdit" in matchers)
    check("plugin.json: hook de Bash declarado", "Bash" in matchers)


def test_marketplace_entry():
    mp = REPO / ".claude-plugin" / "marketplace.json"
    check("marketplace.json existe e faz parse", mp.is_file())
    if not mp.is_file():
        return
    data = json.loads(mp.read_text(encoding="utf-8"))
    entries = [p for p in data.get("plugins", []) if p.get("name") == "marketing"]
    check("marketplace.json tem exatamente uma entrada 'marketing'",
          len(entries) == 1, f"achei {len(entries)}")
    if len(entries) == 1:
        check("marketplace.json: source aponta para ./marketing",
              entries[0].get("source") == "./marketing",
              entries[0].get("source"))


# ── agents: frontmatter and tools ───────────────────────────────────────────

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

AGENTS = {
    "content-lead":          {"lead": True},
    "content-strategist":    {"lead": False},
    "copywriter":            {"lead": False},
    "brand-style-critic":    {"lead": False},
    "fact-checker":          {"lead": False},
}


def frontmatter_of(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def test_agents_frontmatter():
    for name, meta in AGENTS.items():
        file = PLUGIN_DIR / "agents" / f"{name}.md"
        check(f"{name}.md existe", file.is_file())
        if not file.is_file():
            continue
        fm = frontmatter_of(file)
        check(f"{name}: frontmatter declara name == {name!r}",
              fm.get("name") == name, fm.get("name"))
        check(f"{name}: frontmatter declara description",
              bool(fm.get("description")))
        check(f"{name}: frontmatter declara tools",
              bool(fm.get("tools")))
        tools = fm.get("tools", "")
        has_task = "Task" in [t.strip() for t in tools.split(",")]
        if meta["lead"]:
            check(f"{name} (lead): tools inclui Task", has_task, tools)
        else:
            check(f"{name} (worker/gate): tools NÃO inclui Task",
                  not has_task, tools)
            check(f"{name}: descrição diz que é worker sem delegar",
                  "never delegates" in file.read_text(encoding="utf-8"))


def test_content_lead_never_produces():
    """The lead delegates; the only write allowed is its own expertise."""
    file = PLUGIN_DIR / "agents" / "content-lead.md"
    check("content-lead.md existe", file.is_file())
    if not file.is_file():
        return
    text = file.read_text(encoding="utf-8")
    check("content-lead: Writes declara 'nothing except own expertise'",
          "nothing except own expertise" in text)


# ── path-lock: behavior, not just presence ──────────────────────────────────

PATH_LOCK = PLUGIN_DIR / "hooks" / "path-lock.py"


def run_pathlock(agent_type, file_path, cwd):
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(file_path)},
        "agent_type": agent_type,
        "cwd": str(cwd),
    }
    p = subprocess.run(
        [sys.executable, str(PATH_LOCK)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=30,
    )
    return p.returncode, p.stderr


def test_pathlock_exists_and_is_valid_python():
    check("marketing/hooks/path-lock.py existe", PATH_LOCK.is_file())
    check("marketing/hooks/bash-path-lock.py existe",
          (PLUGIN_DIR / "hooks" / "bash-path-lock.py").is_file())
    if not PATH_LOCK.is_file():
        return
    compiled = subprocess.run(
        [sys.executable, "-m", "py_compile", str(PATH_LOCK)],
        capture_output=True, text=True,
    )
    check("marketing/hooks/path-lock.py compila", compiled.returncode == 0,
          compiled.stderr)


def test_pathlock_allows_piece_inside_the_lane():
    if not PATH_LOCK.is_file():
        check("path-lock permite peça dentro da pista", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:copywriter", proj / "docs/marketing/x/pecas/a.md", proj)
    check("copywriter pode escrever docs/marketing/x/pecas/a.md",
          rc == 0, err)


def test_pathlock_denies_outside_the_tree():
    if not PATH_LOCK.is_file():
        check("path-lock nega escrita fora da árvore", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:copywriter", proj / "common/hooks/x.py", proj)
    check("copywriter NÃO pode escrever common/hooks/x.py", rc == 2, err)


def test_pathlock_content_strategist_is_the_only_owner_of_the_brief():
    if not PATH_LOCK.is_file():
        check("só content-strategist escreve BRIEF.md", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc_ok, err_ok = run_pathlock(
        "marketing:content-strategist", proj / "docs/marketing/x/BRIEF.md", proj)
    check("content-strategist pode escrever BRIEF.md", rc_ok == 0, err_ok)

    rc_bloq, err_block = run_pathlock(
        "marketing:copywriter", proj / "docs/marketing/x/BRIEF.md", proj)
    check("copywriter NÃO pode escrever BRIEF.md (só lê)", rc_bloq == 2, err_block)


def test_pathlock_gates_only_write_reviews():
    if not PATH_LOCK.is_file():
        check("gates só escrevem em reviews/", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    for agent in ("brand-style-critic", "fact-checker"):
        rc_ok, err_ok = run_pathlock(
            f"marketing:{agent}", proj / "docs/marketing/reviews/x-brand.md", proj)
        check(f"{agent} pode escrever docs/marketing/reviews/**", rc_ok == 0, err_ok)

        rc_bloq, err_block = run_pathlock(
            f"marketing:{agent}", proj / "docs/marketing/x/pecas/a.md", proj)
        check(f"{agent} NÃO pode escrever peças (é read-only sobre elas)",
              rc_bloq == 2, err_block)


def test_pathlock_lead_produces_nothing():
    if not PATH_LOCK.is_file():
        check("content-lead não escreve artefatos", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:content-lead", proj / "docs/marketing/x/BRIEF.md", proj)
    check("content-lead NÃO pode escrever BRIEF.md (delega, não produz)",
          rc == 2, err)


def test_pathlock_own_expertise_always_allowed():
    if not PATH_LOCK.is_file():
        check("expertise própria é sempre liberada", False, "hook ausente")
        return
    proj = Path(tempfile.mkdtemp(prefix="mkt-proj-"))
    rc, err = run_pathlock(
        "marketing:copywriter",
        proj / ".claude/expertise/copywriter-mental-model.yaml", proj)
    check("copywriter pode sempre escrever a própria expertise", rc == 0, err)


# ── command ──────────────────────────────────────────────────────────────

def test_command_brief_write_review():
    cmd = PLUGIN_DIR / "commands" / "brief-write-review.md"
    check("marketing/commands/brief-write-review.md existe", cmd.is_file())
    if not cmd.is_file():
        return
    text = cmd.read_text(encoding="utf-8")
    fm = frontmatter_of(cmd)
    check("comando declara interaction: routine ou conversational",
          fm.get("interaction") in ("routine", "conversational"),
          fm.get("interaction"))
    check("comando declara argument-hint", bool(fm.get("argument-hint")))
    check("comando cita content-lead", "content-lead" in text)
    check("comando cita o teto de 2 rodadas de revise",
          "2" in text and "REVISE" in text)


def test_catalog_cites_the_command():
    catalog = (REPO / "docs" / "commands.md").read_text(encoding="utf-8")
    check("docs/commands.md tem a linha do /marketing:brief-write-review",
          bool(re.search(r"^\|\s*`/marketing:brief-write-review`\s*\|",
                          catalog, re.M)))


def main():
    test_plugin_json()
    test_marketplace_entry()
    test_agents_frontmatter()
    test_content_lead_never_produces()
    test_pathlock_exists_and_is_valid_python()
    test_pathlock_allows_piece_inside_the_lane()
    test_pathlock_denies_outside_the_tree()
    test_pathlock_content_strategist_is_the_only_owner_of_the_brief()
    test_pathlock_gates_only_write_reviews()
    test_pathlock_lead_produces_nothing()
    test_pathlock_own_expertise_always_allowed()
    test_command_brief_write_review()
    test_catalog_cites_the_command()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
