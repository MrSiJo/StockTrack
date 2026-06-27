"""Unit tests for forbid_environment_ips.py (dependency-free, stdlib only)."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# Add scripts/ to the path so we can import the module directly.
sys.path.insert(0, str(Path(__file__).parent))
from forbid_environment_ips import _RFC1918, main, scan_file


# ── regex unit tests ──────────────────────────────────────────────────────────

class TestRfc1918Regex:
    def _matches(self, text: str) -> bool:
        return bool(_RFC1918.search(text))

    # 192.168.x.x
    def test_flags_192_168(self):
        assert self._matches("192.168.1.1")

    def test_flags_192_168_broadcast(self):
        assert self._matches("192.168.255.255")

    # 10.x.x.x
    def test_flags_10_block(self):
        assert self._matches("10.0.0.1")

    def test_flags_10_block_high(self):
        assert self._matches("10.255.255.255")

    # 172.16–31.x.x
    def test_flags_172_16(self):
        assert self._matches("172.16.0.1")

    def test_flags_172_31(self):
        assert self._matches("172.31.255.255")

    # NOT private
    def test_does_not_flag_public_ip(self):
        assert not self._matches("1.2.3.4")

    def test_does_not_flag_172_15(self):
        assert not self._matches("172.15.0.1")

    def test_does_not_flag_172_32(self):
        assert not self._matches("172.32.0.1")

    def test_does_not_flag_version_string(self):
        # "apscheduler==3.10.*" must not be flagged
        assert not self._matches("apscheduler==3.10.*")

    def test_does_not_flag_windows_nt_10(self):
        # User-agent string – "Windows NT 10.0" must not be flagged
        assert not self._matches(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

    def test_does_not_flag_ao_url(self):
        assert not self._matches("https://ao.com/list/some-product")

    def test_does_not_flag_johnlewis_url(self):
        assert not self._matches("https://www.johnlewis.com/search")


# ── scan_file tests ───────────────────────────────────────────────────────────

class TestScanFile:
    def test_flags_private_ip_in_file(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text('GOTIFY_URL = "http://192.168.1.100:8080"\n', encoding="utf-8")
        violations = scan_file(f)
        assert len(violations) == 1
        assert violations[0][0] == 1  # line 1

    def test_passes_public_retailer_url(self, tmp_path):
        f = tmp_path / "sites.py"
        f.write_text('BASE_URL = "https://ao.com"\n', encoding="utf-8")
        assert scan_file(f) == []

    def test_skips_binary_extension(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"192.168.1.1")  # raw bytes
        assert scan_file(f) == []

    def test_multiple_violations_different_lines(self, tmp_path):
        f = tmp_path / "bad.txt"
        f.write_text("host1 = 10.0.0.1\nhost2 = 192.168.1.1\n", encoding="utf-8")
        violations = scan_file(f)
        assert len(violations) == 2
        assert violations[0][0] == 1
        assert violations[1][0] == 2


# ── main() integration tests ──────────────────────────────────────────────────

class TestMain:
    def test_exits_0_for_clean_file(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text('URL = "https://ao.com"\n', encoding="utf-8")
        assert main([str(f)]) == 0

    def test_exits_1_for_file_with_rfc1918(self, tmp_path):
        f = tmp_path / "bad.env"
        f.write_text("GOTIFY_URL=http://192.168.1.1:8080\n", encoding="utf-8")
        assert main([str(f)]) == 1

    def test_exits_0_for_empty_args(self):
        assert main([]) == 0

    def test_exits_1_if_any_file_has_ip(self, tmp_path):
        good = tmp_path / "good.py"
        good.write_text("pass\n", encoding="utf-8")
        bad = tmp_path / "bad.py"
        bad.write_text("HOST = '10.0.1.5'\n", encoding="utf-8")
        assert main([str(good), str(bad)]) == 1
