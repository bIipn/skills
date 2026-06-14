"""Tests for the Telegram notifier (no network)."""
from backend.notifier import TelegramNotifier, format_trade


def test_disabled_when_unconfigured():
    assert TelegramNotifier("", "").enabled is False
    assert TelegramNotifier("token", "").enabled is False
    assert TelegramNotifier("", "chat").enabled is False
    assert TelegramNotifier("token", "chat").enabled is True


def test_notify_noop_when_disabled():
    n = TelegramNotifier("", "")
    # Must not raise and must not attempt any send.
    n.notify("hello")
    n.notify_error("boom")


def test_error_throttle():
    sent = []
    n = TelegramNotifier("t", "c")
    n._send_sync = lambda text: sent.append(text)  # stub network
    n.notify_error("first")
    n.notify_error("second (throttled)")
    assert len(sent) == 1
    assert "first" in sent[0]


def test_format_trade_profit_and_loss():
    win = format_trade({"kind": "single_condition", "realized_profit": 12.5,
                        "realized_cost": 40.0, "description": "X", "note": "clean"})
    assert "single condition" in win
    assert "+$12.50" in win
    assert "🟢" in win

    loss = format_trade({"kind": "combinatorial", "realized_profit": -3.0,
                         "realized_cost": 10.0, "description": "Y", "note": "slip"})
    assert "-$3.00" in loss
    assert "🔴" in loss
