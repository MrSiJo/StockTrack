from unittest.mock import patch, MagicMock
from stocktrack.cli import main
from stocktrack.sites.base import Product as P


def _fake_handler(products):
    h = MagicMock()
    h.name = "ao"
    h.kind = "listing"
    h.fetch.return_value = "raw"
    h.parse.return_value = products
    return h


def test_cli_returns_parsed_count():
    handler = _fake_handler([P("A", "Meaco 12K", True, "Meaco", 519.0)])
    with patch("stocktrack.sites.get_handler", return_value=handler):
        result = main(["ao", "https://ao.com/test", "--include", "Meaco"])
    assert result["parsed"] == 1
    assert result["matched"] == 1
    assert result["products"][0]["code"] == "A"


def test_cli_exclude_filter():
    products = [
        P("A", "Meaco 12K", True, "Meaco", 519.0),
        P("B", "Meaco Heating", False, "Meaco", 299.0),
    ]
    handler = _fake_handler(products)
    with patch("stocktrack.sites.get_handler", return_value=handler):
        result = main(["ao", "https://ao.com/test", "--include", "Meaco", "--exclude", "Heating"])
    assert result["matched"] == 1
    assert result["products"][0]["code"] == "A"


def test_cli_json_output(capsys):
    handler = _fake_handler([P("A", "Meaco 12K", True, "Meaco", 519.0)])
    with patch("stocktrack.sites.get_handler", return_value=handler):
        main(["ao", "https://ao.com/test", "--json"])
    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out)
    assert data["store"] == "ao"
    assert data["parsed"] == 1
