#!/usr/bin/env python3
"""cepa-until — o supervisor que morre calado.

O run WEGO 2026-09-28-2003 terminou com o registro `.jsonl` só com `run_start`
e `item_start`. O card fechou `done` sozinho às 20:13, mas não houve `verify`,
`item_end` nem `run_end`, e a fila ficou com um `done` sem o build completo. Não
houve kill em nenhuma sessão nem repouso do Mac. A hipótese que sobrou foi o
SIGHUP de uma aba de terminal fechada: o `claude` roda com
`start_new_session=True`, fora do grupo do terminal, e sobrevive; o supervisor
não tratava sinal nenhum e morria no meio do item.

O que estes testes fixam:

  1. SIGHUP (e o terminal sumindo junto) não mata o supervisor: o item em voo
     termina, o build completo roda e o registro fecha com `run_end`;
  2. SIGTERM e Ctrl+C gravam `run_interrompido` no `.jsonl`, com o sinal e o
     item em voo, e deixam o `<run>.estado.json` como `interrompido`;
  3. o `run_start` e o estado carregam o pid e o host do supervisor;
  4. o `cepa-until pendentes`, o `cepa-doctor` e o `/common:until-review`
     apontam o run `rodando` cujo supervisor morreu, com o build completo que
     faltou.

Run: python3 tests/test_cepa_until_supervisor_morto.py
"""

import json
import os
import pty
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, fake_claude, item, ledger_de, monta_repo, roda)
from test_cepa_until_branch_da_noite import (  # noqa: E402
    TRABALHA, VERIFY, plano_de)

DOCTOR = CEPA_UNTIL.parent / "cepa-doctor"
UNTIL_REVIEW = CEPA_UNTIL.parent.parent / "commands" / "until-review.md"

# O `claude` falso espera o arquivo `<tmp>/segue` antes de trabalhar: é a
# janela em que o teste manda o sinal com o item em voo.
ESPERA_E_TRABALHA = (
    "segue = os.path.join(os.path.dirname(os.environ['FAKE_CHAMADAS']), 'segue')\n"
    "open(segue + '.pid', 'w').write(str(os.getpid()))\n"
    "fim = time.time() + 60\n"
    "while not os.path.exists(segue) and time.time() < fim:\n"
    "    time.sleep(0.1)\n"
    + TRABALHA)


def dir_until(raiz):
    return raiz / ".claude" / "programs" / "fila" / "until"


def estado(raiz):
    return json.loads(sorted(dir_until(raiz).glob("*.estado.json"))[-1]
                      .read_text())


def espera(cond, segundos=30):
    fim = time.time() + segundos
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.1)
    return False


def item_em_voo(raiz):
    try:
        return any(e["evento"] == "item_start" for e in ledger_de(raiz))
    except (OSError, ValueError):
        return False


def larga(raiz, binv, plano, args, **popen):
    """Sobe o `cepa-until` em segundo plano (o `roda` do test_cepa_until
    espera o fim, e aqui o teste precisa mandar o sinal no meio)."""
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plano)
    env["FAKE_CHAMADAS"] = str(raiz.parent / "chamadas.jsonl")
    env["CEPA_WORKTREE_HOME"] = str(raiz.parent / "worktrees")
    return subprocess.Popen(
        [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(raiz)] + args
        + ["--sem-analise"], env=env, stdin=subprocess.DEVNULL, **popen)


# ── 1. SIGHUP ───────────────────────────────────────────────────────────────

def test_sighup_com_o_terminal_fechado_nao_mata_o_supervisor():
    """A aba fechada manda SIGHUP e leva o terminal junto: depois dela, cada
    `print` do supervisor bate num terminal que não existe mais."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, ESPERA_E_TRABALHA)
        mestre, escravo = pty.openpty()
        proc = larga(raiz, binv, plano_de(raiz),
                     ["--for", "2h", "--verify", VERIFY],
                     stdout=escravo, stderr=escravo, start_new_session=True)
        os.close(escravo)
        try:
            check("o item entrou em voo",
                  espera(lambda: item_em_voo(raiz)), str(ledger_de(raiz)))
            os.kill(proc.pid, signal.SIGHUP)
            time.sleep(0.5)
            os.close(mestre)
            mestre = None
            (Path(tmp) / "segue").write_text("")
            try:
                codigo = proc.wait(timeout=90)
            except subprocess.TimeoutExpired:
                proc.kill()
                codigo = "não terminou"
        finally:
            if mestre is not None:
                os.close(mestre)
            (Path(tmp) / "segue").write_text("")
        ev = [e["evento"] for e in ledger_de(raiz)]
        check("o supervisor sobrevive ao SIGHUP e sai 0", codigo == 0,
              f"saiu {codigo}; eventos {ev}")
        check("...fecha o item (item_end)", "item_end" in ev, str(ev))
        check("...roda o build completo (verify)", "verify" in ev, str(ev))
        check("...e fecha o registro (run_end)",
              ev and ev[-1] == "run_end", str(ev))


# ── 2. SIGTERM e Ctrl+C ─────────────────────────────────────────────────────

def vivo(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Zumbi que ninguém colheu ainda conta como morto.
    ps = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                        capture_output=True, text=True).stdout.strip()
    return bool(ps) and not ps.startswith("Z")


def _interrompe(sinal):
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, ESPERA_E_TRABALHA)
        proc = larga(raiz, binv, plano_de(raiz),
                     ["--for", "2h", "--verify", VERIFY],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True)
        try:
            espera(lambda: item_em_voo(raiz))
            os.kill(proc.pid, sinal)
            try:
                saida, _ = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                saida, _ = proc.communicate()
            arq = Path(tmp) / "segue.pid"
            filho = int(arq.read_text()) if arq.exists() else None
            time.sleep(0.5)
            filho_vivo = filho is not None and vivo(filho)
        finally:
            # Solta o `claude` falso, que roda na própria sessão e sobrevive.
            (Path(tmp) / "segue").write_text("")
            time.sleep(1.5)
        return (proc.returncode, saida, ledger_de(raiz), estado(raiz),
                filho_vivo)


def test_sigterm_grava_run_interrompido_com_o_item_em_voo():
    codigo, saida, ev, est, filho_vivo = _interrompe(signal.SIGTERM)
    fim = ev[-1] if ev else {}
    check("SIGTERM encerra o `claude` do item (sessão própria) antes de sair",
          not filho_vivo and fim.get("filho_encerrado") is True, str(fim))
    check("SIGTERM fecha o registro com run_interrompido",
          fim.get("evento") == "run_interrompido", str(ev[-2:]))
    check("...com o sinal e o item em voo",
          fim.get("sinal") == "SIGTERM" and fim.get("id") == "a1",
          str(fim))
    check("...o estado vira `interrompido` com o item",
          est.get("estado") == "interrompido"
          and (est.get("item_em_voo") or {}).get("id") == "a1", str(est))
    check("...e o processo sai com 143 (128 + SIGTERM)", codigo == 143,
          f"{codigo}: {saida[-500:]}")


def test_ctrl_c_grava_run_interrompido_com_o_item_em_voo():
    codigo, saida, ev, est, filho_vivo = _interrompe(signal.SIGINT)
    fim = ev[-1] if ev else {}
    check("Ctrl+C encerra o `claude` do item antes de sair",
          not filho_vivo and fim.get("filho_encerrado") is True, str(fim))
    check("Ctrl+C fecha o registro com run_interrompido (SIGINT, a1)",
          fim.get("evento") == "run_interrompido"
          and fim.get("sinal") == "SIGINT" and fim.get("id") == "a1",
          str(ev[-2:]))
    check("...o estado vira `interrompido`",
          est.get("estado") == "interrompido", str(est))
    check("...e o processo sai com 130", codigo == 130,
          f"{codigo}: {saida[-500:]}")


def test_sigterm_no_build_completo_encerra_o_build():
    """O build completo também roda em sessão própria: o SIGTERM no meio dele
    precisa levá-lo junto, e o registro diz que a fase era `verify`."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA)
        marca = Path(tmp) / "build.pid"
        build = f"echo $$ > {marca}; sleep 60"
        proc = larga(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", build],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            espera(lambda: marca.exists() and marca.read_text().strip())
            os.kill(proc.pid, signal.SIGTERM)
            try:
                proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            pid_build = int(marca.read_text())
            time.sleep(0.5)
            build_vivo = vivo(pid_build)
        finally:
            if proc.poll() is None:
                proc.kill()
        fim = ledger_de(raiz)[-1]
        check("SIGTERM no build registra a fase `verify`",
              fim.get("evento") == "run_interrompido"
              and fim.get("fase") == "verify" and fim.get("id") == "a1",
              str(fim))
        check("...e encerra o build", not build_vivo
              and fim.get("filho_encerrado") is True, str(fim))


# ── 3. pid e host ───────────────────────────────────────────────────────────

def test_run_start_e_estado_carregam_pid_e_host():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA)
        roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", VERIFY])
        inicio = [e for e in ledger_de(raiz) if e["evento"] == "run_start"][0]
        est = estado(raiz)
        check("run_start tem pid (int) e o host desta máquina",
              isinstance(inicio.get("pid"), int)
              and inicio.get("host") == socket.gethostname(), str(inicio))
        check("o estado tem o mesmo pid e host",
              est.get("pid") == inicio.get("pid")
              and est.get("host") == inicio.get("host"), str(est))


# ── 4. o run `rodando` com o supervisor morto ───────────────────────────────

def pid_morto():
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def noite_que_morreu(tmp, **troca):
    """Uma noite de verdade (a1 entregue), com o estado e o registro
    rebobinados para o ponto em que o supervisor do WEGO morreu: `rodando`,
    item em voo, sem `item_end`, `verify` nem `run_end`."""
    raiz = monta_repo(tmp, [item("a1")])
    binv = fake_claude(tmp, TRABALHA)
    roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", VERIFY])
    jsonl = sorted(dir_until(raiz).glob("*.jsonl"))[-1]
    eventos = [json.loads(l) for l in jsonl.read_text().splitlines()]
    corte = next(i for i, e in enumerate(eventos) if e["evento"] == "item_start")
    eventos = eventos[:corte + 1]
    if "prazo" in troca:
        eventos[0]["prazo"] = troca.pop("prazo")
    for k in ("pid", "host"):
        # Run anterior ao pid no estado também não o tem no `run_start`.
        if k in troca and troca[k] is None:
            eventos[0].pop(k, None)
    jsonl.write_text("".join(json.dumps(e) + "\n" for e in eventos))
    caminho = sorted(dir_until(raiz).glob("*.estado.json"))[-1]
    est = json.loads(caminho.read_text())
    est.update(estado="rodando", pid=pid_morto(), host=socket.gethostname())
    for k in ("acoes", "fica_com_voce", "itens", "motivo_fim"):
        est.pop(k, None)
    for k, v in troca.items():
        if v is None:
            est.pop(k, None)
        else:
            est[k] = v
    caminho.write_text(json.dumps(est))
    return raiz, eventos[0]


def pendentes(raiz):
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                        "--repo", str(raiz), "--json"],
                       capture_output=True, text=True, timeout=60)
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"erro": p.stdout + p.stderr}


def test_pendentes_acusa_run_rodando_com_o_pid_morto():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, inicio = noite_que_morreu(tmp)
        mortos = pendentes(raiz).get("mortos") or []
        check("pendentes --json lista o run em `mortos`",
              len(mortos) == 1 and mortos[0].get("item") == "a1", str(mortos))
        m = mortos[0] if mortos else {}
        check("...oferecendo o build completo que faltou, na worktree da noite",
              VERIFY in (m.get("comando") or "")
              and inicio["arvore"] in (m.get("comando") or ""), str(m))
        texto = subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                                "--repo", str(raiz)], capture_output=True,
                               text=True, timeout=60).stdout
        check("...e o texto diz que o supervisor morreu", "morreu" in texto,
              texto)


def test_pendentes_nao_acusa_run_com_o_supervisor_vivo():
    with tempfile.TemporaryDirectory() as tmp:
        vivo = subprocess.Popen([sys.executable, "-c",
                                 "import time; time.sleep(60)", "cepa-until"])
        try:
            raiz, _ = noite_que_morreu(tmp, pid=vivo.pid)
            check("supervisor vivo não entra em `mortos`",
                  not pendentes(raiz).get("mortos"), str(pendentes(raiz)))
        finally:
            vivo.kill()


def test_pendentes_nao_acusa_pid_de_outra_maquina():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, _ = noite_que_morreu(tmp, host="outra-maquina.local")
        check("pid de outro host não é conferido aqui",
              not pendentes(raiz).get("mortos"), str(pendentes(raiz)))


def test_run_antigo_sem_pid_passado_do_prazo_e_acusado():
    """O próprio run do WEGO (2026-09-28-2003) é anterior ao pid no estado:
    sem pid, o que diz que ele morreu é o prazo ter passado há muito."""
    with tempfile.TemporaryDirectory() as tmp:
        velho = (datetime.now() - timedelta(hours=6)).isoformat()
        raiz, _ = noite_que_morreu(tmp, pid=None, host=None, prazo=velho)
        mortos = pendentes(raiz).get("mortos") or []
        check("run sem pid, 6h depois do prazo, entra em `mortos`",
              len(mortos) == 1, str(mortos))


def test_run_sem_pid_dentro_do_prazo_nao_e_acusado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, _ = noite_que_morreu(tmp, pid=None, host=None)
        check("run sem pid ainda dentro do prazo não entra em `mortos`",
              not pendentes(raiz).get("mortos"), str(pendentes(raiz)))


def test_doctor_aponta_o_run_com_o_supervisor_morto():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, inicio = noite_que_morreu(tmp)
        p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(raiz), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ,
                                                 CEPA_DOCTOR_INSTALL="off"))
        out = p.stdout + p.stderr
        linhas = [l for l in out.splitlines() if "[until]" in l]
        check("o doctor avisa em [until] que o supervisor morreu",
              any("morreu" in l for l in linhas), out[-1500:])
        check("...com o build completo que faltou",
              any(VERIFY in l for l in linhas), "\n".join(linhas))


def fecha(raiz, run_id, *extra):
    env = dict(os.environ, CEPA_WORKTREE_HOME=str(raiz.parent / "worktrees"))
    return subprocess.run([sys.executable, str(CEPA_UNTIL), "fecha-morto",
                           f"fila/{run_id}", "--repo", str(raiz), *extra],
                          capture_output=True, text=True, cwd=str(raiz),
                          env=env, timeout=120)


def run_de(inicio):
    return inicio["branch"].split("/", 1)[1]


def test_pendentes_e_doctor_mandam_rodar_o_fecha_morto():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, inicio = noite_que_morreu(tmp)
        m = (pendentes(raiz).get("mortos") or [{}])[0]
        check("pendentes traz o comando do fecha-morto",
              m.get("fechar") == f"cepa-until fecha-morto fila/{run_de(inicio)}",
              str(m))
        p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(raiz), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ,
                                                 CEPA_DOCTOR_INSTALL="off"))
        check("...e o doctor também",
              f"cepa-until fecha-morto fila/{run_de(inicio)}" in p.stdout,
              p.stdout[-1500:])


def test_fecha_morto_sem_sim_so_mostra_o_plano():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, inicio = noite_que_morreu(tmp)
        p = fecha(raiz, run_de(inicio))
        check("sem --sim sai 0 e diz como confirmar",
              p.returncode == 0 and "--sim" in p.stdout, p.stdout + p.stderr)
        check("...e não mexe no estado", estado(raiz)["estado"] == "rodando",
              str(estado(raiz)))
        n = sum(1 for e in ledger_de(raiz) if e["evento"] == "verify")
        check("...nem roda o build", n == 0, str(ledger_de(raiz)))


def test_fecha_morto_verde_deixa_o_run_pronto_para_aterrissar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, inicio = noite_que_morreu(tmp)
        run_id = run_de(inicio)
        p = fecha(raiz, run_id, "--sim")
        check("fecha-morto --sim sai 0 com o build verde", p.returncode == 0,
              p.stdout + p.stderr)
        ev = ledger_de(raiz)
        check("...grava o build no registro, marcado como fechamento",
              any(e["evento"] == "verify" and e.get("fechamento")
                  and e.get("verde") for e in ev), str(ev[-3:]))
        check("...e fecha o registro com run_end",
              ev[-1]["evento"] == "run_end"
              and ev[-1].get("motivo") == "supervisor-morto", str(ev[-1]))
        est = estado(raiz)
        check("...o estado vira esperando-dono com a ação aterrissar",
              est.get("estado") == "esperando-dono"
              and any(x.get("id") == "aterrissar" for x in est.get("acoes") or []),
              str(est))
        env = dict(os.environ, CEPA_WORKTREE_HOME=str(raiz.parent / "worktrees"))
        a = subprocess.run([sys.executable, str(CEPA_UNTIL), "aterrissar",
                            f"fila/{run_id}", "--repo", str(raiz), "--sim"],
                           capture_output=True, text=True, cwd=str(raiz),
                           env=env, timeout=120)
        check("...e o aterrissar aceita o run", a.returncode == 0,
              a.stdout + a.stderr)
        check("...o doctor para de apontar o run",
              not pendentes(raiz).get("mortos"), str(pendentes(raiz)))


def test_fecha_morto_vermelho_nao_muda_o_estado():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, inicio = noite_que_morreu(tmp)
        arvore = Path(inicio["arvore"])
        (arvore / "quebra.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=arvore, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "quebra"], cwd=arvore, check=True)
        p = fecha(raiz, run_de(inicio), "--sim")
        check("build vermelho sai com erro", p.returncode != 0,
              p.stdout + p.stderr)
        check("...o registro guarda o vermelho",
              any(e["evento"] == "verify" and e.get("fechamento")
                  and e.get("verde") is False for e in ledger_de(raiz)),
              str(ledger_de(raiz)[-2:]))
        check("...e o estado continua `rodando` (o doctor segue apontando)",
              estado(raiz)["estado"] == "rodando"
              and pendentes(raiz).get("mortos"), str(estado(raiz)))


def test_fecha_morto_recusa_supervisor_vivo():
    with tempfile.TemporaryDirectory() as tmp:
        vivo_ = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(60)", "cepa-until"])
        try:
            raiz, inicio = noite_que_morreu(tmp, pid=vivo_.pid)
            p = fecha(raiz, run_de(inicio), "--sim")
            check("fecha-morto recusa run com o supervisor vivo",
                  p.returncode != 0 and str(vivo_.pid) in p.stderr,
                  p.stdout + p.stderr)
            check("...sem rodar o build",
                  not any(e["evento"] == "verify" and e.get("fechamento")
                          for e in ledger_de(raiz)))
        finally:
            vivo_.kill()


def test_fecha_morto_aceita_run_interrompido():
    with tempfile.TemporaryDirectory() as tmp:
        raiz, inicio = noite_que_morreu(tmp, estado="interrompido")
        check("run interrompido também aparece em `mortos`",
              len(pendentes(raiz).get("mortos") or []) == 1,
              str(pendentes(raiz)))
        p = fecha(raiz, run_de(inicio), "--sim")
        check("...e o fecha-morto o fecha",
              p.returncode == 0
              and estado(raiz)["estado"] == "esperando-dono",
              p.stdout + p.stderr)


def test_help_lista_os_subcomandos():
    """Os subcomandos são despachados antes do argparse do modo principal: sem
    o epílogo, o `--help` não diz que eles existem."""
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "--help"],
                       capture_output=True, text=True, timeout=30)
    for sub in ("aterrissar", "pendentes", "fecha-morto"):
        check(f"--help cita o subcomando {sub}",
              f"cepa-until {sub}" in p.stdout, p.stdout[-800:])
        q = subprocess.run([sys.executable, str(CEPA_UNTIL), sub, "--help"],
                           capture_output=True, text=True, timeout=30)
        check(f"...e `{sub} --help` mostra o uso dele",
              q.returncode == 0 and f"cepa-until {sub}" in q.stdout,
              q.stdout + q.stderr)


def test_until_review_confere_o_supervisor_morto():
    texto = UNTIL_REVIEW.read_text(encoding="utf-8")
    check("o /common:until-review manda conferir `mortos` no pendentes",
          "cepa-until pendentes" in texto and "mortos" in texto
          and "interrompido" in texto and "fecha-morto" in texto)


def main():
    print("cepa-until — supervisor morto\n")
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
