#!/usr/bin/env python3
"""O `cepa-until` diante de uma queda de rede.

## Por que existe

Em 2026-09-18 a internet caiu às 11:32 no meio do WEGO-2293. O `claude` saiu 1
com "Can't reach the API server (ENOTFOUND)"; as duas tentativas seguintes
morreram do mesmo jeito em 3 minutos. O supervisor leu três "sem progresso",
marcou o item `blocked` e desligou pelo disjuntor. Este arquivo prova a regra
que nasceu disso:

  - queda de rede não é falha do item: não gasta a vez dele nem conta no
    disjuntor;
  - o supervisor sonda a rede e retoma o MESMO item quando ela volta;
  - se ela não volta dentro da janela, ou cai três vezes seguidas sem progresso
    entre elas, o run para com motivo `sem-rede`.

O `claude` falso imprime o `result` final no formato real, copiado do `.log`
do run de 2026-09-18.

Run: python3 tests/test_cepa_until_rede.py
"""

import json
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    fake_claude, item, ledger_de, monta_repo, roda)
from test_cepa_until_cota import carrega_modulo  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# O `result` real de 2026-09-18 (campos que importam).
RESULTADO_SEM_REDE = {
    "type": "result", "subtype": "success", "is_error": True,
    "terminal_reason": "api_error", "api_error_status": None,
    "stop_reason": "stop_sequence", "num_turns": 1,
    "result": "API Error: Can't reach the API server — check your internet "
              "or DNS (ENOTFOUND)"}

CORPO = (
    "def sem_rede():\n"
    f"    print(json.dumps({RESULTADO_SEM_REDE!r}), flush=True)\n"
    "    sys.exit(1)\n"
    "N = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
)


def plano_de(raiz):
    return raiz / ".claude" / "programs" / "fila" / "plan.yaml"


def status(plano):
    return {it["id"]: it["status"]
            for it in yaml.safe_load(plano.read_text())["items"]}


def run_end(raiz):
    return [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def escuta_depois(porta, segundos, por=30):
    """Uma porta local que só passa a aceitar conexão depois de `segundos`:
    a rede "voltando"."""
    def corpo():
        time.sleep(segundos)
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", porta))
            s.listen(8)
            s.settimeout(0.5)
            fim = time.monotonic() + por
            while time.monotonic() < fim:
                try:
                    c, _ = s.accept()
                    c.close()
                except socket.timeout:
                    pass
    t = threading.Thread(target=corpo, daemon=True)
    t.start()
    return t


def ambiente(porta, intervalo="0.5"):
    return {"CEPA_UNTIL_SONDA_REDE": f"127.0.0.1:{porta}",
            "CEPA_UNTIL_SONDA_INTERVALO": intervalo}


# ── 1. a rede cai e volta: retoma o mesmo item sem gastar a vez ─────────────

def test_queda_de_rede_espera_a_volta_e_retoma_o_mesmo_item():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = CORPO + (
            "if N == 1:\n"
            "    sem_rede()\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        porta = porta_livre()
        escuta_depois(porta, 2)
        inicio = time.monotonic()
        # Teto de UMA tentativa por item: se a queda contasse como tentativa,
        # o a1 viraria `blocked` na hora e nunca seria retomado.
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--tentativas-por-item", "1"],
                    extra_env=ambiente(porta))
        gasto = time.monotonic() - inicio
        ev = ledger_de(raiz)
        starts = [e["id"] for e in ev if e.get("evento") == "item_start"]
        check("o a1 foi retomado quando a rede voltou",
              starts == ["a1", "a1", "a2"], str(starts))
        check("...e fechou, não virou `blocked` (a queda não gastou a vez)",
              status(plano_de(raiz)) == {"a1": "done", "a2": "done"},
              str(status(plano_de(raiz))))
        check("...o supervisor esperou a rede", gasto >= 2, f"{gasto:.1f}s")
        queda = [e for e in ev if e.get("evento") == "queda_de_rede"]
        check("o registro tem a queda com espera=True",
              len(queda) == 1 and queda[0]["espera"] is True
              and queda[0]["id"] == "a1", str(queda))
        check("...e a volta da rede",
              any(e.get("evento") == "rede_voltou" for e in ev), str(ev))
        check("o run terminou pela fila, não pelo disjuntor",
              run_end(raiz)["motivo"] == "fim-da-fila"
              and run_end(raiz)["quedas_de_rede"] == 1, str(run_end(raiz)))
        check("o relatório lista a queda como não-falha",
              "Quedas de rede (1)" in p.stdout and "SEM REDE" in p.stdout,
              p.stdout[-800:])


def test_queda_de_rede_nao_conta_no_teto_por_item():
    """queda, falha REAL, fecha — com teto de 2 por item. Se a queda contasse,
    a falha real já seria a 2ª vez e o a1 viraria `blocked`."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = CORPO + (
            "if N == 1:\n"
            "    sem_rede()\n"
            "if N == 2:\n"
            "    sys.exit(1)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        porta = porta_livre()
        escuta_depois(porta, 0)
        time.sleep(0.3)
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "2h", "--tentativas-por-item", "2"],
                           extra_env=ambiente(porta))
        check("3 chamadas: queda, falha real, fechou",
              len(chamadas) == 3, str(len(chamadas)))
        check("o a1 fechou — a queda não gastou uma das 2 vezes",
              status(plano_de(raiz)) == {"a1": "done"},
              str(status(plano_de(raiz))))
        fim = run_end(raiz)
        check("só a falha real conta como sem progresso",
              fim["sem_progresso"] == 1 and fim["esgotados"] == 0
              and fim["motivo"] == "fim-da-fila", str(fim))


# ── 2. três quedas seguidas sem progresso param o run ───────────────────────

def test_tres_quedas_seguidas_param_o_run_sem_culpar_o_item():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, CORPO + "sem_rede()\n")
        porta = porta_livre()
        escuta_depois(porta, 0)  # a sonda sempre vê rede
        time.sleep(0.3)
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "2h", "--tentativas-por-item", "2",
                            "--max-falhas", "2"],
                           extra_env=ambiente(porta))
        fim = run_end(raiz)
        check("3 quedas e parou com motivo `sem-rede`",
              len(chamadas) == 3 and fim["motivo"] == "sem-rede",
              f"{len(chamadas)} chamadas · {fim}")
        check("...não pelo disjuntor de 2 nem pelo teto de 2 por item",
              fim["sem_progresso"] == 0 and fim["esgotados"] == 0, str(fim))
        check("o a1 continua `pending`, sem culpa",
              status(plano_de(raiz)) == {"a1": "pending"},
              str(status(plano_de(raiz))))
        check("o detalhe explica que a sonda vê rede e o claude não",
              "3ª queda seguida" in fim["detalhe"], fim["detalhe"])


# ── 3. a rede não volta a tempo: para com `sem-rede` ────────────────────────

def test_rede_que_nao_volta_dentro_da_janela_para_o_run():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, CORPO + "sem_rede()\n")
        porta = porta_livre()  # ninguém escuta: a rede nunca volta
        inicio = time.monotonic()
        # Janela de 12s com reserva de 3s: a espera vai até ~9s da largada.
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "0.2m", "--reserva-minima", "0.05m"],
                           extra_env=ambiente(porta))
        gasto = time.monotonic() - inicio
        fim = run_end(raiz)
        check("uma chamada só, e parou com `sem-rede`",
              len(chamadas) == 1 and fim["motivo"] == "sem-rede",
              f"{len(chamadas)} chamadas · {fim}")
        check("esperou até o prazo menos a reserva, não além",
              5 <= gasto <= 14, f"{gasto:.1f}s")
        check("o detalhe diz até quando esperou",
              "não voltou até" in fim["detalhe"], fim["detalhe"])


def test_queda_perto_do_fim_da_janela_para_sem_sondar():
    """A rede cai quando já falta menos que a reserva mínima: não há o que
    esperar, para na hora com `sem-rede`."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        # Janela de 12s, reserva de 9s: cabe começar (12 >= 9). O item gasta
        # 4s e cai; aí o último instante útil (prazo - reserva = 3s) já passou.
        binv = fake_claude(tmp, CORPO + "time.sleep(4)\nsem_rede()\n")
        porta = porta_livre()  # ninguém escuta
        inicio = time.monotonic()
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "0.2m", "--reserva-minima", "0.15m"],
                           extra_env=ambiente(porta))
        gasto = time.monotonic() - inicio
        fim = run_end(raiz)
        queda = [e for e in ledger_de(raiz) if e.get("evento") == "queda_de_rede"]
        check("parou com `sem-rede` sem tentar esperar",
              len(chamadas) == 1 and fim["motivo"] == "sem-rede"
              and queda and queda[0]["espera"] is False,
              f"{len(chamadas)} chamadas · {fim} · {queda}")
        check("o detalhe diz que não sobra tempo, não que esperou",
              "não sobra tempo" in fim["detalhe"], fim["detalhe"])
        check("não ficou sondando", gasto < 9, f"{gasto:.1f}s")


# ── 4. um item que fecha zera a contagem de quedas ──────────────────────────

def test_item_que_fecha_entre_quedas_zera_a_contagem():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        # queda, queda, a1 fecha, queda, queda, a2 fecha. Sem zerar, a 3ª
        # queda (4ª chamada) encerraria o run.
        corpo = CORPO + (
            "if N in (1, 2, 4, 5):\n"
            "    sem_rede()\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        porta = porta_livre()
        escuta_depois(porta, 0)
        time.sleep(0.3)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=ambiente(porta))
        check("6 chamadas e os dois itens fechados",
              len(chamadas) == 6
              and status(plano_de(raiz)) == {"a1": "done", "a2": "done"},
              f"{len(chamadas)} · {status(plano_de(raiz))}")
        check("o run terminou pela fila",
              run_end(raiz)["motivo"] == "fim-da-fila", str(run_end(raiz)))


# ── 5. o reconhecedor ───────────────────────────────────────────────────────

def test_queda_de_rede_exige_api_error_e_mensagem_de_rede():
    m = carrega_modulo()
    real = json.dumps(RESULTADO_SEM_REDE)
    check("o result real de 2026-09-18 é queda de rede",
          m.queda_de_rede("lixo de hook\n" + real + "\n"))
    prosa = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "o teste falhou com ENOTFOUND no mock"}]}})
    ok = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                     "result": "fechei o item"})
    check("prosa de agente com ENOTFOUND + result normal NÃO é queda",
          not m.queda_de_rede(prosa + "\n" + ok + "\n"))
    teto = json.dumps({"type": "result", "is_error": True,
                       "terminal_reason": "api_error",
                       "result": "You've hit your session limit · resets 3:20am"})
    check("erro de API que não é de rede NÃO é queda (é do teto)",
          not m.queda_de_rede(teto + "\n"))
    check("saída vazia não é queda", not m.queda_de_rede(""))
    sucesso_com_palavra = json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": "corrigi o timeout ECONNRESET no teste do cliente HTTP"})
    check("result de SUCESSO com palavra de rede NÃO é queda",
          not m.queda_de_rede(sucesso_com_palavra + "\n"))
    check("o último result é o que vale",
          not m.queda_de_rede(real + "\n" + ok + "\n"))


def test_espera_a_rede_respeita_o_prazo_e_a_volta():
    m = carrega_modulo()
    n = {"v": 0}

    def sonda():
        n["v"] += 1
        return n["v"] >= 3
    ate = datetime.now() + timedelta(seconds=10)
    inicio = time.monotonic()
    check("volta na 3ª sonda", m.espera_a_rede(ate, sonda, 0.1) is True
          and n["v"] == 3 and time.monotonic() - inicio < 2)
    inicio = time.monotonic()
    check("prazo vencido devolve False",
          m.espera_a_rede(datetime.now() + timedelta(seconds=0.5),
                          lambda: False, 0.1) is False
          and 0.4 <= time.monotonic() - inicio < 2)
    porta = porta_livre()
    check("sonda TCP: porta fechada é sem rede",
          m.rede_alcancavel(f"127.0.0.1:{porta}", timeout=1) is False)
    check("sonda TCP: alvo mal formado é sem rede, não exceção",
          m.rede_alcancavel("semporta", timeout=1) is False)
    escuta_depois(porta, 0, por=3)
    time.sleep(0.3)
    check("sonda TCP: porta aberta é rede",
          m.rede_alcancavel(f"127.0.0.1:{porta}", timeout=1) is True)


def main():
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"\n{nome}")
            fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FALHA(S): {', '.join(FAILURES)}")
        return 1
    print("todos passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
