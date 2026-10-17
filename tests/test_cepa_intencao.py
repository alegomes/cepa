#!/usr/bin/env python3
"""`common/bin/cepa-intencao`: o único escritor do `.claude/session-intent`.

Sem dependência externa — rode com `python3 tests/test_cepa_intencao.py`.
Sai com código != 0 se algo falhar.

Por que existe: o leitor (`_modos.read_intent`) é tolerante e não impõe regra
nenhuma; as regras (plano de 1 a PLANO_MAX, item sem ':', motivo obrigatório na
troca) só existem porque o escritor as recusa. Cada recusa é testada junto com
"o arquivo não mudou", senão uma recusa que escreve pela metade passaria.
O bin roda como subprocesso num repo git temporário: o teste exercita a
superfície de CLI, não funções internas.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from _telemetria_isolada import isola
isola()

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin" / "cepa-intencao"
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modos as M  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


TMP = Path(tempfile.mkdtemp(prefix="cepa-intencao-test-"))
TEL = TMP / "tel"
ENV = {**os.environ, "CEPA_TELEMETRY_DIR": str(TEL), "CLAUDE_CODE_SESSION_ID": "sess-1"}


def novo_repo(nome):
    r = TMP / nome
    r.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    return r


def cepa(repo, *args):
    return subprocess.run([sys.executable, str(BIN), *args], cwd=repo, env=ENV,
                          capture_output=True, text=True)


def arquivo(repo):
    p = repo / ".claude" / "session-intent"
    return p.read_text() if p.exists() else None


def eventos():
    out = []
    for f in sorted(TEL.glob("events-*.jsonl")):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


PLANO = ["levantar o que existe", "escrever o doc", "rodar advisors", "decidir"]


def gravar(repo, plano=PLANO, proposito="institucionalizar as perguntas", extra=()):
    return cepa(repo, "gravar", "--proposito", proposito, "--para-quando",
                "doc decidido", "--plano", *plano, *extra)


# --- gravar -----------------------------------------------------------------
r1 = novo_repo("r1")
p = gravar(r1)
check("gravar sai 0", p.returncode == 0, p.stderr)
d = M.read_intent(r1)
check("round-trip: propósito", d["proposito"] == "institucionalizar as perguntas", d)
check("round-trip: plano", d["plano"] == PLANO, d.get("plano"))
check("round-trip: para_quando", d["para_quando"] == "doc decidido")
check("passo=1 inteiro", d["passo"] == 1)
check("session_id da env", d["session_id"] == "sess-1")
check("branch", d["branch"] == "main", d.get("branch"))
check("passo_desde e aberto_em em UTC Z",
      d["passo_desde"].endswith("Z") and d["aberto_em"].endswith("Z"))
check("resumo na ordem do corte de 80 colunas",
      d["resumo"] == "passo 1/4 · levantar o que existe · institucionalizar as perguntas",
      d["resumo"])
check("historico vazio", d["historico"] == [])
ev = [e for e in eventos() if e["event"] == "intent.written"]
check("evento intent.written (gravar, passos=4)",
      len(ev) == 1 and ev[0]["acao"] == "gravar" and ev[0]["passos"] == 4, ev)
check("telemetria sem texto do propósito",
      "institucionalizar" not in json.dumps(eventos()))

# aspas e barra no propósito sobrevivem ao round-trip
r_q = novo_repo("rq")
gravar(r_q, proposito='dizer "oi" e \\ sair')
check("aspas/barra round-trip", M.read_intent(r_q)["proposito"] == 'dizer "oi" e \\ sair')

# regravar exige motivo
antes = arquivo(r1)
p = gravar(r1, proposito="outro")
check("regravar sem --motivo recusa (4)", p.returncode == 4, p.returncode)
check("regravar recusado não escreve", arquivo(r1) == antes)
p = gravar(r1, plano=["só um"], proposito="outro", extra=("--motivo", "mudou o rumo"))
d = M.read_intent(r1)
check("regravar com motivo ok", p.returncode == 0 and d["proposito"] == "outro", p.stderr)
h = d["historico"]
check("regravar guarda o anterior no histórico",
      len(h) == 1 and h[0]["proposito"] == "institucionalizar as perguntas"
      and h[0]["motivo_da_troca"] == "mudou o rumo" and h[0]["em"].endswith("Z")
      and "rodar advisors" in h[0]["plano_anterior"], h)

# --- --passo ----------------------------------------------------------------
r2 = novo_repo("r2")
gravar(r2)
p = cepa(r2, "--passo", "3")
d = M.read_intent(r2)
check("--passo 3 move o cursor", p.returncode == 0 and d["passo"] == 3, p.stderr)
check("--passo re-renderiza o resumo",
      d["resumo"] == "passo 3/4 · rodar advisors · institucionalizar as perguntas", d["resumo"])
ev = [e for e in eventos() if e["event"] == "intent.cursor_advanced"]
check("evento intent.cursor_advanced (de=1 para=3 passos=4)",
      len(ev) == 1 and (ev[0]["de"], ev[0]["para"], ev[0]["passos"]) == (1, 3, 4), ev)
p = cepa(r2, "--passo", "5")
d = M.read_intent(r2)
check("--passo len+1 = plano cumprido",
      p.returncode == 0 and d["passo"] == 5 and d["resumo"].startswith("plano cumprido 4/4 · "),
      d.get("resumo"))
for ruim in ("0", "6", "-1"):
    antes = arquivo(r2)
    p = cepa(r2, "--passo", ruim)
    check(f"--passo {ruim} recusado e arquivo intacto",
          p.returncode == 2 and arquivo(r2) == antes, (p.returncode, p.stderr))

# --- regras do plano ----------------------------------------------------------
r3 = novo_repo("r3")
p = gravar(r3, plano=["tem: dois pontos"])
check("item com ':' recusado, nada escrito", p.returncode == 2 and arquivo(r3) is None, p.stderr)
p = gravar(r3, plano=[f"passo {i}" for i in range(M.PLANO_MAX + 1)])
check("plano > PLANO_MAX recusado, aponta plan.yaml",
      p.returncode == 2 and arquivo(r3) is None and "plan.yaml" in p.stderr, p.stderr)
p = gravar(r3, plano=[f"passo {i}" for i in range(M.PLANO_MAX)])
check("plano com PLANO_MAX itens aceito", p.returncode == 0, p.stderr)

# --- --proposito / --plano --------------------------------------------------
r4 = novo_repo("r4")
gravar(r4)
antes = arquivo(r4)
p = cepa(r4, "--proposito", "novo")
check("--proposito sem --motivo recusado, arquivo intacto",
      p.returncode == 2 and arquivo(r4) == antes, p.stderr)
cepa(r4, "--passo", "3")
p = cepa(r4, "--proposito", "novo propósito", "--motivo", "o dono reformulou")
d = M.read_intent(r4)
check("--proposito troca e preserva o cursor", p.returncode == 0
      and d["proposito"] == "novo propósito" and d["passo"] == 3, p.stderr)
check("--proposito empurra o anterior pro histórico",
      d["historico"][-1]["proposito"] == "institucionalizar as perguntas"
      and d["historico"][-1]["motivo_da_troca"] == "o dono reformulou"
      and d["historico"][-1]["em"].endswith("Z"), d["historico"])
check("resumo usa o propósito novo", d["resumo"].endswith("· novo propósito"), d["resumo"])
p = cepa(r4, "--plano", "a", "b")
d = M.read_intent(r4)
check("--plano substitui e zera o cursor",
      p.returncode == 0 and d["plano"] == ["a", "b"] and d["passo"] == 1, p.stderr)
check("--plano preserva o plano anterior no histórico",
      "rodar advisors" in d["historico"][-1].get("plano_anterior", ""), d["historico"])
antes = arquivo(r4)
p = cepa(r4, "--plano", "x: y")
check("--plano com ':' recusado, intacto", p.returncode == 2 and arquivo(r4) == antes)
acoes = [e["acao"] for e in eventos() if e["event"] == "intent.written"]
check("eventos proposito e plano emitidos", "proposito" in acoes and "plano" in acoes, acoes)

# --- sem intenção -----------------------------------------------------------
r5 = novo_repo("r5")
for args in (("--passo", "1"), ("--proposito", "x", "--motivo", "y"), ("--plano", "a"), ("mostrar",)):
    p = cepa(r5, *args)
    check(f"sem intenção: {' '.join(args)} recusa (3) em pt-BR e não cria arquivo",
          p.returncode == 3 and "não há intenção" in p.stderr and arquivo(r5) is None,
          (p.returncode, p.stderr))
p = cepa(r2, "mostrar")
check("mostrar imprime o resumo", p.returncode == 0 and "plano cumprido 4/4" in p.stdout, p.stdout)

# --- subcomando depois de --plano --------------------------------------------
r6 = novo_repo("r6")
for sub in ("gravar", "mostrar"):
    for pre in (False, True):
        if pre and arquivo(r6) is None:
            gravar(r6)
        antes = arquivo(r6)
        p = cepa(r6, "--plano", "a", "b", sub)
        check(f"--plano a b {sub} ({'com' if pre else 'sem'} intenção) recusa rc=2, intacto",
              p.returncode == 2 and arquivo(r6) == antes and "ANTES de --plano" in p.stderr,
              (p.returncode, p.stderr))
p = cepa(r6, "gravar", "--plano", "a", "b", "--proposito", "x", "--para-quando", "y",
         "--motivo", "m")
check("gravar --plano a b --proposito x --para-quando y aceito",
      p.returncode == 0 and M.read_intent(r6)["plano"] == ["a", "b"], p.stderr)

# --- gravar sobre arquivo parcial preserva o histórico -------------------------
r7 = novo_repo("r7")
(r7 / ".claude").mkdir()
(r7 / ".claude" / "session-intent").write_text(
    'proposito: "velho"\nhistorico:\n  - em: "2026-01-01T00:00:00Z"\n    proposito: "antigo"\n')
p = gravar(r7)
h = M.read_intent(r7)["historico"]
check("gravar sobre arquivo parcial preserva o histórico",
      p.returncode == 0 and len(h) == 1 and h[0]["proposito"] == "antigo", (p.stderr, h))

# --- stdout == resumo gravado ---------------------------------------------------
r8 = novo_repo("r8")
p = gravar(r8, proposito="linha um\nlinha dois")
check("stdout igual ao resumo gravado (quebra de linha normalizada)",
      p.stdout.strip() == M.read_intent(r8)["resumo"] and "\n" not in p.stdout.strip(),
      (p.stdout, M.read_intent(r8)["resumo"]))

# --- fora de git ------------------------------------------------------------
fora = TMP / "fora"
fora.mkdir()
p = cepa(fora, "--passo", "1")
check("fora de repo git recusa", p.returncode == 2 and "git" in p.stderr, p.stderr)

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
    sys.exit(1)
print("\ntudo ok")
