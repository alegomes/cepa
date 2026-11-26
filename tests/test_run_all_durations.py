#!/usr/bin/env python3
"""tests/run-all.sh records how long each file took and names the slowest.

Run reforma-de-nomes/2026-11-25-2108 spent 393 of 495 min in the full suite
with no way to tell which file weighs. Contract guarded here:

  - each file's line ends with its duration, "(Ns)";
  - the summary has a "mais lentos:" block, slowest first, at most 10 lines;
  - the "  - tests/x.py" lines under "com falha:" stay exactly as before,
    because cepa-run reads them to repeat only the failed files.

No third-party deps — run with `python3 tests/test_run_all_durations.py`.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate  # noqa: E402

isolate()

HERE = Path(__file__).resolve().parent
failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


SLOW = "import time\ntime.sleep(2)\nprint('ok')\n"
FAST = "print('ok')\n"
FAIL = "import sys\nprint('FAIL x')\nsys.exit(1)\n"


def run(files):
    with tempfile.TemporaryDirectory() as tmp:
        tests = Path(tmp) / "tests"
        tests.mkdir()
        for f in ("run-all.sh", "_run_with_timeout.py"):
            shutil.copy(HERE / f, tests / f)
        for name, body in files.items():
            (tests / name).write_text(body)
        env = dict(os.environ, SKIP_PYTEST="1")
        r = subprocess.run(["bash", str(tests / "run-all.sh")], env=env,
                           capture_output=True, text=True, timeout=120)
        return r.stdout + r.stderr, r.returncode


def main():
    files = {f"test_f{i:02d}.py": FAST for i in range(11)}
    files["test_slow.py"] = SLOW
    files["test_broken.py"] = FAIL
    out, rc = run(files)
    lines = out.splitlines()

    check("ok line carries its duration",
          any(re.search(r"ok +tests/test_slow\.py +\((\d+)s\)$", l) for l in lines), out)
    check("FALHA line carries its duration",
          any(re.search(r"FALHA +tests/test_broken\.py .*\((\d+)s\)$", l) for l in lines), out)

    if "mais lentos:" in lines:
        i = lines.index("mais lentos:")
        block = []
        for l in lines[i + 1:]:
            m = re.match(r"^ +(\d+)s +(tests/\S+)$", l)
            if not m:
                break
            block.append((int(m.group(1)), m.group(2)))
    else:
        block = []
    check("summary has a 'mais lentos:' block", bool(block), out)
    check("block lists at most 10 files", 0 < len(block) <= 10, str(block))
    check("slowest file comes first",
          bool(block) and block[0][1] == "tests/test_slow.py" and block[0][0] >= 2, str(block))
    check("block is sorted slowest first",
          [s for s, _ in block] == sorted((s for s, _ in block), reverse=True), str(block))

    check("exit is 1 with a failure", rc == 1, f"rc={rc}")
    check("failure summary line is unchanged", "  - tests/test_broken.py" in lines, out)
    check("failure summary has no duration suffix",
          not any(l.startswith("  - ") and l.endswith("s)") for l in lines), out)

    out, rc = run({"test_one.py": FAST})
    check("green run still ends with 'tudo verde'",
          rc == 0 and out.rstrip().endswith("tudo verde"), out)

    print(f"\n{'FAIL' if failures else 'ok'}: {len(failures)} falha(s)")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
