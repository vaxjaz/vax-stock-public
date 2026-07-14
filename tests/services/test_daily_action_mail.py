# -*- coding: utf-8 -*-

import json
import tempfile
from pathlib import Path

from vaxstock import config
from vaxstock.services.daily_action import (
    _strategy_output_paths, load_daily_strategy_row, send_close_review_email,
    send_daily_action_email,
)


def _action(degraded=False):
    return {
        "status": "written",
        "target_trade_date": "20260713",
        "degraded": degraded,
        "markdown": "# 20260713 每日操作清单\n",
    }


def _secrets():
    return {
        "email_enabled": True,
        "email_user": "sender@example.com",
        "email_authcode": "secret",
        "email_to": "receiver@example.com",
    }


def test_successful_daily_action_email_is_idempotent_per_target():
    saved = config.SECRETS
    calls = []
    try:
        config.SECRETS = _secrets()
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "mail_state.json"

            def _send(*args, **kwargs):
                calls.append((args, kwargs))
                return True

            first = send_daily_action_email(_action(), mail_state_path=state_path, send_func=_send)
            second = send_daily_action_email(_action(), mail_state_path=state_path, send_func=_send)
            state = json.loads(state_path.read_text(encoding="utf-8"))

        assert first["status"] == "sent"
        assert second["status"] == "already_sent"
        assert len(calls) == 1
        assert calls[0][1]["subject"] == "[每日操作] 20260713"
        assert state["sent_targets"]["20260713"]["mode"] == "normal"
    finally:
        config.SECRETS = saved


def test_failed_send_is_not_marked_and_degraded_subject_is_explicit():
    saved = config.SECRETS
    calls = []
    try:
        config.SECRETS = _secrets()
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "mail_state.json"

            def _fail(*args, **kwargs):
                calls.append(kwargs.get("subject"))
                return False

            failed = send_daily_action_email(
                _action(degraded=True), mail_state_path=state_path, send_func=_fail
            )
            assert failed["status"] == "failed"
            assert not state_path.exists()

            sent = send_daily_action_email(
                _action(degraded=True), mail_state_path=state_path,
                send_func=lambda *args, **kwargs: calls.append(kwargs.get("subject")) or True,
            )

        assert sent["status"] == "sent"
        assert calls == ["[每日操作-降级] 20260713", "[每日操作-降级] 20260713"]
    finally:
        config.SECRETS = saved


def test_missing_mail_config_does_not_create_sent_state():
    saved = config.SECRETS
    try:
        config.SECRETS = {"email_enabled": False}
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "mail_state.json"
            result = send_daily_action_email(_action(), mail_state_path=state_path)
            assert result["status"] == "disabled"
            assert not state_path.exists()
    finally:
        config.SECRETS = saved

def test_load_daily_strategy_row_requires_matching_target():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "daily_action_latest.json"
        path.write_text(json.dumps({
            "background": {"target_trade_date": "20260713"},
            "holdings": [{"code": "601138", "action": "持有，不加仓"}],
        }, ensure_ascii=False), encoding="utf-8")
        assert load_daily_strategy_row("601138", "20260713", plan_path=path)["action"] == "持有，不加仓"
        assert load_daily_strategy_row("601138", "20260714", plan_path=path) == {}

def test_close_review_mail_has_independent_idempotent_state():
    saved = config.SECRETS
    calls = []
    try:
        config.SECRETS = _secrets()
        with tempfile.TemporaryDirectory() as tmp:
            daily_state = Path(tmp) / "daily.json"
            close_state = Path(tmp) / "close.json"

            def _send(*args, **kwargs):
                calls.append(kwargs.get("subject"))
                return True

            daily = send_daily_action_email(
                _action(), mail_state_path=daily_state, send_func=_send,
            )
            close = send_close_review_email(
                _action(), mail_state_path=close_state, send_func=_send,
            )
            duplicate = send_close_review_email(
                _action(), mail_state_path=close_state, send_func=_send,
            )
            close_state_data = json.loads(close_state.read_text(encoding="utf-8"))

        assert daily["status"] == "sent"
        assert close["status"] == "sent"
        assert duplicate["status"] == "already_sent"
        assert calls == ["[每日操作] 20260713", "[收盘复盘] 20260713"]
        assert close_state_data["sent_targets"]["20260713"]["mode"] == "close_review"
    finally:
        config.SECRETS = saved

def test_close_review_fast_skips_before_regenerating_when_already_sent():
    from vaxstock.services import daily_action
    saved = daily_action.refresh_daily_action
    try:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "close.json"
            state_path.write_text(json.dumps({
                "sent_targets": {"20260713": {"mode": "close_review"}},
            }), encoding="utf-8")
            daily_action.refresh_daily_action = lambda **kwargs: (_ for _ in ()).throw(
                AssertionError("must not regenerate an already-sent close review")
            )
            result = daily_action.refresh_and_send_close_review(
                target_trade_date="20260713", mail_state_path=state_path,
                reference_quote_loader=lambda: (_ for _ in ()).throw(
                    AssertionError("must not fetch quotes after mail was sent")
                ),
            )
        assert result["action"]["status"] == "skipped_already_sent"
        assert result["mail"]["status"] == "already_sent"
    finally:
        daily_action.refresh_daily_action = saved

def test_close_review_output_paths_do_not_overwrite_premarket_files():
    out_dir = Path("strategy")
    daily = _strategy_output_paths(out_dir, "20260713", "pre_market")
    close = _strategy_output_paths(out_dir, "20260713", "close_review")
    assert daily[0].name == "daily_action_20260713.md"
    assert daily[1].name == "daily_action_latest.md"
    assert close[0].name == "close_review_20260713.md"
    assert close[1].name == "close_review_latest.md"
    assert set(daily).isdisjoint(close)
