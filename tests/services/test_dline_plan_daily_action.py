from vaxstock.services import daily_action, dline_plan


def test_worker_does_not_send_action_email(monkeypatch):
    def unexpected(**kw):
        raise AssertionError("Daily action must remain retired")
    monkeypatch.setattr(daily_action, "refresh_and_send_daily_action", unexpected)
    for status in ("done", "partial_done", "partial_failed", "missing_payload", "no_job"):
        monkeypatch.setattr(dline_plan, "run_observation_job", lambda: {"status": status})
        assert dline_plan.main() == 0
