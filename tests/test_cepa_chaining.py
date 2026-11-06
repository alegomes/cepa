#!/usr/bin/env python3
"""CS-3 (cepa-espiral-c1): the `cepa` launcher opens the next session when the
previous one left the next step recorded.

The session that leaves writes `<main-root>/.claude/sessions/<session_id>.next.json`
with `{"repo", "mode", "brief"}`. `cepa` no longer does `exec` of claude: when
it exits, the launcher reads the file, deletes it, enters `repo` and opens the next
session with `--mode <mode>` and the brief as the initial prompt.

The `claude` here is a stub that records arguments, cwd and the recorded mode. On the
first call it plays the role of the whole session: runs the REAL hook
`session-registry.py` at SessionStart (which links the launcher's CEPA_LAUNCH_ID to the
session_id), writes the `.next.json` as the wrap-up would write it, runs the
SessionEnd and exits.

Contracts guarded here:
  - with the file: the stub runs a second time, cwd = repo, recorded mode =
    discovery, last argument = the brief verbatim; the file vanishes;
  - with `comando` in the file, the initial prompt is `<comando>\\n\\n<brief>` (command
    on line 1); absent, blank or non-string `comando`: the brief alone, no warning;
  - without the file: the stub runs only once and its exit code is that of cepa;
  - CEPA_ENCADEAR=off: only once, the file stays;
  - invalid file (missing repo): only once, the file stays, and cepa says so;
  - with `intencao` in the file, the next session is born with it (purpose,
    goal and plan written for it, step 1, via cepa-intencao); without `intencao`,
    it is born without intent, because the brief talks about the session that left; invalid
    `intencao` warns and the session opens without it; previous intent goes to the
    history; failure to write warns and the session opens; without `--proposito`, nothing;
  - the `.next.json` is not read as a session by the registry (`read_entries`);
  - without the SessionEnd, the record of the session that left does not make the next one
    isolate itself in a worktree.

No third-party deps — run with `python3 tests/test_cepa_chaining.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

for _k in ("CEPA_PROMPT", "CEPA_PROMPT_MODO", "CEPA_ENCADEAR", "CEPA_LAUNCH_ID",
           "CLAUDE_WT_CLAIM", "CEPA_MODO", "CEPA_MODO_DEFAULT"):
    os.environ.pop(_k, None)

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"
REGISTRY = REPO / "common" / "hooks" / "session-registry.py"
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _wtlib as L  # noqa: E402
import _modes  # noqa: E402

BRIEF = 'Abra o /common:epic contratos-e-regras.\nLeia o handoff "anterior" antes.'

# The stub: records each call as a JSON line in $STUB_LOG. Only on the
# first call ($STUB_STATE does not exist yet) does it act as the session that
# ends and leaves the next step.
STUB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
mode = ""
p = Path(".claude/session-mode")
if p.exists():
    mode = p.read_text()
intent = ""
pi = Path(".claude/session-intent")
if pi.is_file():
    intent = pi.read_text()
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd(), "mode": mode, "intent": intent,
                        "launch_id": os.environ.get("CEPA_LAUNCH_ID", "")}) + "\n")
state = Path(os.environ["STUB_STATE"])
if state.exists():
    sys.exit(0)
state.write_text("1")
sid = os.environ.get("STUB_SID", "sess-1")
def hook(event):
    subprocess.run([sys.executable, os.environ["STUB_REGISTRY"]],
                   input=json.dumps({"session_id": sid, "cwd": os.getcwd(),
                                     "hook_event_name": event}),
                   text=True, capture_output=True)
hook("SessionStart")
nxt = os.environ.get("STUB_NEXT")
if nxt:
    sdir = Path(os.environ["STUB_SESSIONS"])
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / f"{sid}.next.json").write_text(nxt)
# Um /clear abre outro session_id no mesmo processo: o segundo também deixa
# próximo passo, e é o dele que vale.
nxt2 = os.environ.get("STUB_NEXT2")
if nxt2:
    sid = "sess-2"
    hook("SessionStart")
    (Path(os.environ["STUB_SESSIONS"]) / f"{sid}.next.json").write_text(nxt2)
if os.environ.get("STUB_SKIP_END") != "1":
    hook("SessionEnd")
# O wrap-up mescla e remove a worktree de dentro da sessão: o claude sai com o
# cwd apontando para uma pasta que já não existe.
if os.environ.get("STUB_RMCWD") == "1":
    import shutil
    shutil.rmtree(os.getcwd())
sys.exit(int(os.environ.get("STUB_RC", "0")))
'''

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def git_repo(path: Path):
    path.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "init", "-q", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"],
                   cwd=path, check=True, env=env)


class World:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.a = t / "repo-a"
        self.b = t / "repo-b"
        git_repo(self.a)
        git_repo(self.b)
        self.stub = t / "fakeclaude"
        self.stub.write_text(STUB)
        self.stub.chmod(0o755)
        self.log = t / "stub.log"
        self.state = t / "stub.state"
        self.wt_home = t / "worktrees"
        self.sessions = self.a / ".claude" / "sessions"
        self.telemetry = t / "telemetry"
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def run(self, nxt=None, env=None, args=None):
        e = {**os.environ,
             "CLAUDE_WT_CLAUDE_BIN": str(self.stub),
             "CEPA_PREFLIGHT": "off",
             "CEPA_WORKTREE_HOME": str(self.wt_home),
             "CEPA_TELEMETRY_DIR": str(self.telemetry),
             "STUB_LOG": str(self.log),
             "STUB_STATE": str(self.state),
             "STUB_REGISTRY": str(REGISTRY),
             "STUB_SESSIONS": str(self.sessions)}
        if nxt is not None:
            e["STUB_NEXT"] = nxt if isinstance(nxt, str) else json.dumps(nxt)
        e.update(env or {})
        return subprocess.run([str(CEPA), "--mode", "construction", *(args or [])],
                              cwd=self.a, env=e,
                              capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text().splitlines() if x.strip()]


def same(a, b):
    return Path(a).resolve() == Path(b).resolve()


def t_chains():
    print("com o próximo passo gravado, a sessão seguinte abre sozinha")
    with World() as w:
        r = w.run(nxt={"repo": str(w.b), "mode": "discovery", "brief": BRIEF})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; stderr={r.stderr!r}")
        if len(c) == 2:
            check("a primeira rodou no repo de origem", same(c[0]["cwd"], w.a), c[0]["cwd"])
            check("a segunda rodou com cwd = repo do arquivo", same(c[1]["cwd"], w.b), c[1]["cwd"])
            check("a segunda abriu em modo discovery",
                  "mode: discovery" in c[1]["mode"], repr(c[1]["mode"]))
            check("o brief é o prompt inicial, verbatim", c[1]["args"][-1:] == [BRIEF],
                  repr(c[1]["args"]))
            check("o args do primeiro claude não vazam para o segundo",
                  "construction" not in c[1]["args"], repr(c[1]["args"]))
            check("cada abertura tem o próprio CEPA_LAUNCH_ID",
                  c[0]["launch_id"] and c[1]["launch_id"]
                  and c[0]["launch_id"] != c[1]["launch_id"], repr(c))
            check("a primeira abertura não tem intenção", c[0]["intent"] == "", repr(c[0]["intent"]))
            check("sem `intencao` no arquivo, a segunda nasce sem intenção (o brief não vira propósito)",
                  c[1]["intent"] == "", repr(c[1]["intent"]))
        check("o .next.json foi apagado", not (w.sessions / "sess-1.next.json").exists())
        check("o cepa não diz intenção gravada", "◆ intenção:" not in r.stderr, r.stderr)
        check("sem `intencao`, nenhum aviso de intenção inválida", "intenção inválida" not in r.stderr, r.stderr)
        check("a anotação do launch foi apagada", not list(w.sessions.glob("*.launch")))
        check("o cepa diz que encadeou", "próxima sessão em" in r.stderr, r.stderr)
        check("a sessão seguinte não foi isolada numa worktree",
              not w.wt_home.exists() or not any(w.wt_home.iterdir()))
        check("sai 0", r.returncode == 0, f"rc={r.returncode}")


INTENT = {"purpose": "Grelhar o dono no epic contratos-e-regras",
            "by_when": "cada ciclo com roteiro em tela e em backend",
            "plan": ["abrir o epic", "grelhar ciclo a ciclo"]}
# The same content in the OLD .next.json format (keys in pt-BR).
OLD_INTENT = {"proposito": INTENT["purpose"], "para_quando": INTENT["by_when"],
                   "plano": INTENT["plan"]}


def t_command_first_line():
    print("o comando gravado pelo wrap-up abre o prompt da sessão seguinte")
    cmd = "/common:epic contratos-e-regras"
    with World() as w:
        r = w.run(nxt={"repo": str(w.b), "mode": "discovery", "comando": f"  {cmd} ", "brief": BRIEF})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; stderr={r.stderr!r}")
        if len(c) == 2:
            last = c[1]["args"][-1]
            check("o prompt é comando + linha em branco + brief verbatim", last == cmd + "\n\n" + BRIEF, repr(last))
            check("a primeira linha é exatamente o comando", last.split("\n")[0] == cmd, repr(last))
    for given_name, val in (("só espaços", "   "), ("vazio", ""), ("não string", 42)):
        with World() as w:
            r = w.run(nxt={"repo": str(w.b), "mode": "discovery", "comando": val, "brief": BRIEF})
            c = w.calls()
            check(f"{given_name}: o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; stderr={r.stderr!r}")
            if len(c) == 2:
                check(f"{given_name}: o prompt é só o brief", c[1]["args"][-1:] == [BRIEF], repr(c[1]["args"]))
            check(f"{given_name}: nenhum aviso sobre comando", "comando" not in r.stderr, r.stderr)


def t_chains_with_intent():
    print("com `intencao` no arquivo, a sessão seguinte nasce com ela, não com o brief")
    with World() as w:
        r = w.run(nxt={"repo": str(w.b), "mode": "discovery", "brief": BRIEF, "intent": INTENT})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; stderr={r.stderr!r}")
        if len(c) == 2:
            it = _modes.parse_intent(c[1]["intent"])
            check("o propósito é o da intenção", it.get("purpose") == INTENT["purpose"],
                  repr(it.get("purpose")))
            check("a meta é a da intenção", it.get("by_when") == INTENT["by_when"],
                  repr(it.get("by_when")))
            check("o plano tem os dois passos, em ordem", it.get("plan") == INTENT["plan"],
                  repr(it.get("plan")))
            check("o passo é 1", it.get("step") == 1, repr(it.get("step")))
            check("o brief continua o prompt inicial", c[1]["args"][-1:] == [BRIEF], repr(c[1]["args"]))
            check("as flags da intenção não vazam para o claude",
                  not {"--purpose", "--by-when", "--plan", "--proposito", "--para-quando", "--plano"} & set(c[1]["args"]), repr(c[1]["args"]))
        check("o cepa diz a intenção gravada", "◆ intenção:" in r.stderr, r.stderr)


def t_invalid_intent_opens_without():
    cases = [("meta vazia", {"purpose": "x", "by_when": "", "plan": ["a"]}),
             ("plano vazio", {"purpose": "x", "by_when": "m", "plan": []}),
             ("passo com quebra de linha", {"purpose": "x", "by_when": "m", "plan": ["a\nb"]})]
    for given_name, it in cases:
        print(f"`intencao` inválida ({given_name}): avisa e a sessão seguinte abre sem intenção")
        with World() as w:
            r = w.run(nxt={"repo": str(w.b), "mode": "discovery", "brief": BRIEF, "intent": it})
            c = w.calls()
            check(f"{given_name}: o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; stderr={r.stderr!r}")
            if len(c) == 2:
                check(f"{given_name}: a segunda nasce sem intenção", c[1]["intent"] == "", repr(c[1]["intent"]))
            check(f"{given_name}: o cepa avisa", "intenção inválida" in r.stderr, r.stderr)


def t_previous_intent_goes_to_history():
    print("repo de destino já tinha intenção: a nova a substitui e a antiga vai ao histórico")
    with World() as w:
        old = {"purpose": "antigo", "by_when": "x", "plan": ["a"], "step": 1,
                  "step_since": "2026-01-01T00:00:00Z", "session_id": "", "branch": "master",
                  "opened_at": "2026-01-01T00:00:00Z", "summary": "passo 1/1 · a · antigo",
                  "history": []}
        (w.b / ".claude").mkdir()
        (w.b / ".claude" / "session-intent").write_text(_modes.render_intent(old))
        w.run(nxt={"repo": str(w.b), "mode": "discovery", "brief": BRIEF, "intent": INTENT})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"{len(c)}")
        if len(c) == 2:
            it = _modes.parse_intent(c[1]["intent"])
            check("o propósito agora é o da intenção", it.get("purpose") == INTENT["purpose"],
                  repr(it.get("purpose")))
            hist = it.get("history") or []
            check("o histórico guarda o propósito antigo",
                  any(h.get("purpose") == "antigo" for h in hist), repr(hist))


def t_whole_intent_on_the_command_line():
    print("--by-when=/--plan= valem como a forma com espaço; passo com * fica literal")
    with World() as w:
        (w.a / "LEIAME").write_text("x")
        r = w.run(args=["--purpose=p", "--by-when=meta m", "--plan=*\nsegundo passo"])
        c = w.calls()
        check("o stub rodou uma vez", len(c) == 1, f"{len(c)}; stderr={r.stderr!r}")
        if c:
            it = _modes.parse_intent(c[0]["intent"])
            check("a meta veio do --by-when=", it.get("by_when") == "meta m", repr(it))
            check("o plano veio do --plano=, um passo por linha, * sem virar nome de arquivo",
                  it.get("plan") == ["*", "segundo passo"], repr(it.get("plan")))
            check("as formas com = não vazam para o claude",
                  not any(x.startswith(("--by-when", "--plan")) for x in c[0]["args"]),
                  repr(c[0]["args"]))


def t_purpose_direct_in_the_worktree():
    print("cepa --purpose dentro da worktree isolada: a intenção mora lá, não na raiz")
    with World() as w:
        r = w.run(args=["-s", "fatia", "--purpose", "x y"])
        c = w.calls()
        check("o stub rodou uma vez", len(c) == 1, f"{len(c)}; stderr={r.stderr!r}")
        if c:
            check("rodou numa worktree", Path(c[0]["cwd"]).resolve().is_relative_to(w.wt_home.resolve()),
                  c[0]["cwd"])
            it = _modes.parse_intent(c[0]["intent"])
            check("a intenção na worktree é 'x y'", it.get("purpose") == "x y", repr(it))
            check("--proposito não vaza para o claude", "--purpose" not in c[0]["args"],
                  repr(c[0]["args"]))
        check("a raiz não ganhou intenção", not (w.a / ".claude" / "session-intent").exists())


def t_purpose_in_branch_session():
    print("já numa branch session/* (caminho launch_here): a intenção é gravada ali")
    with World() as w:
        subprocess.run(["git", "checkout", "-q", "-b", "session/ja-isolada"], cwd=w.a, check=True)
        r = w.run(args=["--purpose", "x y"])
        c = w.calls()
        check("o stub rodou uma vez", len(c) == 1, f"{len(c)}; stderr={r.stderr!r}")
        if c:
            check("rodou no próprio repo, sem nova worktree", same(c[0]["cwd"], w.a), c[0]["cwd"])
            it = _modes.parse_intent(c[0]["intent"])
            check("a intenção existe antes do 1o turno, com 'x y'",
                  it.get("purpose") == "x y", repr(it))
            check("--proposito não vaza para o claude", "--purpose" not in c[0]["args"],
                  repr(c[0]["args"]))


def t_purpose_form_with_equals():
    print("--purpose=<texto> vale como --purpose <texto>; sem valor é erro")
    with World() as w:
        r = w.run(args=["--purpose=a b"])
        c = w.calls()
        check("o stub rodou uma vez", len(c) == 1, f"{len(c)}; stderr={r.stderr!r}")
        if c:
            it = _modes.parse_intent(c[0]["intent"])
            check("a intenção é 'a b'", it.get("purpose") == "a b", repr(it))
            check("a forma com = não vaza para o claude",
                  not any(x.startswith("--purpose") for x in c[0]["args"]), repr(c[0]["args"]))
    with World() as w:
        r = w.run(args=["--purpose"])
        check("sem valor: o claude não abre", len(w.calls()) == 0, f"{len(w.calls())}")
        check("sem valor: sai 2 e diz", r.returncode == 2 and "--purpose exige um valor" in r.stderr,
              f"rc={r.returncode} {r.stderr!r}")


def t_without_purpose_without_intent():
    print("cepa sem --purpose não grava intenção")
    with World() as w:
        r = w.run()
        c = w.calls()
        check("o stub rodou uma vez", len(c) == 1, f"{len(c)}")
        check("sem intenção na raiz", not (w.a / ".claude" / "session-intent").exists())
        check("não fala de intenção", "intenção" not in r.stderr, r.stderr)


def t_writer_failure_does_not_prevent():
    print("cepa-intent recusa: a sessão abre mesmo assim e o cepa avisa")
    with World() as w:
        (w.a / ".claude" / "session-intent").mkdir(parents=True)
        r = w.run(args=["--purpose", "x y"])
        check("o stub rodou (sessão abriu)", len(w.calls()) == 1, f"{len(w.calls())}; {r.stderr!r}")
        check("o cepa avisa que não gravou", "não gravei a intenção" in r.stderr, r.stderr)
        check("sai 0", r.returncode == 0, f"rc={r.returncode}")


def t_without_file():
    print("sem o próximo passo, o cepa sai depois do primeiro claude")
    with World() as w:
        r = w.run(env={"STUB_RC": "3"})
        check("o stub rodou uma vez", len(w.calls()) == 1, f"{len(w.calls())}")
        check("o código de saída é o do claude", r.returncode == 3, f"rc={r.returncode}")
        check("não diz que encadeou", "próxima sessão em" not in r.stderr, r.stderr)


def t_off():
    print("CEPA_ENCADEAR=off: não encadeia e o arquivo fica")
    with World() as w:
        r = w.run(nxt={"repo": str(w.b), "mode": "discovery", "brief": BRIEF},
                  env={"CEPA_ENCADEAR": "off", "STUB_RC": "7"})
        check("o stub rodou uma vez", len(w.calls()) == 1, f"{len(w.calls())}")
        check("o arquivo continua lá", (w.sessions / "sess-1.next.json").exists())
        check("o código de saída é o do claude", r.returncode == 7, f"rc={r.returncode}")


def t_invalid():
    print("próximo passo com repo inexistente: não encadeia, avisa, deixa o arquivo")
    with World() as w:
        r = w.run(nxt={"repo": str(w.b / "nao-existe"), "mode": "discovery", "brief": BRIEF})
        check("o stub rodou uma vez", len(w.calls()) == 1, f"{len(w.calls())}")
        check("o arquivo continua lá", (w.sessions / "sess-1.next.json").exists())
        check("o cepa diz que é inválido", "inválido" in r.stderr, r.stderr)
    with World() as w:
        r = w.run(nxt="{isto não é json")
        check("json quebrado: uma vez só", len(w.calls()) == 1, f"{len(w.calls())}")
        check("json quebrado: o cepa diz", "ilegível" in r.stderr, r.stderr)


def t_empty_fields():
    print("brief ou modo vazio, ou brief que não é texto: não encadeia, avisa, deixa o arquivo")
    cases = {
        "brief em branco": {"mode": "discovery", "brief": "   \n"},
        "brief não-texto": {"mode": "discovery", "brief": 42},
        "modo vazio": {"mode": "", "brief": BRIEF},
    }
    for given_name, fields in cases.items():
        with World() as w:
            r = w.run(nxt={"repo": str(w.b), **fields})
            check(f"{given_name}: o stub rodou uma vez", len(w.calls()) == 1, f"{len(w.calls())}")
            check(f"{given_name}: o arquivo continua lá", (w.sessions / "sess-1.next.json").exists())
            check(f"{given_name}: o cepa diz que é inválido", "inválido" in r.stderr, r.stderr)


def t_most_recent_wins():
    print("duas sessões na mesma abertura (/clear): vale o próximo passo da mais recente")
    with World() as w:
        w.run(nxt={"repo": str(w.a), "mode": "discovery", "brief": "da primeira"},
              env={"STUB_NEXT2": json.dumps({"repo": str(w.b), "mode": "discovery",
                                             "brief": "da segunda"})})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"{len(c)}")
        if len(c) == 2:
            check("a sessão seguinte é a da mais recente (repo b)", same(c[1]["cwd"], w.b),
                  c[1]["cwd"])
            check("com o brief da mais recente", c[1]["args"][-1:] == ["da segunda"],
                  repr(c[1]["args"]))


def t_without_session_end():
    print("sem o SessionEnd, o registro da sessão que saiu não isola a seguinte")
    with World() as w:
        w.run(nxt={"repo": str(w.a), "mode": "discovery", "brief": BRIEF},
              env={"STUB_SKIP_END": "1"})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"{len(c)}")
        if len(c) == 2:
            check("a segunda rodou no próprio repo, sem worktree", same(c[1]["cwd"], w.a),
                  c[1]["cwd"])


def t_worktree_erased():
    print("a sessão apagou a própria worktree (wrap-up): encadeia mesmo assim, sem ruído")
    with World() as w:
        r = w.run(nxt={"repo": str(w.b), "mode": "discovery", "brief": BRIEF},
                  env={"STUB_RMCWD": "1"}, args=["-s", "fatia"])
        c = w.calls()
        check("a primeira rodou numa worktree", len(c) >= 1
              and Path(c[0]["cwd"]).resolve().is_relative_to(w.wt_home.resolve()),
              repr(c[:1]))
        check("o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; stderr={r.stderr!r}")
        if len(c) == 2:
            check("a segunda rodou com cwd = repo do arquivo", same(c[1]["cwd"], w.b), c[1]["cwd"])
        check("sem 'shell-init' nem 'getcwd' no stderr",
              "shell-init" not in r.stderr and "getcwd" not in r.stderr, r.stderr)
        check("o .next.json foi apagado", not (w.sessions / "sess-1.next.json").exists())
        check("sai 0", r.returncode == 0, f"rc={r.returncode} stderr={r.stderr!r}")


def t_record_ignores_next():
    print("o registro de sessões não lê .next.json como sessão")
    with World() as w:
        w.sessions.mkdir(parents=True)
        (w.sessions / "s.next.json").write_text(json.dumps({"repo": "/x", "cwd": str(w.a)}))
        (w.sessions / "s.json").write_text(json.dumps({"session_id": "s", "cwd": str(w.a)}))
        stems = [f.name for f, _ in L.read_entries(str(w.a))]
        check("só a sessão de verdade aparece", stems == ["s.json"], repr(stems))


def t_old_names():
    print("nomes antigos: .next.json com modo/intencao, e as flags --modo/--proposito/--para-quando/--plano")
    with World() as w:  # .next.json in the OLD format (modo + intencao in pt-BR)
        r = w.run(nxt={"repo": str(w.b), "modo": "descoberta", "brief": BRIEF,
                       "intencao": OLD_INTENT})
        c = w.calls()
        check("antigo: o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; {r.stderr!r}")
        if len(c) == 2:
            check("antigo: a segunda abriu em `mode: discovery`", "mode: discovery" in c[1]["mode"],
                  repr(c[1]["mode"]))
            it = _modes.parse_intent(c[1]["intent"])
            check("antigo: a intenção do arquivo antigo foi gravada",
                  it.get("purpose") == INTENT["purpose"] and it.get("plan") == INTENT["plan"], repr(it))
    with World() as w:  # cepa's own old flags
        r = w.run(args=["--proposito=p", "--para-quando=meta m", "--plano=um\ndois"])
        c = w.calls()
        if c:
            it = _modes.parse_intent(c[0]["intent"])
            check("antigo: --proposito=/--para-quando=/--plano= gravam a intenção",
                  (it.get("purpose"), it.get("by_when"), it.get("plan")) == ("p", "meta m", ["um", "dois"]),
                  repr(it))
            check("antigo: as flags antigas não vazam para o claude",
                  not any(x.startswith(("--proposito", "--para-quando", "--plano")) for x in c[0]["args"]),
                  repr(c[0]["args"]))
        else:
            check("antigo: o stub rodou", False, r.stderr)
    with World() as w:
        r = w.run(args=["--proposito", "x y", "--para-quando", "q", "--plano", "a"])
        c = w.calls()
        it = _modes.parse_intent(c[0]["intent"]) if c else {}
        check("antigo: forma com espaço (--proposito x --para-quando q --plano a)",
              it.get("purpose") == "x y" and it.get("by_when") == "q" and it.get("plan") == ["a"], r.stderr)
    with World() as w:
        r = w.run(args=["--proposito"])
        check("antigo: --proposito sem valor sai 2 e diz", r.returncode == 2
              and "--proposito exige um valor" in r.stderr, r.stderr)


if __name__ == "__main__":
    t_chains()
    t_command_first_line()
    t_chains_with_intent()
    t_old_names()
    t_invalid_intent_opens_without()
    t_previous_intent_goes_to_history()
    t_whole_intent_on_the_command_line()
    t_purpose_direct_in_the_worktree()
    t_purpose_in_branch_session()
    t_purpose_form_with_equals()
    t_without_purpose_without_intent()
    t_writer_failure_does_not_prevent()
    t_without_file()
    t_off()
    t_invalid()
    t_empty_fields()
    t_most_recent_wins()
    t_without_session_end()
    t_worktree_erased()
    t_record_ignores_next()
    if failures:
        print(f"\n{len(failures)} FAIL")
        sys.exit(1)
    print("\nOK")
