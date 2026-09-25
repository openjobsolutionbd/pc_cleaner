"""
test_no_network_guarantee.py
-----------------------------
This app is intentionally offline-only: it never sends any data over
a network. That's currently true simply because no code happens to
import a networking library — but "currently true by accident" is a
much weaker guarantee than "enforced by a test that fails the moment
someone adds one".

This test scans every non-test .py source file in the project and
fails if it finds an import of any module capable of making a network
connection (sockets, HTTP clients, FTP, SMTP, etc.). If a future
feature genuinely needs network access, this test will fail loudly
and the person reviewing the change will have to consciously update
this file — which is the point: it turns "no network access" from an
unstated assumption into something that has to be deliberately
overridden, not silently regressed.

Run with: python -m unittest test_no_network_guarantee.py -v
"""

import ast
import os
import unittest

# Standard-library (and common third-party) modules that can open a
# network connection. Importing any of these anywhere in the app's
# source is exactly the regression this test exists to catch.
_NETWORK_MODULES = {
    "socket", "ssl",
    "urllib", "urllib2", "urllib3",
    "http", "http.client",
    "httplib",
    "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "poplib", "imaplib", "nntplib", "telnetlib",
    "xmlrpc", "xmlrpc.client",
    "asyncio",  # commonly used for network I/O; flag it too so it gets a deliberate look
}

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _source_files():
    """Every .py file in the project root, excluding test_*.py files
    (this file included) and anything under a virtual-env-style or
    build folder if present.
    """
    for name in sorted(os.listdir(_PROJECT_DIR)):
        if not name.endswith(".py"):
            continue
        if name.startswith("test_"):
            continue
        yield os.path.join(_PROJECT_DIR, name)


def _imported_module_names(filepath: str) -> set:
    """Parses a .py file with ast (not by executing it) and returns the
    set of top-level module names it imports, e.g. "os.path" -> "os".
    """
    with open(filepath, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=filepath)

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


class TestNoNetworkImports(unittest.TestCase):
    def test_no_source_file_imports_a_networking_module(self):
        offenders = {}
        for filepath in _source_files():
            found = _imported_module_names(filepath) & _NETWORK_MODULES
            if found:
                offenders[os.path.basename(filepath)] = found

        self.assertFalse(
            offenders,
            "This app is meant to be 100% offline. Found networking-capable "
            f"imports in: {offenders}. If this is intentional, it needs a "
            "deliberate decision (and this test updated), not a silent change."
        )

    def test_at_least_one_source_file_was_actually_scanned(self):
        # Guards against this test silently passing because _source_files()
        # found nothing (e.g. run from the wrong working directory).
        self.assertGreater(len(list(_source_files())), 0)


if __name__ == "__main__":
    unittest.main()
