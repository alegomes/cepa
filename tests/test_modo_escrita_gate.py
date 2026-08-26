#!/usr/bin/env python3
"""Testes de regressão de common/hooks/modo-escrita-gate.py.

O modo de uma sessão era prosa: o `session-mode.py` injeta a cada turno "ação
fora deste modo NÃO vira pergunta e NÃO vira trabalho agora", e nada barrava. Na
sessão `session/drain-plan-speed` (26/08/2026) o agente furou o modo sete vezes
seguidas — transformou cada desvio numa pergunta fechada com "Recomendo sim",
colheu o sim, e construiu. Nenhuma captura de desvio foi registrada.

Este gate é o irmão do `reforma-gate.py`: uma lista branca de DESTINOS por modo,
aplicada em Edit/Write/MultiEdit/NotebookEdit e também em Bash.

Contratos guardados aqui:
  - modo com lista branca: destino fora dela bloqueia (rc=2) com o motivo;
  - destino dentro da lista passa;
  - `construcao` e `reforma` são mudos — quem cobra ali são o
    completion-auditor/proof-reviewer e o reforma-gate;
  - sem modo declarado, mudo;
  - Bash não é rota de fuga: `>`, `>>`, `sed -i`, `tee` e `git mv` bloqueiam
    igual (bloquear só Write já deixou agentes escaparem por sed neste repo);
  - `>=` numa condição não vira redirecionamento (falso bloqueio real do
    bash-path-lock, que silenciou perturbações por 2 meses);
  - escrita FORA da raiz da sessão passa — a worktree de perturbação em /tmp e o
    scratchpad da sessão não são governados por modo (path-lock-out-of-root);
  - a mensagem diz o que fazer (registrar pelo off-mode-capture, ou encerrar o
    modo) e NÃO anuncia o kill switch: escape barato é a mesma fuga de novo;
  - CEPA_MODO=off desliga o gate.

Sem deps de terceiros — rode com `python3 tests/test_modo_escrita_gate.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "common" / "hooks" / "modo-escrita-gate.py"

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

    def modo(self, nome):
        (self.path / ".claude" / "session-mode").write_text(
            f"modo: {nome}\norcamento: null\n", encoding="utf-8")

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


# Um caso por modo: o que ele PRODUZ (passa) e o que ele não produz (bloqueia).
PERMITIDO = {
    "exploracao": ["docs/estrategia-x.md", ".claude/programs/p/plan.yaml",
                   "BACKLOG.md"],
    "descoberta": ["docs/discovery/c/framing.md", "docs/spec/x.md",
                   ".claude/acceptance/x.yaml", "BACKLOG.md"],
    "design": ["docs/design/fluxos.md", ".claude/x", "BACKLOG.md"],
    "reflexao": [".claude/reflexao/r.md", "docs/qualquer.md", "BACKLOG.md"],
    "documentacao": ["docs/tutorial/primeiro-dia.md", "docs/reference/api.md",
                     ".claude/x", "BACKLOG.md"],
}
BLOQUEADO = {
    "exploracao": ["common/hooks/novo.py", "common/commands/x.md",
                   "tests/test_x.py", "common/agents/lead.md", "src/App.java"],
    "descoberta": ["docs/estrategia-x.md", "common/hooks/novo.py",
                   "tests/test_x.py"],
    "design": ["docs/how-to/x.md", "common/hooks/novo.py"],
    "reflexao": ["common/hooks/novo.py", "tests/test_x.py"],
    "documentacao": ["common/hooks/novo.py", "tests/test_x.py",
                     "common/commands/x.md"],
}


def test_lista_branca_por_modo():
    for modo, alvos in PERMITIDO.items():
        with Repo() as r:
            r.modo(modo)
            for alvo in alvos:
                p = r.edit(alvo)
                check(f"{modo}: libera {alvo}", p.returncode == 0, p.stderr[:160])
    for modo, alvos in BLOQUEADO.items():
        with Repo() as r:
            r.modo(modo)
            for alvo in alvos:
                p = r.edit(alvo)
                check(f"{modo}: bloqueia {alvo}", p.returncode == 2, p.stderr[:160])


def test_modos_sem_lista_sao_mudos():
    for modo in ("construcao", "reforma"):
        with Repo() as r:
            r.modo(modo)
            for alvo in ("common/hooks/novo.py", "tests/test_x.py",
                         "src/main/java/App.java"):
                p = r.edit(alvo)
                check(f"{modo}: gate é mudo em {alvo}", p.returncode == 0,
                      p.stderr[:160])


def test_sem_modo_e_mudo():
    with Repo() as r:
        p = r.edit("common/hooks/novo.py")
        check("sem modo declarado: gate é mudo", p.returncode == 0, p.stderr[:160])


def test_todas_as_ferramentas_de_escrita():
    with Repo() as r:
        r.modo("exploracao")
        for tool, ti in (("Write", {"file_path": "common/hooks/n.py"}),
                         ("MultiEdit", {"file_path": "common/hooks/n.py"}),
                         ("NotebookEdit", {"notebook_path": "analise/n.ipynb"})):
            p = r.call(tool, ti)
            check(f"exploracao: {tool} bloqueado", p.returncode == 2, p.stderr[:120])


def test_bash_nao_e_rota_de_fuga():
    with Repo() as r:
        r.modo("exploracao")
        for cmd in ('echo x > common/hooks/novo.py',
                    'cat foo >> common/commands/run.md',
                    "sed -i '' 's/a/b/' common/bin/cepa",
                    'tee tests/test_x.py < /dev/null',
                    'git mv common/hooks/a.py common/hooks/b.py'):
            p = r.bash(cmd)
            check(f"bash bloqueado: {cmd[:30]}", p.returncode == 2, p.stderr[:120])


def test_bash_libera_o_que_o_modo_produz():
    with Repo() as r:
        r.modo("exploracao")
        for cmd in ('echo x > docs/estrategia.md',
                    'git commit -m "docs(estrategia): dois caminhos\n\nA -> B"',
                    'grep -rn "modo" common/hooks/',
                    # A forma BSD do sed deixa o `''` como operando: sem filtrar
                    # o token vazio, o SCRIPT `s/a/b/` era contado como arquivo
                    # escrito e este comando legítimo bloqueava.
                    "sed -i '' 's/a/b/' docs/estrategia.md"):
            p = r.bash(cmd)
            check(f"bash liberado: {cmd[:30]}", p.returncode == 0, p.stderr[:160])


def test_ge_nao_e_redirecionamento():
    with Repo() as r:
        r.modo("exploracao")
        p = r.bash('if [ "$n" >= 3 ]; then echo common/hooks/x.py; fi')
        check(">= não vira redirecionamento", p.returncode == 0, p.stderr[:160])


def test_fora_da_raiz_passa():
    """A worktree de perturbação em /tmp e o scratchpad não são do modo.

    Estreitar o gate para fora da raiz foi o que travou o proof-reviewer em
    2026-06-18 (memória path-lock-out-of-root) e deixou 5 cards presos em
    NEEDS-HUMAN. Aqui o modo governa o repo da sessão, e só ele.
    """
    with Repo() as r:
        r.modo("exploracao")
        for alvo in ("/tmp/perturba/App.java", "/tmp/scratch/nota.py"):
            p = r.edit(alvo)
            check(f"fora da raiz passa: {alvo}", p.returncode == 0, p.stderr[:160])


def test_mensagem_diz_o_que_fazer():
    with Repo() as r:
        r.modo("exploracao")
        p = r.edit("common/hooks/novo.py")
        check("mensagem nomeia o modo ativo", "exploracao" in p.stderr, p.stderr[:200])
        check("mensagem nomeia o alvo", "common/hooks/novo.py" in p.stderr,
              p.stderr[:200])
        check("mensagem oferece a captura do desvio",
              "off-mode-capture" in p.stderr, p.stderr[:200])
        check("mensagem oferece encerrar o modo",
              "encerre" in p.stderr.lower(), p.stderr[:300])
        check("mensagem NÃO anuncia o kill switch",
              "CEPA_MODO" not in p.stderr, p.stderr[:300])


def test_kill_switch():
    with Repo() as r:
        r.modo("exploracao")
        p = r.edit("common/hooks/novo.py", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off desliga o gate", p.returncode == 0, p.stderr[:160])


def test_tabela_vem_de_modos_py():
    """A lista branca mora em _modos.py, junto com o resto da tabela de modos.

    Uma segunda tabela de modos no hook é a doença que _modos.py trata.
    """
    sys.path.insert(0, str(REPO / "common" / "hooks"))
    from _modos import MODOS
    for nome, d in MODOS.items():
        check(f"_modos: {nome} declara `escrita`", "escrita" in d,
              "modo sem lista branca declarada — nem 'tudo' nem os globs")
    src = GATE.read_text(encoding="utf-8") if GATE.exists() else ""
    check("o hook importa a tabela em vez de copiá-la", "_modos" in src)


def main():
    print("test_modo_escrita_gate")
    if not GATE.exists():
        print(f"  FAIL hook ausente: {GATE}")
        return 1
    for fn in (test_lista_branca_por_modo, test_modos_sem_lista_sao_mudos,
               test_sem_modo_e_mudo, test_todas_as_ferramentas_de_escrita,
               test_bash_nao_e_rota_de_fuga, test_bash_libera_o_que_o_modo_produz,
               test_ge_nao_e_redirecionamento, test_fora_da_raiz_passa,
               test_mensagem_diz_o_que_fazer, test_kill_switch,
               test_tabela_vem_de_modos_py):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
