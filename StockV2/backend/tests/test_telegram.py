from unittest.mock import MagicMock, patch
from datetime import date


def test_send_returns_false_when_not_configured():
    from domains.alerts.telegram import AlertService
    svc = AlertService()
    svc._token = ""
    svc._chat_id = ""
    assert svc.send("hello") is False


def test_send_returns_true_on_200():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 200

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response):
        result = svc.send("test message")
    assert result is True


def test_send_returns_false_on_non_200():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response):
        result = svc.send("test message")
    assert result is False


def test_send_returns_false_on_exception():
    from domains.alerts.telegram import AlertService
    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", side_effect=Exception("network error")):
        result = svc.send("test message")
    assert result is False


def test_send_daily_digest_formats_signals():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 200

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    signals = [
        {"symbol": "TCS", "confidence_score": 0.82, "strategy_name": "RSI Oversold/Overbought"},
        {"symbol": "INFY", "confidence_score": 0.71, "strategy_name": "MACD Crossover"},
    ]

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response) as mock_post:
        result = svc.send_daily_digest(signals, scan_date=date(2026, 8, 10))
    assert result is True
    call_args = mock_post.call_args
    sent_text = call_args[1]["json"]["text"]
    assert "TCS" in sent_text
    assert "82%" in sent_text
    assert "10 Aug 2026" in sent_text


def test_send_daily_digest_no_signals():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 200

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response) as mock_post:
        svc.send_daily_digest([])
    sent_text = mock_post.call_args[1]["json"]["text"]
    assert "No high-confidence" in sent_text
