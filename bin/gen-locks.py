#!/usr/bin/env python3
"""gen-locks — gera as cópias por topologia do bash-path-lock a partir de um molde.

## Por que existe

`bash-path-lock.py` vive em cinco cópias, uma por topologia com hook. Até
2026-08-17 a regra de manutenção era humana: "todo fix aterrissa nas 5". Ela
falhou duas vezes de forma verificável:

- o conserto do falso-positivo do `>=` (o hook lia o `>` de `>=` como
  redirecionamento e bloqueava comando legítimo) teve de ser propagado à mão;
- o tratamento de `git mv` como escrita ficou só na cópia do `docs-topology`.
  Nas outras quatro, um agente movia arquivo para fora da própria pista com
  `git mv` e o cadeado não via nada. Ninguém percebeu até um teste comparar as
  cópias.

O modo de falha é silencioso — a cópia defasada não quebra, ela **permite** o
que as outras bloqueiam, e o relatório do agente lê como sucesso.

`tests/test_lock_copies_drift.py` detecta a divergência **depois** que ela
acontece. Este gerador a torna impossível: existe um molde, e as cinco cópias
são função dele.

## Por que só o bash-path-lock, e não o path-lock

O `path-lock.py` carrega o `ALLOWED_WRITES` — o mapa de quem escreve onde, que
é **dado da topologia**, não do motor. Centralizá-lo aqui tiraria a lista de
permissões de perto dos agentes que ela governa, que é onde ela precisa estar
para alguém conferir contra o `Writes:` do agente. O `bash-path-lock` não tem
esse problema: ele importa o allowlist do irmão e é 100% mecânica.

Para o `path-lock`, a garantia continua sendo o detector — declarado, com o
motivo, em vez de uma centralização que pioraria a leitura.

## Uso

    python3 bin/gen-locks.py --check    # as cópias no disco batem com o molde?
    python3 bin/gen-locks.py --write    # regenera as cinco
    python3 bin/gen-locks.py --diff     # mostra o que mudaria

`--check` é o que o teste chama. Sai não-zero quando alguma cópia divergiu.
"""

import argparse
import difflib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "common" / "hooks" / "_templates" / "bash-path-lock.py.tmpl"
TARGET = "hooks/bash-path-lock.py"

# Tabela por topologia. É a ÚNICA coisa que legitimamente varia entre as cópias
# — e, por estar aqui, é auditável de uma olhada. Adicionar uma topologia nova
# com hook é acrescentar uma linha e rodar --write.
#
#   dir     diretório da topologia no repo
#   plugin  nome do plugin (o prefixo que chega em agent_type)
#   alias   prefixo do módulo importado via importlib (não pode colidir)
#   noun    o que a topologia escreve — muda a frase do bloqueio: as topologias
#           de build escrevem `código`; design/discovery/docs escrevem
#           `artefatos`. Dizer "source" a quem só escreve documento faz a
#           mensagem soar errada para quem a lê.
TOPOLOGIES = [
    {"dir": "build-team",    "plugin": "build-team", "alias": "multiteam", "noun": "código"},
    {"dir": "build-hex",     "plugin": "build-hex",  "alias": "hex",       "noun": "código"},
    {"dir": "discovery",     "plugin": "discovery",  "alias": "discovery", "noun": "artefatos"},
    {"dir": "design",        "plugin": "design",     "alias": "design",    "noun": "artefatos"},
    {"dir": "docs-topology", "plugin": "docs",       "alias": "docs",      "noun": "artefatos"},
]

# Como cada cópia obtém o allowlist do path-lock irmão. O build-hex é o único
# que resolve papéis arquiteturais (domain/api/adapter…) para nomes de módulo,
# lendo `build-hex.yaml` do projeto; as outras leem o dict fixo do módulo.
HEX_RESOLUTION = """    roles, extra = pl.load_config(project_root)
    allowed_writes = pl.build_allowed_writes(roles, extra)
    agent = pl.detect_agent(payload)
    allowed = allowed_writes.get(agent)"""

PLAIN_RESOLUTION = """    agent = pl.detect_agent(payload)
    allowed = pl.ALLOWED_WRITES.get(agent)"""


def render(topo: dict) -> str:
    src = TEMPLATE.read_text(encoding="utf-8")
    # O cabeçalho do molde explica o molde, não a cópia. A cópia ganha o seu.
    body = src.split("\n#!/usr/bin/env python3\n", 1)
    if len(body) == 2:
        src = "#!/usr/bin/env python3\n" + body[1]
    else:  # o shebang é a 1ª linha do molde? então tira só o bloco de comentário
        lines = src.splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("#!"))
        src = "\n".join(lines[start:])

    resolution = HEX_RESOLUTION if topo["dir"] == "build-hex" else PLAIN_RESOLUTION
    marks = {
        "@@PLUGIN@@": topo["plugin"],
        "@@ALIAS@@": topo["alias"],
        "@@NOUN@@": topo["noun"],
        "@@ALLOWLIST_RESOLUTION@@": resolution,
    }
    for mark, value in marks.items():
        src = src.replace(mark, value)
    leftover = [m for m in marks if m in src]
    assert not leftover, f"marca não substituída em {topo['dir']}: {leftover}"
    return src


def main():
    ap = argparse.ArgumentParser(description="Gera as cópias do bash-path-lock.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="as cópias batem com o molde?")
    g.add_argument("--write", action="store_true", help="regenera as cinco cópias")
    g.add_argument("--diff", action="store_true", help="mostra o que mudaria")
    args = ap.parse_args()

    if not TEMPLATE.exists():
        print(f"✗ molde ausente: {TEMPLATE}", file=sys.stderr)
        return 2

    divergent = []
    for topo in TOPOLOGIES:
        path = REPO / topo["dir"] / TARGET
        want = render(topo)
        have = path.read_text(encoding="utf-8") if path.exists() else ""

        if args.write:
            if have != want:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(want, encoding="utf-8")
                print(f"  regenerado  {path.relative_to(REPO)}")
            else:
                print(f"  já em dia   {path.relative_to(REPO)}")
            continue

        if have != want:
            divergent.append(topo["dir"])
            if args.diff:
                print(f"\n=== {path.relative_to(REPO)} ===")
                for line in difflib.unified_diff(
                        have.splitlines(), want.splitlines(),
                        fromfile="no disco", tofile="do molde", lineterm="", n=2):
                    print(line)

    if args.write:
        return 0

    if divergent:
        print(f"\n✗ {len(divergent)} cópia(s) divergem do molde: {', '.join(divergent)}")
        print("  Edite common/hooks/_templates/bash-path-lock.py.tmpl e rode")
        print("  `python3 bin/gen-locks.py --write`. Editar a cópia direto não")
        print("  propaga — é exatamente assim que o `git mv` ficou anos faltando")
        print("  em quatro das cinco.")
        return 1
    print(f"✓ as {len(TOPOLOGIES)} cópias são exatamente o molde renderizado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
