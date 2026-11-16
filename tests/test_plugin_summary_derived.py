#!/usr/bin/env python3
"""The plugin list humans see is derived from marketplace.json, not hardcoded.

The pain: the installer's final summary hardcoded 11 plugins and docs/getting-started.md
listed 10, while marketplace.json had 12 (compass missing from both, marketing from the
doc). Both now come from bin/plugin-summary.py, which reads marketplace.json.

Run: python3 tests/test_plugin_summary_derived.py   (or pytest)
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "bin" / "plugin-summary.py"
INSTALL = REPO / "bin" / "install.sh"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
DOC = REPO / "docs" / "getting-started.md"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60)


def names():
    return [p["name"] for p in json.loads(MARKETPLACE.read_text())["plugins"]]


def with_fake_plugin(tmp):
    data = json.loads(MARKETPLACE.read_text())
    data["plugins"].append({"name": "zz-fake-plugin", "source": "./zz", "description": "Fake. Second sentence."})
    path = Path(tmp) / "marketplace.json"
    path.write_text(json.dumps(data))
    return path


def test_summary_lists_exactly_marketplace_names_in_order():
    r = run()
    assert r.returncode == 0, r.stderr
    got = [line.split()[0] for line in r.stdout.splitlines()]
    assert got == names(), got


def test_summary_follows_marketplace_json():
    with tempfile.TemporaryDirectory() as tmp:
        r = run("--marketplace", str(with_fake_plugin(tmp)))
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[-1].split()[0] == "zz-fake-plugin" and "— Fake" in lines[-1], lines[-1]
    assert "Second sentence" not in r.stdout


def test_installer_has_no_hardcoded_summary_and_calls_the_script():
    src = INSTALL.read_text()
    assert "plugin-summary.py" in src
    for n in names():
        assert not re.search(rf'echo\s+"\s+{re.escape(n)}\s+—', src), f"hardcoded summary line for {n}"


def test_installer_summary_block_executed_lists_the_marketplace():
    """Run the installer's own summary block (not install.sh itself) against a temp marketplace."""
    lines = INSTALL.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == 'echo "Plugins installed:"')
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == 'echo ""')
    snippet = "set -e\n" + "\n".join(lines[start:end]) + "\n"
    with tempfile.TemporaryDirectory() as tmp:
        market = with_fake_plugin(tmp)
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "REPO_DIR": str(REPO), "MARKETPLACE_JSON": str(market)}
        r = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, timeout=60, env=env)
        expected = [p["name"] for p in json.loads(market.read_text())["plugins"]]
    assert r.returncode == 0, r.stderr
    out = r.stdout.splitlines()
    assert out and out[0] == "Plugins installed:", out
    got = [l.split()[0] for l in out[1:] if l.strip()]
    assert got == expected and "zz-fake-plugin" in got, (got, r.stderr)


def test_getting_started_block_in_sync():
    r = run("--check", str(DOC))
    assert r.returncode == 0, r.stderr
    block = DOC.read_text().split("<!-- plugins:begin", 1)[1].split("<!-- plugins:end -->", 1)[0]
    assert re.findall(r"^\s+- `([^`]+)`", block, re.M) == names()


def test_check_goes_red_on_stale_copy():
    text = DOC.read_text()
    with tempfile.TemporaryDirectory() as tmp:
        stale = Path(tmp) / "getting-started.md"
        stale.write_text("\n".join(l for l in text.splitlines() if "`compass`" not in l) + "\n")
        r = run("--check", str(stale))
        assert r.returncode == 1 and "out of sync" in r.stderr, (r.returncode, r.stderr)
        assert run("--write", str(stale)).returncode == 0
        assert run("--check", str(stale)).returncode == 0
        # a fake plugin in the marketplace makes the (now fresh) doc stale again
        assert run("--check", str(stale), "--marketplace", str(with_fake_plugin(tmp))).returncode == 1


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}   {e}")
    sys.exit(1 if failed else 0)
