#!/usr/bin/env python3
"""CS-3 (cepa-espiral-c1): o launcher `cepa` abre a sessão seguinte quando a
anterior deixou o próximo passo gravado.

A sessão que sai deixa `<raiz-principal>/.claude/sessions/<session_id>.next.json`
com `{"repo", "modo", "brief"}`. O `cepa` não faz mais `exec` do claude: quando
ele sai, o launcher lê o arquivo, apaga, entra em `repo` e abre a sessão
seguinte com `--modo <modo>` e o brief como prompt inicial.

O `claude` aqui é um stub que registra argumentos, cwd e o modo gravado. Na
primeira chamada ele faz o papel da sessão inteira: roda o hook REAL
`session-registry.py` no SessionStart (que liga o CEPA_LAUNCH_ID do launcher ao
session_id), escreve o `.next.json` como o wrap-up escreveria, roda o
SessionEnd e sai.

Contratos guardados aqui:
  - com o arquivo: o stub roda uma segunda vez, cwd = repo, modo gravado =
    descoberta, último argumento = o brief verbatim; o arquivo some;
  - sem o arquivo: o stub roda uma vez só e o código de saída dele é o do cepa;
  - CEPA_ENCADEAR=off: uma vez só, o arquivo fica;
  - arquivo inválido (repo inexistente): uma vez só, o arquivo fica, e o cepa diz;
  - o `.next.json` não é lido como sessão pelo registro (`read_entries`);
  - sem o SessionEnd, o registro da sessão que saiu não faz a seguinte se
    isolar numa worktree.

Sem deps de terceiros — rode com `python3 tests/test_cepa_encadeamento.py`.
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

BRIEF = 'Abra o /common:epic contratos-e-regras.\nLeia o handoff "anterior" antes.'

# O stub: registra cada chamada como uma linha JSON em $STUB_LOG. Só na
# primeira chamada ($STUB_STATE ainda não existe) ele age como a sessão que
# termina e deixa o próximo passo.
STUB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
mode = ""
p = Path(".claude/session-mode")
if p.exists():
    mode = p.read_text()
with open(os.environ["STUB_LOG"], "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd(), "mode": mode,
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
if os.environ.get("STUB_SKIP_END") != "1":
    hook("SessionEnd")
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

    def run(self, nxt=None, env=None):
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
        return subprocess.run([str(CEPA), "--modo", "construcao"], cwd=self.a, env=e,
                              capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text().splitlines() if x.strip()]


def same(a, b):
    return Path(a).resolve() == Path(b).resolve()


def t_encadeia():
    print("com o próximo passo gravado, a sessão seguinte abre sozinha")
    with World() as w:
        r = w.run(nxt={"repo": str(w.b), "modo": "descoberta", "brief": BRIEF})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"rodou {len(c)}; stderr={r.stderr!r}")
        if len(c) == 2:
            check("a primeira rodou no repo de origem", same(c[0]["cwd"], w.a), c[0]["cwd"])
            check("a segunda rodou com cwd = repo do arquivo", same(c[1]["cwd"], w.b), c[1]["cwd"])
            check("a segunda abriu em modo descoberta",
                  "modo: descoberta" in c[1]["mode"], repr(c[1]["mode"]))
            check("o brief é o prompt inicial, verbatim", c[1]["args"][-1:] == [BRIEF],
                  repr(c[1]["args"]))
            check("o args do primeiro claude não vazam para o segundo",
                  "construcao" not in c[1]["args"], repr(c[1]["args"]))
            check("cada abertura tem o próprio CEPA_LAUNCH_ID",
                  c[0]["launch_id"] and c[1]["launch_id"]
                  and c[0]["launch_id"] != c[1]["launch_id"], repr(c))
        check("o .next.json foi apagado", not (w.sessions / "sess-1.next.json").exists())
        check("a anotação do launch foi apagada", not list(w.sessions.glob("*.launch")))
        check("o cepa diz que encadeou", "próxima sessão em" in r.stderr, r.stderr)
        check("a sessão seguinte não foi isolada numa worktree",
              not w.wt_home.exists() or not any(w.wt_home.iterdir()))
        check("sai 0", r.returncode == 0, f"rc={r.returncode}")


def t_sem_arquivo():
    print("sem o próximo passo, o cepa sai depois do primeiro claude")
    with World() as w:
        r = w.run(env={"STUB_RC": "3"})
        check("o stub rodou uma vez", len(w.calls()) == 1, f"{len(w.calls())}")
        check("o código de saída é o do claude", r.returncode == 3, f"rc={r.returncode}")
        check("não diz que encadeou", "próxima sessão em" not in r.stderr, r.stderr)


def t_desligado():
    print("CEPA_ENCADEAR=off: não encadeia e o arquivo fica")
    with World() as w:
        w.run(nxt={"repo": str(w.b), "modo": "descoberta", "brief": BRIEF},
              env={"CEPA_ENCADEAR": "off"})
        check("o stub rodou uma vez", len(w.calls()) == 1, f"{len(w.calls())}")
        check("o arquivo continua lá", (w.sessions / "sess-1.next.json").exists())


def t_invalido():
    print("próximo passo com repo inexistente: não encadeia, avisa, deixa o arquivo")
    with World() as w:
        r = w.run(nxt={"repo": str(w.b / "nao-existe"), "modo": "descoberta", "brief": BRIEF})
        check("o stub rodou uma vez", len(w.calls()) == 1, f"{len(w.calls())}")
        check("o arquivo continua lá", (w.sessions / "sess-1.next.json").exists())
        check("o cepa diz que é inválido", "inválido" in r.stderr, r.stderr)
    with World() as w:
        r = w.run(nxt="{isto não é json")
        check("json quebrado: uma vez só", len(w.calls()) == 1, f"{len(w.calls())}")
        check("json quebrado: o cepa diz", "ilegível" in r.stderr, r.stderr)


def t_sem_session_end():
    print("sem o SessionEnd, o registro da sessão que saiu não isola a seguinte")
    with World() as w:
        w.run(nxt={"repo": str(w.a), "modo": "descoberta", "brief": BRIEF},
              env={"STUB_SKIP_END": "1"})
        c = w.calls()
        check("o stub rodou duas vezes", len(c) == 2, f"{len(c)}")
        if len(c) == 2:
            check("a segunda rodou no próprio repo, sem worktree", same(c[1]["cwd"], w.a),
                  c[1]["cwd"])


def t_registro_ignora_next():
    print("o registro de sessões não lê .next.json como sessão")
    with World() as w:
        w.sessions.mkdir(parents=True)
        (w.sessions / "s.next.json").write_text(json.dumps({"repo": "/x", "cwd": str(w.a)}))
        (w.sessions / "s.json").write_text(json.dumps({"session_id": "s", "cwd": str(w.a)}))
        stems = [f.name for f, _ in L.read_entries(str(w.a))]
        check("só a sessão de verdade aparece", stems == ["s.json"], repr(stems))


if __name__ == "__main__":
    t_encadeia()
    t_sem_arquivo()
    t_desligado()
    t_invalido()
    t_sem_session_end()
    t_registro_ignora_next()
    if failures:
        print(f"\n{len(failures)} FAIL")
        sys.exit(1)
    print("\nOK")
