#!/usr/bin/env python3
"""
forbid_environment_ips.py — pre-commit hook

Rejects any staged file that contains an RFC1918 LAN IP literal:
  10.0.0.0/8        (10.x.x.x)
  172.16.0.0/12     (172.16.x.x – 172.31.x.x)
  192.168.0.0/16    (192.168.x.x)

Public retailer URLs (ao.com, johnlewis.com, …) contain no such literals and
are therefore always allowed.  Localhost (127.x.x.x) is NOT checked; use
gitleaks for credential scanning.

Exit 0 = clean.  Exit 1 = at least one violation found (filenames + lines
printed to stderr so pre-commit surfaces them).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Compiled RFC1918 pattern – matches only full dotted-quad octets so we don't
# flag "10." inside version strings like "apscheduler==3.10.*".
_RFC1918 = re.compile(
    r"""
    (?<!\d)          # not preceded by a digit
    (?:
        10\.
        (?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.
        (?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.
        (?:25[0-5]|2[0-4]\d|[01]?\d\d?)
    |
        172\.
        (?:1[6-9]|2\d|3[01])\.
        (?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.
        (?:25[0-5]|2[0-4]\d|[01]?\d\d?)
    |
        192\.168\.
        (?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.
        (?:25[0-5]|2[0-4]\d|[01]?\d\d?)
    )
    (?!\d)           # not followed by a digit
    """,
    re.VERBOSE,
)

# File extensions we skip entirely (binary / lock files where a match would be
# a false positive and the content isn't human-authored).
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2",
                  ".ttf", ".eot", ".pdf", ".zip", ".gz", ".db"}


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, line_content) for every violating line."""
    if path.suffix.lower() in _SKIP_SUFFIXES:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return []
    violations: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _RFC1918.search(line):
            violations.append((lineno, line.rstrip()))
    return violations


def main(argv: list[str]) -> int:
    files = argv  # pre-commit passes staged file paths as positional args
    found_any = False
    for filename in files:
        path = Path(filename)
        violations = scan_file(path)
        if violations:
            found_any = True
            for lineno, line in violations:
                print(f"{filename}:{lineno}: RFC1918 IP found → {line}",
                      file=sys.stderr)
    return 1 if found_any else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
