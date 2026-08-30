#!/usr/bin/env python3
"""Testes do `common/bin/cepa-until` — o supervisor de janela de tempo.

Rode com `python3 tests/test_cepa_until.py` (só precisa do PyYAML).

## O que estes testes provam, e o que NÃO provam

O supervisor tem uma responsabilidade só: decidir QUANDO disparar mais um
subprocesso e quando parar. Tudo o que acontece DENTRO do subprocesso é do
`/common:drain-plan` e da topologia, e nenhum teste aqui toca nisso.

Então o `claude` é substituído por um script falso no PATH, que faz o que o
drain-plan faria com o plano (marcar `done`, abrir `human_pending`, não fazer
nada, travar). Isso deixa medir exatamente as quatro decisões do supervisor:

  - o prazo é respeitado ANTES de começar um item, nunca no meio dele;
  - o disjuntor conta falhas SEGUIDAS e progresso zera a contagem;
  - `human_pending` é PROGRESSO — a dívida com o humano não pode parecer falha,
    senão três itens adiados matam a noite às 22h;
  - a verdade do desfecho é o STATUS NO PLANO, não o código de saída do
    subprocesso (um `claude` que sai 0 sem mexer no item é falha).

O que estes testes NÃO provam: que uma noite de 12h de verdade aguenta. Isso é
uma noite de calendário, e só o primeiro run real diz.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── cenário ─────────────────────────────────────────────────────────────────

def monta_repo(tmp, itens):
    """Repo git com uma fila `fila` e os itens pedidos.

    O repo fica em `<tmp>/repo`, e NÃO na raiz do tmp, porque o `claude` falso e
    o registro de chamadas moram no tmp: dentro do repo eles sujariam a árvore e
    o guarda de largada recusaria o run — que foi exatamente o primeiro modo de
    falha destes testes.
    """
    raiz = Path(tmp) / "repo"
    raiz.mkdir(parents=True, exist_ok=True)
    d = raiz / ".claude" / "programs" / "fila"
    d.mkdir(parents=True)
    plano = {"schema_version": 2, "mode": "single-track", "program": "fila",
             "source": "teste", "items": itens}
    (d / "plan.yaml").write_text(yaml.safe_dump(plano, allow_unicode=True),
                                 encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=raiz, check=True)
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=raiz, check=True)
    return raiz


def item(ident, status="pending", human_pending=None):
    return {"id": ident, "title": f"item {ident}", "why": "porque",
            "status": status, "blocked_by": [], "human_pending": human_pending,
            "evidence": None}


def fake_claude(tmp, corpo):
    """Um `claude` falso no PATH. `corpo` é python3 que recebe PLANO e ARGS."""
    binv = Path(tmp) / "bin"
    binv.mkdir(exist_ok=True)
    script = binv / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys, yaml, json, time\n"
        "PLANO = os.environ['FAKE_PLANO']\n"
        "ARGS = sys.argv[1:]\n"
        "def carrega():\n"
        "    return yaml.safe_load(open(PLANO, encoding='utf-8'))\n"
        "def grava(p):\n"
        "    open(PLANO, 'w', encoding='utf-8').write("
        "yaml.safe_dump(p, allow_unicode=True))\n"
        "def marca(ident, **campos):\n"
        "    p = carrega()\n"
        "    for it in p['items']:\n"
        "        if it['id'] == ident:\n"
        "            it.update(campos)\n"
        "    grava(p)\n"
        # Espelha a regra de adiamento do `cepa-plan monta_lote`: item com
        # `human_pending` aberto NÃO é entregue de novo ao executor. Sem isto o
        # falso remarca o mesmo item para sempre e o teste mede a si mesmo.
        "def primeiro_pendente():\n"
        "    for it in carrega()['items']:\n"
        "        if it['status'] == 'pending' and not it.get('human_pending'):\n"
        "            return it['id']\n"
        "    return None\n"
        "with open(os.environ['FAKE_CHAMADAS'], 'a') as f:\n"
        "    f.write(json.dumps(ARGS) + '\\n')\n"
        + corpo + "\n",
        encoding="utf-8")
    script.chmod(0o755)
    return binv


def roda(raiz, binv, plano, args, timeout=120, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plano)
    chamadas = Path(raiz).parent / "chamadas.jsonl"
    env["FAKE_CHAMADAS"] = str(chamadas)
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(raiz)]
                       + args, capture_output=True, text=True, env=env,
                       timeout=timeout)
    linhas = []
    if chamadas.exists():
        linhas = [json.loads(l) for l in chamadas.read_text().splitlines() if l.strip()]
    return p, linhas


def ledger_de(raiz):
    d = Path(raiz) / ".claude" / "programs" / "fila" / "until"
    eventos = []
    for f in sorted(d.glob("*.jsonl")):
        eventos += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return eventos


# ── 1. relógio ──────────────────────────────────────────────────────────────

def test_duracao_sem_unidade_e_recusada():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "12"])
        check("--for sem unidade é recusado", p.returncode == 2,
              f"saiu {p.returncode}")
        # A recusa tem de nomear a FLAG e o VALOR recusados. Só exigir "saiu 2"
        # e "o texto cita 12h/90m" deixa passar uma versão que aceita `--for 12`
        # e morre depois no --reserva-minima: mesmo código de saída, mensagem
        # mandando você conferir o argumento errado. (Perturbação, 2026-08-30.)
        check("...e a recusa nomeia --for e o valor recusado",
              "--for '12'" in p.stderr, p.stderr[:300])
        check("...e a recusa diz qual é o formato",
              "12h" in p.stderr and "90m" in p.stderr, p.stderr[:300])
        check("...e nada foi disparado", not chamadas, str(chamadas))


def test_recusa_nomeia_a_flag_certa_entre_as_tres_duracoes():
    """--for, --reserva-minima e --folga passam pelo mesmo parser. Uma recusa
    que nomeia sempre `--for` manda você conferir o argumento errado."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        for flag, valor in (("--reserva-minima", "25"), ("--folga", "30")):
            p, chamadas = roda(raiz, binv, plano, ["--for", "2h", flag, valor])
            check(f"{flag} inválida é recusada", p.returncode == 2,
                  f"saiu {p.returncode}")
            check(f"...e a recusa nomeia {flag}, não --for",
                  f"{flag} '{valor}'" in p.stderr, p.stderr[:300])
            check("...e nada foi disparado", not chamadas, str(chamadas))


def test_reserva_minima_impede_comecar_item_que_nao_cabe():
    """O corte é ANTES do item. Uma janela menor que a reserva mínima não
    dispara nada — começar um item que não cabe é trabalho jogado fora."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano,
                           ["--for", "10m", "--reserva-minima", "25m"])
        check("janela menor que a reserva não dispara item", not chamadas,
              f"disparou {len(chamadas)}x")
        check("...e o run termina por `prazo`",
              any(e.get("evento") == "run_end" and e.get("motivo") == "prazo"
                  for e in ledger_de(raiz)),
              json.dumps(ledger_de(raiz))[:300])
        check("...e o item continua pendente",
              yaml.safe_load(plano.read_text())["items"][0]["status"] == "pending")


# ── 2. progresso e disjuntor ────────────────────────────────────────────────

def test_fila_inteira_executa_ate_esvaziar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        check("três itens, três subprocessos", len(chamadas) == 3,
              f"{len(chamadas)}: {chamadas}")
        check("um item por subprocesso (--max 1 no prompt)",
              all(any("--max 1" in a for a in c) for c in chamadas), str(chamadas))
        check("todos ficaram done",
              all(it["status"] == "done"
                  for it in yaml.safe_load(plano.read_text())["items"]))
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("o run termina por fim-da-fila", fim["motivo"] == "fim-da-fila",
              str(fim))
        check("...e conta 3 com progresso", fim["com_progresso"] == 3, str(fim))


def test_disjuntor_para_depois_de_n_falhas_seguidas():
    """`claude` sai 0 mas não mexe no item: o supervisor não pode acreditar no
    código de saída, senão gira a noite inteira no mesmo item."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, "sys.exit(0)")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h", "--max-falhas", "3"])
        check("para na 3ª falha seguida", len(chamadas) == 3,
              f"disparou {len(chamadas)}x")
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("o run termina por `disjuntor`", fim["motivo"] == "disjuntor", str(fim))
        check("exit 0 sem mexer no item NÃO é progresso",
              fim["com_progresso"] == 0 and fim["sem_progresso"] == 3, str(fim))


def test_progresso_zera_o_disjuntor():
    """Duas falhas, um sucesso, duas falhas: com o teto em 3, isso NÃO pode
    parar o run — senão azar espalhado encerra uma noite saudável."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = (
            "n = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
            "if n == 3:\n"
            "    marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h", "--max-falhas", "3"])
        check("o sucesso do meio zerou a contagem", len(chamadas) == 6,
              f"disparou {len(chamadas)}x (esperado 2 falhas + 1 ok + 3 falhas)")
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("e o fim é o disjuntor, na segunda sequência",
              fim["motivo"] == "disjuntor" and fim["com_progresso"] == 1, str(fim))


def test_human_pending_e_progresso_e_nao_falha():
    """A rota que só o humano fecha ADIA o item (decisão do dono, 2026-08-28).
    Se o supervisor a lesse como falha, três adiamentos matariam a noite."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(
            tmp, "marca(primeiro_pendente(), human_pending='valide o deploy à mão')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h", "--max-falhas", "3"])
        check("três adiamentos NÃO disparam o disjuntor", len(chamadas) == 3,
              f"disparou {len(chamadas)}x")
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("adiamento conta como progresso",
              fim["com_progresso"] == 3 and fim["sem_progresso"] == 0, str(fim))
        check("o run termina por fim-da-fila, não por disjuntor",
              fim["motivo"] == "fim-da-fila", str(fim))
        check("a rota aberta aparece no relatório do fim",
              "valide o deploy à mão" in p.stdout, p.stdout[-400:])


def test_item_blocked_nao_trava_a_noite_atras_dele():
    """Decisão do dono, 2026-08-30: `blocked` ADIA em vez de parar o lote. Era
    o último jeito de um item só travar uma janela inteira — o supervisor
    disparava uma vez, o `queue` parava em `bloqueado-antes` e a noite acabava
    às 23h05 com um item feito."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        corpo = ("ident = primeiro_pendente()\n"
                 "if ident == 'a1':\n"
                 "    marca(ident, status='blocked', evidence='a API de fora caiu')\n"
                 "else:\n"
                 "    marca(ident, status='done')\n")
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        check("o item travado NÃO encerra a janela", len(chamadas) == 3,
              f"disparou {len(chamadas)}x")
        depois = {it["id"]: it["status"]
                  for it in yaml.safe_load(plano.read_text())["items"]}
        check("o travado fica `blocked` e não é re-executado",
              depois["a1"] == "blocked", depois)
        check("...e os seguintes fecharam",
              depois["a2"] == "done" and depois["a3"] == "done", depois)
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("o run termina por fim-da-fila, não por `bloqueado-antes`",
              fim["motivo"] == "fim-da-fila", str(fim))
        check("...e a razão do fim cita os adiados",
              "adiado" in (fim.get("detalhe") or "").lower(), str(fim))
        # Sem estas duas, tirar `blocked` da contagem de progresso passava
        # despercebido: os três itens rodavam igual, mas o travado passava a
        # contar como FALHA e, numa noite com vários `blocked` em sequência, o
        # disjuntor encerraria a janela cedo sem ninguém saber por quê.
        # (Achado pelo proof gate, 2026-08-30.)
        check("o item travado conta como PROGRESSO, não como falha",
              fim["com_progresso"] == 3 and fim["sem_progresso"] == 0, str(fim))


# ── 3. guardas de largada ───────────────────────────────────────────────────

def test_arvore_suja_recusa_o_run():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        (raiz / "lixo.txt").write_text("pendura", encoding="utf-8")
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        check("árvore suja recusa", p.returncode == 2, f"saiu {p.returncode}")
        check("...e nada foi disparado", not chamadas, str(chamadas))
        check("...e a recusa nomeia o escape --sujo-ok",
              "--sujo-ok" in p.stderr, p.stderr[:300])
        p2, chamadas2 = roda(raiz, binv, plano, ["--for", "2h", "--sujo-ok"])
        check("--sujo-ok deixa passar", len(chamadas2) == 1,
              f"saiu {p2.returncode}, disparou {len(chamadas2)}x")


def test_fila_inexistente_recusa_antes_de_disparar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        env = dict(os.environ)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(plano)
        env["FAKE_CHAMADAS"] = str(raiz.parent / "chamadas.jsonl")
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "nao-existe",
                            "--repo", str(raiz), "--for", "2h"],
                           capture_output=True, text=True, env=env, timeout=60)
        check("fila inexistente recusa", p.returncode == 2, f"saiu {p.returncode}")
        check("...e a recusa nomeia a fila",
              "nao-existe" in p.stderr, p.stderr[:300])


# ── 4. o contrato com o subprocesso ─────────────────────────────────────────

def test_permissoes_liberadas_por_default_e_desligaveis():
    """Decisão do dono: sem `--dangerously-skip-permissions` o subprocesso trava
    no primeiro pedido e a noite morre em silêncio. Fica ligado por default e
    desligável, nunca o contrário."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        check("por default o subprocesso nasce sem pedir permissão",
              chamadas and "--dangerously-skip-permissions" in chamadas[0],
              str(chamadas))
        check("...e o banner diz isso em voz alta",
              "--dangerously-skip-permissions LIGADO" in p.stdout,
              p.stdout[:600])

        raiz2 = monta_repo(tempfile.mkdtemp(), [item("a1")])
        plano2 = raiz2 / ".claude" / "programs" / "fila" / "plan.yaml"
        p2, chamadas2 = roda(raiz2, binv, plano2, ["--for", "2h", "--com-permissoes"])
        check("--com-permissoes tira a flag",
              chamadas2 and "--dangerously-skip-permissions" not in chamadas2[-1],
              str(chamadas2))


def test_until_calcula_o_proximo_horario():
    """`--until 07:00` é uma das duas formas documentadas de dar a janela, e
    não tinha um teste sequer — toda a cobertura passava por `--for`."""
    from datetime import datetime, timedelta
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"

        alvo = datetime.now() + timedelta(hours=3)
        p, _ = roda(raiz, binv, plano,
                    ["--until", alvo.strftime("%H:%M"), "--dry-run"])
        check("--until aceita HH:MM", p.returncode == 0, p.stderr[:300])
        check("...e o prazo é o horário pedido, no dia certo",
              alvo.strftime("%d/%m %H:%M") in p.stdout, p.stdout[:800])

        # Horário já passado hoje = amanhã. Sem isto, `--until 07:00` digitado
        # às 23h daria uma janela NEGATIVA e o run morreria na largada.
        passado = datetime.now() - timedelta(hours=2)
        amanha = passado + timedelta(days=1)
        p2, _ = roda(raiz, binv, plano,
                     ["--until", passado.strftime("%H:%M"), "--dry-run"])
        check("horário já passado hoje vira o de amanhã",
              amanha.strftime("%d/%m %H:%M") in p2.stdout, p2.stdout[:800])


def test_until_mal_formado_e_recusado_nomeando_a_flag():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        for ruim in ("7h", "25:00", "abc"):
            p, chamadas = roda(raiz, binv, plano, ["--until", ruim])
            check(f"--until {ruim!r} é recusado", p.returncode == 2,
                  f"saiu {p.returncode}")
            check(f"...e a recusa nomeia --until e o valor",
                  f"--until {ruim!r}" in p.stderr, p.stderr[:300])
            check("...e nada foi disparado", not chamadas, str(chamadas))


def test_folga_e_reserva_tem_os_defaults_declarados():
    """Os dois números que decidem o corte nas pontas da janela. Ficam pinados
    porque são a diferença entre um item morto pela metade e um item que
    terminou: a reserva mínima decide o que NÃO começa, a folga decide quanto
    um item já rodando pode passar do prazo. Folga a 60min é decisão do dono
    (2026-08-30), revendo os 30min iniciais."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, _ = roda(raiz, binv, plano, ["--for", "12h", "--dry-run"])
        check("a folga default é 60min",
              "mata item que passar 1h00 do prazo" in p.stdout, p.stdout[:800])
        check("a reserva mínima default é 25min",
              "não começa item com menos de 25min" in p.stdout, p.stdout[:800])


def test_dry_run_nao_executa_nada():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h", "--dry-run"])
        check("--dry-run não dispara", not chamadas, str(chamadas))
        check("...e nomeia o 1º item que rodaria", "a1" in p.stdout, p.stdout[:600])
        check("...e a fila fica intacta",
              all(it["status"] == "pending"
                  for it in yaml.safe_load(plano.read_text())["items"]))


def test_item_que_estoura_a_folga_e_morto_com_o_grupo_todo():
    """A folga (60min por default) só existe porque há quem a faça valer: o
    kill do GRUPO de processos. O grupo, e não só o `claude`, porque o que
    segura a árvore é o build que ele disparou — matar o pai deixaria o filho
    órfão rodando a noite inteira. Nada exercia esse caminho.

    Janela em segundos (o parser aceita fração de minuto), senão o teste
    levaria uma hora. (Achado pelo proof gate, 2026-08-30.)"""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        marca = Path(tmp) / "filho-sobreviveu.txt"
        corpo = (
            'import subprocess, time\n'
            'filho = [sys.executable, \'-c\', \'import sys,time; time.sleep(25); open(sys.argv[1], "w").write("vivo")\', os.environ[\'FAKE_FILHO\']]\n'
            'subprocess.Popen(filho)\n'
            'time.sleep(120)\n')
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano,
                           ["--for", "0.2m", "--reserva-minima", "0.05m",
                            "--folga", "0.05m"],
                           timeout=180, extra_env={"FAKE_FILHO": str(marca)})
        check("o item foi disparado", len(chamadas) == 1, str(chamadas))
        fins = [e for e in ledger_de(raiz) if e.get("evento") == "item_end"]
        check("o item que estourou a folga é registrado como timeout",
              fins and fins[0]["timeout"] is True, str(fins))
        check("...e timeout NÃO é progresso",
              fins and fins[0]["progresso"] is False, str(fins))
        check("...e o item continua pendente na fila",
              yaml.safe_load(plano.read_text())["items"][0]["status"] == "pending")
        # ATENÇÃO ao relógio: o filho só escreveria aos ~25s, e o run inteiro
        # acaba aos ~15s. Conferir o marcador na hora daria "não existe" mesmo
        # com o kill errado — foi o buraco que uma perturbação (matar só o pai,
        # `proc.terminate()`) atravessou VERDE. Então esperamos passar a hora
        # em que o órfão teria escrito, e só então cobramos o silêncio.
        limite = time.monotonic() + 20
        while time.monotonic() < limite and not marca.exists():
            time.sleep(0.5)
        check("o processo-filho morreu junto (kill do grupo, não só do pai)",
              not marca.exists(),
              "o filho sobreviveu ao kill — killpg não pegou o grupo")
        check("o run termina reconhecendo o prazo",
              [e for e in ledger_de(raiz)
               if e.get("evento") == "run_end"][0]["motivo"] == "prazo",
              str(ledger_de(raiz)[-1]))


def test_processo_que_ignora_sigterm_e_morto_no_sigkill():
    """O SIGTERM é um PEDIDO, e um build com trap pode recusá-lo. Sem a
    escalada para SIGKILL, o supervisor acharia que matou e o processo seguiria
    rodando a noite inteira. Só um processo que IGNORA o SIGTERM exercita esse
    caminho — sem ele a escalada podia sumir sem nenhum teste acusar.
    (Achado perturbando a perturbação, 2026-08-30.)"""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        marca = Path(tmp) / "filho-sobreviveu.txt"
        corpo = (
            'import signal, subprocess, time\n'
            'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
            'filho = [sys.executable, \'-c\', \'import sys,signal,time; \'\n'
            '         \'signal.signal(signal.SIGTERM, signal.SIG_IGN); \'\n'
            '         \'time.sleep(25); open(sys.argv[1], "w").write("vivo")\',\n'
            '         os.environ[\'FAKE_FILHO\']]\n'
            'subprocess.Popen(filho)\n'
            'time.sleep(120)\n')
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano,
                           ["--for", "0.2m", "--reserva-minima", "0.05m",
                            "--folga", "0.05m"],
                           timeout=200,
                           extra_env={"FAKE_FILHO": str(marca),
                                      "CEPA_UNTIL_GRACA_SIGTERM": "2"})
        fins = [e for e in ledger_de(raiz) if e.get("evento") == "item_end"]
        check("o item que ignora SIGTERM ainda é registrado como timeout",
              fins and fins[0]["timeout"] is True, str(fins))
        limite = time.monotonic() + 22
        while time.monotonic() < limite and not marca.exists():
            time.sleep(0.5)
        check("quem ignora o SIGTERM morre no SIGKILL", not marca.exists(),
              "o processo sobreviveu à escalada — o SIGKILL não chegou")


def test_aviso_da_fila_chega_ao_registro_e_a_tela():
    """Reserva órfã (run morto que largou o item reservado) é devolvida pelo
    `queue` como AVISO. De manhã, esse aviso é a única pista de que uma sessão
    anterior morreu no meio — some calado se ninguém o repassar."""
    import socket
    from datetime import datetime, timezone
    morto = subprocess.Popen([sys.executable, "-c", "pass"])
    morto.wait()
    dono = {"session_id": "sessao-morta", "pid": morto.pid,
            "hostname": socket.gethostname(), "cwd": "/tmp",
            "started_at": datetime.now(timezone.utc).isoformat()}
    with tempfile.TemporaryDirectory() as tmp:
        it = item("a1")
        it.update(status="in_progress", claimed_by=dono)
        raiz = monta_repo(tmp, [it])
        binv = fake_claude(tmp, "marca(primeiro_pendente() or 'a1', status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        check("a reserva órfã volta a ser executável", len(chamadas) == 1,
              f"disparou {len(chamadas)}x")
        avisos = [e for e in ledger_de(raiz) if e.get("evento") == "aviso"]
        check("o aviso da fila é gravado no registro", avisos, str(ledger_de(raiz)))
        check("...e diz que a reserva era órfã",
              any("órfã" in (a.get("texto") or "") for a in avisos), str(avisos))
        check("...e aparece na tela também",
              "órfã" in p.stdout, p.stdout[:900])


def test_branch_diferente_da_largada_encerra_o_run():
    """Decisão do dono: commit por item numa branch só. O supervisor não
    commita nem cria branch — quem faz isso é o fluxo dentro do subprocesso —,
    então sem conferência a noite podia se espalhar em branches caladas.
    (Achado pelo gate de aceite, 2026-08-30.)"""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        corpo = ("ident = primeiro_pendente()\n"
                 "marca(ident, status='done')\n"
                 "if ident == 'a1':\n"
                 "    import subprocess\n"
                 "    subprocess.run(['git', 'checkout', '-q', '-b', 'outra'],\n"
                 "                   cwd=os.path.dirname(os.path.dirname(\n"
                 "                       os.path.dirname(os.path.dirname(PLANO)))))\n")
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        check("o run para quando a branch muda", len(chamadas) == 1,
              f"disparou {len(chamadas)}x")
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("e o motivo é `branch-mudou`", fim["motivo"] == "branch-mudou",
              str(fim))
        check("...e o detalhe nomeia as duas branches",
              "outra" in (fim.get("detalhe") or "")
              and "main" in (fim.get("detalhe") or ""), str(fim))
        check("os itens seguintes NÃO foram executados",
              yaml.safe_load(plano.read_text())["items"][1]["status"] == "pending")


def test_registro_grava_um_evento_por_item():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        ev = ledger_de(raiz)
        check("o registro abre com run_start",
              ev and ev[0]["evento"] == "run_start", str(ev[:1]))
        fins = [e for e in ev if e.get("evento") == "item_end"]
        check("um item_end por item", len(fins) == 2, str(fins))
        check("cada item_end carrega status, exit e segundos",
              all({"status", "exit_code", "segundos", "progresso"} <= set(f)
                  for f in fins), str(fins))
        check("o registro fecha com run_end",
              ev[-1]["evento"] == "run_end", str(ev[-1:]))


def main():
    print("cepa-until — supervisor de janela de tempo\n")
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
