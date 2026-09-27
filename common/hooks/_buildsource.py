#!/usr/bin/env python3
"""_buildsource — o que conta como "código de produção" para as heurísticas
que respondem "esta baseline de build ainda descreve o que está no disco?".

WHY THIS EXISTS
----------------
`mark-build-stale.py` já tinha essa heurística (`is_source`) desde que nasceu:
edição em fonte/manifesto de build invalida o `.claude/last-build.json`, edição
em doc/spec/teste não. O `maven-reactor-guard.py` precisou da MESMA pergunta em
2026-09-27, mas sobre um CARIMBO DE TEMPO em vez de um evento de Edit/Write —
"algum arquivo fonte do reator mudou depois deste horário?" (a liberação de
"instalação fresca da raiz", ver docstring do guard). Copiar a lista de
extensões teria criado a terceira fonte da mesma verdade — exatamente o padrão
que `_shellscan.py` já documenta ter custado caro duas vezes (falso-positivo do
`>=` sobrevivendo 2 meses numa cópia esquecida, e o mesmo com o commit de
várias linhas). Então ambos importam daqui.
"""

import os

SOURCE_EXTENSIONS = {
    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy", ".clj",
    # JavaScript / TypeScript
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    # Python
    ".py", ".pyx",
    # Go / Rust
    ".go", ".rs",
    # Ruby / PHP / C# / Swift / ObjC
    ".rb", ".php", ".cs", ".swift", ".m", ".mm",
    # C / C++
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx",
    # Elixir
    ".ex", ".exs",
    # SQL (treated as source — migrations affect runtime behavior)
    ".sql",
}

BUILD_FILES = {
    "pom.xml",
    "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts",
    "package.json", "package-lock.json",
    "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum",
    "requirements.txt", "Pipfile", "Pipfile.lock",
    "pyproject.toml", "poetry.lock",
    "Gemfile", "Gemfile.lock",
}

EXCLUDED_PATH_FRAGMENTS = (
    ".claude/",
    "docs/",
    "/spec/", "/specs/",
    "/src/test/", "/test/", "/tests/", "/__tests__/",
)

# Diretórios podados de bandeja ao andar pelo reator: nunca contêm fonte, e um
# `target/` ou `node_modules/` de projeto grande tem ordens de magnitude mais
# arquivos que o código-fonte em cima do qual a pergunta realmente é feita.
_PRUNE_DIRS = {"target", ".git", "node_modules", ".claude"}


def is_source(file_path: str) -> bool:
    """Heurística: editar este arquivo invalida 'a build ainda está verde?'."""
    from pathlib import Path
    p = Path(file_path)
    posix = str(p).replace(os.sep, "/")

    for fragment in EXCLUDED_PATH_FRAGMENTS:
        if fragment in posix:
            return False

    if p.name in BUILD_FILES:
        return True

    if p.suffix.lower() in SOURCE_EXTENSIONS:
        return True

    return False


def any_source_newer(root, after_ts: float) -> bool:
    """True se algum arquivo-fonte (ver `is_source`) sob `root` tem mtime
    posterior a `after_ts` (epoch, mesma escala de `os.path.getmtime`).

    Um único `os.walk`, podando os diretórios de `_PRUNE_DIRS` — é chamada a
    cada `-pl` sem `-am` que o `maven-reactor-guard` avalia, então precisa ser
    rápida mesmo num reator grande. Arquivo ilegível (removido entre o walk e o
    stat, permissão) é ignorado, não interrompe a varredura.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PRUNE_DIRS]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if not is_source("/" + rel):
                continue
            try:
                if os.path.getmtime(full) > after_ts:
                    return True
            except OSError:
                continue
    return False
