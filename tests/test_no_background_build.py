#!/usr/bin/env python3
"""Testes do `common/hooks/no-background-build.py`.

O hook fecha a porta pela qual 34 dos 49 minutos do run de 2026-08-30 saíram:
dentro do `cepa-until` cada item é um `claude -p`, e um build mandado para o
segundo plano nunca é colhido — o turno acaba, o processo morre, o item fica
`in_progress` sem desfecho.

Três eixos, e cada um é uma forma diferente de o hook ficar inútil:
  - o ESCOPO (só dentro da janela) — sem ele o hook estraga sessão interativa,
    onde mandar para o segundo plano é a coisa certa;
  - o EFEITO (as duas vias de desanexar) — barrar só o `run_in_background`
    deixa o `&` livre, que é o padrão registrado na memória
    `gate-por-nome-de-ferramenta-falha-aberto`;
  - o ALVO (build sim, servidor não) — bloquear servidor mataria o gate de
    prova de UI, que depende de subir o app de lado.

Rode com `python3 tests/test_no_background_build.py`.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "no-background-build.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def roda(command, background=False, na_janela=True):
    """Chama o hook como o harness chama: payload no stdin, veredito no exit."""
    import os
    env = dict(os.environ)
    if na_janela:
        env["CEPA_UNTIL_RUN"] = "1"
    else:
        env.pop("CEPA_UNTIL_RUN", None)
    payload = {"tool_name": "Bash",
               "tool_input": {"command": command,
                              "run_in_background": background}}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


# ── escopo: só dentro da janela ─────────────────────────────────────────────

def test_fora_da_janela_o_hook_nao_existe():
    """Numa sessão interativa, `run_in_background` é o conselho CERTO — é o que
    o próprio no-busy-wait manda fazer. O hook não pode atrapalhar isso."""
    p = roda("./mvnw verify", background=True, na_janela=False)
    check("build em segundo plano passa fora da janela", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


def test_dentro_da_janela_o_build_em_segundo_plano_e_bloqueado():
    p = roda("./mvnw clean verify", background=True)
    check("build com run_in_background é bloqueado", p.returncode == 2,
          f"saiu {p.returncode}")
    check("...e a recusa explica que não há turno seguinte",
          "NÃO HÁ TURNO SEGUINTE" in p.stderr, p.stderr[:300])
    check("...e diz o que fazer no lugar (primeiro plano ou desfecho nomeado)",
          "PRIMEIRO PLANO" in p.stderr and "cepa-plan finish" in p.stderr,
          p.stderr[:400])


# ── efeito: as duas vias de desanexar ───────────────────────────────────────

def test_o_mesmo_efeito_pelo_shell_tambem_e_bloqueado():
    """Barrar só o nome da ferramenta libera calado quando aparece outro
    mecanismo para o mesmo efeito — é a 4ª vez que o padrão aparece no repo."""
    for cmd in ("./mvnw verify &",
                "nohup ./mvnw verify > /tmp/b.log 2>&1 &",
                "setsid npm test",
                "./gradlew test & disown"):
        p = roda(cmd)
        check(f"desanexado no shell é bloqueado: {cmd[:34]}", p.returncode == 2,
              f"saiu {p.returncode}")


def test_build_em_primeiro_plano_passa():
    """É a saída que o hook manda tomar. Se ele barrasse isto também, não
    sobraria nenhuma forma de rodar o build e o item nunca fecharia."""
    for cmd in ("./mvnw clean verify",
                "./mvnw verify 2>&1 | tail -40",
                "npm test && echo ok"):
        p = roda(cmd)
        check(f"primeiro plano passa: {cmd[:34]}", p.returncode == 0,
              f"saiu {p.returncode}: {p.stderr[:200]}")


# ── alvo: build sim, servidor não ───────────────────────────────────────────

def test_subir_servico_de_apoio_em_segundo_plano_passa():
    """O gate de prova de UI sobe o app de lado e roda o fluxo contra ele.
    Bloquear isso mataria o gate — e um servidor não produz veredito nenhum
    para alguém colher."""
    for cmd in ("./mvnw quarkus:dev", "npm run dev", "docker compose up",
                "python3 -m http.server 8080"):
        p = roda(cmd, background=True)
        check(f"serviço de apoio passa: {cmd[:34]}", p.returncode == 0,
              f"saiu {p.returncode}: {p.stderr[:200]}")


def test_comando_qualquer_em_segundo_plano_passa():
    """O hook cobra build, não background. Barrar tudo viraria um segundo
    no-busy-wait, com outro nome e sem a medição que o justifique."""
    p = roda("git fetch --all", background=True)
    check("comando sem veredito de build passa", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


# ── bordas ──────────────────────────────────────────────────────────────────

def test_escape_hatch_declarado():
    p = roda("./mvnw verify  # fundo-ok", background=True)
    check("`# fundo-ok` libera", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


def test_texto_citado_nao_e_shell():
    """WEGO-2087: mensagem de commit multilinha lida como vários comandos já
    barrou escrita fantasma. Um `&` dentro de aspas é texto."""
    p = roda('git commit -m "roda ./mvnw verify & confere o log"')
    check("`&` dentro de aspas não é desanexação", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:200]}")


def test_payload_ilegivel_libera_em_vez_de_estourar():
    import os
    env = dict(os.environ); env["CEPA_UNTIL_RUN"] = "1"
    p = subprocess.run([sys.executable, str(HOOK)], input="{nao json",
                       capture_output=True, text=True, env=env)
    check("payload quebrado não bloqueia nem estoura", p.returncode == 0,
          f"saiu {p.returncode}")


def test_outra_ferramenta_passa_direto():
    import os
    env = dict(os.environ); env["CEPA_UNTIL_RUN"] = "1"
    payload = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x"}}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    check("hook de Bash não opina sobre Write", p.returncode == 0,
          f"saiu {p.returncode}")


def main():
    print("no-background-build — build em segundo plano dentro do cepa-until\n")
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
