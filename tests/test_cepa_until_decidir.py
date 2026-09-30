#!/usr/bin/env python3
"""cepa-until decidir — o fim do run pergunta, em vez de só contar.

Em 30/09 o dono leu no fim de um run "a fila acabou, e 14 ficaram adiados
(cada um com o motivo, no relatório)" e "Fica com você: WEGO-2336 (o motivo
está na linha de cada um, em Itens)", e perguntou o que fazer com aquilo. A
aterrissagem aparecia como comando para copiar, e a pergunta que travava o
WEGO-2336 estava no meio de 600 caracteres de evidência.

O que estes casos provam:

  - o `cepa-plan finish --pergunta` grava a pergunta fechada do item, e o
    `queue` a devolve junto com o adiado;
  - o `cepa-plan responde` devolve um `blocked` para `pending` e fecha a rota
    humana, com a resposta do dono na evidência, e SÓ num terminal (um agente
    de `claude -p` não tem TTY e não fecha a rota no lugar do humano);
  - o `decide` pergunta aterrissar e cada item que só o dono destrava, aplica
    cada resposta e deixa o resto para depois com o comando de volta;
  - o run de verdade, num terminal, termina perguntando; sem terminal, lista
    as pendências com o comando `cepa-until decidir`.

Rode com `python3 tests/test_cepa_until_decidir.py`.
"""

import importlib.machinery
import importlib.util
import json
import os
import pty
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, fake_claude, item, monta_repo, roda)

CEPA_PLAN = CEPA_UNTIL.parent / "cepa-plan"
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def carrega_modulo():
    loader = importlib.machinery.SourceFileLoader("cepa_until", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def em_tty(cmd, cwd, entradas=(), env=None, timeout=120):
    """Roda `cmd` num pseudo-terminal e responde cada pergunta quando ela
    aparece: `entradas` é uma lista de (trecho que a tela mostra, resposta)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(cmd[0], cmd, env or dict(os.environ))
    saida, fila, fim = "", list(entradas), time.time() + timeout
    while time.time() < fim:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                dado = os.read(fd, 4096)
            except OSError:
                break
            if not dado:
                break
            saida += dado.decode(errors="replace")
        while fila and fila[0][0] in saida:
            gatilho, resposta = fila.pop(0)
            # Consome o gatilho para a próxima pergunta igual não casar nele.
            saida = saida.replace(gatilho, f"<{gatilho}>", 1)
            os.write(fd, (resposta + "\n").encode())
    _, st = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(st), saida


def plano_de(raiz):
    return raiz / ".claude" / "programs" / "fila" / "plan.yaml"


def itens_de(raiz):
    return {it["id"]: it for it in
            yaml.safe_load(plano_de(raiz).read_text())["items"]}


def test_finish_grava_a_pergunta_e_o_queue_a_devolve():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        p = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "finish", "fila", "a1",
             "--status", "blocked", "--evidence", "não há produção para medir",
             "--pergunta", "Fecho o card como medir depois do go-live?",
             "--repo", str(raiz)], capture_output=True, text=True)
        check("finish com --pergunta sai 0", p.returncode == 0, p.stderr)
        check("...e grava owner_question",
              itens_de(raiz)["a1"].get("owner_question")
              == "Fecho o card como medir depois do go-live?",
              itens_de(raiz)["a1"])
        q = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "queue", "fila", "--json",
             "--repo", str(raiz)], capture_output=True, text=True)
        adiado = json.loads(q.stdout)["deferred"][0]
        check("o queue devolve a pergunta junto com o adiado",
              adiado.get("question", "").startswith("Fecho o card"), adiado)
        check("...e a evidência inteira, não só o detalhe",
              adiado.get("evidence") == "não há produção para medir", adiado)


def test_responde_recusa_sem_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1", status="blocked")])
        p = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "responde", "fila", "a1",
             "--resposta", "pode seguir", "--repo", str(raiz)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check("sem TTY, `responde` recusa", p.returncode == 2, p.stdout)
        check("...e diz que só o dono responde", "terminal" in p.stderr,
              p.stderr)
        check("...e o item continua `blocked`",
              itens_de(raiz)["a1"]["status"] == "blocked")


def test_responde_no_terminal_destrava_blocked_e_fecha_rota():
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        travado["evidence"] = "não há produção"
        travado["owner_question"] = "Fecho o card?"
        rota = item("a2", human_pending="valide o login real")
        raiz = monta_repo(tmp, [travado, rota])
        rc, out = em_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a1", "--resposta", "vira item do checklist",
                          "--repo", str(raiz)], str(raiz))
        a1 = itens_de(raiz)["a1"]
        check("no terminal, `responde` sai 0", rc == 0, out)
        check("o blocked volta para pending", a1["status"] == "pending", a1)
        check("...com a resposta do dono na evidência",
              "vira item do checklist" in a1["evidence"], a1["evidence"])
        check("...guardando a evidência anterior",
              "não há produção" in a1["evidence"], a1["evidence"])
        check("...e a pergunta respondida sai do item",
              "owner_question" not in a1, a1)
        rc, out = em_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a2", "--resposta", "login ok, trilha gravada",
                          "--repo", str(raiz)], str(raiz))
        a2 = itens_de(raiz)["a2"]
        check("a rota humana fecha", a2.get("human_pending") is None, a2)
        check("...e o texto da rota fica na evidência",
              "valide o login real" in a2["evidence"]
              and "trilha gravada" in a2["evidence"], a2["evidence"])


def test_decide_pergunta_e_aplica_cada_resposta():
    m = carrega_modulo()
    adiados = [
        {"id": "W-1", "title": "medir produção", "reason": "bloqueado-antes",
         "question": None, "human_pending": None,
         "evidence": "não existe produção do wego-acessos"},
        {"id": "W-2", "title": "login real", "reason": "human_pending",
         "question": None, "human_pending": "rode o login do Bradesco",
         "evidence": None},
        {"id": "W-3", "title": "outra", "reason": "bloqueado-antes",
         "question": "Largo o card?", "human_pending": None,
         "evidence": "a evidência longa"},
        {"id": "W-4", "title": "cascata", "reason": "depende-de-adiado"},
    ]
    analise = m.decisoes_da_analise(
        "texto\n```json cepa-decisoes\n"
        '{"aterrissar": {"recomendo": "sim", "porque": "build verde"},'
        ' "itens": [{"id": "W-1", "pergunta": "Movo para o checklist?",'
        ' "recomendo": "sim", "porque": "não trava a fila"}]}\n```\n')
    check("o bloco da análise é lido",
          analise["itens"]["W-1"]["pergunta"] == "Movo para o checklist?",
          analise)
    est = {"acoes": [{"id": "aterrissar", "frase": "leva 5 commits"}]}
    respostas = iter(["s", "r", "vira checklist", "", "e", "q"])
    tela, respondidos, aterrissou = [], [], []
    aplicados, depois = m.decide(
        Path("/nao/existe"), "fila", "run1", est, adiados, analise,
        pergunta=lambda _p: next(respostas), saida=tela.append,
        responde=lambda i, t: (respondidos.append((i, t)), (0, f"{i} ok"))[1],
        aterrissa=lambda: aterrissou.append(1) or 0)
    texto = "\n".join(tela)
    check("pergunta aterrissar e aterrissa com s", aterrissou == [1], texto)
    check("...mostrando a recomendação da análise",
          "Recomendo sim: build verde" in texto, texto)
    check("a pergunta da análise aparece no lugar da evidência",
          "Movo para o checklist?" in texto, texto)
    check("a resposta digitada vai para o `responde`",
          respondidos == [("W-1", "vira checklist")], respondidos)
    check("rota humana mostra a rota verbatim",
          "rode o login do Bradesco" in texto, texto)
    check("[e] mostra a evidência inteira do item com pergunta",
          "a evidência longa" in texto, texto)
    check("q encerra e o que sobrou fica para depois",
          any(x.startswith("W-3") for x in depois)
          and any(x.startswith("W-2") for x in depois), depois)
    check("cascata não vira pergunta, só aparece como não sendo do dono",
          "W-4 (depende de um item adiado" in texto, texto)
    check("o fecho diz como voltar",
          "cepa-until decidir fila/run1" in texto, texto)
    check("aplicados listam aterrissar e W-1",
          aplicados == ["aterrissar", "W-1: W-1 ok"], aplicados)


def test_analise_sem_bloco_ou_quebrada_nao_derruba():
    m = carrega_modulo()
    check("sem bloco devolve vazio", m.decisoes_da_analise("só texto") == {})
    check("JSON quebrado devolve vazio",
          m.decisoes_da_analise("```json cepa-decisoes\n{quebrado\n```") == {})


BLOQUEIA_COM_PERGUNTA = (
    "ident = primeiro_pendente()\n"
    "if ident == 'a1':\n"
    "    marca(ident, status='blocked', evidence='não há produção',\n"
    "          owner_question='Fecho o card como medir depois do go-live?')\n"
    "elif ident:\n"
    "    marca(ident, status='done')\n")


def test_run_sem_terminal_lista_as_pendencias_e_o_comando():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOQUEIA_COM_PERGUNTA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        check("o fim lista o que espera o dono",
              "esperam por você" in p.stdout, p.stdout[-1500:])
        check("...com a pergunta do item, não a evidência",
              "Fecho o card como medir depois do go-live?" in p.stdout,
              p.stdout[-1500:])
        check("...e o comando para responder",
              "cepa-until decidir fila/" in p.stdout, p.stdout[-800:])


def test_run_no_terminal_termina_perguntando_e_aplica():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BLOQUEIA_COM_PERGUNTA)
        env = dict(os.environ)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(plano_de(raiz))
        env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
        env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
        rc, out = em_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(raiz),
             "--for", "2h", "--sem-verify", "--sem-analise"], str(raiz),
            entradas=[("[r] respondo e devolvo", "r"),
                      ("Sua resposta", "vira item do checklist")], env=env)
        check("o run sai 0", rc == 0, out[-1500:])
        check("pergunta o item travado com a pergunta gravada",
              "Fecho o card como medir depois do go-live?" in out, out[-1500:])
        a1 = itens_de(raiz)["a1"]
        check("a resposta volta o item para a fila",
              a1["status"] == "pending"
              and "vira item do checklist" in a1["evidence"], a1)


def env_do_run(tmp, raiz, binv):
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plano_de(raiz))
    env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
    env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
    return env


def test_run_no_terminal_pergunta_aterrissar_e_aterrissa_com_s():
    """AC1: o `s` no prompt do fim do run aterrissa de verdade."""
    from test_cepa_until_aterrissar import com_origin, estado
    from test_cepa_until_branch_da_noite import TRABALHA, VERIFY, git
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        com_origin(raiz)
        binv = fake_claude(tmp, TRABALHA)
        rc, out = em_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(raiz),
             "--for", "2h", "--verify", VERIFY, "--sem-analise"], str(raiz),
            entradas=[("Aterrisso agora?", "s")],
            env=env_do_run(tmp, raiz, binv), timeout=240)
        check("o run sai 0", rc == 0, out[-1500:])
        check("o fim pergunta se aterrissa", "Aterrisso agora?" in out,
              out[-1500:])
        log = git(raiz, "log", "--format=%s", "HEAD").splitlines()
        check("com s, o commit do item chega à main", "a1" in log, str(log))
        check("...e o estado do run vira aterrissado",
              estado(raiz).get("estado") == "aterrissado", str(estado(raiz)))


def test_reservado_nao_vira_pergunta():
    """AC3: outra sessão viva no item não é assunto do dono."""
    m = carrega_modulo()
    tela, perguntas = [], []
    m.decide(Path("/nao/existe"), "fila", "run1", {},
             [{"id": "W-9", "title": "em outra sessão", "reason": "reservado"},
              {"id": "W-8", "title": "cascata",
               "reason": "depende-de-adiado"}],
             {}, pergunta=lambda p_: perguntas.append(p_) or "",
             saida=tela.append)
    texto = "\n".join(tela)
    check("nenhuma pergunta é feita", perguntas == [], perguntas)
    check("...e o fecho diz que nada espera por você",
          "nada espera por você" in texto, texto)


def test_decidir_como_processo_com_e_sem_terminal():
    """AC5: `cepa-until decidir <fila>/<run>` depois do run, e AC2 na ponta:
    a rota humana fecha respondendo dentro do decide."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = ("ident = primeiro_pendente()\n"
                 "if ident == 'a1':\n"
                 "    marca(ident, status='blocked', evidence='sem produção',\n"
                 "          owner_question='Fecho o card?')\n"
                 "elif ident == 'a2':\n"
                 "    marca(ident, status='pending', evidence='feito',\n"
                 "          human_pending='valide o login real')\n")
        binv = fake_claude(tmp, corpo)
        roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        run_id = sorted((raiz / ".claude" / "programs" / "fila" / "until")
                        .glob("*.estado.json"))[-1].name.split(".")[0]
        cmd = [sys.executable, str(CEPA_UNTIL), "decidir", f"fila/{run_id}",
               "--repo", str(raiz)]
        p = subprocess.run(cmd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("sem terminal, decidir sai 0 e lista", p.returncode == 0
              and "Fecho o card?" in p.stdout
              and "valide o login real" in p.stdout, p.stdout + p.stderr)
        check("...sem mexer na fila",
              itens_de(raiz)["a1"]["status"] == "blocked")
        rc, out = em_tty(cmd, str(raiz), entradas=[
            ("[r] respondo e devolvo", "r"), ("Sua resposta", "vira checklist"),
            ("[f] já fiz", "f"), ("Sua resposta", "login ok")])
        a1, a2 = itens_de(raiz)["a1"], itens_de(raiz)["a2"]
        check("no terminal, decidir aplica o blocked",
              rc == 0 and a1["status"] == "pending"
              and "vira checklist" in a1["evidence"], out[-1200:])
        check("...e fecha a rota humana com a resposta",
              a2.get("human_pending") is None
              and "login ok" in a2["evidence"], a2)


def test_instrucoes_dos_agentes_pedem_a_pergunta():
    """AC6: sem estas linhas, o agente volta a travar item sem pergunta e a
    análise volta a não gravar o bloco que o terminal lê."""
    comandos = CEPA_UNTIL.parent.parent / "commands"
    review = (comandos / "until-review.md").read_text(encoding="utf-8")
    drain = (comandos / "drain-plan.md").read_text(encoding="utf-8")
    check("until-review manda gravar o bloco cepa-decisoes",
          "```json cepa-decisoes" in review, "")
    check("...cobrindo todos os adiados da fila, pelo queue",
          "deferred" in review and "cepa-plan queue" in review, "")
    check("...e diz que as ações vêm da lista fechada",
          "lista fechada" in review, "")
    check("drain-plan manda gravar --pergunta ao travar",
          "--pergunta" in drain, "")


REVIEW_COM_BLOCO = (
    "if ARGS and ARGS[1].startswith('/common:until-review'):\n"
    "    print('RELATORIO')\n"
    "    print('```json cepa-decisoes')\n"
    "    print(json.dumps({'itens': [{'id': 'a1', 'pergunta': "
    "'Movo a medição para o checklist?', 'recomendo': 'sim', "
    "'porque': 'não trava a fila'}]}))\n"
    "    print('```')\n"
    "    sys.exit(0)\n")


def test_fim_com_analise_pergunta_com_a_redacao_do_bloco():
    """Caminho de saída 3 (com análise): a pergunta vem do bloco da análise
    quando o agente não gravou nenhuma."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = REVIEW_COM_BLOCO + (
            "marca(primeiro_pendente(), status='blocked', "
            "evidence='evidência crua longa')\n")
        binv = fake_claude(tmp, corpo)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--com-analise"])
        fim = p.stdout.split("── esperam por você")[-1]
        check("com análise, o fim lista o que espera o dono",
              "── esperam por você" in p.stdout, p.stdout[-1200:])
        check("...com a pergunta redigida pela análise",
              "Movo a medição para o checklist?" in fim, fim)


def test_fim_parado_pela_cota_tambem_pergunta():
    """Caminho de saída 2 (cota): a análise não roda, mas as perguntas sim."""
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        travado["evidence"] = "sem produção"
        travado["owner_question"] = "Fecho o card?"
        raiz = monta_repo(tmp, [travado, item("a2")])
        corpo = ("if ARGS and ARGS[1].startswith('/common:until-review'):\n"
                 "    sys.exit(0)\n"
                 "print(json.dumps({'type': 'result', 'result': "
                 "\"You've hit your session limit\"}))\n")
        binv = fake_claude(tmp, corpo)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--com-analise"])
        from test_cepa_until import ledger_de
        fim = [e for e in ledger_de(raiz) if e["evento"] == "run_end"][0]
        check("o run parou pela cota", fim["motivo"] == "limite-de-uso", str(fim))
        check("...e mesmo assim termina perguntando",
              "── esperam por você" in p.stdout
              and "Fecho o card?" in p.stdout, p.stdout[-1200:])


def test_lista_sem_terminal_filtra_o_que_nao_e_do_dono():
    m = carrega_modulo()
    tela = []
    m.pendencias_em_texto(
        "fila", "run1", {"acoes": [{"id": "aterrissar", "frase": "leva 3"}]},
        [{"id": "W-1", "reason": "human_pending",
          "human_pending": "rode o login real"},
         {"id": "W-2", "reason": "reservado", "detail": "sessão viva"},
         {"id": "W-3", "reason": "depende-de-adiado", "detail": "de W-1"}],
        {}, saida=tela.append)
    texto = "\n".join(tela)
    check("sem terminal, lista aterrissar", "aterrissar: leva 3" in texto,
          texto)
    check("...e a rota humana verbatim", "rode o login real" in texto, texto)
    check("...contando 2, sem reservado nem cascata",
          "esperam por você: 2" in texto and "W-2" not in texto
          and "W-3" not in texto, texto)


def test_bloco_que_nao_e_objeto_e_ignorado():
    m = carrega_modulo()
    check("lista no lugar de objeto devolve vazio",
          m.decisoes_da_analise("```json cepa-decisoes\n[1, 2]\n```") == {})


def test_pergunta_sai_quando_o_item_volta_a_andar_e_reserva_some_no_responde():
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        travado["owner_question"] = "Fecho?"
        outro = item("a2", status="blocked")
        outro["evidence"] = "x"
        outro["claimed_by"] = {"session": "morta"}
        raiz = monta_repo(tmp, [travado, outro])
        subprocess.run(
            [sys.executable, str(CEPA_PLAN), "finish", "fila", "a1",
             "--status", "pending", "--evidence", "destravou",
             "--repo", str(raiz)], capture_output=True, text=True, check=True)
        check("finish pending sem --pergunta tira a pergunta velha",
              "owner_question" not in itens_de(raiz)["a1"], itens_de(raiz)["a1"])
        em_tty([sys.executable, str(CEPA_PLAN), "responde", "fila", "a2",
                "--resposta", "segue", "--repo", str(raiz)], str(raiz))
        check("responde limpa a reserva do item",
              "claimed_by" not in itens_de(raiz)["a2"], itens_de(raiz)["a2"])


def test_entrada_hostil_nao_corrompe_a_fila_nem_sai_da_pasta():
    """Nível adversarial: a resposta é texto livre do dono e vai para o YAML
    da fila; o alvo do `decidir` vira caminho no disco."""
    hostil = "a: b\n- c # x 'q' \"z\" {{}} [1] ---\n!!python/object:os.system"
    with tempfile.TemporaryDirectory() as tmp:
        travado = item("a1", status="blocked")
        raiz = monta_repo(tmp, [travado])
        rc, out = em_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                          "a1", "--resposta", hostil, "--repo", str(raiz)],
                         str(raiz))
        check("resposta com sintaxe de YAML é aceita", rc == 0, out)
        v = subprocess.run([sys.executable, str(CEPA_PLAN), "validate",
                            str(plano_de(raiz))], capture_output=True, text=True)
        check("...a fila continua válida", v.returncode == 0, v.stdout + v.stderr)
        ev = itens_de(raiz)["a1"]["evidence"]
        check("...e o texto fica como texto, numa linha",
              "!!python/object:os.system" in ev and "\n" not in ev, ev)
        vazio = em_tty([sys.executable, str(CEPA_PLAN), "responde", "fila",
                        "a1", "--resposta", "   ", "--repo", str(raiz)],
                       str(raiz))
        check("resposta só de espaços é recusada", vazio[0] == 2, vazio[1])
        # Um estado de verdade fora da pasta do run: sem ele, o alvo com `..`
        # recusava só porque o arquivo não existia (achado da prova, 30/09).
        fora = raiz / ".claude" / "programs" / "x.estado.json"
        fora.write_text('{"acoes": []}')
        # `until/..` só resolve se a pasta do run existir, como existe depois
        # do primeiro run.
        (raiz / ".claude" / "programs" / "fila" / "until").mkdir()
        for alvo in ("../../etc/passwd", "semBarra", "fila/../../x",
                     "fila/../x", "../fila/x"):
            p_ = subprocess.run([sys.executable, str(CEPA_UNTIL), "decidir",
                                 alvo, "--repo", str(raiz)],
                                capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=60)
            check(f"alvo {alvo!r} recusa com 2, sem traceback",
                  p_.returncode == 2 and "Traceback" not in p_.stderr
                  and "esperam por você" not in p_.stdout,
                  p_.stdout + p_.stderr)


def test_run_ja_aterrissado_nao_pergunta_de_novo():
    """No run WEGO 2026-09-29-2059 o dono aterrissou às 07:15 e o `decidir`
    ainda listava a aterrissagem: a ação fica no estado como registro."""
    m = carrega_modulo()
    est = {"estado": "aterrissado",
           "acoes": [{"id": "aterrissar", "frase": "leva 5"}]}
    tela, perguntas = [], []
    m.decide(Path("/nao/existe"), "fila", "run1", est, [], {},
             pergunta=lambda p_: perguntas.append(p_) or "", saida=tela.append)
    check("run aterrissado não pergunta aterrissar", perguntas == [], perguntas)
    tela2 = []
    m.pendencias_em_texto("fila", "run1", est, [], {}, saida=tela2.append)
    check("...nem lista sem terminal", tela2 == [], tela2)


def main():
    print("cepa-until decidir — o fim do run pergunta\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
