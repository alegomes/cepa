#!/usr/bin/env python3
"""O `cepa-until` diante da cota de 5h da conta.

## Por que existe

Em 2026-09-17 a fila WEGO bateu o teto de uso à 01:00, com reset às 3:20 e
janela até 06:17. O supervisor parou ali: ~3h de janela sem uso, e o WEGO-2291
cortado no meio perdeu o que já tinha feito. Duas regras nasceram disso, e este
arquivo prova as duas:

  - bateu o teto e o reset cabe na janela → espera o reset e retoma o MESMO
    item, sem culpar o item nem gastar a vez dele;
  - a cota de 5h não comporta o próximo item → espera o reset ANTES de
    começar, em vez de começar um item que será cortado no meio.

O `claude` falso imprime o `rate_limit_event` do stream-json no formato real,
copiado de uma execução do `claude` 2.1.276 em 2026-09-18.

Run: python3 tests/test_cepa_until_cota.py
"""

import importlib.machinery
import importlib.util
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, fake_claude, item, ledger_de, monta_repo, roda)

FAILURES = []

# Espera de 1s depois do reset, em vez de 2min: o caso mede a decisão, não a
# paciência.
MARGEM = {"CEPA_UNTIL_MARGEM_RESET": "1"}


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


# Código do `claude` falso: imprime um `rate_limit_event` no formato real.
EVENTO = (
    "def evento(uso, reset, status='allowed'):\n"
    "    print(json.dumps({'type': 'rate_limit_event', 'rate_limit_info': {\n"
    "        'status': status, 'resetsAt': reset, 'rateLimitType': 'five_hour',\n"
    "        'isUsingOverage': False, 'unifiedWindows': {\n"
    "            'five_hour': {'utilization': uso, 'resetsAt': reset},\n"
    "            'seven_day': {'utilization': 0.6, 'resetsAt': reset + 400000}}},\n"
    "        'uuid': 'u', 'session_id': 's'}), flush=True)\n"
    "def resultado(texto, erro=False):\n"
    "    print(json.dumps({'type': 'result', 'subtype': 'success',\n"
    "        'is_error': erro, 'result': texto}), flush=True)\n"
    "N = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
)

TEXTO_DO_TETO = "You've hit your session limit · resets 3:20am"


def plano_de(raiz):
    return raiz / ".claude" / "programs" / "fila" / "plan.yaml"


def status(plano):
    return {it["id"]: it["status"]
            for it in yaml.safe_load(plano.read_text())["items"]}


def run_end(raiz):
    return [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]


# ── O1: bateu o teto, espera o reset ────────────────────────────────────────

def test_bateu_o_teto_espera_o_reset_e_retoma_o_mesmo_item():
    """O caso da noite de 2026-09-17, com o reset a 2s em vez de 2h20."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = EVENTO + (
            "if N == 1:\n"
            "    evento(1.0, int(time.time()) + 2, 'rejected')\n"
            f"    resultado({TEXTO_DO_TETO!r}, True)\n"
            "    sys.exit(1)\n"
            "evento(0.02, int(time.time()) + 18000)\n"
            "if N >= 3:\n"
            "    marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        inicio = time.monotonic()
        # A 2ª tentativa falha de verdade e a 3ª fecha. Com teto de 2 por item,
        # isso só dá certo se a tentativa cortada pelo teto NÃO contou: senão a
        # falha da 2ª já seria a última vez e o a1 viraria `blocked`.
        p, chamadas = roda(raiz, binv, plano_de(raiz),
                           ["--for", "2h", "--tentativas-por-item", "2"],
                           extra_env=MARGEM)
        gasto = time.monotonic() - inicio
        starts = [e["id"] for e in ledger_de(raiz) if e.get("evento") == "item_start"]
        check("o a1 foi retomado depois do reset",
              starts == ["a1", "a1", "a1", "a2"], str(starts))
        check("...e fechou, não virou `blocked`",
              status(plano_de(raiz)) == {"a1": "done", "a2": "done"},
              str(status(plano_de(raiz))))
        check("...o supervisor dormiu até o reset", gasto >= 2, f"{gasto:.1f}s")
        ev = [e for e in ledger_de(raiz) if e.get("evento") == "limite_de_uso"]
        check("...o registro diz que esperou", ev and ev[0].get("espera") is True,
              str(ev))
        fim = run_end(raiz)
        check("...e o run acaba pela fila; só a falha real foi contada",
              fim["motivo"] == "fim-da-fila" and fim["sem_progresso"] == 1
              and fim["esperas_de_cota"] == 1, str(fim))
        check("...o relatório lista a espera",
              "Esperas pela cota de 5h (1)" in p.stdout, p.stdout[-600:])


def test_reset_fora_da_janela_para_em_vez_de_esperar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = EVENTO + (
            "evento(1.0, int(time.time()) + 5 * 3600, 'rejected')\n"
            f"resultado({TEXTO_DO_TETO!r}, True)\n"
            "sys.exit(1)\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=MARGEM)
        check("uma tentativa só", len(chamadas) == 1, f"{len(chamadas)}x")
        fim = run_end(raiz)
        check("...parou com motivo limite-de-uso",
              fim["motivo"] == "limite-de-uso", str(fim))
        check("...dizendo que o reset não cabe na janela",
              "não deixa a reserva mínima" in (fim.get("detalhe") or ""),
              fim.get("detalhe"))
        check("...e o item segue pendente",
              status(plano_de(raiz))["a1"] == "pending")


def test_tres_cortes_seguidos_encerram_o_run():
    """Um reset que não levanta o teto faria o supervisor esperar a noite
    inteira em ciclos. Três cortes seguidos sem progresso encerram."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = EVENTO + (
            "evento(1.0, int(time.time()) + 1, 'rejected')\n"
            f"resultado({TEXTO_DO_TETO!r}, True)\n"
            "sys.exit(1)\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=MARGEM)
        check("três tentativas e para", len(chamadas) == 3, f"{len(chamadas)}x")
        fim = run_end(raiz)
        check("...com o motivo dizendo que o reset não levanta o teto",
              fim["motivo"] == "limite-de-uso"
              and "não está levantando" in (fim.get("detalhe") or ""), str(fim))
        check("...e o item NÃO foi bloqueado pelo teto de tentativas",
              status(plano_de(raiz))["a1"] == "pending",
              str(status(plano_de(raiz))))


def test_prosa_sobre_o_teto_no_meio_do_stream_nao_e_teto():
    """No stream-json o texto de todos os turnos vai para o log. Um agente que
    CITA a mensagem num turno do meio não é a conta esgotada."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        corpo = EVENTO + (
            "evento(0.3, int(time.time()) + 18000)\n"
            "print(json.dumps({'type': 'assistant', 'message': {'content': [\n"
            f"    {{'type': 'text', 'text': {TEXTO_DO_TETO!r}}}]}}}}))\n"
            "resultado('terminei sem fechar o item')\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=MARGEM)
        fim = run_end(raiz)
        check("a citação não vira teto de uso",
              fim["limite_de_uso"] == 0 and fim["sem_progresso"] >= 1, str(fim))


# ── O2: não começa item que a cota não comporta ─────────────────────────────

def test_pausa_antes_do_item_que_a_cota_nao_comporta():
    """a1 larga com 50%, a2 com 75%: um item custa 25 pontos. A leitura de 75%
    é da largada do a2, então ela ainda não inclui o a2: a projeção para o a3
    é 75 + 25 + 25 = 125%, e o a3 espera o reset. Somar o custo uma vez só
    daria 100% e o a3 largaria para ser cortado no meio."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        # O reset nasce na 1ª chamada do `claude` falso, não no começo do teste:
        # com o relógio disparado antes do git init e da largada, uma máquina
        # lenta deixava o reset passar antes do a3 e o caso media outra coisa.
        guarda_reset = Path(tmp) / "reset"
        corpo = EVENTO + (
            f"G = {str(guarda_reset)!r}\n"
            "if N == 1: open(G, 'w').write(str(int(time.time()) + 10))\n"
            "R = int(open(G).read())\n"
            "if N == 1: evento(0.5, R)\n"
            "elif N == 2: evento(0.75, R)\n"
            "else: evento(0.05, R + 18000)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=MARGEM)
        ev = ledger_de(raiz)
        ordem = [e["evento"] + (":" + e["id"] if "id" in e else "") for e in ev
                 if e["evento"] in ("item_start", "pausa_de_cota")]
        check("a pausa veio antes do a3, e só dele",
              ordem == ["item_start:a1", "item_start:a2", "pausa_de_cota",
                        "item_start:a3"], str(ordem))
        a3 = [e for e in ev if e.get("evento") == "item_start" and e["id"] == "a3"]
        check("...o a3 só largou depois do reset",
              a3 and datetime.fromisoformat(a3[0]["quando"]).timestamp()
              >= int(guarda_reset.read_text()),
              str(a3))
        pausa = [e for e in ev if e["evento"] == "pausa_de_cota"]
        check("...o registro guarda uso e custo medido",
              pausa and pausa[0]["uso"] == 0.75
              and abs(pausa[0]["custo_item"] - 0.25) < 1e-9, str(pausa))
        check("...e os três fecharam",
              set(status(plano_de(raiz)).values()) == {"done"},
              str(status(plano_de(raiz))))


def test_cota_folgada_nao_pausa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        corpo = EVENTO + (
            "R = int(time.time()) + 18000\n"
            "evento(0.1 * N, R)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=MARGEM)
        ev = ledger_de(raiz)
        check("nenhuma pausa com a cota em 10-30%",
              not [e for e in ev if e["evento"] == "pausa_de_cota"], str(ev))
        check("...e os três rodaram", len(chamadas) == 3, f"{len(chamadas)}x")


def test_pausa_que_nao_cabe_na_janela_para_antes_do_item():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        corpo = EVENTO + (
            "R = int(time.time()) + 3 * 3600\n"
            "evento(0.5 if N == 1 else 0.8, R)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=MARGEM)
        check("o a3 não começou", len(chamadas) == 2, f"{len(chamadas)}x")
        fim = run_end(raiz)
        check("...o run parou com motivo cota-no-fim",
              fim["motivo"] == "cota-no-fim" and "80%" in (fim.get("detalhe") or ""),
              str(fim))
        check("...e o a3 segue pendente",
              status(plano_de(raiz))["a3"] == "pending")


def test_sem_historico_cota_acima_de_90_nao_comeca_item():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = EVENTO + (
            "evento(0.95, int(time.time()) + 3 * 3600)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, corpo)
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"],
                           extra_env=MARGEM)
        check("só o a1 rodou", len(chamadas) == 1, f"{len(chamadas)}x")
        check("...e o run parou pela cota",
              run_end(raiz)["motivo"] == "cota-no-fim", str(run_end(raiz)))


def test_subprocesso_roda_em_stream_json():
    """Sem stream-json não há `rate_limit_event`, e a regra da cota fica cega."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        p, chamadas = roda(raiz, binv, plano_de(raiz), ["--for", "2h"])
        args = chamadas[0] if chamadas else []
        check("o `claude` recebe --output-format stream-json --verbose",
              "stream-json" in args and "--verbose" in args
              and args[args.index("--output-format") + 1] == "stream-json",
              str(args))


# ── horário do reset em texto ───────────────────────────────────────────────

def test_horario_do_reset_em_texto():
    m = carrega_modulo()
    agora = datetime(2026, 9, 18, 1, 0)
    check("3:20am à 01:00 é hoje",
          m.horario_do_reset("resets 3:20am", agora) == datetime(2026, 9, 18, 3, 20))
    check("8pm às 21:00 é amanhã",
          m.horario_do_reset("resets 8pm", datetime(2026, 9, 18, 21, 0))
          == datetime(2026, 9, 19, 20, 0))
    check("12:30pm é meio-dia e meia",
          m.horario_do_reset("resets 12:30pm", agora) == datetime(2026, 9, 18, 12, 30))
    check("reset de 5min atrás é o de agora, não o de amanhã",
          m.horario_do_reset("resets 3:20am", datetime(2026, 9, 18, 3, 25))
          == datetime(2026, 9, 18, 3, 20))
    check("com data na frente (teto semanal) não vira horário",
          m.horario_do_reset("resets Sep 22, 4pm", agora) is None)
    check("com fuso entre parênteses vira horário",
          m.horario_do_reset("resets 3:20am (America/Sao_Paulo)", agora) is not None)
    check("hora impossível não vira horário",
          m.horario_do_reset("resets 13:00pm", agora) is None)


def test_custo_de_item_so_compara_a_mesma_janela():
    m = carrega_modulo()
    check("dois pares na mesma janela: o maior salto",
          abs(m.custo_de_item([(0.1, 1), (0.3, 1), (0.35, 1)]) - 0.2) < 1e-9)
    check("par que atravessa o reset não conta",
          m.custo_de_item([(0.9, 1), (0.05, 2)]) is None)
    check("uma leitura só: sem custo", m.custo_de_item([(0.5, 1)]) is None)


def main():
    print("cepa-until — cota de 5h da conta\n")
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
