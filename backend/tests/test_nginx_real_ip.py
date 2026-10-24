"""The UI container's nginx real IP handling (frontend/docker-entrypoint.d).

Behind the HTTPS reverse proxy every request reaches the UI nginx from the
proxy's address, so without real IP handling the API's rate limit keys every
browser to one bucket. REAL_IP_FROM lists the proxies whose appended
X-Forwarded-For entry nginx may trust; the entrypoint script turns it into
``set_real_ip_from`` lines. Addresses below are documentation ranges.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "frontend" / "docker-entrypoint.d" / "40-stocktrack-real-ip.sh"
NGINX_CONF = REPO / "frontend" / "nginx.conf"
SH = shutil.which("sh")

needs_sh = pytest.mark.skipif(SH is None, reason="needs a POSIX sh")


def _run(tmp_path, real_ip_from):
    out = tmp_path / "real-ip.conf"
    env = {k: v for k, v in os.environ.items() if k != "REAL_IP_FROM"}
    env["STOCKTRACK_REAL_IP_CONF"] = str(out)
    if real_ip_from is not None:
        env["REAL_IP_FROM"] = real_ip_from
    proc = subprocess.run([SH, str(SCRIPT)], env=env, capture_output=True, text=True,
                          check=False)
    return proc, out


def _directives(out: Path) -> list[str]:
    return [ln.strip() for ln in out.read_text().splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


@needs_sh
def test_unset_writes_an_empty_snippet(tmp_path):
    proc, out = _run(tmp_path, None)
    assert proc.returncode == 0, proc.stderr
    assert _directives(out) == []


@needs_sh
def test_blank_writes_an_empty_snippet(tmp_path):
    proc, out = _run(tmp_path, "   ")
    assert proc.returncode == 0, proc.stderr
    assert _directives(out) == []


@needs_sh
def test_each_entry_becomes_a_trusted_proxy(tmp_path):
    proc, out = _run(tmp_path, "203.0.113.0/24  198.51.100.7 2001:db8::/32")
    assert proc.returncode == 0, proc.stderr
    assert _directives(out) == [
        "set_real_ip_from 203.0.113.0/24;",
        "set_real_ip_from 198.51.100.7;",
        "set_real_ip_from 2001:db8::/32;",
        "real_ip_header X-Forwarded-For;",
        # Off: only the entry the trusted proxy appended (the right most) is
        # used, never anything further left that the client could forge.
        "real_ip_recursive off;",
    ]


@needs_sh
@pytest.mark.parametrize("bad", ["203.0.113.0/24;evil", "all", "$(id)", "a b;c"])
def test_rejects_anything_but_addresses(tmp_path, bad):
    proc, _ = _run(tmp_path, bad)
    assert proc.returncode != 0
    assert "REAL_IP_FROM" in proc.stderr


def test_server_block_includes_the_snippet():
    conf = NGINX_CONF.read_text(encoding="utf-8")
    # A glob include: a missing file (nginx run without the entrypoint) is fine.
    assert re.search(r"^\s*include /etc/nginx/stocktrack/\*\.conf;", conf, re.M)


def test_the_script_writes_where_nginx_includes():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "/etc/nginx/stocktrack/real-ip.conf" in script


def test_dockerfile_installs_the_entrypoint_script():
    dockerfile = (REPO / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "docker-entrypoint.d/40-stocktrack-real-ip.sh" in dockerfile


def test_compose_passes_real_ip_from_to_the_ui():
    compose = (REPO / "compose.yaml").read_text(encoding="utf-8")
    ui = compose.split("stocktrack-ui:", 1)[1]
    assert "REAL_IP_FROM" in ui
