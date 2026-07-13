# -*- coding: utf-8 -*-

from vaxstock.services import daily_action, dline_plan


def test_dline_terminal_status_sends_normal_or_degraded_daily_action():
    saved_run = dline_plan.run_observation_job
    saved_send = daily_action.refresh_and_send_daily_action
    calls = []
    try:
        daily_action.refresh_and_send_daily_action = lambda **kwargs: (
            calls.append(kwargs) or {"action": {"status": "written"}, "mail": {"status": "sent"}}
        )

        dline_plan.run_observation_job = lambda: {
            "status": "done", "target_trade_date": "20260713"
        }
        assert dline_plan.main() == 0
        assert calls == [{"target_trade_date": "20260713", "degraded": False}]

        calls.clear()
        for status in ("partial_done", "partial_failed", "missing_payload"):
            dline_plan.run_observation_job = lambda status=status: {
                "status": status, "target_trade_date": "20260713"
            }
            assert dline_plan.main() == 0
        assert calls == [
            {"target_trade_date": "20260713", "degraded": True},
            {"target_trade_date": "20260713", "degraded": True},
            {"target_trade_date": "20260713", "degraded": True},
        ]

        calls.clear()
        dline_plan.run_observation_job = lambda: {"status": "no_job"}
        assert dline_plan.main() == 0
        assert calls == []
    finally:
        dline_plan.run_observation_job = saved_run
        daily_action.refresh_and_send_daily_action = saved_send