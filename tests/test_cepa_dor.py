#!/usr/bin/env python3
"""Regression tests for common/bin/cepa-dor (Definition of Ready do Maestro).

No third-party deps beyond PyYAML (already required by the script itself) —
run with `python3 tests/test_cepa_dor.py`. Exits non-zero on first failure.

Guards the intake-gate contracts from the v1 design (Componente 4):
  - surface intersection on a `cartorios` (arquivo-cartório) file downs BOTH
    slices; intersection on any other file is a warning, not a veto (P3,
    docs/spec/planejador-de-lotes-paralelos.md CS-4); no `cartorios` field
    means no data, so nothing is vetoed on overlap — only warned;
  - enforcement zone is an unconditional veto;
  - open human_gate / missing acceptance_cmd in a no-build repo → NOT-READY;
  - D7 floor (<4 demandas) blocks the program;
  - a clean plan comes out READY (exit 0 or 1-with-warnings, never 2);
  - unknown schema_version is refused (conhecidas: 1 e 2);
  - `mode` (fio condutor, schema compartilhado com o board-flow): um plano v1
    sem `mode` segue válido sem migração, v2 exige o campo, single-track em v1
    manda subir a versão, single-track em v2 é recusado apontando o caminho, e
    valor desconhecido não passa em silêncio;
  - "BDD ou substrato" (A3): um slice cujo aceite só nomeia passos privados de
    implementação reprova nomeando a lacuna; declarar `acceptance_form:
    substrate` (ou escrever a tripla observável) passa.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOR = REPO / "common" / "bin" / "cepa-dor"

FAILURES = []


def run_dor(plan_text, repo, extra=None):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(plan_text)
        plan = f.name
    cmd = [sys.executable, str(DOR), plan, "--repo", str(repo)] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def make_repo(tmp, no_build=True):
    """Tiny committed git repo the surfaces expand against."""
    repo = Path(tmp) / "r"
    repo.mkdir()
    for p in ["src/a.py", "src/b.py", "docs/x.md", "plug/hooks/h.py", "package-lock.json"]:
        (repo / p).parent.mkdir(parents=True, exist_ok=True)
        (repo / p).write_text("x")
    if no_build:
        (repo / ".claude").mkdir()
        (repo / ".claude" / "no-build").write_text("")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


PLAN_4D = """\
schema_version: 1
program: t
waves:
  - id: 1
    slices: [S1, S2]
    status: pending
slices:
  S1: {{demanda: A, surface: [{s1}], human_gate: {hg1}, acceptance: ok, acceptance_form: substrate, {ac1} context: [x]}}
  S2: {{demanda: B, surface: [{s2}], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S3: {{demanda: C, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S4: {{demanda: D, surface: ["src/b.py"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
"""


def with_cartorios(plan_text, files):
    """Insere o campo opcional `cartorios:` no topo de um plano já formatado."""
    block = "cartorios:\n" + "".join(f'  - "{f}"\n' for f in files)
    return plan_text.replace("program: t\n", "program: t\n" + block, 1)

# Plano de 1 slice na onda (S2..S4 existem só para o piso D7) usado para
# exercitar a forma do aceite isoladamente.
PLAN_FORM = """\
schema_version: 1
program: t
waves:
  - id: 1
    slices: [S1]
    status: pending
slices:
  S1:
    demanda: A
    surface: ["src/a.py"]
    human_gate: none
    acceptance: "{acc}"
    acceptance_cmd: "true"
    context: [x]
{form}\
  S2: {{demanda: B, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S3: {{demanda: C, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S4: {{demanda: D, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
"""

# Aceite que só nomeia passos privados de implementação — o caso que o A3 pega.
ACC_PRIVADO = "refatorar o parser e extrair o helper de normalizacao"
ACC_BDD = ("Dado um card em Review sem razao, Quando o agente posta a "
           "devolucao, Entao o hook bloqueia nomeando o campo")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)

        # clean plan → READY, exit 0/1
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        # note: S2/S3 share docs/x.md but are in DIFFERENT waves? No — S2 in
        # wave, S3 not in wave 1 → disjunção só entre slices DA onda.
        check("plano limpo sai READY", r.returncode in (0, 1), r.stdout)
        check("disjunção só compara slices da MESMA onda",
              "intersecta a de S3" not in r.stdout, r.stdout)

        # sem `cartorios` no plano: interseção NÃO veta mais — só avisa
        # (P3: afrouxamento do intake, docs/spec/planejador-de-lotes-paralelos.md)
        r = run_dor(PLAN_4D.format(s1='"src/*.py"', s2='"src/b.py"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("sem cartorios declarado, interseção não veta",
              r.returncode != 2 or "NOT-READY" not in r.stdout, r.stdout)
        check("sem cartorios declarado, interseção é avisada",
              "cruzam fora de arquivo-cartório" in r.stdout, r.stdout)

        # interseção NUM arquivo-cartório declarado derruba os DOIS slices
        plan_cart = with_cartorios(
            PLAN_4D.format(s1='"src/*.py"', s2='"src/b.py"',
                           hg1="none", ac1='acceptance_cmd: "true",'),
            ["src/b.py"])
        r = run_dor(plan_cart, repo)
        check("interseção num arquivo-cartório derruba os DOIS slices",
              r.returncode == 2 and r.stdout.count("NOT-READY") == 2, r.stdout)
        check("a lacuna nomeia o arquivo-cartório",
              "arquivo-cartório" in r.stdout, r.stdout)

        # interseção declarada como cartório MAS que não bate com o slice não veta
        plan_cart_miss = with_cartorios(
            PLAN_4D.format(s1='"src/*.py"', s2='"src/b.py"',
                           hg1="none", ac1='acceptance_cmd: "true",'),
            ["docs/x.md"])
        r = run_dor(plan_cart_miss, repo)
        check("cartório declarado que não intersecta os slices não veta",
              r.returncode != 2 or "NOT-READY" not in r.stdout, r.stdout)

        # arquivo-cartório que nenhum slice declara → aviso da onda, não veto
        plan_undeclared = with_cartorios(
            PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                           hg1="none", ac1='acceptance_cmd: "true",'),
            ["src/b.py"])  # S4 declara src/b.py só fora da onda 1
        r = run_dor(plan_undeclared, repo)
        check("cartório fora de toda superfície da onda é avisado",
              "fora de toda superfície" in r.stdout, r.stdout)
        check("cartório fora de toda superfície não veta",
              r.returncode != 2 or "NOT-READY" not in r.stdout, r.stdout)

        # sem `cartorios`, um arquivo que batia na heurística HIGH_FRICTION
        # antiga (removida por P3) não gera aviso — trava contra a
        # heurística voltar por engano ou um bug equivalente
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("sem cartorios, arquivo da heurística antiga não gera aviso",
              "fora de toda superfície" not in r.stdout, r.stdout)

        # enforcement zone veto
        r = run_dor(PLAN_4D.format(s1='"plug/hooks/h.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("zona de enforcement é veto", r.returncode == 2
              and "zona de enforcement" in r.stdout, r.stdout)

        # open human gate
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1='"open: naming"',
                                   ac1='acceptance_cmd: "true",'), repo)
        check("human_gate aberto → NOT-READY", r.returncode == 2
              and "decisão estratégica em aberto" in r.stdout, r.stdout)

        # missing acceptance_cmd in no-build repo
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1=""), repo)
        check("no-build sem acceptance_cmd → NOT-READY", r.returncode == 2
              and "acceptance_cmd" in r.stdout, r.stdout)

        # D7 floor
        plan_3d = PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                 hg1="none", ac1='acceptance_cmd: "true",')
        plan_3d = "\n".join(l for l in plan_3d.splitlines()
                            if not l.startswith("  S4"))
        r = run_dor(plan_3d, repo)
        check("piso D7 (<4 demandas) bloqueia", r.returncode == 2
              and "piso é 4" in r.stdout, r.stdout)

        # unknown schema_version (v1 e v2 são conhecidas; 3 não)
        r = run_dor("schema_version: 3\nprogram: t\nwaves: []\nslices: {}\n",
                    repo)
        check("schema_version desconhecida é recusada", r.returncode == 2
              and "schema_version" in r.stdout, r.stdout)

        # ── `mode` (fio condutor): schema compartilhado com o board-flow ─────
        # COMPATIBILIDADE v1 — a asserção que sustenta "plano no disco não
        # precisa ser migrado": PLAN_4D é v1 e sem `mode`, como todo plano
        # escrito antes do campo existir, e tem de passar exatamente como antes.
        wave_v1 = PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                 hg1="none", ac1='acceptance_cmd: "true",')
        r = run_dor(wave_v1, repo)
        check("v1 sem `mode` segue válido (legado = parallel-waves)",
              r.returncode in (0, 1), r.stdout)

        # v2 com o mode explícito de onda: mesmo plano, mesmo veredito
        wave_v2 = wave_v1.replace("schema_version: 1",
                                  "schema_version: 2\nmode: parallel-waves", 1)
        check("o fixture v2 difere mesmo do v1", wave_v2 != wave_v1)
        r = run_dor(wave_v2, repo)
        check("v2 com mode: parallel-waves é aceito",
              r.returncode in (0, 1), r.stdout)

        # v2 exige o campo — sem ele não dá para saber que documento é
        r = run_dor(wave_v1.replace("schema_version: 1", "schema_version: 2", 1),
                    repo)
        check("v2 sem `mode` é recusado", r.returncode == 2
              and "exige `mode` explícito" in r.stdout, r.stdout)

        # single-track NÃO existia em v1 — a recusa manda subir a versão em vez
        # de aceitar um documento que aquela versão nunca descreveu
        r = run_dor("schema_version: 1\nmode: single-track\nprogram: t\n"
                    "items:\n  - id: X\n    why: y\n    status: pending\n", repo)
        check("single-track em plano v1 é recusado", r.returncode == 2
              and "não existe no schema v1" in r.stdout, r.stdout)
        check("a recusa do v1 manda subir para v2",
              "schema_version: 2" in r.stdout, r.stdout)

        # single-track em v2 é recusado APONTANDO O CAMINHO — um erro cru aqui
        # devolveria "nenhuma onda pending", que não diz o que fazer.
        r = run_dor("schema_version: 2\nmode: single-track\nprogram: t\n"
                    "items:\n  - id: X\n    why: y\n    status: pending\n", repo)
        # NÃO casar só por "single-track": a mensagem genérica de mode
        # desconhecido também contém essa palavra ("esperado 'parallel-waves'
        # ou 'single-track'"), e a asserção passaria pelo motivo errado — foi
        # o que a perturbação pegou. Casar pela orientação específica.
        check("plano single-track é recusado pelo cepa-dor",
              r.returncode == 2 and "um item por vez" in r.stdout, r.stdout)
        check("recusa do single-track aponta /common:next",
              "/common:next" in r.stdout, r.stdout)

        # valor inválido não passa em silêncio como se fosse onda
        r = run_dor("schema_version: 2\nmode: talvez\nprogram: t\n"
                    "waves: []\nslices: {}\n", repo)
        check("mode desconhecido é recusado", r.returncode == 2
              and "mode desconhecido" in r.stdout, r.stdout)

        # ── A3: "BDD ou substrato" ──────────────────────────────────────────
        # US sem BDD e sem declaração de substrato → NOT-READY, lacuna nomeada
        r = run_dor(PLAN_FORM.format(acc=ACC_PRIVADO, form=""), repo)
        check("aceite só com passos privados → NOT-READY", r.returncode == 2
              and "NOT-READY" in r.stdout, r.stdout)
        check("a lacuna do aceite é NOMEADA (BDD ou substrato)",
              "Given/When/Then" in r.stdout and "substrate" in r.stdout,
              r.stdout)

        # substrato declarado → passa (aceite técnico é legítimo p/ TS)
        r = run_dor(PLAN_FORM.format(acc=ACC_PRIVADO,
                                     form="    acceptance_form: substrate\n"),
                    repo)
        check("substrato declarado passa", r.returncode in (0, 1), r.stdout)

        # tripla observável (pt-BR) sem declarar forma → passa
        r = run_dor(PLAN_FORM.format(acc=ACC_BDD, form=""), repo)
        check("Given/When/Then observável passa sem declarar forma",
              r.returncode in (0, 1), r.stdout)

        # declarou bdd mas não escreveu a tripla → NOT-READY
        r = run_dor(PLAN_FORM.format(acc=ACC_PRIVADO,
                                     form="    acceptance_form: bdd\n"), repo)
        check("acceptance_form: bdd sem tripla → NOT-READY",
              r.returncode == 2 and "acceptance_form: bdd" in r.stdout,
              r.stdout)

        # valor inválido é recusado em vez de ignorado em silêncio
        r = run_dor(PLAN_FORM.format(acc=ACC_BDD,
                                     form="    acceptance_form: talvez\n"), repo)
        check("acceptance_form inválido → NOT-READY", r.returncode == 2
              and "inválido" in r.stdout, r.stdout)

        # baseline não-verde em repo COM build
        repo2 = make_repo(tempfile.mkdtemp(dir=tmp), no_build=False)
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo2)
        check("baseline ausente em repo com build → NOT-READY",
              r.returncode == 2 and "baseline" in r.stdout, r.stdout)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
