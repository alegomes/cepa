#!/usr/bin/env python3
"""Regression tests for the `--modo` gate in common/bin/cepa.

Toda sessão declara em qual dos sete modos de trabalho ela opera
(docs/modos-de-trabalho.md). O modo é gravado em .claude/session-mode no
diretório onde a sessão vai de fato rodar. Sem modo o cepa não sobe: um default
silencioso reconstruiria exatamente o vazamento entre atividades que o modo
existe para fechar.

Contratos guardados aqui:
  - modo válido grava o arquivo e repassa os demais args ao claude;
  - modo desconhecido é erro (rc=2), nunca vira pergunta nem chute;
  - sem modo e sem tty → recusa subir, e NÃO grava arquivo;
  - CEPA_MODO=off desliga a exigência inteira (escape hatch);
  - reforma sem orçamento é recusada — reforma sem escopo fechado não termina;
  - a detecção de "há humano para perguntar" olha stdin, não só /dev/tty:
    /dev/tty segue legível com stdin redirecionado, e sozinho ele deixaria um
    script pipe-alimentado parar num menu interativo.

Sem deps de terceiros — rode com `python3 tests/test_cepa_modo.py`.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# O cepa lê CEPA_PROMPT/CEPA_PROMPT_MODO do ambiente. Herdadas do shell de quem
# roda a suíte (o cepa-until roda com elas), viram um prompt que o teste não
# pediu e quebram o "repassa só os args do usuário". Quem quer o prompt passa
# no env= do próprio caso.
for _k in ("CEPA_PROMPT", "CEPA_PROMPT_MODO"):
    os.environ.pop(_k, None)

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"

FAKE_CLAUDE = '#!/bin/sh\nprintf "CLAUDE_ARGS:%s\\n" "$*"\n'

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


class Repo:
    """Um git repo descartável com um `claude` falso no lugar do de verdade."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "repo"
        self.path.mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=self.path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "init"],
            cwd=self.path, check=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        )
        fake = Path(self.tmp.name) / "fakeclaude"
        fake.write_text(FAKE_CLAUDE)
        fake.chmod(0o755)
        self.fake = fake
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def run(self, *args, env=None):
        e = {**os.environ,
             "CLAUDE_WT_CLAUDE_BIN": str(self.fake),
             "CEPA_PREFLIGHT": "off"}
        e.update(env or {})
        return subprocess.run(
            [str(CEPA), *args], cwd=self.path, env=e,
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
        )

    @property
    def mode_file(self):
        return self.path / ".claude" / "session-mode"


# Flags que o PRÓPRIO cepa acrescenta antes das suas: hoje só a de permissão
# (toda sessão nasce em bypassPermissions). O contrato testado aqui é "não
# engoliu o que você digitou", então elas saem da comparação.
FLAGS_DO_CEPA = ("--dangerously-skip-permissions", "--permission-mode")


def claude_args(proc):
    """Os args do usuário que chegaram ao claude falso."""
    linha = ""
    for l in proc.stdout.splitlines():
        if l.startswith("CLAUDE_ARGS:"):
            linha = l[len("CLAUDE_ARGS:"):]
    return [x for x in linha.split() if x.split("=")[0] not in FLAGS_DO_CEPA]


def test_modo_valido():
    with Repo() as r:
        p = r.run("--modo", "construcao", "--resume")
        check("modo válido: rc=0", p.returncode == 0, p.stderr)
        check("modo válido: grava o arquivo", r.mode_file.exists())
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("modo válido: registra o modo", "modo: construcao" in body, body)
        check("modo válido: repassa os args ao claude",
              claude_args(p) == ["--resume"], p.stdout)


def test_modo_invalido():
    with Repo() as r:
        p = r.run("--modo=xpto")
        check("modo inválido: rc=2", p.returncode == 2, str(p.returncode))
        check("modo inválido: não grava", not r.mode_file.exists())
        check("modo inválido: lista os válidos", "construcao" in p.stderr, p.stderr)


def test_sem_modo_sem_tty():
    with Repo() as r:
        p = r.run()
        check("sem modo: recusa subir", p.returncode == 2, str(p.returncode))
        check("sem modo: não grava", not r.mode_file.exists())
        check("sem modo: não caiu no menu interativo",
              "Em qual modo" not in p.stderr, p.stderr)
        check("sem modo: ensina o escape", "CEPA_MODO=off" in p.stderr, p.stderr)


def test_kill_switch():
    with Repo() as r:
        p = r.run("--resume", env={"CEPA_MODO": "off"})
        check("CEPA_MODO=off: sobe", p.returncode == 0, p.stderr)
        check("CEPA_MODO=off: não grava", not r.mode_file.exists())
        check("CEPA_MODO=off: entrega ao claude",
              claude_args(p) == ["--resume"], p.stdout)


def test_reforma_orcamento():
    with Repo() as r:
        p = r.run("--modo", "reforma")
        check("reforma sem orçamento: recusa", p.returncode == 2, str(p.returncode))
        check("reforma sem orçamento: não grava", not r.mode_file.exists())
    with Repo() as r:
        p = r.run("--modo", "reforma", "--orcamento", "só o módulo de auth")
        check("reforma com orçamento: rc=0", p.returncode == 0, p.stderr)
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("reforma com orçamento: registra o escopo",
              'orcamento: "só o módulo de auth"' in body, body)


# --- hook session-mode.py ---------------------------------------------------
HOOK = REPO / "common" / "hooks" / "session-mode.py"


def run_hook(cwd, env=None, **payload):
    """`payload` vira campos do JSON do hook (session_id, prompt). A marca do
    cepa-until sai do ambiente: a suíte roda dentro dele, e com ela o hook
    cala a intenção — quem quer testar isso passa no env= do caso."""
    import json as _json
    e = {k: v for k, v in os.environ.items() if k != "CEPA_UNTIL_RUN"}
    e.update(env or {})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=_json.dumps({"cwd": str(cwd), **payload}),
        capture_output=True, text=True, timeout=15, env=e,
    )


def ctx(proc):
    """O texto que o modelo de fato recebe — decodificado, não o JSON cru."""
    import json as _json
    if not proc.stdout.strip():
        return ""
    return _json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]


def write_mode(repo, body):
    d = repo.path / ".claude"
    d.mkdir(exist_ok=True)
    (d / "session-mode").write_text(body, encoding="utf-8")


def test_hook_injeta_modo_e_saida():
    with Repo() as r:
        write_mode(r, "modo: construcao\nrotina: null\norcamento: null\n")
        p = run_hook(r.path)
        check("hook: rc=0", p.returncode == 0, p.stderr)
        c = ctx(p)
        check("hook: nomeia o modo", "construcao" in c, c)
        check("hook: dá a condição de saída",
              "completion-auditor" in c and "PROVEN" in c, c)
        check("hook: manda capturar o desvio", "off-mode-capture" in c, c)


def test_hook_reforma_mostra_orcamento():
    with Repo() as r:
        write_mode(r, 'modo: reforma\norcamento: "só o módulo de auth"\n')
        p = run_hook(r.path)
        c = ctx(p)
        check("hook reforma: mostra o orçamento", "só o módulo de auth" in c, c)
        check("hook reforma: cobra teste externo não editado",
              "teste" in c and "externo" in c, c)


def test_hook_silencioso_sem_modo():
    with Repo() as r:
        p = run_hook(r.path)
        check("hook: silencioso sem arquivo de modo", p.stdout.strip() == "",
              repr(p.stdout))
        check("hook: rc=0 sem arquivo", p.returncode == 0, p.stderr)


def test_hook_respeita_kill_switch():
    with Repo() as r:
        write_mode(r, "modo: construcao\n")
        p = run_hook(r.path, env={"CEPA_MODO": "off"})
        check("hook: CEPA_MODO=off silencia", p.stdout.strip() == "", repr(p.stdout))


def test_hook_nunca_quebra_o_turno():
    with Repo() as r:
        write_mode(r, "lixo que não é yaml\n:::\n")
        p = run_hook(r.path)
        check("hook: arquivo corrompido não quebra", p.returncode == 0, p.stderr)
        check("hook: arquivo corrompido não injeta nada",
              p.stdout.strip() == "", repr(p.stdout))


# --- intenção da sessão no hook (.claude/session-intent) ----------------------
# Desenho: docs/estrategia-intencao-da-sessao.md. Três estados, teto de duas
# linhas cada: vazio (os três primeiros prompts + pedido de gravar), intenção
# de OUTRA sessão (pergunta, nunca exibida como atual) e normal (passo N/M, há
# quantos turnos, próximo). Rodada do cepa-until não recebe intenção.

sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modos as _M  # noqa: E402

PLANO = ["levantar o que existe", "escrever o doc", "rodar advisors", "decidir"]
SID = "209286bf-1111-2222-3333-444455556666"


def write_intent(repo, **campos):
    d = {"proposito": "institucionalizar as quatro perguntas",
         "para_quando": "doc decidido", "plano": PLANO, "passo": 2,
         "passo_desde": "2026-10-16T21:40:00Z", "session_id": SID[:8],
         "branch": "main", "aberto_em": "2026-10-16T18:30:00Z"}
    d.update(campos)
    (repo.path / ".claude").mkdir(exist_ok=True)
    (repo.path / ".claude" / "session-intent").write_text(_M.render_intent(d), encoding="utf-8")


def write_log(repo, entradas):
    """entradas: [("2026-10-16", "21:41:00", "prompt"), ...] no formato do session-log."""
    out, dia = ["# Session log", ""], None
    for d, h, t in entradas:
        if d != dia:
            out += [f"## {d}", ""]
            dia = d
        out += [f"### {h} UTC", "", t, ""]
    (repo.path / ".claude").mkdir(exist_ok=True)
    (repo.path / ".claude" / "session-log.md").write_text("\n".join(out), encoding="utf-8")


def register(repo, sid, started_at):
    d = repo.path / ".claude" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    import json as _json
    (d / f"{sid}.json").write_text(_json.dumps({"session_id": sid, "started_at": started_at}))


def intent_lines(c):
    """As linhas de intenção do contexto: a primeira começa em [intenção]; a do
    modo é sempre uma linha só e vem antes."""
    ls = c.split("\n")
    for i, l in enumerate(ls):
        if l.startswith("[intenção]"):
            return ls[i:]
    return []


def test_intencao_vazia_traz_os_primeiros_prompts():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        write_log(r, [("2026-10-15", "10:00:00", "prompt de outra sessão"),
                      ("2026-10-16", "18:01:00", "quero institucionalizar as perguntas"),
                      ("2026-10-16", "18:02:00", "primeiro levante o que existe"),
                      ("2026-10-16", "18:03:00", "x" * 300),
                      ("2026-10-16", "18:04:00", "quarto prompt")])
        p = run_hook(r.path, session_id=SID, prompt="quarto prompt")
        check("intenção vazia: rc=0", p.returncode == 0, p.stderr)
        c = ctx(p)
        il = intent_lines(c)
        check("intenção vazia: diz que não há intenção gravada",
              "ainda não tem intenção gravada" in c, c)
        check("intenção vazia: traz os três primeiros prompts da sessão",
              "quero institucionalizar" in c and "primeiro levante" in c and "xxx" in c, c)
        check("intenção vazia: prompt de sessão anterior fica de fora",
              "outra sessão" not in c, c)
        check("intenção vazia: o quarto prompt fica de fora", "quarto prompt" not in c, c)
        check("intenção vazia: prompt longo é cortado", "x" * 200 not in c and "…" in c, c)
        check("intenção vazia: pede para gravar com cepa-intencao e ensina o whereami",
              "cepa-intencao gravar" in c and "/common:whereami" in c, c)
        check("intenção vazia: manda não propor em prompt trivial", "trivial" in c, c)
        check("intenção vazia: teto de duas linhas", 1 <= len(il) <= 2, il)
        check("intenção vazia: o modo continua lá", "[modo]" in c, c)


def test_intencao_vazia_primeiro_turno_usa_o_prompt_atual():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        p = run_hook(r.path, session_id=SID, prompt="  quero   um comando whereami ")
        c = ctx(p)
        check("intenção vazia, log vazio: o prompt do turno entra",
              '"quero um comando whereami"' in c, c)


def test_intencao_vazia_sem_registro_cai_para_hoje():
    from datetime import datetime, timezone
    hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        write_log(r, [("2020-01-01", "10:00:00", "prompt antigo"),
                      (hoje, "00:00:01", "prompt de hoje")])
        c = ctx(run_hook(r.path, session_id="sem-registro", prompt="prompt de hoje"))
        check("sem registro: usa os prompts de hoje",
              "prompt de hoje" in c and "prompt antigo" not in c, c)


def test_intencao_vazia_sem_modo_e_silenciosa():
    with Repo() as r:
        p = run_hook(r.path, session_id=SID, prompt="oi")
        check("intenção vazia sem modo: silêncio (sessão não aberta pelo cepa)",
              p.stdout.strip() == "", repr(p.stdout))


def test_intencao_normal_passo_idade_proximo():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        write_intent(r)
        write_log(r, [("2026-10-16", "21:30:00", "antes do cursor"),
                      ("2026-10-16", "21:41:00", "depois 1"),
                      ("2026-10-17", "09:00:00", "depois 2")])
        p = run_hook(r.path, session_id=SID, prompt="depois 2")
        c = ctx(p)
        il = intent_lines(c)
        check("intenção normal: propósito, passo N/M e nome do passo",
              "institucionalizar as quatro perguntas" in c
              and "Passo 2/4: escrever o doc" in c, c)
        check("intenção normal: há quantos turnos o cursor está parado",
              "(há 2 turnos)" in c, c)
        check("intenção normal: próximo passo", "Próximo: rodar advisors." in c, c)
        check("intenção normal: ensina a avançar o cursor",
              "Ao concluir o passo, rode `cepa-intencao --passo 3`." in c, c)
        check("intenção normal: não despeja o plano inteiro",
              "levantar o que existe" not in c and "decidir" not in c, c)
        check("intenção normal: teto de duas linhas", len(il) == 2, il)
        check("intenção normal: não pergunta sobre outra sessão", "outra sessão" not in c, c)


def test_intencao_normal_um_turno_no_singular():
    with Repo() as r:
        write_intent(r)
        write_log(r, [("2026-10-16", "21:41:00", "depois 1")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("intenção normal: '(há 1 turno)' no singular", "(há 1 turno)" in c, c)


def test_intencao_corta_proposito_e_passo_longos():
    with Repo() as r:
        write_intent(r, proposito="p" * 500, plano=["a" * 300, "b"], passo=1)
        write_log(r, [])
        c = ctx(run_hook(r.path, session_id=SID))
        check("propósito longo é cortado no hook", "p" * 160 not in c and "p" * 150 in c, c)
        check("nome de passo longo é cortado no hook", "a" * 80 not in c and "a" * 70 in c, c)


def test_intencao_vazia_prompt_do_turno_e_log_parcial():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        write_log(r, [("2026-10-16", "18:01:00", "primeiro do log")])
        c = ctx(run_hook(r.path, session_id=SID, prompt="segundo, o do turno"))
        check("log com 1 prompt + prompt do turno diferente: entram os dois, em ordem",
              '"primeiro do log" | "segundo, o do turno"' in c, c)
        c = ctx(run_hook(r.path, session_id=SID, prompt="primeiro do log"))
        check("prompt do turno já no log: não duplica",
              c.count("primeiro do log") == 1, c)
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        c = ctx(run_hook(r.path, session_id=SID, prompt=""))
        check("log vazio e prompt vazio: 'nenhum ainda'", "Primeiros prompts: nenhum ainda." in c, c)


def test_intencao_vazia_corte_em_120():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        longo = "".join(chr(97 + i % 26) for i in range(125))
        c = ctx(run_hook(r.path, session_id=SID, prompt=longo))
        check("prompt cortado em 120 caracteres (119 + …)",
              f'"{longo[:119]}…"' in c, c)
        curto = "y" * 120
        c = ctx(run_hook(r.path, session_id=SID, prompt=curto))
        check("prompt de exatos 120 caracteres não é cortado", f'"{curto}"' in c, c)


def test_intencao_vazia_log_multilinha_e_titulo():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")
        write_log(r, [("2026-10-16", "18:01:00", "linha um\n# meu título\nlinha dois")])
        c = ctx(run_hook(r.path, session_id=SID, prompt="linha um # meu título linha dois"))
        check("prompt de várias linhas vira uma, título markdown preservado",
              '"linha um # meu título linha dois"' in c and c.count("linha um") == 1, c)


def test_intencao_vazia_registro_no_clone_principal():
    """Numa worktree ligada, o log é da worktree e o registro é do clone principal."""
    with Repo() as r:
        wt = Path(r.tmp.name) / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "--detach", str(wt)],
                       cwd=r.path, check=True)
        (wt / ".claude").mkdir()
        (wt / ".claude" / "session-mode").write_text("modo: exploracao\n")
        register(r, SID, "2026-10-16T18:00:00+00:00")  # no clone principal
        (wt / ".claude" / "session-log.md").write_text(
            "# Session log\n\n## 2026-10-15\n\n### 10:00:00 UTC\n\nvelho\n\n"
            "## 2026-10-16\n\n### 18:01:00 UTC\n\nda sessão\n\n")
        # o prompt do turno é OUTRO: se o registro não for achado, o fallback
        # (prompts de hoje) não vê nada do log, e só o prompt do turno sobra
        c = ctx(run_hook(wt, session_id=SID, prompt="o do turno"))
        check("worktree ligada: acha o início no registro do clone principal",
              '"da sessão" | "o do turno"' in c and "velho" not in c, c)


def test_intencao_mesma_sessao_tolerante():
    with Repo() as r:
        write_intent(r)
        c = ctx(run_hook(r.path))  # payload sem session_id
        check("payload sem session_id: não acusa outra sessão",
              "Passo 2/4" in c and "outra sessão" not in c, c)
    with Repo() as r:
        write_intent(r, session_id="")
        c = ctx(run_hook(r.path, session_id=SID))
        check("arquivo sem session_id: não acusa outra sessão",
              "Passo 2/4" in c and "outra sessão" not in c, c)
    with Repo() as r:
        write_intent(r, session_id=SID)
        c = ctx(run_hook(r.path, session_id=SID[:8]))
        check("id gravado mais longo que o atual: mesma sessão por prefixo",
              "Passo 2/4" in c and "outra sessão" not in c, c)


def test_intencao_outra_sessao_detalhes():
    with Repo() as r:
        write_intent(r, session_id="aaaaaaaa")
        c = ctx(run_hook(r.path, session_id=SID))
        check("outra sessão: data com hora (aberto_em)", "2026-10-16 18:30 UTC" in c, c)
        check("outra sessão: manda não tratar como atual", "Não a trate como a desta sessão" in c, c)
        check("outra sessão: mostra o propósito gravado",
              '"institucionalizar as quatro perguntas"' in c, c)
    with Repo() as r:
        write_intent(r, session_id="aaaaaaaa", aberto_em="")
        c = ctx(run_hook(r.path, session_id=SID))
        check("outra sessão sem aberto_em: 'data desconhecida'", "data desconhecida" in c, c)


def test_intencao_passo_fora_do_plano_cai_no_1():
    for valor in ("0", "6"):
        with Repo() as r:
            write_intent(r)
            f = r.path / ".claude" / "session-intent"
            f.write_text(f.read_text().replace("passo: 2", f"passo: {valor}"))
            c = ctx(run_hook(r.path, session_id=SID))
            check(f"passo {valor} com plano de 4: cai no passo 1", "Passo 1/4" in c, c)
    with Repo() as r:
        write_intent(r)
        f = r.path / ".claude" / "session-intent"
        f.write_text(f.read_text().replace("passo: 2", "passo: 5"))
        c = ctx(run_hook(r.path, session_id=SID))
        check("passo M+1 (5 com plano de 4) é plano cumprido, não passo 1",
              "Plano cumprido (4/4)" in c, c)


def test_intencao_idade_bordas():
    with Repo() as r:
        write_intent(r, passo_desde="2026-10-16T21:40:00Z")
        write_log(r, [("2026-10-16", "21:39:59", "antes"),
                      ("2026-10-16", "21:40:00", "no mesmo segundo")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("prompt no mesmo segundo do passo_desde conta", "(há 1 turno)" in c, c)
    with Repo() as r:
        write_intent(r, passo_desde="2026-10-16T21:40:00Z")
        write_log(r, [("2026-10-16", "21:39:00", "antes")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("nenhum prompt depois do cursor: '(há 0 turnos)'", "(há 0 turnos)" in c, c)
    with Repo() as r:
        write_intent(r, passo_desde="2026-10-16T21:40:00")  # sem fuso: lido como UTC
        write_log(r, [("2026-10-16", "21:41:00", "depois")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("passo_desde sem fuso é lido como UTC", "(há 1 turno)" in c, c)


def test_intencao_plano_cumprido_ponto_de_parada():
    with Repo() as r:
        write_intent(r, passo=5, para_quando="q" * 400)
        c = ctx(run_hook(r.path, session_id=SID))
        check("plano cumprido: rótulo 'ponto de parada:'", "; ponto de parada: q" in c, c)
        check("plano cumprido: ponto de parada cortado em 160",
              "q" * 160 not in c and "q" * 159 + "…" in c, c)
    with Repo() as r:
        write_intent(r, passo=5, para_quando="")
        c = ctx(run_hook(r.path, session_id=SID))
        check("plano cumprido sem ponto de parada: sem o rótulo",
              "ponto de parada" not in c and "Plano cumprido (4/4). Próximo" in c, c)


def test_intencao_penultimo_passo_aponta_o_ultimo():
    with Repo() as r:
        write_intent(r, passo=3)
        c = ctx(run_hook(r.path, session_id=SID))
        check("penúltimo passo: próximo é o último passo, não o wrap-up",
              "Passo 3/4: rodar advisors" in c and "Próximo: decidir." in c
              and "wrap-up" not in c, c)


def test_intencao_idade_ignora_entrada_vazia_do_log():
    with Repo() as r:
        write_intent(r, passo_desde="2026-10-16T21:40:00Z")
        write_log(r, [("2026-10-16", "21:41:00", "   "),
                      ("2026-10-16", "21:42:00", "de verdade")])
        c = ctx(run_hook(r.path, session_id=SID))
        check("entrada vazia do log não conta como turno", "(há 1 turno)" in c, c)


def test_intencao_ultimo_passo_aponta_wrap_up():
    with Repo() as r:
        write_intent(r, passo=4)
        c = ctx(run_hook(r.path, session_id=SID))
        check("último passo: próximo é o wrap-up",
              "Passo 4/4: decidir" in c and "plano cumprido: hora de /common:wrap-up" in c, c)


def test_intencao_plano_cumprido():
    with Repo() as r:
        write_intent(r, passo=5)
        c = ctx(run_hook(r.path, session_id=SID))
        il = intent_lines(c)
        check("plano cumprido: diz que cumpriu M/M e aponta wrap-up",
              "Plano cumprido (4/4)" in c and "/common:wrap-up" in c, c)
        check("plano cumprido: mostra o ponto de parada", "doc decidido" in c, c)
        check("plano cumprido: uma linha", len(il) == 1, il)


def test_intencao_sem_modo_ainda_e_injetada():
    with Repo() as r:
        write_intent(r)
        c = ctx(run_hook(r.path, session_id=SID))
        check("intenção sem modo: injetada", "Passo 2/4" in c and "[modo]" not in c, c)


def test_intencao_de_outra_sessao_vira_pergunta():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        write_intent(r, session_id="aaaaaaaa")
        p = run_hook(r.path, session_id=SID)
        c = ctx(p)
        il = intent_lines(c)
        check("outra sessão: diz que foi gravada em outra sessão, com a data",
              "outra sessão" in c and "2026-10-16" in c, c)
        check("outra sessão: pergunta continuo ou abro nova",
              "continuo ou abro nova" in c, c)
        check("outra sessão: diz como responder (continuar / gravar)",
              "cepa-intencao continuar" in c and "--motivo" in c, c)
        check("outra sessão: NÃO exibe o passo como atual", "Passo 2/4" not in c, c)
        check("outra sessão: teto de duas linhas", len(il) == 2, il)


def test_intencao_continuar_resolve_a_pergunta():
    """O `continuar` do escritor é o que faz a pergunta de D1 parar de voltar."""
    with Repo() as r:
        write_intent(r, session_id="aaaaaaaa")
        e = {**os.environ, "CLAUDE_CODE_SESSION_ID": SID}
        w = subprocess.run([sys.executable, str(REPO / "common" / "bin" / "cepa-intencao"),
                            "continuar"], cwd=r.path, env=e, capture_output=True, text=True)
        c = ctx(run_hook(r.path, session_id=SID))
        check("continuar: o hook volta a exibir a intenção como atual",
              w.returncode == 0 and "Passo 2/4" in c and "outra sessão" not in c,
              (w.stderr, c))


def test_intencao_calada_no_cepa_until():
    with Repo() as r:
        write_mode(r, "modo: construcao\n")
        write_intent(r, session_id="aaaaaaaa")
        c = ctx(run_hook(r.path, env={"CEPA_UNTIL_RUN": "1"}, session_id=SID))
        check("cepa-until: sem intenção no contexto", "[intenção]" not in c, c)
        check("cepa-until: o modo segue", "[modo]" in c, c)
    with Repo() as r:
        write_intent(r)
        p = run_hook(r.path, env={"CEPA_UNTIL_RUN": "1"}, session_id=SID)
        check("cepa-until sem modo: silêncio total", p.stdout.strip() == "", repr(p.stdout))


def test_intencao_corrompida_nao_quebra():
    with Repo() as r:
        write_mode(r, "modo: exploracao\n")
        (r.path / ".claude" / "session-intent").write_text("::: lixo\n\x00passo: x\n")
        p = run_hook(r.path, session_id=SID)
        c = ctx(p)
        check("intenção corrompida: rc=0", p.returncode == 0, p.stderr)
        check("intenção corrompida: tratada como vazia",
              "ainda não tem intenção gravada" in c, c)
    with Repo() as r:
        write_intent(r, passo_desde="ontem")
        f = r.path / ".claude" / "session-intent"
        f.write_text(f.read_text().replace("passo: 2", "passo: abc"))
        p = run_hook(r.path, session_id=SID)
        c = ctx(p)
        check("passo e passo_desde inválidos: rc=0, cai no passo 1 sem idade",
              p.returncode == 0 and "Passo 1/4" in c and "(há" not in c, (p.stderr, c))


def test_intencao_respeita_kill_switch():
    with Repo() as r:
        write_intent(r)
        p = run_hook(r.path, env={"CEPA_MODO": "off"}, session_id=SID)
        check("CEPA_MODO=off: cala a intenção também", p.stdout.strip() == "", repr(p.stdout))


# --- ajuda do menu de modos -------------------------------------------------
# O menu do `cepa` listava os sete nomes e mais nada. Quem não lembra o que
# "reforma" cobra escolhia pelo nome — e o modo, que é fronteira, virava rótulo.
# A ajuda mostra o propósito de cada modo lido de _modos.py (fonte única), sem
# abrir o doc de 307 linhas.

def test_ajuda_nao_interativa():
    """`cepa --modo ajuda` imprime os propósitos e NÃO sobe sessão nenhuma."""
    with Repo() as r:
        p = r.run("--modo", "ajuda")
        saida = p.stdout + p.stderr
        check("ajuda: rc=0", p.returncode == 0, str(p.returncode) + saida)
        check("ajuda: não lança o claude", "CLAUDE_ARGS" not in p.stdout, p.stdout)
        check("ajuda: não grava modo", not r.mode_file.exists())
        check("ajuda: nomeia os sete modos",
              all(m in saida for m in
                  ("exploracao", "descoberta", "design", "construcao",
                   "reforma", "reflexao", "documentacao")), saida)
        check("ajuda: diz o propósito, não só o nome",
              "comportamento externo" in saida or "sem mudar nada que se veja" in saida,
              saida)


def _pty_run(repo, teclado):
    """Roda o cepa com um terminal de verdade e digita `teclado` nele.

    O `cepa` lê de /dev/tty, então não basta um pipe: o processo precisa de um
    terminal de controle próprio (setsid + TIOCSCTTY), senão /dev/tty apontaria
    para o terminal de quem roda os testes.
    """
    import fcntl, pty, termios, time
    mestre, escravo = pty.openpty()

    def ctty():
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    proc = subprocess.Popen(
        [str(CEPA), "--resume"], cwd=repo.path,
        env={**os.environ, "CLAUDE_WT_CLAUDE_BIN": str(repo.fake),
             "CEPA_PREFLIGHT": "off"},
        stdin=escravo, stdout=escravo, stderr=escravo,
        preexec_fn=ctty, close_fds=True,
    )
    os.close(escravo)
    for tecla in teclado:
        time.sleep(0.4)
        os.write(mestre, tecla.encode())
    buf = b""
    fim = time.time() + 20
    while time.time() < fim:
        try:
            pedaco = os.read(mestre, 65536)
        except OSError:
            break
        if not pedaco:
            break
        buf += pedaco
        if proc.poll() is not None and b"CLAUDE_ARGS" in buf:
            break
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    os.close(mestre)
    return proc.returncode, buf.decode("utf-8", "replace")


def test_ajuda_no_menu_e_reapresenta():
    """No menu, `?` mostra os propósitos e o menu volta — não é escolha inválida."""
    with Repo() as r:
        rc, saida = _pty_run(r, ["?\n", "construcao\n"])
        check("menu: oferece a ajuda", "?" in saida and "ajuda" in saida, saida)
        check("menu ?: mostra o propósito",
              "comportamento externo" in saida or "sem mudar nada que se veja" in saida,
              saida)
        check("menu ?: não trata como modo desconhecido",
              "modo desconhecido" not in saida, saida)
        check("menu ?: pergunta de novo", saida.count("modo?") >= 2, saida)
        check("menu ?: a escolha seguinte vale", rc == 0, str(rc) + saida)
        body = r.mode_file.read_text() if r.mode_file.exists() else ""
        check("menu ?: grava o modo escolhido", "modo: construcao" in body, body)


def main():
    print("test_cepa_modo")
    for fn in (test_modo_valido, test_modo_invalido, test_sem_modo_sem_tty,
               test_kill_switch, test_reforma_orcamento,
               test_ajuda_nao_interativa, test_ajuda_no_menu_e_reapresenta,
               test_hook_injeta_modo_e_saida, test_hook_reforma_mostra_orcamento,
               test_hook_silencioso_sem_modo, test_hook_respeita_kill_switch,
               test_hook_nunca_quebra_o_turno,
               test_intencao_vazia_traz_os_primeiros_prompts,
               test_intencao_vazia_primeiro_turno_usa_o_prompt_atual,
               test_intencao_vazia_sem_registro_cai_para_hoje,
               test_intencao_vazia_sem_modo_e_silenciosa,
               test_intencao_normal_passo_idade_proximo,
               test_intencao_normal_um_turno_no_singular,
               test_intencao_corta_proposito_e_passo_longos,
               test_intencao_vazia_prompt_do_turno_e_log_parcial,
               test_intencao_vazia_corte_em_120, test_intencao_vazia_log_multilinha_e_titulo,
               test_intencao_vazia_registro_no_clone_principal,
               test_intencao_mesma_sessao_tolerante, test_intencao_outra_sessao_detalhes,
               test_intencao_passo_fora_do_plano_cai_no_1, test_intencao_idade_bordas,
               test_intencao_plano_cumprido_ponto_de_parada,
               test_intencao_penultimo_passo_aponta_o_ultimo,
               test_intencao_idade_ignora_entrada_vazia_do_log,
               test_intencao_ultimo_passo_aponta_wrap_up, test_intencao_plano_cumprido,
               test_intencao_sem_modo_ainda_e_injetada,
               test_intencao_de_outra_sessao_vira_pergunta,
               test_intencao_continuar_resolve_a_pergunta,
               test_intencao_calada_no_cepa_until, test_intencao_corrompida_nao_quebra,
               test_intencao_respeita_kill_switch):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
