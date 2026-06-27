from unittest.mock import patch, MagicMock
from stocktrack.services.gotify import send

CFG = {"url": "https://gotify.example", "token": "tok", "retries": 3}

def _mock_resp(status=200):
    r = MagicMock()
    r.status_code = status
    return r

def test_send_success():
    with patch("httpx.post", return_value=_mock_resp(200)) as mock:
        assert send(CFG, "title", "msg") is True
        mock.assert_called_once()

def test_send_4xx_no_retry():
    """4xx: exactly one attempt then False — a bad token won't fix itself."""
    with patch("httpx.post", return_value=_mock_resp(401)) as mock:
        assert send(CFG, "title", "msg", sleep=0) is False
        assert mock.call_count == 1

def test_send_5xx_retries_and_fails():
    """5xx: retries exactly cfg['retries'] times then returns False."""
    with patch("httpx.post", return_value=_mock_resp(503)) as mock:
        assert send(CFG, "title", "msg", sleep=0) is False
        assert mock.call_count == CFG["retries"]

def test_send_no_config_returns_true():
    assert send({}, "title", "msg") is True

def test_send_click_url():
    with patch("httpx.post", return_value=_mock_resp(200)) as mock:
        send(CFG, "t", "m", click_url="https://example.com", markdown=True)
        payload = mock.call_args.kwargs["json"]
        assert payload["extras"]["client::notification"]["click"]["url"] == "https://example.com"
        assert payload["extras"]["client::display"]["contentType"] == "text/markdown"
