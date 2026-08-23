#!/usr/bin/env python3
"""Detector de divergência entre as 5 cópias dos path-locks (P0-3, revisão 2026-08-17).

Sem dependências — rode com `python3 tests/test_lock_copies_drift.py`.
Sai não-zero em falha.

## O problema que este arquivo existe para pegar

`path-lock.py` e `bash-path-lock.py` são os dois hooks que sustentam a garantia
central do produto: worker escreve só na própria pista, lead delega em vez de
codar. Eles existem em **cinco cópias**, uma por topologia com hook, e a regra
de manutenção é humana — "todo fix aterrissa nas 5". Ela já falhou: o conserto
do falso-positivo `>=` (o hook lia o `>` de `>=` como redirecionamento e
bloqueava comando legítimo) teve de ser propagado à mão, e a memória do projeto
registra o episódio da cópia que ficou para trás.

O modo de falha é silencioso, que é o que o torna caro: a cópia defasada não
quebra nada — ela **permite** o que as outras quatro bloqueiam, e o relatório
do agente lê como sucesso.

## O que é comparado: código, não prosa

A comparação é feita sobre a **árvore sintática** (AST) de cada função, com
docstrings removidos. Isso é uma decisão, tomada depois de a primeira versão
deste teste (comparação textual) acusar seis divergências que se revelaram
todas cosméticas: comentários reescritos, docstrings de estilos diferentes e
`list[str]` contra `list` numa anotação. Nenhuma mudava comportamento.

Um detector que grita por vírgula ensina a ignorá-lo, e o dia em que ele grita
por um `>=` virando `>` é o dia em que alguém aperta "ignorar". Então:

- **Comentário, docstring e anotação de tipo não são comparados.** Prosa por
  topologia é legítima — o `build-hex` carrega o incidente real que originou o
  hook, e faz sentido que carregue.
- **Todo o resto é.** Comparar o corpo em AST pega exatamente a classe que
  importa: uma condição alterada numa cópia só, que é como o falso-positivo do
  `>=` sobreviveu em quatro cópias e não na quinta.

Cobertura por arquivo:

- **`bash-path-lock.py`: o módulo inteiro**, incluindo as tabelas de regex no
  nível do módulo — que é onde o bug do `>=` morava.
- **`common/hooks/_shellscan.py` contra o `bash-path-lock`**: o motor de leitura
  da linha de comando (máscara de aspas, quebra em segmentos, regex de
  redirecionamento) existe em duas fontes — o molde das 5 cópias e este módulo,
  de onde o `enforcement-guard` e o `maven-reactor-guard` importam. Duas fontes
  porque hook de outro plugin não importa do `common`. Antes de 23/08/2026 eram
  **sete cópias manuais** e este detector conhecia cinco: o falso-positivo do
  `>=` ficou 2 meses sem conserto no `enforcement-guard`, e o commit de várias
  linhas (WEGO-2087) repetiu a história.
- **`path-lock.py`: o núcleo compartilhado** (`detect_agent`,
  `is_own_expertise_file`, `path_matches`) mais o `main` das topologias sem YAML
  próprio. O `main` do `build-hex` e o `debug_log` legitimamente diferem, e
  estão declarados em `EXEMPT` **com o motivo** — exceção declarada é decisão;
  exceção silenciosa é a doença que este arquivo trata.

## Perturbação (como saber que este teste prova algo)

Edite qualquer função comparada em UMA cópia — por exemplo troque um `>=` por
`>` em `build-hex/hooks/bash-path-lock.py` — e este teste fica vermelho
nomeando a cópia divergente. Se ficar verde, ele não está provando nada.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Diretório da topologia → os tokens que aquela cópia legitimamente carrega.
# Todos viram <T> antes da comparação. Manter esta tabela é o preço de ter 5
# cópias; quando a geração automática existir (2ª metade do item no BACKLOG),
# ela lê daqui.
TOPOLOGIES = {
    "build-team": ["build-team", "multiteam"],
    "build-hex": ["build-hex", "hex", "HEX_PATHLOCK_DEBUG"],
    "discovery": ["discovery"],
    "design": ["design"],
    "docs-topology": ["docs-topology", "docs"],
}

# Funções do path-lock.py que TÊM de ser idênticas nas cópias onde existem.
PATHLOCK_CORE = ["detect_agent", "is_own_expertise_file", "path_matches"]

# Divergências legítimas, com o motivo. Sem motivo escrito, não entra aqui.
EXEMPT = {
    ("path-lock.py", "main"):
        "build-hex resolve papéis→módulos via build-hex.yaml (load_roles + "
        "build_allowed_writes) antes de gatear; as outras topologias têm o mapa "
        "de globs fixo no módulo. O fluxo de decisão é o mesmo; o preâmbulo não.",
    ("bash-path-lock.py", "main"):
        "mesmo motivo do path-lock:main — o build-hex resolve papéis→módulos "
        "pelo build-hex.yaml antes de gatear, e o main é onde esse preâmbulo "
        "acontece. A extração de alvos de escrita (_segment_targets, "
        "extract_write_targets) e as tabelas de regex, que é onde mora o risco, "
        "seguem comparadas nas 5.",
    ("path-lock.py", "debug_log"):
        "existe só em build-hex e docs-topology, e a do build-hex recebe o mapa "
        "de papéis (`roles`) para logar qual módulo cada papel virou — dado que "
        "só existe onde há build-hex.yaml. É função de diagnóstico, fora do "
        "caminho de decisão do gate: divergir aqui não permite nem bloqueia nada.",
}

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def normalize(src: str) -> str:
    """Apaga o que é legitimamente por-topologia, preserva o resto.

    Só substituições MECÂNICAS entram aqui. Se um dia for preciso normalizar
    lógica para dois arquivos baterem, a resposta é consertar a cópia, não
    ampliar esta função — normalizar diferença de comportamento é como um
    detector de divergência para de detectar.
    """
    # O alias do módulo importado (`hex_path_lock`, `design_path_lock`, ...):
    # `_` é caractere de palavra, então a substituição por \b abaixo não o
    # alcança. Precisa vir antes, e explicitamente.
    src = re.sub(r"\b\w+_path_lock\b", "<T>_path_lock", src)
    words = sorted({w for ws in TOPOLOGIES.values() for w in ws}, key=len, reverse=True)
    for w in words:
        src = re.sub(rf"\b{re.escape(w)}\b", "<T>", src)
    # O substantivo do que a topologia escreve: build-* escreve `source`,
    # design/discovery/docs escrevem `artifacts`. Diferença declarada, não
    # acidental.
    src = re.sub(r"Writing (?:source|artifacts) via Bash", "Writing <NOUN> via Bash", src)
    # Espaço em branco no fim de linha não é divergência.
    return "\n".join(line.rstrip() for line in src.splitlines()).strip()


def _is_docstring(node) -> bool:
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def _strip_docstrings(tree):
    """Tira o docstring do módulo e de cada função, recursivamente.

    Comentários já não existem na AST — é justamente por isso que a comparação
    é feita aqui e não no texto.
    """
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and _is_docstring(body[0]):
            node.body = body[1:] or [ast.Pass()]
    return tree


def module_constants(src: str) -> str:
    """Statements de nível de módulo que NÃO são função, import ou o guard final.

    É aqui que vivem `_REDIR_RE`, `_UNCOVERED_RE`, `_SEP_RE` e `_PSEUDO` — as
    tabelas que decidem o que conta como escrita. `PLUGIN_NAME` sai da conta
    porque é justamente o que cada topologia tem de próprio.
    """
    tree = _strip_docstrings(ast.parse(normalize(src)))
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.Import, ast.ImportFrom, ast.If)):
            continue
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "PLUGIN_NAME" in names:
                continue
        out.append(ast.dump(node))
    return "\n".join(out)


def code_of(src: str) -> str:
    """A AST do módulo inteiro, sem docstrings, como string comparável.

    Uma linha por statement de topo, para que a primeira divergência relatada
    seja localizável em vez de um paredão de texto.
    """
    tree = _strip_docstrings(ast.parse(normalize(src)))
    return "\n".join(ast.dump(node) for node in tree.body)


def _is_diagnostic_call(node) -> bool:
    """`debug_log(...)` solto — diagnóstico, fora do caminho de decisão.

    Só duas das cinco cópias têm o `debug_log` (build-hex e docs-topology), e a
    chamada dele no `main` faria os `main` divergirem por uma linha que não
    permite nem bloqueia nada. Tirar SÓ essa chamada mantém o resto do `main`
    sob comparação — exceptuar o `main` inteiro cegaria a checagem justamente
    na função que decide.
    """
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "debug_log")


def functions_of(src: str) -> dict:
    """nome → AST do CORPO da função (sem docstring, sem assinatura).

    Sem a assinatura de propósito: `list[str]` contra `list` é estilo de
    anotação, não comportamento, e uma delas é só mais nova que a outra.
    """
    tree = _strip_docstrings(ast.parse(normalize(src)))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            body = [b for b in node.body if not _is_diagnostic_call(b)]
            out[node.name] = "\n".join(ast.dump(b) for b in body)
    return out


def copies(filename: str) -> dict:
    out = {}
    for topo in TOPOLOGIES:
        p = REPO / topo / "hooks" / filename
        if p.exists():
            out[topo] = p.read_text(encoding="utf-8")
    return out


# ── casos ────────────────────────────────────────────────────────────────────

def test_todas_as_copias_existem():
    for filename in ("path-lock.py", "bash-path-lock.py"):
        found = copies(filename)
        check(f"{filename}: as 5 cópias existem",
              len(found) == len(TOPOLOGIES),
              f"achei {sorted(found)}")


def test_bash_path_lock_identico():
    """Toda função e toda tabela de nível de módulo, nas 5 cópias.

    As tabelas entram porque é onde o bug do `>=` morava: `_REDIR_RE` é uma
    constante de módulo, não uma função, e uma regressão ali não apareceria numa
    comparação que só olhasse funções.
    """
    found = copies("bash-path-lock.py")
    if not found:
        check("bash-path-lock.py: cópias encontradas", False)
        return

    # 1. tabelas / constantes de nível de módulo
    consts = {t: module_constants(s) for t, s in found.items()}
    ref_topo = "build-hex"
    ref = consts[ref_topo]
    divergent = [t for t, s in consts.items() if s != ref]
    check("bash-path-lock.py: tabelas de módulo idênticas nas 5 cópias",
          not divergent, f"divergem de {ref_topo}: {divergent}")
    for t in divergent:
        _report_first_diff(ref_topo, ref, t, consts[t])

    # 2. funções, uma a uma
    funcs = {t: functions_of(s) for t, s in found.items()}
    names = sorted({n for f in funcs.values() for n in f})
    for name in names:
        if ("bash-path-lock.py", name) in EXEMPT:
            continue
        present = {t: f[name] for t, f in funcs.items() if name in f}
        if len(present) < 2:
            continue
        ref = present[ref_topo] if ref_topo in present else present[sorted(present)[0]]
        base = ref_topo if ref_topo in present else sorted(present)[0]
        divergent = [t for t, s in present.items() if s != ref]
        check(f"bash-path-lock.py:{name} idêntico em {len(present)} cópias",
              not divergent, f"divergem de {base}: {divergent}")
        for t in divergent:
            _report_first_diff(f"{base}:{name}", ref, t, present[t])


def test_path_lock_nucleo_identico():
    """O núcleo compartilhado tem de bater; o resto é declarado em EXEMPT."""
    found = copies("path-lock.py")
    if not found:
        check("path-lock.py: cópias encontradas", False)
        return
    funcs = {t: functions_of(s) for t, s in found.items()}
    for name in PATHLOCK_CORE:
        present = {t: f[name] for t, f in funcs.items() if name in f}
        if len(present) < 2:
            continue  # função de uma cópia só — nada a comparar
        ref_topo = "build-hex" if "build-hex" in present else sorted(present)[0]
        ref = present[ref_topo]
        divergent = [t for t, s in present.items() if s != ref]
        check(f"path-lock.py:{name} idêntico em {len(present)} cópias",
              not divergent,
              f"divergem de {ref_topo}: {divergent}")
        if divergent:
            for t in divergent:
                _report_first_diff(f"{ref_topo}:{name}", ref, t, present[t])


def test_exempcoes_tem_motivo():
    """Uma exceção sem motivo escrito é uma divergência que se disfarçou."""
    for key, reason in EXEMPT.items():
        check(f"exceção {key[0]}:{key[1]} declara motivo",
              isinstance(reason, str) and len(reason.strip()) > 40,
              "motivo ausente ou vago demais para auditar")


def test_main_do_pathlock_bate_fora_do_hex():
    """As 4 topologias sem YAML de módulos compartilham o `main` inteiro.

    O `build-hex` está em EXEMPT; as outras quatro não têm desculpa — se uma
    delas divergir, é exatamente o caso "4 de 5 consertadas".
    """
    found = {t: s for t, s in copies("path-lock.py").items() if t != "build-hex"}
    mains = {t: fs["main"] for t, fs in ((t, functions_of(s)) for t, s in found.items())
             if "main" in fs}
    if len(mains) < 2:
        check("path-lock.py:main comparável fora do build-hex", False)
        return
    ref_topo = sorted(mains)[0]
    ref = mains[ref_topo]
    divergent = [t for t, s in mains.items() if s != ref]
    check(f"path-lock.py:main idêntico nas {len(mains)} topologias sem build-hex.yaml",
          not divergent,
          f"divergem de {ref_topo}: {divergent}")
    if divergent:
        for t in divergent:
            _report_first_diff(f"{ref_topo}:main", ref, t, mains[t])


# O motor de leitura de linha de comando, nas duas fontes que restaram: o molde
# das 5 cópias (representado pela do build-hex) e common/hooks/_shellscan.py,
# de onde os dois guards do common importam.
SHELLSCAN_FUNCS = ["_quoted_mask", "_split_segments", "_strip_redirections",
                   "_unquoted_view", "_unquote", "_is_flag"]
SHELLSCAN_CONSTS = ["_REDIR_RE", "_REDIR_STRIP_RE", "_SEP_PAIRS", "_SEP_CHARS",
                    "_PSEUDO"]


def named_constants(src: str, names: list) -> dict:
    """nome → AST da atribuição, para as constantes pedidas."""
    tree = _strip_docstrings(ast.parse(normalize(src)))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    out[t.id] = ast.dump(node.value)
    return out


def test_motor_do_shellscan_bate_com_o_bash_path_lock():
    """As duas fontes do motor de parsing têm de dizer a mesma coisa.

    Perturbação: troque `(?![&=])` por `(?!&)` no `_REDIR_RE` de
    `common/hooks/_shellscan.py` — o falso-positivo do `>=`, exatamente como ele
    sobreviveu no enforcement-guard — e este caso fica vermelho nomeando a
    constante. Se ficar verde, ele não está provando nada.
    """
    ref_p = REPO / "build-hex" / "hooks" / "bash-path-lock.py"
    scan_p = REPO / "common" / "hooks" / "_shellscan.py"
    check("common/hooks/_shellscan.py existe", scan_p.exists())
    if not (ref_p.exists() and scan_p.exists()):
        return
    ref_src, scan_src = ref_p.read_text(encoding="utf-8"), scan_p.read_text(encoding="utf-8")

    ref_c, scan_c = (named_constants(ref_src, SHELLSCAN_CONSTS),
                     named_constants(scan_src, SHELLSCAN_CONSTS))
    for name in SHELLSCAN_CONSTS:
        check(f"_shellscan:{name} presente nas duas fontes",
              name in ref_c and name in scan_c,
              f"bash-path-lock={name in ref_c} _shellscan={name in scan_c}")
        if name in ref_c and name in scan_c:
            check(f"_shellscan:{name} idêntico ao bash-path-lock",
                  ref_c[name] == scan_c[name],
                  "a tabela divergiu entre as duas fontes do motor")

    ref_f, scan_f = functions_of(ref_src), functions_of(scan_src)
    for name in SHELLSCAN_FUNCS:
        check(f"_shellscan:{name} presente nas duas fontes",
              name in ref_f and name in scan_f,
              f"bash-path-lock={name in ref_f} _shellscan={name in scan_f}")
        if name in ref_f and name in scan_f:
            igual = ref_f[name] == scan_f[name]
            check(f"_shellscan:{name} idêntico ao bash-path-lock", igual,
                  "o corpo divergiu entre as duas fontes do motor")
            if not igual:
                _report_first_diff(f"bash-path-lock:{name}", ref_f[name],
                                   "_shellscan", scan_f[name])


def test_guards_do_common_nao_recopiam_o_motor():
    """Os dois guards importam o motor; não podem voltar a definir o seu.

    Redefinir `_quoted_mask` ou `_REDIR_RE` num guard é exatamente como a
    duplicação começou da primeira vez — e a cópia nova não seria vista por
    nenhum dos casos acima, porque eles comparam as DUAS fontes declaradas.
    """
    for nome in ("enforcement-guard.py", "maven-reactor-guard.py"):
        p = REPO / "common" / "hooks" / nome
        check(f"{nome} existe", p.exists())
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        check(f"{nome} importa _shellscan", "import _shellscan" in src,
              "o guard precisa importar o motor em vez de copiá-lo")
        tree = ast.parse(src)
        redefinidos = [n.name for n in tree.body
                       if isinstance(n, ast.FunctionDef)
                       and n.name in SHELLSCAN_FUNCS]
        redefinidos += [t.id for n in tree.body if isinstance(n, ast.Assign)
                        for t in n.targets
                        if isinstance(t, ast.Name) and t.id in SHELLSCAN_CONSTS
                        and not (isinstance(n.value, ast.Attribute))]
        check(f"{nome} não redefine nada do motor", not redefinidos,
              f"redefinido localmente: {sorted(set(redefinidos))}")


def _report_first_diff(ref_label, ref, other_label, other):
    """Mostra o TRECHO que difere — não o começo da linha, que é igual.

    A comparação é sobre dumps de AST, que são longos e começam idênticos:
    imprimir os primeiros 100 caracteres mostraria duas linhas iguais e mandaria
    quem lê caçar a diferença na mão. Aqui a janela é centrada no primeiro
    caractere divergente.
    """
    a, b = ref.splitlines(), other.splitlines()
    for i in range(max(len(a), len(b))):
        la = a[i] if i < len(a) else ""
        lb = b[i] if i < len(b) else ""
        if la == lb:
            continue
        j = next((k for k in range(min(len(la), len(lb))) if la[k] != lb[k]),
                 min(len(la), len(lb)))
        lo, hi = max(0, j - 40), j + 70
        pre = "…" if lo else ""
        print(f"       1ª divergência (statement {i + 1}, caractere {j}):")
        print(f"         {ref_label}: {pre}{la[lo:hi] or '<ausente>'}")
        print(f"         {other_label}: {pre}{lb[lo:hi] or '<ausente>'}")
        return


def test_bash_path_lock_sai_do_molde():
    """As 5 cópias têm de ser exatamente o molde renderizado.

    Esta é a garantia FORTE, e ela substitui a comparação entre cópias para
    este arquivo: comparar cópias entre si prova que elas concordam; comparar
    com o molde prova que elas vêm de um lugar só. A diferença importa quando
    alguém edita as cinco à mão de um jeito consistente e errado.

    Construir o gerador rendeu um achado que a comparação entre cópias não
    tinha dado: `discovery` e `docs-topology` diziam "Writing source via Bash"
    na mensagem de bloqueio, sendo que os agentes deles escrevem documento, não
    código — vieram copiados do build-team sem ajustar a palavra. A comparação
    entre cópias tratava esse substantivo como diferença legítima por
    topologia; o molde obriga a declarar qual é o certo para cada uma.
    """
    gen = REPO / "bin" / "gen-locks.py"
    check("bin/gen-locks.py existe", gen.exists())
    if not gen.exists():
        return
    r = subprocess.run([sys.executable, str(gen), "--check"],
                       capture_output=True, text=True, cwd=str(REPO))
    check("as 5 cópias são exatamente o molde renderizado",
          r.returncode == 0, (r.stdout + r.stderr).strip()[:300])


def main():
    test_todas_as_copias_existem()
    test_bash_path_lock_sai_do_molde()
    test_bash_path_lock_identico()
    test_path_lock_nucleo_identico()
    test_main_do_pathlock_bate_fora_do_hex()
    test_motor_do_shellscan_bate_com_o_bash_path_lock()
    test_guards_do_common_nao_recopiam_o_motor()
    test_exempcoes_tem_motivo()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        print("\nUma cópia saiu da linha. Propague o conserto para TODAS antes de "
              "seguir — é exatamente a classe de falha que este teste existe para "
              "pegar (ver o item P0-3 no BACKLOG).")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
