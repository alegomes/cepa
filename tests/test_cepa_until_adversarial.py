#!/usr/bin/env python3
"""Entrada adversária no `cepa-until` — o nível l4 do proof gate.

## Por que este arquivo existe separado

O `test_cepa_until.py` prova que o supervisor faz a coisa certa quando tudo
está no lugar. Este prova o que ele faz quando NÃO está — e para um executor
que roda sozinho de madrugada essa é a metade que importa mais, porque não há
ninguém para ler um traceback às 3h.

A regra que todos os casos aqui compartilham: **o supervisor pode recusar, pode
encerrar, pode contar como falha — mas nunca pode estourar.** Um traceback mata
a janela inteira e deixa o registro pela metade, que é exatamente o contrário
do que ele existe para fazer.

Duas superfícies de entrada:
  - a LINHA DE COMANDO (durações absurdas, teto inválido, flags conflitantes);
  - o ESTADO EM DISCO, que muda embaixo dele durante o run (o `plan.yaml`
    corrompido ou apagado no meio, o `claude` que some do PATH).

Run: python3 tests/test_cepa_until_adversarial.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    fake_claude, item, ledger_de, monta_repo, roda)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def sem_traceback(p, nome):
    check(f"{nome}: não estoura",
          "Traceback" not in (p.stderr or ""),
          (p.stderr or "").strip()[-300:])


# ── 1. linha de comando ─────────────────────────────────────────────────────

def test_duracoes_absurdas_sao_recusadas_sem_estourar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        for ruim in ("0h", "0m", "-3h", "1e9h", "h", "12hh", ""):
            p, chamadas = roda(raiz, binv, plano, ["--for", ruim])
            sem_traceback(p, f"--for {ruim!r}")
            check(f"--for {ruim!r} é recusado", p.returncode == 2,
                  f"saiu {p.returncode}")
            check(f"--for {ruim!r} não dispara nada", not chamadas, str(chamadas))


def test_janela_gigante_nao_quebra_a_aritmetica():
    """Uma janela absurda tem que ou ser aceita e virar uma data válida, ou ser
    recusada — nunca virar um `OverflowError` no meio da noite."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        for grande in ("99999h", "1000000m"):
            p, _ = roda(raiz, binv, plano, ["--for", grande, "--dry-run"])
            sem_traceback(p, f"--for {grande}")
            check(f"--for {grande} termina com veredito",
                  p.returncode in (0, 2), f"saiu {p.returncode}")


def test_disjuntor_invalido_e_recusado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        for ruim in ("0", "-1"):
            p, chamadas = roda(raiz, binv, plano,
                               ["--for", "2h", "--max-falhas", ruim])
            sem_traceback(p, f"--max-falhas {ruim}")
            check(f"--max-falhas {ruim} é recusado", p.returncode == 2,
                  f"saiu {p.returncode}")
            check("...e nada foi disparado", not chamadas, str(chamadas))


def test_nome_de_fila_hostil_nao_vira_comando():
    """O nome da fila entra no prompt do subprocesso. Ele é passado como
    ELEMENTO DE LISTA, nunca por shell, então metacaractere é texto — mas isso
    precisa continuar verdade, e é o tipo de coisa que uma refatoração para
    `shell=True` quebraria em silêncio."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        canario = Path(tmp) / "executou.txt"
        hostil = f"fila; touch {canario}"
        env = dict(os.environ)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(plano)
        env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
        p = subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parent.parent / "common" / "bin" / "cepa-until"),
             hostil, "--repo", str(raiz), "--for", "2h"],
            capture_output=True, text=True, env=env, timeout=120)
        sem_traceback(p, "nome de fila hostil")
        check("nome de fila hostil não executa nada",
              not canario.exists(), "o `touch` embutido no nome rodou")
        check("...e o comando recusa a fila inexistente", p.returncode == 2,
              f"saiu {p.returncode}")


# ── 2. o disco muda embaixo dele ────────────────────────────────────────────

def test_plano_corrompido_no_meio_do_run_encerra_sem_estourar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2"), item("a3")])
        corpo = ("marca(primeiro_pendente(), status='done')\n"
                 "open(PLANO, 'w').write('isto: [nao: e: yaml valido\\n')\n")
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        sem_traceback(p, "plano corrompido")
        check("dispara uma vez e encerra", len(chamadas) == 1,
              f"disparou {len(chamadas)}x")
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("o run encerra por `fila-ilegivel`",
              fim["motivo"] == "fila-ilegivel", str(fim))
        check("...e o registro fecha mesmo assim",
              fim.get("itens") is not None, str(fim))


def test_plano_apagado_no_meio_do_run_encerra_sem_estourar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = ("marca(primeiro_pendente(), status='done')\n"
                 "os.unlink(PLANO)\n")
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        sem_traceback(p, "plano apagado")
        check("dispara uma vez e encerra", len(chamadas) == 1,
              f"disparou {len(chamadas)}x")
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("o run encerra por `fila-ilegivel`",
              fim["motivo"] == "fila-ilegivel", str(fim))


def test_claude_corrompido_no_meio_e_falha_contada_nao_traceback():
    """O `claude` passa no teste da largada e vira lixo depois. Estourar aqui
    mataria o supervisor e a janela junto, com o registro pela metade."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = ("marca(primeiro_pendente(), status='done')\n"
                 "alvo = os.path.join(os.environ['FAKE_BIN'], 'claude')\n"
                 "os.unlink(alvo)\n"
                 "os.mkdir(alvo)\n")   # diretório no lugar do binário: OSError no spawn
        binv = fake_claude(tmp, corpo)
        plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
        # PATH FIXO, e este é o ponto: com o PATH herdado, apagar o falso fazia
        # o execvp seguir procurando e achar o `claude` DE VERDADE — o teste
        # rodou o agente real por 87s antes de eu perceber. Um teste que invoca
        # o binário real não mede nada e ainda gasta a sessão de quem o roda.
        p, chamadas = roda(raiz, binv, plano, ["--for", "2h", "--max-falhas", "2"],
                           extra_env={"FAKE_BIN": str(binv),
                                      "PATH": "/usr/bin:/bin"})
        sem_traceback(p, "claude corrompido")
        fins = [e for e in ledger_de(raiz) if e.get("evento") == "item_end"]
        check("o item que nem lançou é registrado sem progresso",
              any(f["progresso"] is False for f in fins), str(fins))
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("e o run encerra pelo disjuntor, com registro completo",
              fim["motivo"] == "disjuntor", str(fim))
        check("...e o relatório nomeia que nem deu para lançar",
              "lançar" in p.stdout, p.stdout[-500:])


def test_item_esgotado_que_nao_consegue_ser_bloqueado_encerra_sem_laco():
    """O teto de tentativas por item depende de ESCREVER `blocked` no plano —
    é o que faz o `queue` parar de reoferecer o item. Se essa escrita falhar
    (disco cheio, permissão, plano de outro dono), o supervisor não pode
    seguir: o próximo `queue` devolveria o mesmo item e a janela viraria um
    laço. Ele encerra com motivo próprio, e sem traceback.
    """
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        d = Path(raiz) / ".claude" / "programs" / "fila"
        # O falso trava a ESCRITA no diretório da fila (o `finish` grava um
        # .tmp ao lado e renomeia), mantendo a LEITURA de pé — que é a forma
        # da falha: o supervisor continua enxergando a fila e continua sem
        # conseguir tirar o item da frente.
        binv = fake_claude(tmp, f"os.chmod({str(d)!r}, 0o555)")
        plano = d / "plan.yaml"
        try:
            p, chamadas = roda(raiz, binv, plano, ["--for", "2h"])
        finally:
            os.chmod(d, 0o755)
        sem_traceback(p, "escrita do `blocked` recusada")
        check("o run não vira laço no mesmo item", len(chamadas) <= 3,
              f"disparou {len(chamadas)}x")
        fim = [e for e in ledger_de(raiz) if e.get("evento") == "run_end"][0]
        check("...encerra por `item-preso`", fim["motivo"] == "item-preso",
              str(fim))
        check("...e o motivo nomeia o item e o que falhou",
              "a1" in (fim.get("detalhe") or "")
              and "tentativas" in (fim.get("detalhe") or ""), str(fim))
        ev = [e for e in ledger_de(raiz) if e.get("evento") == "esgotado"]
        check("...o registro guarda que o bloqueio NÃO pegou",
              ev and ev[-1].get("bloqueado") is False, str(ev))


def main():
    print("cepa-until — entrada adversária (nível l4)\n")
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
