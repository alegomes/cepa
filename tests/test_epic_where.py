#!/usr/bin/env python3
"""The Epic's "where are we", derived: `cepa-plan epics`, the session hook and /common:whereami.

Run with `python3 tests/test_epic_where.py`. Decision (queue item
`onde-estamos-do-epic`): the summary is not a block written into the Epic; it is
derived from the ladder plus the single-track queues linked to each cycle, so it
cannot drift.

What these tests charge:

  - cycles are `fechado` / `em-andamento` / `sem-fila`, with the three linking
    rules (source + "ciclo N", name `<slug>-c<N>`, prefix declared in the header);
  - the open questions of the Epic and the open owner questions of the queues
    (`owner_question`, `human_pending`) show up; `--brief` is one short line;
  - no `docs/epics` -> silence, rc 0 (and `{"epics": []}` with --json);
  - the hook adds the `[epic]` line on the session's first turn only, never in a
    `cepa-until` run;
  - the docs (whereami, epic) mention the command.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml  # noqa: F401
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
HOOK = REPO / "common" / "hooks" / "session-mode.py"
WHEREAMI = REPO / "common" / "commands" / "whereami.md"
EPIC_CMD = REPO / "common" / "commands" / "epic.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


class TmpRepo:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        self.path.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=self.path, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                       cwd=self.path, check=True, env=GIT_ENV)
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def epic(self, name, text):
        d = self.path / "docs" / "epics"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(text, encoding="utf-8")

    def queue(self, name, source, items):
        d = self.path / ".claude" / "queues" / name
        d.mkdir(parents=True, exist_ok=True)
        plan = {"schema_version": 2, "mode": "single-track", "queue": name,
                "source": source, "items": items}
        (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                      encoding="utf-8")


def item(ident, status, **extra):
    return {"id": ident, "title": f"peça {ident}", "why": "x", "status": status,
            "blocked_by": [], "human_pending": None, **extra}


def epics(repo_path, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN), "epics", "--repo",
                           str(repo_path), *args],
                          capture_output=True, text=True, timeout=60)


def run_hook(cwd, env=None, **payload):
    e = {k: v for k, v in os.environ.items() if k != "CEPA_UNTIL_RUN"}
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"cwd": str(cwd), **payload}),
        capture_output=True, text=True, timeout=30, env=e)


def ctx(proc):
    if not proc.stdout.strip():
        return ""
    return json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


def write_log(repo, entries):
    out, day = ["# Session log", ""], None
    for d, h, t in entries:
        if d != day:
            out += [f"## {d}", ""]
            day = d
        out += [f"### {h} UTC", "", t, ""]
    (repo.path / ".claude").mkdir(exist_ok=True)
    (repo.path / ".claude" / "session-log.md").write_text("\n".join(out),
                                                          encoding="utf-8")


EPIC_X = """# Epic: Exemplo X

**Status:** ready · **Aberto em:** 2026-10-01

## Value ladder

| Cycle | Script | Effect on screen | Effect in backend | What it crosses |
|---|---|---|---|---|
| 1. A | o dono vê A | tela A | api A | Peça A. |
| 2. B | o dono vê B | tela B | api B | Peça B. |
| 3. C | o dono vê C | tela C | api C | Peça C. |

## Perguntas em aberto

- [ ] Quantos contratos existem em mãos?
- [x] Já respondida.
- [ ] Quem escreve o roteiro do ciclo 1?
"""


def test_cycles_and_rules():
    with TmpRepo() as r:
        r.epic("x", EPIC_X)
        r.queue("x-c1", "outra coisa", [item("A-1", "done"), item("A-2", "done")])
        r.queue("fila-b", "docs/epics/x.md, ciclo 2 (3 peças)", [
            item("B-1", "done"),
            item("B-2", "blocked",
                 owner_question="Fecho ou devolvo? Recomendo devolver"),
            item("B-3", "pending", human_pending="aprovar o PR"),
        ])
        p = epics(r.path, "--json")
        check("json: rc 0", p.returncode == 0, p.stderr)
        data = json.loads(p.stdout)
        e = data["epics"][0]
        check("json: chaves do Epic", set(e) == {
            "name", "path", "queue_prefix", "title", "status", "cycles",
            "open_questions",
            "missing"}, str(set(e)))
        check("json: nome, caminho, título, status",
              (e["name"], e["path"], e["title"], e["status"]) ==
              ("x", "docs/epics/x.md", "Exemplo X", "ready"), str(e))
        cy = {c["number"]: c for c in e["cycles"]}
        check("json: 3 ciclos com rótulo", len(cy) == 3 and cy[1]["label"] == "A",
              str(e["cycles"]))
        check("ciclo 1 fechado pela regra (b)",
              cy[1]["state"] == "fechado"
              and cy[1]["queues"][0]["queue"] == "x-c1", str(cy[1]))
        check("ciclo 2 em andamento pela regra (a)",
              cy[2]["state"] == "em-andamento"
              and cy[2]["queues"][0]["queue"] == "fila-b", str(cy[2]))
        q2 = cy[2]["queues"][0]
        check("ciclo 2: contagens",
              q2["counts"]["done"] == 1 and q2["counts"]["blocked"] == 1
              and q2["counts"]["pending"] == 1, str(q2["counts"]))
        check("ciclo 2: duas entradas abertas",
              len(q2["open"]) == 2
              and {o["id"] for o in q2["open"]} == {"B-2", "B-3"}, str(q2["open"]))
        blocked = next(o for o in q2["open"] if o["id"] == "B-2")
        check("ciclo 2: pergunta do dono preservada",
              blocked["question"] == "Fecho ou devolvo? Recomendo devolver"
              and blocked["status"] == "blocked", str(blocked))
        check("ciclo 3 sem fila",
              cy[3]["state"] == "sem-fila" and cy[3]["queues"] == [], str(cy[3]))
        check("perguntas em aberto: só as 2 sem marca",
              e["open_questions"] == ["Quantos contratos existem em mãos?",
                                      "Quem escreve o roteiro do ciclo 1?"],
              str(e["open_questions"]))
        check("missing cita o ciclo sem fila",
              any("ciclo 3" in m and "sem fila" in m for m in e["missing"]),
              str(e["missing"]))

        t = epics(r.path).stdout
        check("texto: fechado / em andamento / sem fila",
              "fechado" in t and "em andamento" in t and "sem fila" in t, t)
        check("texto: pergunta da fila e do Epic",
              "Fecho ou devolvo?" in t and "Quantos contratos existem" in t, t)
        check("texto: sugestão usa <slug>-c3 sem prefixo no cabeçalho",
              "/common:queue x-c3 --from-epic" in t, t)
        check("texto: próximo ciclo sem fila com o comando",
              "/common:queue x-c3 --from-epic docs/epics/x.md --cycle 3" in t, t)

        check("json: queue_prefix nulo sem prefixo no cabeçalho",
              e["queue_prefix"] is None, str(e.get("queue_prefix")))

        b = epics(r.path, "--brief").stdout
        check("brief: uma linha [epic] <= 220",
              len(b.strip().splitlines()) == 1 and b.startswith("[epic]")
              and len(b.strip()) <= 220, repr(b))
        check("brief: aponta o whereami e a pergunta pendente na fila",
              "/common:whereami" in b and "pendente" in b, b)


def test_rule_c():
    with TmpRepo() as r:
        r.epic("espiral", "# Epic: E\n\n**Status:** rascunho\n"
               "**Construção:** `.claude/programs/foo-bar-c<N>/plan.yaml`\n\n"
               "## Escada de valor\n\n"
               "| Ciclo | Roteiro | O que atravessa |\n|---|---|---|\n"
               "| 1. Um | vê | A; B |\n| 2. Dois | vê | C |\n")
        r.queue("foo-bar-c1", "docs/spec/foo.md", [item("1", "done")])
        e = json.loads(epics(r.path, "--json").stdout)["epics"][0]
        c1, c2 = e["cycles"]
        check("regra (c): ciclo 1 ligado a foo-bar-c1",
              c1["state"] == "fechado" and c1["queues"][0]["queue"] == "foo-bar-c1",
              str(c1))
        check("regra (c): ciclo 2 sem fila", c2["state"] == "sem-fila", str(c2))
        check("json: queue_prefix = prefixo do cabeçalho",
              e["queue_prefix"] == "foo-bar", str(e.get("queue_prefix")))
        t = epics(r.path).stdout
        check("sugestão usa o prefixo do cabeçalho",
              "/common:queue foo-bar-c2 --from-epic" in t, t)


def test_unreadable_and_empty_queue():
    with TmpRepo() as r:
        r.epic("x", EPIC_X)
        r.queue("x-c1", "x", [item("A-1", "done")])
        r.queue("x-c2", "x", [])
        (r.path / ".claude" / "queues" / "x-c1" / "queue.yaml").write_text(
            "items: [unclosed\n  - : :\n", encoding="utf-8")
        p = epics(r.path, "--json")
        e = json.loads(p.stdout)["epics"][0]
        cy = {c["number"]: c for c in e["cycles"]}
        check("fila corrompida: rc 0", p.returncode == 0, p.stderr)
        check("fila corrompida: stderr cita o arquivo e o aviso",
              "x-c1" in p.stderr and "queue.yaml" in p.stderr
              and "sem fila" in p.stderr, p.stderr)
        check("fila corrompida: ciclo 1 sem-fila", cy[1]["state"] == "sem-fila",
              str(cy[1]))
        q2 = cy[2]["queues"][0]
        check("fila vazia: em-andamento com 0/0",
              cy[2]["state"] == "em-andamento"
              and sum(q2["counts"].values()) == 0, str(cy[2]))
        check("fila vazia: texto mostra 0/0 done",
              "0/0 done" in epics(r.path).stdout, epics(r.path).stdout)


def test_brief_long():
    rows = "\n".join(f"| {n}. Rótulo muito comprido do ciclo número {n} "
                     f"para estourar | vê | C{n}. |" for n in range(1, 9))
    with TmpRepo() as r:
        r.epic("longo", "# Epic: L\n\n**Status:** ready\n\n## Value ladder\n\n"
               "| Cycle | Script | What it crosses |\n|---|---|---|\n" + rows
               + "\n\n## Perguntas\n\n" + "\n".join(
                   f"- [ ] pergunta {i}?" for i in range(5)) + "\n")
        for n in (1, 2, 3):
            r.queue(f"longo-c{n}", "x", [item("a", "done"), item("b", "pending")])
        b = epics(r.path, "--brief").stdout
        lines = b.strip().splitlines()
        tail = " Detalhe: /common:whereami."
        check("brief longo: uma linha [epic]",
              len(lines) == 1 and b.startswith("[epic]"), repr(b))
        check("brief longo: <= 200 e mantém o Detalhe",
              len(lines[0]) <= 200 and lines[0].endswith(tail), str(len(lines[0])))
        check("brief longo: rótulos largados ou corte com …",
              "Rótulo muito comprido" not in lines[0] or "…" in lines[0],
              lines[0])


def test_no_epics():
    with TmpRepo() as r:
        p = epics(r.path)
        check("sem docs/epics: rc 0 e vazio", p.returncode == 0 and p.stdout == "",
              repr(p.stdout) + p.stderr)
        p = epics(r.path, "--brief")
        check("sem docs/epics --brief: vazio", p.returncode == 0 and p.stdout == "")
        p = epics(r.path, "--json")
        check("sem docs/epics --json: epics vazio",
              p.returncode == 0 and json.loads(p.stdout) == {"epics": []}, p.stdout)
        (r.path / "docs" / "epics").mkdir(parents=True)
        check("docs/epics sem .md: vazio", epics(r.path).stdout == "")


def test_hook():
    today = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y-%m-%d")
    with TmpRepo() as r:
        r.epic("x", EPIC_X)
        p = run_hook(r.path, session_id="s1", prompt="oi")
        check("hook 1o turno sem log: tem [epic]", "[epic]" in ctx(p),
              ctx(p) + p.stderr)
        write_log(r, [(today, "10:00:00", "primeiro"),
                      (today, "10:05:00", "segundo")])
        p = run_hook(r.path, session_id="s1", prompt="terceiro")
        check("hook com 2 prompts antes: sem [epic]", "[epic]" not in ctx(p),
              ctx(p))
        write_log(r, [])
        p = run_hook(r.path, env={"CEPA_UNTIL_RUN": "1"}, session_id="s1",
                     prompt="oi")
        check("hook em run do cepa-until: sem [epic]", "[epic]" not in ctx(p),
              ctx(p))
    with TmpRepo() as r:
        p = run_hook(r.path, session_id="s1", prompt="oi")
        check("hook sem docs/epics: silêncio", ctx(p) == "", ctx(p))


def test_hook_fail_silent():
    """`cepa-plan epics` failing (rc 3, or missing) must not break the hook."""
    with TmpRepo() as r, tempfile.TemporaryDirectory() as plug:
        r.epic("x", EPIC_X)
        r.queue("x-c1", "x", [item("A-1", "done")])
        p = run_hook(r.path, session_id="s1", prompt="oi")
        check("controle: o hook real imprime [epic]", "[epic]" in ctx(p),
              ctx(p) + p.stderr)
        hooks = Path(plug) / "hooks"
        shutil.copytree(HOOK.parent, hooks,
                        ignore=shutil.ignore_patterns("__pycache__"))
        (Path(plug) / "bin").mkdir()
        fake = Path(plug) / "bin" / "cepa-plan"
        for variant in ("exit 3", "missing"):
            if variant == "exit 3":
                fake.write_text("import sys\nsys.exit(3)\n")
            elif fake.exists():
                fake.unlink()
            p = subprocess.run(
                [sys.executable, str(hooks / "session-mode.py")],
                input=json.dumps({"cwd": str(r.path), "session_id": "s1",
                                  "prompt": "oi"}),
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items()
                     if k != "CEPA_UNTIL_RUN"})
            check(f"fail-silent ({variant}): rc 0", p.returncode == 0,
                  p.stderr)
            check(f"fail-silent ({variant}): sem [epic]",
                  "[epic]" not in ctx(p), ctx(p))
            check(f"fail-silent ({variant}): sem traceback",
                  "Traceback" not in p.stderr, p.stderr)


def test_whereami_step0_runs():
    txt = WHEREAMI.read_text(encoding="utf-8")
    m = re.search(r'^\s*(python3 "\$\{CLAUDE_PLUGIN_ROOT\}/bin/cepa-plan" '
                  r'epics --repo \.)\s*$', txt, re.M)
    check("whereami.md: linha do passo 0 extraível", m is not None)
    if not m:
        return
    with TmpRepo() as r:
        r.epic("x", EPIC_X)
        r.queue("x-c1", "x", [item("A-1", "done")])
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO / "common")}
        env.pop("CEPA_UNTIL_RUN", None)
        p = subprocess.run(["bash", "-c", m.group(1)], cwd=r.path, env=env,
                           capture_output=True, text=True, timeout=60)
        check("passo 0 do whereami: rc 0", p.returncode == 0, p.stderr)
        check("passo 0 do whereami: linhas de ciclo",
              "ciclo 1 A: fechado" in p.stdout and "ciclo 3 C: sem fila"
              in p.stdout, p.stdout + p.stderr)


def test_docs():
    w = WHEREAMI.read_text(encoding="utf-8")
    check("whereami.md traz o comando do passo 0",
          'cepa-plan" epics --repo .' in w)
    check("whereami.md mantém a linha do cepa-intent state",
          'cepa-intent" state' in w)
    check("epic.md menciona cepa-plan epics",
          "cepa-plan epics" in EPIC_CMD.read_text(encoding="utf-8"))


def test_real_repo():
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--git-common-dir"],
                       capture_output=True, text=True)
    common = Path(r.stdout.strip())
    if not common.is_absolute():
        common = (REPO / common).resolve()
    main = common.parent if common.name == ".git" else common
    if not (main / ".claude" / "queues" / "cepa-espiral-c1").exists() \
            and not (main / ".claude" / "programs" / "cepa-espiral-c1").exists():
        print("  skip fila cepa-espiral-c1 ausente no clone principal")
        return
    p = epics(REPO, "--json")
    data = json.loads(p.stdout) if p.stdout.strip() else {"epics": []}
    e = next((x for x in data["epics"] if x["name"] == "cepa-em-espiral"), None)
    check("real: Epic cepa-em-espiral com 4 ciclos",
          e is not None and len(e["cycles"]) == 4, p.stdout[:300] + p.stderr)
    if e:
        qs = [x["queue"] for x in e["cycles"][0]["queues"]]
        check("real: ciclo 1 ligado a cepa-espiral-c1 (regra c)",
              qs == ["cepa-espiral-c1"], str(qs))


for fn in (test_cycles_and_rules, test_rule_c,
           test_unreadable_and_empty_queue, test_brief_long, test_no_epics, test_hook,
           test_hook_fail_silent, test_whereami_step0_runs,
           test_docs, test_real_repo):
    print(fn.__name__)
    fn()

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("\ntudo certo")
