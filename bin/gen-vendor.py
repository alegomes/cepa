#!/usr/bin/env python3
"""gen-vendor — keeps the vendored PyYAML copies identical to their source.

## Why it exists

Cepa runs on a `python3` that may have no PyYAML installed
(docs/spec/cepa-roda-sem-pyyaml-instalado.md), so each plugin that reads YAML
carries its own copy of PyYAML 6.0.3 in `<plugin>/_vendor/yaml/`. Four plugins
means four copies, and a human rule ("touch all four") is the kind that
silently fails: one copy lags and the same YAML parses differently depending
on which plugin's script reads it.

`common/_vendor/yaml/` is the single source. `board-flow`, `maestro` and
`build-hex` are a function of it. This script checks that and regenerates them.

## What is compared

Bytes, file by file, over the relative paths under the source folder.
`__pycache__/` and `*.pyc` are ignored on both sides: they are what Python
leaves behind when it imports the copy, not part of it. Three kinds of drift
are reported, each naming the repo-relative path inside the copy:

- a file whose bytes differ from the source's;
- a file the source has that the copy lacks;
- a file the copy has that the source does not.

Because the source is the truth, a changed byte in `common/_vendor/yaml/` is
reported as the three copies diverging, not as a problem of the source.

## Upgrading PyYAML

Manual, on purpose, and offline: replace the files in
`common/_vendor/yaml/` (keep `LICENSE`) and run `--write`. There is no command
that downloads anything.

## Usage

    python3 bin/gen-vendor.py --check   # are the three copies equal to the source?
    python3 bin/gen-vendor.py --write   # regenerates the three from the source

    --root DIR   operate on another tree with the same layout (the test uses a
                 temporary copy, so drift cases never touch the real repo)

`--write` leaves `__pycache__/` alone (it neither copies nor deletes it).
`--check` exits 0 when equal, 1 on drift, 2 when it refuses to run.

It refuses (exit 2, before reading, copying or deleting anything in ANY copy)
when the source is missing or empty, when the source holds a symlink that does
not lead to a file (broken, or to a folder), when a copy folder or the source does not
resolve to exactly `<root>/<folder>` (a symlink in the path would make `--write`
delete files outside the root), or, for `--write`, when a directory sits where a
file is expected (the directory is never deleted). A symlinked file inside a
copy counts as `difere`: a copy must be real files, because the installer copies
the plugin folder; `--write` unlinks it before copying so the source is never
written through the link.
This script does not import `yaml`: it only compares bytes.
"""

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = "common/_vendor/yaml"
COPIES = ["board-flow/_vendor/yaml", "maestro/_vendor/yaml", "build-hex/_vendor/yaml"]


def files_of(folder: Path) -> set:
    """Relative paths of every file under `folder`, minus bytecode leftovers."""
    return {
        p.relative_to(folder)
        for p in folder.rglob("*")
        if (p.is_file() or p.is_symlink())
        and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def drift(root: Path, copy: str) -> list:
    """Problems of one copy against the source, as (kind, repo-relative path)."""
    src, dst = root / SOURCE, root / copy
    have, want = files_of(dst), files_of(src)
    out = []
    for rel in sorted(want | have):
        shown = f"{copy}/{rel.as_posix()}"
        if rel not in have:
            out.append(("ausente", shown))
        elif rel not in want:
            out.append(("sobrando", shown))
        elif (dst / rel).is_symlink():
            out.append(("difere", shown))
        elif (src / rel).read_bytes() != (dst / rel).read_bytes():
            out.append(("difere", shown))
    return out


def write(root: Path, copy: str) -> None:
    src, dst = root / SOURCE, root / copy
    want = files_of(src)
    for rel in sorted(files_of(dst) - want):
        (dst / rel).unlink()
        print(f"  removido    {copy}/{rel.as_posix()}")
    for rel in sorted(want):
        target = dst / rel
        if (target.is_file() and not target.is_symlink()
                and target.read_bytes() == (src / rel).read_bytes()):
            continue
        if target.is_symlink():
            target.unlink()  # never write through a link: it may point at the source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, target)
        print(f"  regenerado  {copy}/{rel.as_posix()}")
    print(f"  em dia      {copy}")


def refusal(root: Path, writing: bool):
    """A reason to refuse before touching anything, or None."""
    for folder in [SOURCE] + COPIES:
        if (root / folder).resolve() != root / folder:
            return f"✗ {folder} não resolve para dentro de {root} (link simbólico?); recusado"
    if not files_of(root / SOURCE):
        return f"✗ origem ausente ou vazia: {SOURCE}"
    for rel in sorted(files_of(root / SOURCE)):
        s = root / SOURCE / rel
        if s.is_symlink() and not s.is_file():  # broken link, or link to a folder
            return f"✗ {SOURCE}/{rel.as_posix()} é um link simbólico que não leva a um arquivo; recusado (nada foi tocado)"
    if writing:
        for copy in COPIES:
            for rel in sorted(files_of(root / SOURCE)):
                t = root / copy / rel
                if t.is_dir() and not t.is_symlink():
                    return f"✗ {copy}/{rel.as_posix()} é uma pasta onde deveria haver um arquivo; recusado (nada foi apagado)"
    return None


def main():
    ap = argparse.ArgumentParser(description="Mantém as cópias do PyYAML iguais à origem.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="as cópias batem com a origem?")
    g.add_argument("--write", action="store_true", help="regenera as três cópias")
    ap.add_argument("--root", type=Path, default=REPO,
                    help="raiz com o mesmo layout (padrão: o repo deste script)")
    args = ap.parse_args()
    root = args.root.resolve()

    why = refusal(root, args.write)
    if why:
        print(why, file=sys.stderr)
        return 2

    if args.write:
        for copy in COPIES:
            write(root, copy)
        return 0

    problems = [(copy, kind, path) for copy in COPIES for kind, path in drift(root, copy)]
    if problems:
        for _, kind, path in problems:
            print(f"  {kind:<9} {path}")
        bad = sorted({c for c, _, _ in problems})
        print(f"\n✗ {len(bad)} cópia(s) divergem de {SOURCE}: {', '.join(bad)}")
        print(f"  A origem é {SOURCE}. Rode `python3 bin/gen-vendor.py --write`;")
        print("  editar uma cópia direto não propaga.")
        return 1
    print(f"✓ as {len(COPIES)} cópias são idênticas a {SOURCE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
