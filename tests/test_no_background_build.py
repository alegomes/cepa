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

As duas portas acrescentadas em 04/09/2026, depois do run que perdeu 6h54 de
uma janela de 8h sem passar pela porta do Bash:
  - o VIGIA (Monitor) — vigia que não termina sozinho segura o turno até o
    relógio do item matar tudo; vigia com fim declarado continua liberado;
  - a PARADA (Stop) — parar com subagente despachado sem resultado, ou vigia
    armado sem `TaskStop`, é o mesmo efeito por uma terceira porta.

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


# ── porta 2: o vigia (Monitor) ─────────────────────────────────────────────
def roda_monitor(entrada, na_janela=True):
    import os
    env = dict(os.environ)
    if na_janela:
        env["CEPA_UNTIL_RUN"] = "1"
    else:
        env.pop("CEPA_UNTIL_RUN", None)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Monitor",
               "tool_input": entrada}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


def test_vigia_sem_fim_e_bloqueado_na_janela():
    casos = [
        ("while true", {"command": "while true; do git log -1; sleep 30; done",
                        "description": "branches", "timeout_ms": 3600000,
                        "persistent": False}),
        ("persistent", {"command": "gh pr checks 1 && break", "persistent": True}),
        ("tail -f", {"command": "tail -f app.log | grep --line-buffered ERROR"}),
        ("websocket", {"ws": {"url": "wss://x/y"}, "description": "eventos"}),
    ]
    for nome, entrada in casos:
        p = roda_monitor(entrada)
        check(f"vigia sem fim bloqueado: {nome}", p.returncode == 2,
              f"saiu {p.returncode}")


def test_vigia_com_fim_declarado_passa():
    entrada = {"command": "for i in 1 2 3; do gh run view --json status; done",
               "description": "CI", "timeout_ms": 60000, "persistent": False}
    p = roda_monitor(entrada)
    check("vigia que termina sozinho passa", p.returncode == 0,
          f"saiu {p.returncode}: {p.stderr[:120]}")


def test_vigia_fora_da_janela_passa():
    entrada = {"command": "while true; do sleep 5; done", "persistent": True}
    p = roda_monitor(entrada, na_janela=False)
    check("vigia sem fim passa fora da janela", p.returncode == 0,
          f"saiu {p.returncode}")


def test_vigia_com_escape_declarado_passa():
    entrada = {"command": "while true; do sleep 5; done  # fundo-ok"}
    p = roda_monitor(entrada)
    check("escape `# fundo-ok` libera o vigia", p.returncode == 0,
          f"saiu {p.returncode}")


# ── porta 3: a parada (Stop) ───────────────────────────────────────────────
def _transcript(tmp, blocos_por_linha):
    """Escreve um transcript no formato que o harness grava."""
    caminho = tmp / "t.jsonl"
    with caminho.open("w", encoding="utf-8") as f:
        for blocos in blocos_por_linha:
            f.write(json.dumps({"type": "assistant",
                                "message": {"content": blocos}}) + "\n")
    return caminho


def roda_stop(caminho, na_janela=True, stop_hook_active=False):
    import os
    env = dict(os.environ)
    if na_janela:
        env["CEPA_UNTIL_RUN"] = "1"
    else:
        env.pop("CEPA_UNTIL_RUN", None)
    payload = {"hook_event_name": "Stop", "transcript_path": str(caminho),
               "stop_hook_active": stop_hook_active}
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    try:
        saida = json.loads(p.stdout) if p.stdout.strip() else {}
    except json.JSONDecodeError:
        saida = {}
    return p, saida


DESPACHO = [{"type": "tool_use", "id": "tu_1", "name": "Agent",
             "input": {"description": "Build WEGO-2224"}}]
RESULTADO = [{"type": "tool_result", "tool_use_id": "tu_1",
              "content": "pronto, Tasks mescladas"}]
ARMA_VIGIA = [{"type": "tool_result", "tool_use_id": "tu_2",
               "content": "Monitor started (task bqwpma178, timeout 3600000ms)."}]
PARA_VIGIA = [{"type": "tool_result", "tool_use_id": "tu_3",
               "content": "{\"message\":\"Successfully stopped task: bqwpma178 (...)\"}"}]


def test_parada_com_subagente_pendente_e_bloqueada():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DESPACHO])
        p, saida = roda_stop(c)
        check("parada com subagente sem resultado é bloqueada",
              saida.get("decision") == "block" and p.returncode == 0,
              f"saiu {p.returncode}: {p.stdout[:120]}")
        check("o bloqueio nomeia o subagente pendente",
              "Build WEGO-2224" in (saida.get("reason") or ""),
              (saida.get("reason") or "")[:120])


def test_parada_com_vigia_armado_e_bloqueada():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [ARMA_VIGIA])
        _, saida = roda_stop(c)
        check("parada com vigia armado é bloqueada",
              saida.get("decision") == "block",
              json.dumps(saida)[:160])


def test_parada_limpa_passa():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DESPACHO, RESULTADO, ARMA_VIGIA, PARA_VIGIA])
        p, saida = roda_stop(c)
        check("subagente colhido e vigia parado: a parada passa",
              not saida and p.returncode == 0,
              f"saiu {p.returncode}: {p.stdout[:160]}")


def test_parada_fora_da_janela_passa():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DESPACHO, ARMA_VIGIA])
        _, saida = roda_stop(c, na_janela=False)
        check("fora da janela a parada nunca é bloqueada", not saida,
              json.dumps(saida)[:160])


def test_parada_nao_bloqueia_duas_vezes_seguidas():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        c = _transcript(Path(d), [DESPACHO])
        _, saida = roda_stop(c, stop_hook_active=True)
        check("trava anti-loop: bloqueio já ativo não bloqueia de novo",
              not saida, json.dumps(saida)[:160])


def test_transcript_ausente_nao_estoura():
    p, saida = roda_stop(Path("/nao/existe/t.jsonl"))
    check("transcript ausente libera em vez de estourar",
          p.returncode == 0 and not saida, f"saiu {p.returncode}")


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
