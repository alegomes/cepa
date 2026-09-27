#!/usr/bin/env python3
"""Regression tests: onda do Maestro que terminou e ninguém aterrissou.

## O defeito

O merge train do /maestro:run só roda com a sessão do maestro viva. Na onda 1
do WEGO-paralelo (2026-08-24) ela morreu antes de chegar lá: cinco slices
DONE, `landed: []` no wave-state.yaml, e nada no disco distinguia "onda
rodando" de "onda esperando você". As branches foram mescladas à mão, horas e
meio dia depois, por quem por acaso reparou.

## O que estes testes seguram

- o wave-state separa "a filha terminou" (DONE) de "a branch está na
  integração" (LANDED), e `aguardando-merge` lista o primeiro sem o segundo;
- o critério de pronto do item: sessão morta logo depois da última filha, e a
  sessão seguinte ouve "5 slices terminadas esperando merge" sem abrir o
  wave-state.yaml. A frase sai do `maestro-programs --aguardando-merge`, que é o
  que o /common:next chama, e do cepa-doctor;
- `landed` recusa slice que não é DONE: marcar FAIL como aterrissada apagaria o
  estado que manda a slice re-forkar;
- wave-state antigo (merge só na lista `landed:`) continua lido certo;
- retentativa registrada com `set-slice` no meio da onda entra na fronteira de
  término na hora, não na onda seguinte.

Run: python3 tests/test_maestro_merge_pendente.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WAVE_STATE = REPO / "maestro" / "bin" / "maestro-wave-state"
PROGRAMS = REPO / "maestro" / "bin" / "maestro-programs"
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

SLICES = ["S-2050", "S-2059", "S-2067", "S-2070", "S-2107"]

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def ws(progdir, *args):
    return subprocess.run([sys.executable, str(WAVE_STATE)] + list(args[:1])
                          + [str(progdir)] + list(args[1:]),
                          capture_output=True, text=True)


def monta(tmp, nome="WEGO-paralelo"):
    """Repo git com um programa de ondas cuja onda 1 foi iniciada."""
    raiz = Path(tmp)
    progdir = raiz / ".claude" / "programs" / nome
    progdir.mkdir(parents=True)
    (progdir / "plan.yaml").write_text(yaml.safe_dump({
        "schema_version": 2, "mode": "parallel-waves", "program": nome,
        "waves": [{"id": 1, "slices": SLICES, "status": "pending"}],
    }))
    (raiz / "README.md").write_text("base\n")
    subprocess.run(["git", "init", "-q", "."], cwd=raiz, check=True)
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=raiz, check=True)
    r = ws(progdir, "init", "--plan", str(progdir / "plan.yaml"), "--wave", "1")
    assert r.returncode == 0, r.stderr
    return raiz, progdir


def termina_todas(progdir):
    """A última filha terminou; a sessão do maestro morre aqui."""
    for s in SLICES:
        r = ws(progdir, "set-slice", s, "DONE")
        assert r.returncode == 0, r.stderr


def aguardando(progdir):
    r = ws(progdir, "aguardando-merge", "--json")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["aguardando_merge"]


def test_sessao_morta_proxima_sessao_ouve_o_que_espera(tmp):
    raiz, progdir = monta(tmp)
    termina_todas(progdir)
    r = subprocess.run([sys.executable, str(PROGRAMS), str(raiz),
                        "--aguardando-merge"], capture_output=True, text=True)
    check("maestro-programs --aguardando-merge sai 0", r.returncode == 0, r.stderr)
    check("...e diz '5 slice(s) terminada(s) esperando merge'",
          "5 slice(s) terminada(s) esperando merge" in r.stdout, r.stdout)
    check("...nomeando as slices", all(s in r.stdout for s in SLICES), r.stdout)
    check("...e a rota /maestro:resume <programa>",
          "/maestro:resume WEGO-paralelo" in r.stdout, r.stdout)
    listagem = subprocess.run([sys.executable, str(PROGRAMS), str(raiz)],
                              capture_output=True, text=True)
    check("a listagem normal também mostra a espera",
          "esperando merge" in listagem.stdout, listagem.stdout)


def test_doctor_cobra_a_onda_parada(tmp):
    raiz, progdir = monta(tmp)
    termina_todas(progdir)
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"], cwd=str(raiz),
                       capture_output=True, text=True, timeout=120)
    out = p.stdout + p.stderr
    check("doctor avisa na área [maestro]", "[maestro]" in out and "⚠" in out, out)
    check("...com a contagem e a rota",
          "5 slice(s) terminada(s) esperando merge" in out
          and "/maestro:resume WEGO-paralelo" in out, out)


def test_landed_tira_da_espera_e_silencia(tmp):
    raiz, progdir = monta(tmp)
    termina_todas(progdir)
    for s in SLICES[:3]:
        r = ws(progdir, "landed", s)
        check(f"landed {s} sai 0", r.returncode == 0, r.stderr)
    estado = yaml.safe_load((progdir / "wave-state.yaml").read_text())
    check("slice aterrissada vira LANDED",
          estado["slices"]["S-2050"]["status"] == "LANDED", estado)
    check("sobram as 2 não aterrissadas, na ordem",
          aguardando(progdir) == SLICES[3:], aguardando(progdir))
    for s in SLICES[3:]:
        ws(progdir, "landed", s)
    check("tudo aterrissado: nada espera", aguardando(progdir) == [])
    r = subprocess.run([sys.executable, str(PROGRAMS), str(raiz),
                        "--aguardando-merge"], capture_output=True, text=True)
    check("...e o maestro-programs fica calado", r.stdout.strip() == "", r.stdout)
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"], cwd=str(raiz),
                       capture_output=True, text=True, timeout=120)
    check("...e o doctor também", "[maestro]" not in p.stdout + p.stderr)
    check("LANDED conta como terminal na fronteira de término",
          ws(progdir, "check-terminal").returncode == 0)


def test_landed_recusa_slice_que_nao_terminou_bem(tmp):
    _, progdir = monta(tmp)
    ws(progdir, "set-slice", "S-2067", "FAIL")
    r = ws(progdir, "landed", "S-2067")
    check("landed de slice FAIL sai 2", r.returncode == 2, r.stdout + r.stderr)
    check("...dizendo o que registrar antes", "set-slice" in r.stderr, r.stderr)
    estado = yaml.safe_load((progdir / "wave-state.yaml").read_text())
    check("...e o FAIL continua lá",
          estado["slices"]["S-2067"]["status"] == "FAIL"
          and "S-2067" not in estado["landed"], estado)


def test_wave_state_antigo_com_lista_landed(tmp):
    _, progdir = monta(tmp)
    termina_todas(progdir)
    arq = progdir / "wave-state.yaml"
    estado = yaml.safe_load(arq.read_text())
    estado["landed"] = ["S-2050", "S-2059", "S-2070"]  # mesclados à mão, formato antigo
    arq.write_text(yaml.safe_dump(estado, sort_keys=False))
    check("nome na lista `landed:` conta como aterrissado",
          aguardando(progdir) == ["S-2067", "S-2107"], aguardando(progdir))


def test_slice_ainda_rodando_nao_e_cobrada(tmp):
    _, progdir = monta(tmp)
    ws(progdir, "set-slice", "S-2050", "DONE")
    ws(progdir, "set-slice", "S-2059", "running")
    check("só a DONE espera merge; a running não é dívida sua",
          aguardando(progdir) == ["S-2050"], aguardando(progdir))


def test_retentativa_registrada_entra_na_fronteira(tmp):
    _, progdir = monta(tmp)
    termina_todas(progdir)
    r = ws(progdir, "set-slice", "S-2067R", "running",
           "--detail", "retentativa de S-2067")
    check("set-slice registra a retentativa nova", r.returncode == 0, r.stderr)
    check("...e a fronteira de término a enxerga na hora (exit 2)",
          ws(progdir, "check-terminal").returncode == 2)


def test_comandos_chamam_a_checagem(tmp):
    nxt = (REPO / "common" / "commands" / "next.md").read_text()
    check("/common:next roda maestro-programs --aguardando-merge",
          "maestro-programs . --aguardando-merge" in nxt)
    res = (REPO / "maestro" / "commands" / "resume.md").read_text()
    check("/maestro:resume vai ao merge train quando a onda terminou sem merge",
          "aguardando-merge" in res and "Passo 9" in res)
    run = (REPO / "maestro" / "commands" / "run.md").read_text()
    check("/maestro:run registra a retentativa no instante do fork",
          "Retentativa com nome novo" in run
          and "set-slice PROGDIR <slice>R running" in run)


def main():
    testes = [v for k, v in globals().items() if k.startswith("test_")]
    for t in testes:
        with tempfile.TemporaryDirectory() as tmp:
            t(tmp)
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print(f"\n{len(testes)} testes ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
