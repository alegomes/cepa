"""One stderr line when a hook cannot load the plugin's vendored PyYAML copy
(docs/spec/cepa-roda-sem-pyyaml-instalado.md, CS-4).

Private helper, same pattern as `_jiramut.py`. A hook calls `warn(exc, module)`
from its `except ImportError` around `import yaml`, then does what it always
did there. This never changes an exit code and never raises. It warns once per
process (so a hook that also imports `_jiramut` or `_autonomy` prints one line),
and every run in that state warns again: no state on disk.

The hook is named by the entry script (`sys.argv[0]`), falling back to `module`
(the caller's file stem) when there is no script, e.g. `python3 -c`.
`lang="pt"` is for hooks whose messages are in Portuguese.
"""
import os
import sys

_warned = False


def warn(exc, module, lang="en"):
    global _warned
    try:
        if _warned:
            return
        _warned = True
        name = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0]
        if not name or name.startswith("-"):
            name = module
        vendor = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "_vendor", "yaml")
        why = " ".join(f"{type(exc).__name__}: {exc}".split())
        if lang == "pt":
            msg = (f"[{name}] não consegui carregar o PyYAML ({why}); esperava a cópia "
                   f"do plugin em {vendor}. Sigo o caminho de sempre.")
        else:
            msg = (f"[{name}] could not load PyYAML ({why}); expected the plugin's "
                   f"copy at {vendor}. Carrying on the way it always does.")
        print(msg, file=sys.stderr)
    except Exception:  # noqa: BLE001  a warning must never break a hook
        pass
