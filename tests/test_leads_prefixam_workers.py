#!/usr/bin/env python3
"""Os leads do build-hex chamam os workers com o prefixo do plugin (`<plugin>:<nome>`).

Sem dependência externa — rode com `python3 tests/test_leads_prefixam_workers.py`.

## Por que existe

Instalados como plugin, os agentes se endereçam como `<plugin>:<nome>` (ex.:
`build-hex:epic-author`). Os três leads do build-hex mandavam delegar pelo nome curto, então
a primeira chamada ao Task falhava com 'Agent type not found' e era refeita: um turno
perdido por item. Medição (feedback fb-20261016-2, run `until/2026-10-16-0822`, item
`S3-clientes-provedor-unificados`, build-hex 1.4.1): as 3 chamadas do planning-lead falharam
e foram refeitas, 3 turnos jogados fora num único item. Pior: `product-manager`,
`qa-engineer` e `security-reviewer` existem também no build-team, então um nome curto pode
até resolver para o plugin errado, sem erro nenhum.

O conserto foi aplicado em 3 cópias; a cópia N+1 (um lead novo, ou um worker novo citado
sem prefixo) nasceria quebrada em silêncio. Este teste é o radar. A regra é mecânica e
derivada do disco, não de uma lista fixa: o conjunto de nomes de agente vem de
`*/agents/*.md`; todo nome entre crases num lead tem que vir prefixado com o plugin dono, e
todo `<plugin>:<nome>` tem que apontar para um arquivo que existe.
"""

import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Só o build-hex por enquanto. Os leads das outras topologias ainda usam nome curto;
# prefixá-los é um follow-up, e entram aqui quando forem consertados.
PLUGINS_COBERTOS = ["build-hex"]

TOKEN = re.compile(r"`([a-z][a-z0-9-]*(?::[a-z][a-z0-9-]*)?)`")


def mapa_agentes(repo: Path) -> dict:
    """nome -> conjunto de plugins que têm `<plugin>/agents/<nome>.md`."""
    mapa = {}
    for p in repo.glob("*/agents/*.md"):
        mapa.setdefault(p.stem, set()).add(p.parent.parent.name)
    return mapa


def verificar(repo: Path, plugins: list) -> list:
    """Devolve as mensagens de violação nos `*-lead.md` dos plugins dados."""
    mapa = mapa_agentes(repo)
    leads = [p for pl in plugins for p in sorted((repo / pl / "agents").glob("*-lead.md"))]
    if not leads:
        return ["nenhum */agents/*-lead.md encontrado — o detector quebrou, não o repo"]
    if not mapa:
        return ["nenhum nome de agente encontrado em */agents/*.md — o detector "
                "quebrou, não o repo"]

    plugins_conhecidos = {d for nomes in mapa.values() for d in nomes}
    erros = []
    for lead in leads:
        rel = lead.relative_to(repo)
        dono = lead.parent.parent.name  # plugin do lead: <dono>/agents/<lead>.md
        for n, linha in enumerate(lead.read_text(encoding="utf-8").splitlines(), 1):
            for m in TOKEN.finditer(linha):
                tok = m.group(1)
                if ":" in tok:
                    plugin, nome = tok.split(":", 1)
                    # só é referência a agente se o plugin existe ou o nome é de
                    # agente; senão é outra coisa (ex.: `file:line`)
                    if plugin not in plugins_conhecidos and nome not in mapa:
                        continue
                    if not (repo / plugin / "agents" / f"{nome}.md").is_file():
                        erros.append(f"{rel}:{n}: `{tok}` aponta para "
                                     f"{plugin}/agents/{nome}.md, que não existe")
                    elif plugin not in (dono, "common"):
                        # existe, mas em outro plugin: o lead só delega a si mesmo
                        # (mesmo plugin) ou ao `common`
                        if dono in mapa.get(nome, ()):
                            certo = f"`{dono}:{nome}`"
                        elif "common" in mapa.get(nome, ()):
                            certo = f"`common:{nome}`"
                        else:
                            certo = None
                        msg = (f"{rel}:{n}: `{tok}` em lead do {dono}: plugin errado; ")
                        msg += (f"o dono aqui é {certo}" if certo else
                                f"`{nome}` não existe em {dono} nem em common")
                        erros.append(msg)
                elif tok in mapa:
                    donos = sorted(mapa[tok])
                    if len(donos) == 1:
                        erros.append(f"{rel}:{n}: `{tok}` sem prefixo; use "
                                     f"`{donos[0]}:{tok}`")
                    else:
                        opcoes = ", ".join(f"`{d}:{tok}`" for d in donos)
                        erros.append(f"{rel}:{n}: `{tok}` sem prefixo e existe em "
                                     f"vários plugins ({opcoes}); o lead deve "
                                     f"escolher o dono")
            # frontmatter `description:` — texto que o orquestrador lê ao escolher
            if re.match(r"description:", linha):
                m = re.search(r"Delegates to (.*)", linha)
                if m:
                    for palavra in re.findall(r"(?<![:\w-])([a-z][a-z0-9-]*)(?![:\w-])",
                                              m.group(1)):
                        if palavra in mapa:
                            erros.append(f"{rel}:{n}: description cita `{palavra}` "
                                         f"sem prefixo "
                                         f"({', '.join(sorted(mapa[palavra]))})")
    return erros


def autoteste() -> list:
    """Prova que o verificador é capaz de ficar vermelho (e de ficar verde)."""
    falhas = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        ag = t / "x" / "agents"
        ag.mkdir(parents=True)
        (ag / "foo.md").write_text("---\nname: foo\n---\n", encoding="utf-8")
        lead = ag / "y-lead.md"

        lead.write_text("---\nname: y-lead\n---\nDelegue a `foo`.\n", encoding="utf-8")
        if not any("y-lead.md:4" in e and "x:foo" in e for e in verificar(t, ["x"])):
            falhas.append("autoteste: nome curto `foo` não foi detectado")

        lead.write_text("---\nname: y-lead\n---\nDelegue a `x:foo`.\n", encoding="utf-8")
        if verificar(t, ["x"]):
            falhas.append("autoteste: `x:foo` válido foi reprovado")

        lead.write_text("---\nname: y-lead\n---\nDelegue a `x:fo`.\n", encoding="utf-8")
        if not verificar(t, ["x"]):
            falhas.append("autoteste: `x:fo` (typo) não foi detectado")

        # plugin errado: `z` também tem `foo`, mas o lead é de `x`
        zag = t / "z" / "agents"
        zag.mkdir(parents=True)
        (zag / "foo.md").write_text("---\nname: foo\n---\n", encoding="utf-8")
        lead.write_text("---\nname: y-lead\n---\nDelegue a `z:foo`.\n", encoding="utf-8")
        if not any("plugin errado" in e and "x:foo" in e for e in verificar(t, ["x"])):
            falhas.append("autoteste: `z:foo` em lead de `x` não foi detectado")

        cag = t / "common" / "agents"
        cag.mkdir(parents=True)
        (cag / "bar.md").write_text("---\nname: bar\n---\n", encoding="utf-8")
        lead.write_text("---\nname: y-lead\n---\n`common:bar` e `file:line`.\n",
                        encoding="utf-8")
        if verificar(t, ["x"]):
            falhas.append("autoteste: `common:bar` / `file:line` foram reprovados")

        lead.write_text("---\ndescription: Delegates to foo, bar\n---\n", encoding="utf-8")
        if not verificar(t, ["x"]):
            falhas.append("autoteste: nome curto na description não foi detectado")
    return falhas


def main():
    falhas = autoteste()
    print("ok   autoteste" if not falhas else "FAIL autoteste")

    erros = verificar(REPO, PLUGINS_COBERTOS)
    leads = [p for pl in PLUGINS_COBERTOS for p in (REPO / pl / "agents").glob("*-lead.md")]
    for e in erros:
        print("FAIL", e, file=sys.stderr)
    if not erros:
        print(f"ok   {len(leads)} leads de {', '.join(PLUGINS_COBERTOS)}: workers todos "
              "com prefixo do plugin dono")

    todas = falhas + erros
    for f in falhas:
        print("FAIL", f, file=sys.stderr)
    if todas:
        print(f"\n{len(todas)} falha(s). Nos leads, chame o worker como "
              "`<plugin>:<nome>` (ex.: `build-hex:epic-author`).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
