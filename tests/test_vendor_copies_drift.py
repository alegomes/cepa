#!/usr/bin/env python3
"""Drift detector for the vendored PyYAML copies (CS-5 of queue `pyyaml`,
docs/spec/cepa-roda-sem-pyyaml-instalado.md).

No dependencies, no yaml import. Run with `python3 tests/test_vendor_copies_drift.py`;
exits non-zero on failure.

`common/_vendor/yaml/` is the source; `board-flow`, `maestro` and `build-hex` are
generated from it by `bin/gen-vendor.py`. This test drives that script with
`--check` / `--write`. Every drift case runs against a TEMP copy of the four
`_vendor/yaml` folders (via `--root`), never the real tree.

Cases:
  (a) real tree: `--check` exits 0
  (b) one byte of maestro/_vendor/yaml/scanner.py changed: non-zero, path named
  (c) a file deleted from a copy: non-zero, path named
  (d) an extra file in a copy: non-zero, path named
  (e) `--write` on the drifted tree brings `--check` back to 0, byte restored
  (f) a changed byte in the SOURCE: the three copies are reported; `--write` propagates
  (g) `__pycache__` / `*.pyc` inside a copy is not drift
  (h) LICENSE is covered like any other file
  (i) a copy folder (or the source) that resolves outside --root: exit 2 naming it,
      for --check and --write, nothing read, copied or deleted anywhere
  (j) a symlinked file in a copy is `difere`; --write unlinks before copying and
      the source stays intact
  (k) source absent or empty: --check and --write exit 2, copies untouched
  (l) a whole copy folder missing: `ausente` for its files; --write recreates it
  (m) a nested subfolder in the source is reported missing in the 3 copies and created
  (n) the `removido` line names the extra file and the file is gone
  (p) broken symlink / symlink to a folder inside a copy: drift, named; --write removes
  (q) symlink to a folder where a file is expected: replaced by a real file, target intact
  (r) broken symlink (or link to a folder) in the SOURCE: exit 2 up front, nothing touched
  (o) a directory named like an expected file: clean non-zero exit naming it
      (--write also refuses to delete the directory)

Perturbation: make `bin/gen-vendor.py` compare only file names (or only sizes)
and (b), (f) and (h) turn red, because a one-byte substitution keeps both.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "bin" / "gen-vendor.py"
PLUGINS = ["common", "board-flow", "maestro", "build-hex"]
FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def run(mode, root=None):
    cmd = [sys.executable, str(GEN), mode]
    if root is not None:
        cmd += ["--root", str(root)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    return r.returncode, r.stdout + r.stderr


def temp_tree():
    """Temp copy of the four vendored folders only (no __pycache__)."""
    tmp = Path(tempfile.mkdtemp(prefix="vendor-drift-"))
    for p in PLUGINS:
        shutil.copytree(REPO / p / "_vendor" / "yaml", tmp / p / "_vendor" / "yaml",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return tmp


def flip_byte(path: Path):
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01  # same length, same name: only the content differs
    path.write_bytes(bytes(data))


def test_real_tree():
    check("gen-vendor.py existe", GEN.exists())
    if not GEN.exists():
        return
    code, out = run("--check")
    check("(a) árvore real: --check sai 0", code == 0, out.strip()[:300])


def test_byte_changed():
    tmp = temp_tree()
    try:
        flip_byte(tmp / "maestro/_vendor/yaml/scanner.py")
        code, out = run("--check", tmp)
        check("(b) byte alterado: sai != 0", code != 0, f"code={code}")
        check("(b) byte alterado: nomeia maestro/_vendor/yaml/scanner.py",
              "maestro/_vendor/yaml/scanner.py" in out, out.strip()[:300])
        check("(b) não acusa as cópias sãs",
              "board-flow/_vendor" not in out and "build-hex/_vendor" not in out, out.strip()[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_file_deleted():
    tmp = temp_tree()
    try:
        (tmp / "board-flow/_vendor/yaml/parser.py").unlink()
        code, out = run("--check", tmp)
        check("(c) arquivo apagado: sai != 0", code != 0, f"code={code}")
        check("(c) arquivo apagado: nomeia board-flow/_vendor/yaml/parser.py",
              "board-flow/_vendor/yaml/parser.py" in out, out.strip()[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_extra_file():
    tmp = temp_tree()
    try:
        (tmp / "build-hex/_vendor/yaml/extra.py").write_text("x = 1\n")
        code, out = run("--check", tmp)
        check("(d) arquivo sobrando: sai != 0", code != 0, f"code={code}")
        check("(d) arquivo sobrando: nomeia build-hex/_vendor/yaml/extra.py",
              "build-hex/_vendor/yaml/extra.py" in out, out.strip()[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_repairs():
    tmp = temp_tree()
    try:
        scanner = tmp / "maestro/_vendor/yaml/scanner.py"
        original = scanner.read_bytes()
        flip_byte(scanner)
        (tmp / "board-flow/_vendor/yaml/parser.py").unlink()
        (tmp / "build-hex/_vendor/yaml/extra.py").write_text("x = 1\n")
        check("(e) pré-condição: árvore divergente", run("--check", tmp)[0] != 0)
        code, out = run("--write", tmp)
        check("(e) --write sai 0", code == 0, out.strip()[:300])
        code, out = run("--check", tmp)
        check("(e) depois do --write, --check sai 0", code == 0, out.strip()[:300])
        check("(e) o byte voltou", scanner.read_bytes() == original)
        check("(e) o arquivo apagado voltou",
              (tmp / "board-flow/_vendor/yaml/parser.py").exists())
        check("(e) o arquivo sobrando saiu",
              not (tmp / "build-hex/_vendor/yaml/extra.py").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_source_changed():
    tmp = temp_tree()
    try:
        src = tmp / "common/_vendor/yaml/reader.py"
        flip_byte(src)
        code, out = run("--check", tmp)
        check("(f) byte na origem: sai != 0", code != 0, f"code={code}")
        for p in ("board-flow", "maestro", "build-hex"):
            check(f"(f) byte na origem: acusa {p}/_vendor/yaml/reader.py",
                  f"{p}/_vendor/yaml/reader.py" in out, out.strip()[:300])
        code, out = run("--write", tmp)
        check("(f) --write sai 0", code == 0, out.strip()[:300])
        for p in ("board-flow", "maestro", "build-hex"):
            check(f"(f) --write propagou para {p}",
                  (tmp / p / "_vendor/yaml/reader.py").read_bytes() == src.read_bytes())
        check("(f) depois do --write, --check sai 0", run("--check", tmp)[0] == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pycache_ignored():
    tmp = temp_tree()
    try:
        cache = tmp / "maestro/_vendor/yaml/__pycache__"
        cache.mkdir()
        (cache / "scanner.cpython-312.pyc").write_bytes(b"\x00\x01")
        (tmp / "maestro/_vendor/yaml/stray.pyc").write_bytes(b"\x00")
        code, out = run("--check", tmp)
        check("(g) __pycache__ e .pyc não são desvio", code == 0, out.strip()[:300])
        # A non-.pyc file inside __pycache__ is ignored because of the folder, not the suffix.
        store = cache / ".DS_Store"
        store.write_bytes(b"finder")
        code, out = run("--check", tmp)
        check("(g) arquivo não-.pyc dentro de __pycache__ não é desvio", code == 0,
              out.strip()[:300])
        run("--write", tmp)
        check("(g) --write não mexe no __pycache__", (cache / "scanner.cpython-312.pyc").exists())
        check("(g) --write deixa o .DS_Store de __pycache__ onde está", store.exists())
        # A .pyc OUTSIDE __pycache__ is ignored too (suffix rule), and --write leaves it.
        check("(g) .pyc fora de __pycache__ é ignorado e fica", (tmp / "maestro/_vendor/yaml/stray.pyc").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_license_covered():
    tmp = temp_tree()
    try:
        check("(h) LICENSE existe nas quatro",
              all((tmp / p / "_vendor/yaml/LICENSE").exists() for p in PLUGINS))
        flip_byte(tmp / "build-hex/_vendor/yaml/LICENSE")
        code, out = run("--check", tmp)
        check("(h) LICENSE alterada: sai != 0 e nomeia", code != 0
              and "build-hex/_vendor/yaml/LICENSE" in out, out.strip()[:300])
        run("--write", tmp)
        (tmp / "maestro/_vendor/yaml/LICENSE").unlink()
        code, out = run("--check", tmp)
        check("(h) LICENSE ausente: sai != 0 e nomeia", code != 0
              and "maestro/_vendor/yaml/LICENSE" in out, out.strip()[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def snapshot(tmp: Path) -> dict:
    """relative path -> bytes of every real file under tmp (symlinks not followed)."""
    return {p.relative_to(tmp).as_posix(): p.read_bytes()
            for p in sorted(tmp.rglob("*")) if p.is_file() and not p.is_symlink()}


def test_symlink_escape():
    tmp = temp_tree()
    outside = Path(tempfile.mkdtemp(prefix="vendor-outside-"))
    try:
        shutil.move(str(tmp / "maestro/_vendor"), str(outside / "_vendor"))
        keep = outside / "_vendor/yaml/keepme.txt"
        keep.write_text("do not delete\n")
        os.symlink(outside / "_vendor", tmp / "maestro/_vendor")
        flip_byte(tmp / "board-flow/_vendor/yaml/reader.py")  # a drift --write would fix
        before = snapshot(tmp)
        outside_before = snapshot(outside)
        for mode in ("--check", "--write"):
            code, out = run(mode, tmp)
            check(f"(i) maestro/_vendor fora da raiz, {mode}: sai 2", code == 2,
                  f"code={code} {out.strip()[:200]}")
            check(f"(i) {mode}: nomeia maestro/_vendor/yaml",
                  "maestro/_vendor/yaml" in out, out.strip()[:300])
        check("(i) keepme.txt continua lá", keep.exists())
        check("(i) nada fora da raiz foi alterado", snapshot(outside) == outside_before)
        check("(i) as outras cópias não foram tocadas", snapshot(tmp) == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def test_symlink_escape_source():
    tmp = temp_tree()
    outside = Path(tempfile.mkdtemp(prefix="vendor-outside-"))
    try:
        shutil.move(str(tmp / "common/_vendor"), str(outside / "_vendor"))
        os.symlink(outside / "_vendor", tmp / "common/_vendor")
        for mode in ("--check", "--write"):
            code, out = run(mode, tmp)
            check(f"(i) origem fora da raiz, {mode}: sai 2 e nomeia common/_vendor/yaml",
                  code == 2 and "common/_vendor/yaml" in out, f"code={code} {out.strip()[:200]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def test_symlinked_file_in_copy():
    tmp = temp_tree()
    try:
        src = tmp / "common/_vendor/yaml/reader.py"
        link = tmp / "maestro/_vendor/yaml/reader.py"
        link.unlink()
        os.symlink(src, link)
        code, out = run("--check", tmp)
        check("(j) link em cópia: sai != 0", code != 0, f"code={code}")
        check("(j) link em cópia: nomeia maestro/_vendor/yaml/reader.py como difere",
              "difere" in out and "maestro/_vendor/yaml/reader.py" in out, out.strip()[:300])
        src_bytes = src.read_bytes()
        code, out = run("--write", tmp)
        check("(j) --write sai 0", code == 0, out.strip()[:300])
        check("(j) a cópia virou arquivo real", link.is_file() and not link.is_symlink())
        check("(j) a origem está intacta", src.read_bytes() == src_bytes
              and not src.is_symlink())
        check("(j) depois do --write, --check sai 0", run("--check", tmp)[0] == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_source_absent_or_empty():
    for how in ("ausente", "vazia"):
        tmp = temp_tree()
        try:
            src = tmp / "common/_vendor/yaml"
            if how == "ausente":
                shutil.rmtree(src)
            else:
                for f in src.iterdir():
                    f.unlink()
            before = snapshot(tmp)
            for mode in ("--check", "--write"):
                code, out = run(mode, tmp)
                check(f"(k) origem {how}, {mode}: sai 2", code == 2,
                      f"code={code} {out.strip()[:200]}")
            check(f"(k) origem {how}: --write não apagou nada nas cópias",
                  snapshot(tmp) == before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def test_whole_copy_missing():
    tmp = temp_tree()
    try:
        shutil.rmtree(tmp / "maestro/_vendor/yaml")
        code, out = run("--check", tmp)
        check("(l) pasta inteira ausente: sai != 0", code != 0, f"code={code}")
        for name in ("scanner.py", "LICENSE", "__init__.py"):
            line = f"ausente   maestro/_vendor/yaml/{name}"
            check(f"(l) acusa {name} como ausente", line in out, out.strip()[:300])
        code, out = run("--write", tmp)
        check("(l) --write sai 0", code == 0, out.strip()[:300])
        check("(l) --write recriou a pasta", (tmp / "maestro/_vendor/yaml/scanner.py").is_file())
        check("(l) depois do --write, --check sai 0", run("--check", tmp)[0] == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_nested_subfolder():
    tmp = temp_tree()
    try:
        nested = tmp / "common/_vendor/yaml/sub/deep/a.py"
        nested.parent.mkdir(parents=True)
        nested.write_text("a = 1\n")
        code, out = run("--check", tmp)
        check("(m) subpasta na origem: sai != 0", code != 0, f"code={code}")
        for p in ("board-flow", "maestro", "build-hex"):
            check(f"(m) acusa {p}/_vendor/yaml/sub/deep/a.py ausente",
                  f"ausente   {p}/_vendor/yaml/sub/deep/a.py" in out, out.strip()[:300])
        code, out = run("--write", tmp)
        check("(m) --write sai 0", code == 0, out.strip()[:300])
        for p in ("board-flow", "maestro", "build-hex"):
            check(f"(m) --write criou {p}/.../sub/deep/a.py",
                  (tmp / p / "_vendor/yaml/sub/deep/a.py").read_text() == "a = 1\n")
        check("(m) depois do --write, --check sai 0", run("--check", tmp)[0] == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_removido_line():
    tmp = temp_tree()
    try:
        extra = tmp / "build-hex/_vendor/yaml/extra.py"
        extra.write_text("x = 1\n")
        code, out = run("--write", tmp)
        check("(n) --write sai 0", code == 0, out.strip()[:300])
        check("(n) a saída tem 'removido' e o caminho",
              "removido    build-hex/_vendor/yaml/extra.py" in out, out.strip()[:300])
        check("(n) o arquivo sumiu", not extra.exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_directory_named_like_a_file():
    tmp = temp_tree()
    try:
        reader = tmp / "maestro/_vendor/yaml/reader.py"
        reader.unlink()
        (reader / "inner").mkdir(parents=True)
        (reader / "inner/keep.txt").write_text("keep\n")
        (tmp / "build-hex/_vendor/yaml/extra.py").write_text("x = 1\n")
        before = snapshot(tmp)
        for mode in ("--check", "--write"):
            code, out = run(mode, tmp)
            check(f"(o) pasta com nome de arquivo, {mode}: sai != 0", code != 0, f"code={code}")
            check(f"(o) {mode}: sem traceback", "Traceback" not in out, out.strip()[-300:])
            check(f"(o) {mode}: nomeia maestro/_vendor/yaml/reader.py",
                  "maestro/_vendor/yaml/reader.py" in out, out.strip()[:300])
        check("(o) a pasta continua lá", (reader / "inner/keep.txt").exists())
        check("(o) --write recusou antes de mexer em qualquer cópia", snapshot(tmp) == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_stray_links_in_copy():
    for kind in ("quebrado", "para pasta"):
        tmp = temp_tree()
        outside = Path(tempfile.mkdtemp(prefix="vendor-outside-"))
        try:
            (outside / "keep.txt").write_text("keep\n")
            link = tmp / "maestro/_vendor/yaml/stray_link"
            os.symlink(outside / "nope" if kind == "quebrado" else outside, link)
            code, out = run("--check", tmp)
            check(f"(p) link {kind} na cópia: sai != 0", code != 0, f"code={code}")
            check(f"(p) link {kind}: nomeia maestro/_vendor/yaml/stray_link",
                  "maestro/_vendor/yaml/stray_link" in out, out.strip()[:300])
            code, out = run("--write", tmp)
            check(f"(p) link {kind}: --write sai 0", code == 0, out.strip()[:300])
            check(f"(p) link {kind}: --write removeu o link", not link.is_symlink())
            check(f"(p) link {kind}: o alvo do link está intacto",
                  (outside / "keep.txt").read_text() == "keep\n")
            check(f"(p) link {kind}: depois do --write, --check sai 0", run("--check", tmp)[0] == 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(outside, ignore_errors=True)


def test_dir_link_where_file_expected():
    tmp = temp_tree()
    outside = Path(tempfile.mkdtemp(prefix="vendor-outside-"))
    try:
        (outside / "keep.txt").write_text("keep\n")
        reader = tmp / "maestro/_vendor/yaml/reader.py"
        reader.unlink()
        os.symlink(outside, reader)
        src_bytes = (tmp / "common/_vendor/yaml/reader.py").read_bytes()
        code, out = run("--check", tmp)
        check("(q) link para pasta no lugar de arquivo: --check sai != 0 e nomeia",
              code != 0 and "maestro/_vendor/yaml/reader.py" in out, out.strip()[:300])
        code, out = run("--write", tmp)
        check("(q) --write sai 0 (o link não é pasta de verdade)", code == 0, out.strip()[:300])
        check("(q) virou arquivo real com os bytes da origem",
              reader.is_file() and not reader.is_symlink() and reader.read_bytes() == src_bytes)
        check("(q) nada foi escrito através do link",
              sorted(p.name for p in outside.iterdir()) == ["keep.txt"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


def test_broken_link_in_source():
    for kind in ("quebrado", "para pasta"):
        tmp = temp_tree()
        outside = Path(tempfile.mkdtemp(prefix="vendor-outside-"))
        try:
            link = tmp / "common/_vendor/yaml/zz_link.py"
            os.symlink(outside / "nope" if kind == "quebrado" else outside, link)
            before = snapshot(tmp)
            flip_byte(tmp / "board-flow/_vendor/yaml/reader.py")  # drift a --write would fix
            before = snapshot(tmp)
            for mode in ("--check", "--write"):
                code, out = run(mode, tmp)
                check(f"(r) link {kind} na origem, {mode}: sai 2", code == 2,
                      f"code={code} {out.strip()[:200]}")
                check(f"(r) {mode}: sem traceback e nomeia common/_vendor/yaml/zz_link.py",
                      "Traceback" not in out and "common/_vendor/yaml/zz_link.py" in out,
                      out.strip()[-300:])
            check(f"(r) link {kind}: nada foi tocado", snapshot(tmp) == before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(outside, ignore_errors=True)


def main():
    test_real_tree()
    test_byte_changed()
    test_file_deleted()
    test_extra_file()
    test_write_repairs()
    test_source_changed()
    test_pycache_ignored()
    test_license_covered()
    test_symlink_escape()
    test_symlink_escape_source()
    test_symlinked_file_in_copy()
    test_source_absent_or_empty()
    test_whole_copy_missing()
    test_nested_subfolder()
    test_removido_line()
    test_directory_named_like_a_file()
    test_stray_links_in_copy()
    test_dir_link_where_file_expected()
    test_broken_link_in_source()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
