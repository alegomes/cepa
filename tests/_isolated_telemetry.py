"""Sends a test's telemetry to a disposable ledger, never to the real one.

The defect (measured on 2026-08-26 by `/common:metrics` itself): the hooks write
events to `~/.claude/cepa-telemetry/` and the suite executes those same hooks. Only
3 of the 53 test files defined `CEPA_TELEMETRY_DIR`; another 7 executed an
emitting hook without isolating it and wrote to the real ledger, the file that
`/common:metrics` reads to say how the harness behaves in real use.

The damage is not volume (81 events per suite run), it is a wrong reading: the
2026-08-26 report listed repos that do not exist, `main-repo` with 206 green and
206 red (an exact tie is the signature of a fixture, not of work), plus
`r2`, `r3`, `r4`, `pert2`, `sem-git`. The two highest-volume lines of that
report's "Suggested readings" (`r3: 39 blocks`, `?: 310 proven artifacts
blocked`) were rehearsal, not use. A metric that mixes rehearsal with use
measures the rehearsal.

Usage, at the top of the test, before any subprocess:

    from _isolated_telemetry import isolate
    isolate()

The bare import works because `python3 tests/test_x.py` puts `tests/` at
sys.path[0]. A `tests/sitecustomize.py` was tried before, which would have caught
all 7 at once without touching any: it does not work, because the `site` module
imports `sitecustomize` at interpreter startup, BEFORE the script's directory
enters sys.path. The explicit call in each file is more tedious and is the one
that works, and it shows up when reading the test instead of acting at a distance.

Who else calls it: `tests/conftest.py` (pytest family) and `tests/run-all.sh`
(its own export, so the isolation is visible to whoever reads the runner).

Never overwrites a `CEPA_TELEMETRY_DIR` that is already set: several tests point
it at their own tmpdir and check what they wrote there.
"""

import os
import tempfile
from pathlib import Path

# Fixed path, not one mkdtemp per process: the suite runs dozens of processes and
# a new temp dir in each would fill /tmp with junk nobody looks at. Fixed, it can
# be inspected when a telemetry test fails.
NAME = "cepa-telemetry-tests"


def isolate() -> str:
    """Points CEPA_TELEMETRY_DIR at the disposable ledger, if nobody pointed it elsewhere.

    Returns the directory in use (the one already set, or the disposable one)."""
    already_set = os.environ.get("CEPA_TELEMETRY_DIR")
    if already_set:
        return already_set
    d = Path(tempfile.gettempdir()) / NAME
    os.environ["CEPA_TELEMETRY_DIR"] = str(d)
    return str(d)
