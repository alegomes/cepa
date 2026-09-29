#!/usr/bin/env python3
"""cepa-until aterrissar — passo 3 do until-fim-sem-dono.

O run não toca a `main` (decisão 3 do dono, 26/09): no fim ele grava a ação
`aterrissar` no `<run>.estado.json`, e quem a dispara é o dono. O comando é
camada fina sobre os guardas que já existem (C3 de
`docs/estrategia-fim-do-cepa-until.md`): dono único pelo `worktree-guard.py`,
parar no conflito, nunca fazer push com build vermelho, gravar o ponto de
retorno, recusar se o estado mudou desde a proposta, e retomar de onde parou.

Todos os casos rodam um `cepa-until` de verdade contra um repo falso, e depois
o `cepa-until aterrissar` contra o que ele deixou.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, fake_claude, item, ledger_de, monta_repo, roda)
from test_cepa_until_branch_da_noite import (  # noqa: E402
    TRABALHA, VERIFY, git, plano_de)


def estado(raiz):
    d = raiz / ".claude" / "programs" / "fila" / "until"
    return json.loads(sorted(d.glob("*.estado.json"))[-1].read_text())


def noite(raiz):
    """Roda uma noite com a1 entregue e devolve (run_id, branch, arvore)."""
    tmp = raiz.parent
    binv = fake_claude(tmp, TRABALHA)
    roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", VERIFY])
    inicio = [e for e in ledger_de(raiz) if e["evento"] == "run_start"][0]
    return inicio["branch"].split("/", 1)[1], inicio["branch"], inicio["arvore"]


def aterrissa(raiz, run_id, *extra):
    env = dict(os.environ)
    env.setdefault("CEPA_WORKTREE_HOME", str(raiz.parent / "worktrees"))
    return subprocess.run(
        [sys.executable, str(CEPA_UNTIL), "aterrissar", f"fila/{run_id}",
         "--repo", str(raiz), *extra],
        capture_output=True, text=True, cwd=str(raiz), env=env, timeout=120)


def commit(raiz, arquivo, conteudo, msg):
    (raiz / arquivo).write_text(conteudo)
    # Só o arquivo: a fila que o run marcou no clone fica sem commit, como
    # fica de verdade depois de um run.
    git(raiz, "add", arquivo)
    git(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg)


def com_origin(raiz):
    remoto = raiz.parent / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remoto)], check=True)
    git(raiz, "remote", "add", "origin", str(remoto))
    git(raiz, "push", "-q", "-u", "origin", "HEAD")
    return remoto


def test_sem_sim_so_mostra_o_plano():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, branch, _ = noite(raiz)
        antes = git(raiz, "rev-parse", "HEAD")
        p = aterrissa(raiz, run_id)
        check("sem --sim sai 0", p.returncode == 0, p.stderr + p.stdout)
        check("...mostra o efeito e como confirmar",
              "--sim" in p.stdout and branch in p.stdout, p.stdout)
        check("...e não mexe na main", git(raiz, "rev-parse", "HEAD") == antes)


def test_aterrissa_constroi_faz_push_e_limpa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        remoto = com_origin(raiz)
        run_id, branch, arvore = noite(raiz)
        antes = git(raiz, "rev-parse", "HEAD")
        p = aterrissa(raiz, run_id, "--sim")
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + p.stdout)
        log = git(raiz, "log", "--format=%s", "HEAD").splitlines()
        check("o commit do item está na main", "a1" in log, str(log))
        check("...por um merge (--no-ff)",
              len(git(raiz, "rev-list", "--parents", "-1", "HEAD").split()) == 3)
        check("o push levou a main ao origin",
              git(raiz, "rev-parse", "HEAD")
              == subprocess.run(["git", "--git-dir", str(remoto), "rev-parse",
                                 "HEAD"], capture_output=True,
                                text=True).stdout.strip())
        check("a branch da noite some",
              not git(raiz, "branch", "--list", branch))
        check("...e a worktree dela também", not Path(arvore).exists(), arvore)
        est = estado(raiz)
        check("o estado vira aterrissado com o ponto de retorno",
              est.get("estado") == "aterrissado"
              and (est.get("aterrissagem") or {}).get("retorno") == antes,
              str(est))


def test_build_vermelho_depois_do_merge_volta_ao_retorno_sem_push():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        remoto = com_origin(raiz)
        run_id, branch, _ = noite(raiz)
        # A main andou depois do run, e a soma dos dois fica vermelha.
        commit(raiz, "quebra.txt", "x", "main andou")
        git(raiz, "push", "-q")
        retorno = git(raiz, "rev-parse", "HEAD")
        p = aterrissa(raiz, run_id, "--sim")
        check("sai com erro", p.returncode != 0, p.stdout)
        check("a main volta ao ponto de retorno",
              git(raiz, "rev-parse", "HEAD") == retorno)
        check("...o origin não recebe nada",
              subprocess.run(["git", "--git-dir", str(remoto), "rev-parse",
                              "HEAD"], capture_output=True,
                             text=True).stdout.strip() == retorno)
        check("a branch da noite continua", git(raiz, "branch", "--list", branch))
        check("o estado continua esperando-dono",
              estado(raiz).get("estado") == "esperando-dono", str(estado(raiz)))
        check("a saída diz que o build ficou vermelho",
              "vermelho" in p.stdout.lower(), p.stdout)
        check("...e o desfazer preserva a fila que o run marcou no clone",
              "status: done" in plano_de(raiz).read_text(),
              plano_de(raiz).read_text()[:300])


def test_conflito_para_e_rodar_de_novo_retoma():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, branch, arvore = noite(raiz)
        commit(raiz, "a1.txt", "outro conteudo", "main mexeu no a1.txt")
        p = aterrissa(raiz, run_id, "--sim")
        check("o conflito para com erro", p.returncode != 0, p.stdout)
        check("...e nomeia o arquivo", "a1.txt" in p.stdout, p.stdout)
        check("...deixando o conflito para o dono",
              "a1.txt" in git(raiz, "diff", "--name-only", "--diff-filter=U"))
        # O dono resolve e conclui o merge.
        (raiz / "a1.txt").write_text("resolvido")
        git(raiz, "add", "a1.txt")
        git(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
            "resolve")
        p = aterrissa(raiz, run_id, "--sim")
        check("rodar de novo retoma do build e termina",
              p.returncode == 0 and estado(raiz).get("estado") == "aterrissado",
              p.stdout + p.stderr)
        check("...sem fazer outro merge",
              git(raiz, "log", "-1", "--format=%s") == "resolve",
              git(raiz, "log", "-3", "--format=%s"))
        check("...e limpa a branch da noite",
              not git(raiz, "branch", "--list", branch))


def test_dono_vivo_na_branch_da_noite_recusa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, branch, arvore = noite(raiz)
        d = raiz / ".claude" / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (d / "viva.json").write_text(json.dumps({
            "session_id": "viva", "pid": os.getpid(),
            "hostname": socket.gethostname(), "cwd": arvore,
            "branch": branch, "started_at": agora, "last_seen": agora}))
        antes = git(raiz, "rev-parse", "HEAD")
        p = aterrissa(raiz, run_id, "--sim")
        check("recusa com sessão viva na branch da noite",
              p.returncode != 0 and git(raiz, "rev-parse", "HEAD") == antes,
              p.stdout + p.stderr)
        check("...e diz quem está nela", arvore in p.stdout + p.stderr,
              p.stdout + p.stderr)


def test_branch_da_noite_que_mudou_depois_da_proposta_recusa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, branch, arvore = noite(raiz)
        commit(Path(arvore), "tarde.txt", "x", "commit depois do fim do run")
        antes = git(raiz, "rev-parse", "HEAD")
        p = aterrissa(raiz, run_id, "--sim")
        check("recusa quando a branch da noite andou depois da proposta",
              p.returncode != 0 and git(raiz, "rev-parse", "HEAD") == antes,
              p.stdout + p.stderr)
        check("...e diz o que mudou", "mudou" in p.stdout + p.stderr,
              p.stdout + p.stderr)


def test_clone_com_mudanca_nao_commitada_recusa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, _, _ = noite(raiz)
        (raiz / "rascunho.txt").write_text("x")
        antes = git(raiz, "rev-parse", "HEAD")
        p = aterrissa(raiz, run_id, "--sim")
        check("recusa com o clone sujo",
              p.returncode != 0 and git(raiz, "rev-parse", "HEAD") == antes,
              p.stdout + p.stderr)


def test_o_resumo_do_run_aponta_o_comando():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, TRABALHA)
        p, _ = roda(raiz, binv, plano_de(raiz), ["--for", "2h", "--verify", VERIFY])
        run_id = [e for e in ledger_de(raiz)
                  if e["evento"] == "run_start"][0]["branch"].split("/", 1)[1]
        cmd = f"cepa-until aterrissar fila/{run_id}"
        check("o terminal mostra o comando", cmd in p.stdout, p.stdout[-800:])
        acao = (estado(raiz).get("acoes") or [{}])[0]
        check("...e o estado também", cmd in (acao.get("comando") or ""), str(acao))


# ── passo 5: pendentes, doctor e next leem o estado do run ─────────────────

DOCTOR = CEPA_UNTIL.parent / "cepa-doctor"
NEXT = CEPA_UNTIL.parents[1] / "commands" / "next.md"


def pendentes(raiz):
    return subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                           "--repo", str(raiz)], capture_output=True, text=True,
                          cwd=str(raiz), timeout=60)


def test_5_pendentes_lista_o_run_esperando_e_some_depois_de_aterrissar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, _, _ = noite(raiz)
        p = pendentes(raiz)
        check("pendentes lista o run com o comando",
              p.returncode == 0
              and f"cepa-until aterrissar fila/{run_id}" in p.stdout,
              p.stdout + p.stderr)
        aterrissa(raiz, run_id, "--sim")
        check("...e some depois de aterrissado",
              run_id not in pendentes(raiz).stdout, pendentes(raiz).stdout)


def test_5_merge_feito_a_mao_tambem_tira_o_run_da_lista():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, branch, _ = noite(raiz)
        git(raiz, "-c", "user.email=t@t", "-c", "user.name=t", "merge",
            "-q", "--no-ff", "--no-edit", branch)
        check("branch já mesclada no clone não é pendência",
              run_id not in pendentes(raiz).stdout, pendentes(raiz).stdout)


def test_5_doctor_avisa_o_run_esperando_o_dono():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1")])
        run_id, _, _ = noite(raiz)
        p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(raiz), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ,
                                                 CEPA_DOCTOR_INSTALL="off"))
        out = p.stdout + p.stderr
        check("o doctor avisa na área [until] com o comando",
              "[until]" in out
              and f"cepa-until aterrissar fila/{run_id}" in out, out[-1500:])


def test_5_next_le_os_runs_esperando():
    texto = NEXT.read_text(encoding="utf-8")
    check("o /common:next manda rodar o cepa-until pendentes",
          "cepa-until pendentes" in texto)


def test_5_cabecalho_curto_sem_caminho_absoluto_e_com_custo():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta_repo(tmp, [item("a1"), item("a2")])
        corpo = TRABALHA + (
            "print(json.dumps({'type': 'result', 'result': 'ok',"
            " 'total_cost_usd': 1.25}))\n")
        binv = fake_claude(tmp, corpo)
        p, _ = roda(raiz, binv, plano_de(raiz),
                    ["--for", "2h", "--verify", VERIFY])
        cab = p.stdout.split("\n\n")[0].splitlines()
        check("o cabeçalho tem no máximo 7 linhas", len(cab) <= 7,
              "\n".join(cab))
        check("nenhum caminho absoluto do repo na saída",
              str(raiz) not in p.stdout
              and str(raiz.resolve()) not in p.stdout, p.stdout)
        check("o resumo traz o custo com a conta",
              "US$ 2,50" in p.stdout and "1,25 + 1,25" in p.stdout,
              p.stdout[-900:])
        check("...e o estado também",
              estado(raiz).get("custo_usd") == 2.5, str(estado(raiz)))


def main():
    print("cepa-until aterrissar\n")
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
