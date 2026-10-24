"""Plugin loader: built in discovery, plugin dir, replacement, skips, report."""
import sys
import textwrap

import pytest

from stocktrack import sites

PLUGIN_OK = """
from .base import Product, SiteHandler

PLUGIN_API = 1

class ShopHandler(SiteHandler):
    name = "{name}"
    kind = "listing"
    def fetch(self, url):
        return ""
    def parse(self, raw):
        return [Product(code="X1", title="{title}", in_stock=True)]

handler = ShopHandler()
HANDLERS = [handler]
"""


@pytest.fixture
def plugin_dir(tmp_path):
    """Yield a plugins dir; restore the built in registry afterwards."""
    yield tmp_path
    sites.load_registry(None)


def _write(d, filename, body):
    (d / filename).write_text(textwrap.dedent(body), encoding="utf-8")


def _report(module):
    return {m["module"]: m for m in sites.plugin_report()["modules"]}[module]


def test_builtins_follow_the_contract():
    for mod in (sites.ao, sites.johnlewis, sites.cityplumbing):
        assert mod.PLUGIN_API == 1
        assert mod.HANDLERS
    assert ("ao", "product") in {(h.name, h.kind) for h in sites.ao.HANDLERS}


def test_no_plugins_dir_means_builtins_only():
    sites.load_registry(None)
    report = sites.plugin_report()
    assert report["plugins_dir"] is False
    assert report["plugin_api"] == sites.PLUGIN_API
    assert {m["source"] for m in report["modules"]} == {"builtin"}
    assert {m["status"] for m in report["modules"]} == {"loaded"}
    assert sites.available() == ["ao", "cityplumbing", "johnlewis"]


def test_new_plugin_adds_a_store(plugin_dir):
    _write(plugin_dir, "shop.py", PLUGIN_OK.format(name="shop", title="Shop item"))
    sites.load_registry(plugin_dir)
    assert "shop" in sites.available()
    assert sites.get_handler("shop").parse("")[0].title == "Shop item"
    assert sys.modules["stocktrack.sites.shop"].PLUGIN_API == 1
    entry = _report("shop")
    assert entry["source"] == "plugin" and entry["status"] == "loaded"
    assert entry["handlers"] == ["shop/listing"]


def test_plugin_with_builtin_stem_replaces_the_module(plugin_dir):
    original = sites.ao
    _write(plugin_dir, "ao.py", PLUGIN_OK.format(name="ao", title="Patched AO"))
    sites.load_registry(plugin_dir)
    from stocktrack.sites import ao  # what a test file in the plugins repo does
    assert ao is not original
    assert sys.modules["stocktrack.sites.ao"] is ao
    assert sites.get_handler("ao").parse("")[0].title == "Patched AO"
    # The whole module is replaced: the built in product handler goes with it.
    with pytest.raises(ValueError):
        sites.get_handler("ao", "product")
    assert _report("ao")["source"] == "plugin"
    builtin = [m for m in sites.plugin_report()["modules"]
               if m["module"] == "ao" and m["source"] == "builtin"]
    assert builtin[0]["status"] == "replaced"


def test_restoring_builtins_after_replacement(plugin_dir):
    original = sites.ao
    _write(plugin_dir, "ao.py", PLUGIN_OK.format(name="ao", title="Patched AO"))
    sites.load_registry(plugin_dir)
    sites.load_registry(None)
    assert sites.ao is original
    assert sys.modules["stocktrack.sites.ao"] is original
    assert sites.get_handler("ao", "product") is original.product_handler


def test_new_stem_overrides_an_existing_pair(plugin_dir):
    _write(plugin_dir, "zz_jl.py", PLUGIN_OK.format(name="johnlewis", title="JL v2"))
    sites.load_registry(plugin_dir)
    assert sites.get_handler("johnlewis").parse("")[0].title == "JL v2"


@pytest.mark.parametrize("body, needle", [
    ("raise RuntimeError('boom')", "boom"),
    ("HANDLERS = []", "PLUGIN_API"),
    ("PLUGIN_API = 1", "HANDLERS"),
    ("PLUGIN_API = 99\nHANDLERS = []", "99"),
    ("PLUGIN_API = 1\nHANDLERS = ['not a handler']", "SiteHandler"),
])
def test_bad_plugin_is_skipped_and_reported(plugin_dir, body, needle):
    _write(plugin_dir, "bad.py", body)
    sites.load_registry(plugin_dir)
    entry = _report("bad")
    assert entry["status"] == "skipped"
    assert needle in entry["error"]
    assert "bad" not in sys.modules.get("stocktrack.sites", sites).__dict__
    assert "stocktrack.sites.bad" not in sys.modules
    assert sites.skipped_plugins() == [entry]


def test_bad_replacement_keeps_the_builtin(plugin_dir):
    original = sites.ao
    _write(plugin_dir, "ao.py", "raise ImportError('broken fix')")
    sites.load_registry(plugin_dir)
    assert sites.ao is original
    assert sys.modules["stocktrack.sites.ao"] is original
    assert sites.get_handler("ao", "product") is original.product_handler
    statuses = {(m["source"], m["status"]) for m in sites.plugin_report()["modules"]
                if m["module"] == "ao"}
    assert statuses == {("builtin", "loaded"), ("plugin", "skipped")}


def test_package_plugins_and_ignored_files(plugin_dir):
    pkg = plugin_dir / "pkgshop"
    pkg.mkdir()
    # Inside a package, ".base" is the package's own module: import absolutely.
    body = PLUGIN_OK.format(name="pkgshop", title="Pkg").replace(
        "from .base", "from stocktrack.sites.base")
    _write(pkg, "__init__.py", body)
    _write(plugin_dir, "_private.py", "raise RuntimeError('must not load')")
    (plugin_dir / "notes.txt").write_text("ignored", encoding="utf-8")
    (plugin_dir / "emptydir").mkdir()
    sites.load_registry(plugin_dir)
    assert "pkgshop" in sites.available()
    modules = {m["module"] for m in sites.plugin_report()["modules"]}
    assert "_private" not in modules and "emptydir" not in modules


def test_missing_plugins_dir_is_reported_not_fatal(tmp_path):
    try:
        sites.load_registry(tmp_path / "nope")
        report = sites.plugin_report()
        assert report["plugins_dir"] is True
        assert report["plugins_dir_error"]
        assert "ao" in sites.available()
    finally:
        sites.load_registry(None)


def test_env_var_is_read_at_import(monkeypatch, plugin_dir):
    _write(plugin_dir, "shop.py", PLUGIN_OK.format(name="shop", title="Env"))
    monkeypatch.setenv("STOCKTRACK_PLUGINS_DIR", str(plugin_dir))
    sites.load_registry(sites.plugins_dir_from_env())
    assert "shop" in sites.available()
    monkeypatch.setenv("STOCKTRACK_PLUGINS_DIR", "")
    assert sites.plugins_dir_from_env() is None
