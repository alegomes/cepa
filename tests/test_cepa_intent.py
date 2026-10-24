#!/usr/bin/env python3
"""`common/bin/cepa-intent`: o único escritor do `.claude/session-intent`.

Sem dependência externa — rode com `python3 tests/test_cepa_intent.py`.
Sai com código != 0 se algo falhar.

(Os nomes antigos — `gravar`, `--proposito`, etc. — ainda funcionam; a seção
"nomes antigos" no fim prova.)

Por que existe: o leitor (`_modes.read_intent`) é tolerante e não impõe regra
nenhuma; as regras (plano de 1 a PLAN_MAX, item sem ':', motivo obrigatório na
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
BIN = REPO / "common" / "bin" / "cepa-intent"
BIN_ANTIGO = REPO / "common" / "bin" / "cepa-intencao"  # atalho: nome antigo
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modes as M  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


TMP = Path(tempfile.mkdtemp(prefix="cepa-intent-test-"))
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
    return cepa(repo, "write", "--purpose", proposito, "--by-when",
                "doc decidido", "--plan", *plano, *extra)


# --- gravar -----------------------------------------------------------------
r1 = novo_repo("r1")
p = gravar(r1)
check("gravar sai 0", p.returncode == 0, p.stderr)
d = M.read_intent(r1)
check("round-trip: propósito", d["purpose"] == "institucionalizar as perguntas", d)
check("round-trip: plano", d["plan"] == PLANO, d.get("plan"))
check("round-trip: para_quando", d["by_when"] == "doc decidido")
check("passo=1 inteiro", d["step"] == 1)
check("session_id da env", d["session_id"] == "sess-1")
check("branch", d["branch"] == "main", d.get("branch"))
check("passo_desde e aberto_em em UTC Z",
      d["step_since"].endswith("Z") and d["opened_at"].endswith("Z"))
check("resumo na ordem do corte de 80 colunas",
      d["summary"] == "passo 1/4 · levantar o que existe · institucionalizar as perguntas",
      d["summary"])
check("historico vazio", d["history"] == [])
ev = [e for e in eventos() if e["event"] == "intent.written"]
check("evento intent.written (gravar, passos=4)",
      len(ev) == 1 and ev[0]["acao"] == "gravar" and ev[0]["passos"] == 4, ev)
check("telemetria sem texto do propósito",
      "institucionalizar" not in json.dumps(eventos()))

# aspas e barra no propósito sobrevivem ao round-trip
r_q = novo_repo("rq")
gravar(r_q, proposito='dizer "oi" e \\ sair')
check("aspas/barra round-trip", M.read_intent(r_q)["purpose"] == 'dizer "oi" e \\ sair')

# regravar exige motivo
antes = arquivo(r1)
p = gravar(r1, proposito="outro")
check("regravar sem --motivo recusa (4)", p.returncode == 4, p.returncode)
check("regravar recusado não escreve", arquivo(r1) == antes)
p = gravar(r1, plano=["só um"], proposito="outro", extra=("--reason", "mudou o rumo"))
d = M.read_intent(r1)
check("regravar com motivo ok", p.returncode == 0 and d["purpose"] == "outro", p.stderr)
h = d["history"]
check("regravar guarda o anterior no histórico",
      len(h) == 1 and h[0]["purpose"] == "institucionalizar as perguntas"
      and h[0]["change_reason"] == "mudou o rumo" and h[0]["at"].endswith("Z")
      and "rodar advisors" in h[0]["previous_plan"], h)

# --- --passo ----------------------------------------------------------------
r2 = novo_repo("r2")
gravar(r2)
p = cepa(r2, "--step", "3")
d = M.read_intent(r2)
check("--passo 3 move o cursor", p.returncode == 0 and d["step"] == 3, p.stderr)
check("--passo re-renderiza o resumo",
      d["summary"] == "passo 3/4 · rodar advisors · institucionalizar as perguntas", d["summary"])
ev = [e for e in eventos() if e["event"] == "intent.cursor_advanced"]
check("evento intent.cursor_advanced (de=1 para=3 passos=4)",
      len(ev) == 1 and (ev[0]["de"], ev[0]["para"], ev[0]["passos"]) == (1, 3, 4), ev)
p = cepa(r2, "--step", "5")
d = M.read_intent(r2)
check("--passo len+1 = plano cumprido",
      p.returncode == 0 and d["step"] == 5 and d["summary"].startswith("plano cumprido 4/4 · "),
      d.get("summary"))
for ruim in ("0", "6", "-1"):
    antes = arquivo(r2)
    p = cepa(r2, "--step", ruim)
    check(f"--passo {ruim} recusado e arquivo intacto",
          p.returncode == 2 and arquivo(r2) == antes, (p.returncode, p.stderr))

# --- regras do plano ----------------------------------------------------------
r3 = novo_repo("r3")
p = gravar(r3, plano=["tem: dois pontos"])
check("item com ':' recusado, nada escrito", p.returncode == 2 and arquivo(r3) is None, p.stderr)
p = gravar(r3, plano=[f"passo {i}" for i in range(M.PLAN_MAX + 1)])
check("plano > PLAN_MAX recusado, aponta plan.yaml",
      p.returncode == 2 and arquivo(r3) is None and "plan.yaml" in p.stderr, p.stderr)
p = gravar(r3, plano=[f"passo {i}" for i in range(M.PLAN_MAX)])
check("plano com PLAN_MAX itens aceito", p.returncode == 0, p.stderr)

# --- --proposito / --plano --------------------------------------------------
r4 = novo_repo("r4")
gravar(r4)
antes = arquivo(r4)
p = cepa(r4, "--purpose", "novo")
check("--proposito sem --motivo recusado, arquivo intacto",
      p.returncode == 2 and arquivo(r4) == antes, p.stderr)
cepa(r4, "--step", "3")
p = cepa(r4, "--purpose", "novo propósito", "--reason", "o dono reformulou")
d = M.read_intent(r4)
check("--proposito troca e preserva o cursor", p.returncode == 0
      and d["purpose"] == "novo propósito" and d["step"] == 3, p.stderr)
check("--proposito empurra o anterior pro histórico",
      d["history"][-1]["purpose"] == "institucionalizar as perguntas"
      and d["history"][-1]["change_reason"] == "o dono reformulou"
      and d["history"][-1]["at"].endswith("Z"), d["history"])
check("resumo usa o propósito novo", d["summary"].endswith("· novo propósito"), d["summary"])
p = cepa(r4, "--plan", "a", "b")
d = M.read_intent(r4)
check("--plano substitui e zera o cursor",
      p.returncode == 0 and d["plan"] == ["a", "b"] and d["step"] == 1, p.stderr)
check("--plano preserva o plano anterior no histórico",
      "rodar advisors" in d["history"][-1].get("previous_plan", ""), d["history"])
antes = arquivo(r4)
p = cepa(r4, "--plan", "x: y")
check("--plano com ':' recusado, intacto", p.returncode == 2 and arquivo(r4) == antes)
acoes = [e["acao"] for e in eventos() if e["event"] == "intent.written"]
check("eventos proposito e plano emitidos", "proposito" in acoes and "plano" in acoes, acoes)

# --- sem intenção -----------------------------------------------------------
r5 = novo_repo("r5")
for args in (("--step", "1"), ("--purpose", "x", "--reason", "y"), ("--plan", "a"), ("show",)):
    p = cepa(r5, *args)
    check(f"sem intenção: {' '.join(args)} recusa (3) em pt-BR e não cria arquivo",
          p.returncode == 3 and "não há intenção" in p.stderr and arquivo(r5) is None,
          (p.returncode, p.stderr))
p = cepa(r2, "show")
check("mostrar imprime o resumo", p.returncode == 0 and "plano cumprido 4/4" in p.stdout, p.stdout)

# --- subcomando depois de --plano --------------------------------------------
r6 = novo_repo("r6")
for sub in ("write", "show", "continue"):
    for pre in (False, True):
        if pre and arquivo(r6) is None:
            gravar(r6)
        antes = arquivo(r6)
        p = cepa(r6, "--plan", "a", "b", sub)
        check(f"--plano a b {sub} ({'com' if pre else 'sem'} intenção) recusa rc=2, intacto",
              p.returncode == 2 and arquivo(r6) == antes and "ANTES de --plan" in p.stderr,
              (p.returncode, p.stderr))
p = cepa(r6, "write", "--plan", "a", "b", "--purpose", "x", "--by-when", "y",
         "--reason", "m")
check("gravar --plano a b --proposito x --para-quando y aceito",
      p.returncode == 0 and M.read_intent(r6)["plan"] == ["a", "b"], p.stderr)

# --- gravar sobre arquivo parcial preserva o histórico -------------------------
r7 = novo_repo("r7")
(r7 / ".claude").mkdir()
(r7 / ".claude" / "session-intent").write_text(
    # arquivo no formato ANTIGO (chaves em pt-BR): o leitor ainda o entende
    'proposito: "velho"\nhistorico:\n  - em: "2026-01-01T00:00:00Z"\n    proposito: "antigo"\n')
p = gravar(r7)
h = M.read_intent(r7)["history"]
check("gravar sobre arquivo parcial preserva o histórico",
      p.returncode == 0 and len(h) == 1 and h[0]["purpose"] == "antigo", (p.stderr, h))

# --- stdout == resumo gravado ---------------------------------------------------
r8 = novo_repo("r8")
p = gravar(r8, proposito="linha um\nlinha dois")
check("stdout igual ao resumo gravado (quebra de linha normalizada)",
      p.stdout.strip() == M.read_intent(r8)["summary"] and "\n" not in p.stdout.strip(),
      (p.stdout, M.read_intent(r8)["summary"]))

# --- recusas que nada mais cobria (cada uma: rc=2 e arquivo byte a byte igual) ----
import hashlib  # noqa: E402


def md5(repo):
    a = arquivo(repo)
    return hashlib.md5((a or "").encode()).hexdigest()


r9 = novo_repo("r9")
gravar(r9)


def recusa2(nome, *args):
    antes = md5(r9)
    p = cepa(r9, *args)
    check(f"{nome}: rc=2 e arquivo intacto",
          p.returncode == 2 and md5(r9) == antes, (p.returncode, p.stderr))


recusa2("item de plano vazio (--plano \"\")", "--plan", "a", "")
recusa2("item de plano só espaços (--plano \"  \")", "--plan", "a", "  ")
recusa2("gravar com item vazio", "write", "--purpose", "x", "--by-when", "y",
        "--plan", "a", "", "--reason", "m")
recusa2("gravar --passo N", "write", "--step", "2", "--purpose", "x",
        "--by-when", "y", "--plan", "a", "--reason", "m")
recusa2("gravar sem --proposito", "write", "--by-when", "y", "--plan", "a",
        "--reason", "m")
recusa2("gravar sem --para-quando", "write", "--purpose", "x", "--plan", "a",
        "--reason", "m")
recusa2("gravar sem --plano", "write", "--purpose", "x", "--by-when", "y",
        "--reason", "m")
recusa2("--passo junto com --proposito", "--step", "2", "--purpose", "x", "--reason", "m")
recusa2("--passo junto com --plano", "--step", "2", "--plan", "a", "b")

r10 = novo_repo("r10")
p = gravar(r10, proposito="a\nb")
d = M.read_intent(r10)
check("propósito 'a\\nb' relido do arquivo é 'a b'",
      p.returncode == 0 and d["purpose"] == "a b", d.get("purpose"))
check("resumo do propósito 'a\\nb' termina em '· a b'", d["summary"].endswith("· a b"), d["summary"])

# --- continuar: adota nesta sessão a intenção de outra (D1) ---------------------
r11 = novo_repo("r11")
p = subprocess.run([sys.executable, str(BIN), "continue"], cwd=r11,
                   env={**ENV, "CLAUDE_CODE_SESSION_ID": "sess-2"}, capture_output=True, text=True)
check("continuar sem intenção recusa (3) e não cria arquivo",
      p.returncode == 3 and arquivo(r11) is None, (p.returncode, p.stderr))
gravar(r11)
cepa(r11, "--step", "2")
antes = M.read_intent(r11)
p = subprocess.run([sys.executable, str(BIN), "continue"], cwd=r11,
                   env={**ENV, "CLAUDE_CODE_SESSION_ID": "sess-2"}, capture_output=True, text=True)
depois = M.read_intent(r11)
check("continuar troca o session_id pelo da sessão atual",
      p.returncode == 0 and depois["session_id"] == "sess-2", (p.stderr, depois))
check("continuar preserva propósito, plano, passo e passo_desde",
      all(depois[k] == antes[k] for k in ("purpose", "plan", "step", "step_since",
                                          "opened_at", "history")), (antes, depois))
check("continuar imprime o resumo", p.stdout.strip() == depois["summary"], p.stdout)
for extra in (["--step", "3"], ["--reason", "m"], ["--purpose", "x"]):
    antes_txt = arquivo(r11)
    p = cepa(r11, "continue", *extra)
    check(f"continuar {' '.join(extra)} recusa rc=2, intacto",
          p.returncode == 2 and arquivo(r11) == antes_txt, (p.returncode, p.stderr))

for extra in (["--plan", "a"], ["--by-when", "y"]):
    antes_txt = arquivo(r11)
    p = cepa(r11, "continue", *extra)
    check(f"continuar {' '.join(extra)} recusa rc=2, intacto",
          p.returncode == 2 and arquivo(r11) == antes_txt, (p.returncode, p.stderr))

# continuar troca o branch e NÃO mexe na idade do cursor (passo_desde antigo)
r12 = novo_repo("r12")
(r12 / ".claude").mkdir()
(r12 / ".claude" / "session-intent").write_text(M.render_intent({
    "purpose": "p", "by_when": "q", "plan": ["a", "b"], "step": 2,
    "step_since": "2020-01-01T00:00:00Z", "session_id": "velha", "branch": "outro",
    "opened_at": "2020-01-01T00:00:00Z", "summary": "passo 2/2 · b · p",
    "history": [{"at": "2019-12-31T00:00:00Z", "purpose": "antigo",
                 "change_reason": "o dono reformulou"}]}))
p = subprocess.run([sys.executable, str(BIN), "continue"], cwd=r12,
                   env={**{k: v for k, v in ENV.items() if k != "CLAUDE_CODE_SESSION_ID"},
                        "CLAUDE_SESSION_ID": "sess-3"}, capture_output=True, text=True)
d = M.read_intent(r12)
check("continuar troca o branch pelo atual", p.returncode == 0 and d["branch"] == "main",
      (p.stderr, d))
check("continuar mantém passo_desde antigo", d["step_since"] == "2020-01-01T00:00:00Z", d)
check("continuar preserva o histórico",
      d.get("history") == [{"at": "2019-12-31T00:00:00Z", "purpose": "antigo",
                            "change_reason": "o dono reformulou"}], d)
check("continuar usa CLAUDE_SESSION_ID quando CLAUDE_CODE_SESSION_ID falta",
      d["session_id"] == "sess-3", d)

antes_txt = arquivo(r11)
p = subprocess.run([sys.executable, str(BIN), "continue"], cwd=r11,
                   env={k: v for k, v in ENV.items()
                        if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID")},
                   capture_output=True, text=True)
check("continuar sem id de sessão no ambiente recusa rc=2, intacto",
      p.returncode == 2 and arquivo(r11) == antes_txt, (p.returncode, p.stderr))

# --- fora de git ------------------------------------------------------------
fora = TMP / "fora"
fora.mkdir()
p = cepa(fora, "--step", "1")
check("fora de repo git recusa", p.returncode == 2 and "git" in p.stderr, p.stderr)

# --- nomes antigos: ações, opções, chaves e o atalho `cepa-intencao` ------------
def antigo(repo, *args, bin=BIN, env=None):
    return subprocess.run([sys.executable, str(bin), *args], cwd=repo, env=env or ENV,
                          capture_output=True, text=True)


ra = novo_repo("ra")
p = antigo(ra, "gravar", "--proposito", "p antigo", "--para-quando", "q", "--plano", "a", "b", "c")
d = M.read_intent(ra)
check("antigo: `gravar --proposito --para-quando --plano` ainda grava",
      p.returncode == 0 and d["purpose"] == "p antigo" and d["plan"] == ["a", "b", "c"], p.stderr)
txt = arquivo(ra)
check("antigo: o arquivo sai SÓ com as chaves novas",
      txt.startswith('purpose: "p antigo"') and "\nproposito" not in txt and "\npasso" not in txt
      and "\nstep: 1" in txt and "\nopened_at:" in txt and "\nsummary:" in txt, txt)
p = antigo(ra, "--passo", "2")
check("antigo: `--passo 2` move o cursor", p.returncode == 0 and M.read_intent(ra)["step"] == 2, p.stderr)
p = antigo(ra, "--proposito", "p2", "--motivo", "porque sim")
h = M.read_intent(ra)["history"]
check("antigo: `--proposito --motivo` troca e o histórico sai com chaves novas",
      p.returncode == 0 and h[-1]["change_reason"] == "porque sim" and h[-1]["purpose"] == "p antigo"
      and h[-1]["at"].endswith("Z"), (p.stderr, h))
p = antigo(ra, "--plano", "x", "y")
check("antigo: `--plano x y` substitui", p.returncode == 0 and M.read_intent(ra)["plan"] == ["x", "y"], p.stderr)
p = antigo(ra, "mostrar")
check("antigo: `mostrar` imprime", p.returncode == 0 and "p2" in p.stdout, p.stderr)
p = antigo(ra, "continuar", env={**ENV, "CLAUDE_CODE_SESSION_ID": "sess-9"})
check("antigo: `continuar` adota a sessão", p.returncode == 0
      and M.read_intent(ra)["session_id"] == "sess-9", p.stderr)
p = antigo(ra, "--plano", "a", "b", "gravar")
check("antigo: `--plano a b gravar` recusa", p.returncode == 2 and "ANTES de --plan" in p.stderr, p.stderr)
p = antigo(ra, "gravar", "--proposito", "x", "--para-quando", "y", "--plano", "a")
check("antigo: regravar sem --motivo recusa (4)", p.returncode == 4, (p.returncode, p.stderr))

# `estado` / `encerrar` antigos produzem a mesma saída que `state` / `close`
for velho, novo in (("estado", "state"), ("encerrar", "close")):
    a, b = antigo(ra, velho), antigo(ra, novo)
    check(f"antigo: `{velho}` == `{novo}`", a.returncode == 0 and a.stdout == b.stdout and a.stdout.strip(),
          (a.stdout, b.stdout))
check("`state` imprime `state:` na primeira linha",
      antigo(ra, "state").stdout.splitlines()[0].startswith("state: "), antigo(ra, "state").stdout)

# o arquivo no formato ANTIGO é lido, e a próxima escrita o converte
rb = novo_repo("rb")
(rb / ".claude").mkdir()
(rb / ".claude" / "session-intent").write_text(
    'proposito: "do arquivo antigo"\npara_quando: "q"\nplano:\n  - "a"\n  - "b"\n'
    'passo: 2\npasso_desde: "2020-01-01T00:00:00Z"\nsession_id: "sess-1"\nbranch: "main"\n'
    'aberto_em: "2020-01-01T00:00:00Z"\nresumo: "passo 2/2 · b · do arquivo antigo"\n'
    'historico:\n  - em: "2019-01-01T00:00:00Z"\n    proposito: "mais antigo"\n'
    '    motivo_da_troca: "m"\n')
d = M.read_intent(rb)
check("arquivo antigo: lido com as chaves novas",
      d["purpose"] == "do arquivo antigo" and d["step"] == 2 and d["plan"] == ["a", "b"]
      and d["history"] == [{"at": "2019-01-01T00:00:00Z", "purpose": "mais antigo",
                            "change_reason": "m"}], d)
p = cepa(rb, "--step", "3")
txt = arquivo(rb)
check("arquivo antigo: uma escrita o converte para as chaves novas",
      p.returncode == 0 and "proposito" not in txt and "historico" not in txt
      and "motivo_da_troca" not in txt and "step: 3" in txt and "history:" in txt, txt)

# o atalho `cepa-intencao` é o mesmo comando (até o executável direto)
rc_ = novo_repo("rc")
p = antigo(rc_, "write", "--purpose", "pelo atalho", "--by-when", "q", "--plan", "a", "b", bin=BIN_ANTIGO)
check("atalho cepa-intencao: write grava", p.returncode == 0
      and M.read_intent(rc_)["purpose"] == "pelo atalho", p.stderr)
p = subprocess.run([str(BIN_ANTIGO), "show"], cwd=rc_, env=ENV, capture_output=True, text=True)
q = subprocess.run([str(BIN), "show"], cwd=rc_, env=ENV, capture_output=True, text=True)
check("atalho cepa-intencao roda como executável e imprime o mesmo que cepa-intent",
      p.returncode == 0 and p.stdout == q.stdout and "pelo atalho" in p.stdout, (p.stderr, p.stdout))

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
    sys.exit(1)
print("\ntudo ok")
