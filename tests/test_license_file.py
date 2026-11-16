#!/usr/bin/env python3
"""The repository root carries the standard, unmodified MIT License.

No third-party deps - run with `python3 tests/test_license_file.py`.

GitHub's license detector (and choosealicense.com) recognise the OSI text of
the MIT License. This test embeds that canonical text and checks that LICENSE:

  - exists at the repository root, named exactly `LICENSE`;
  - starts with the line `MIT License`;
  - has the copyright line `Copyright (c) 2026 Alexandre Gomes`;
  - has a body that, whitespace-normalized, equals the canonical text, so a
    truncated or edited paragraph turns this red.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LICENSE = REPO / "LICENSE"

COPYRIGHT = "Copyright (c) 2026 Alexandre Gomes"

CANONICAL_BODY = """\
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {str(detail)[-400:]}")
        FAILURES.append(name)


def norm(text):
    return " ".join(text.split())


def main():
    exists = LICENSE.is_file()
    check("LICENSE exists at the repo root", exists, str(LICENSE))
    if not exists:
        print()
        print(f"{len(FAILURES)} failure(s)")
        return 1

    text = LICENSE.read_text(encoding="utf-8")
    lines = text.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]

    check("first non-empty line is `MIT License`",
          bool(non_empty) and non_empty[0].strip() == "MIT License", non_empty[:1])
    check("copyright line is exact", COPYRIGHT in [ln.strip() for ln in lines]
          and sum(ln.startswith("Copyright") for ln in lines) == 1, lines[:5])

    rest = [ln for ln in non_empty[1:] if ln.strip() != COPYRIGHT]
    check("body equals the canonical MIT text (whitespace-normalized)",
          norm("\n".join(rest)) == norm(CANONICAL_BODY), norm("\n".join(rest)))
    check("ends with a single trailing newline",
          text.endswith("\n") and not text.endswith("\n\n"), repr(text[-20:]))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
