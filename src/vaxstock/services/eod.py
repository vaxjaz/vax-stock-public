"""Daily macro email and replaceable inputs for the intraday planner.

No daily reports, research ledgers, factor/result accumulation or evaluation.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from vaxstock import config
from vaxstock.analysis.freshness import assess_eod_freshness
from vaxstock.report.claude_md import compact_for_claude
from vaxstock.report.macro_email import build_macro_email
from vaxstock.services.collect import collect_payload
from vaxstock.services.eod_predictor import predictions_from_payload
from vaxstock.services.forecast_planner import enqueue_observation_job, _write_json
from vaxstock.services.macro_mail import send_macro_email
from vaxstock.sources.tushare_src import TushareSource

logger = logging.getLogger(__name__)


def run_eod() -> dict:
    source = TushareSource(config.SECRETS.get("tushare_token"))
    payload, tracks = collect_payload(source)
    baseline = str((payload.get("market_overview") or {}).get("trade_date") or "").strip()
    if len(baseline) != 8 or not baseline.isdigit():
        raise ValueError("market_overview.trade_date missing/invalid; no daily state or email written")
    freshness = assess_eod_freshness(payload)
    payload["freshness"] = freshness
    # Only the latest inputs survive. Individual metrics remain necessary for
    # next-day trigger generation and yesterday's baseline in intraday alerts.
    runtime = config.STATE_DIR / "eod"
    payload_path = runtime / "current_payload.json"
    baseline_path = runtime / "current_baseline.json"
    _write_json(payload_path, payload)
    _write_json(baseline_path, compact_for_claude(payload))
    try:
        target = _next_trade_date(source, baseline)
        if target and freshness.get("forecast_eligible"):
            allowed = set(freshness.get("eligible_codes") or [])
            eligible = dict(payload)
            eligible["stocks"] = [s for s in payload.get("stocks", []) if s.get("code") in allowed]
            # C context is computed in memory only; no prediction/result history.
            predictions = predictions_from_payload(eligible, target, generation_mode="live")
            enqueue_observation_job(
                payload_path, target, baseline_trade_date=baseline,
                c_predictions=predictions, task_codes=allowed, current_only=True,
            )
        else:
            # Prevent the worker from retrying yesterday's job on missing/stale data.
            from vaxstock.services.forecast_planner import CURRENT_OBSERVATION_JOB_FILE, CURRENT_TASKS_FILE
            _write_json(CURRENT_OBSERVATION_JOB_FILE, {})
            _write_json(CURRENT_TASKS_FILE, {"tasks": [], "target_trade_dates": []})
            logger.warning("Intraday planning skipped: calendar/freshness unavailable")
    except Exception:
        logger.exception("Intraday planning failed; macro delivery continues")
        from vaxstock.services.forecast_planner import CURRENT_OBSERVATION_JOB_FILE, CURRENT_TASKS_FILE
        _write_json(CURRENT_OBSERVATION_JOB_FILE, {})
        _write_json(CURRENT_TASKS_FILE, {"tasks": [], "target_trade_dates": []})
    body = build_macro_email(payload, tracks)
    try:
        mail = send_macro_email(trade_date=baseline, body=body)
    except Exception:
        logger.exception("Macro email failed; current intraday inputs remain available")
        mail = {"status": "failed", "sent": False}
    return {"payload": str(payload_path), "baseline": str(baseline_path), "mail": mail}


def _next_trade_date(source, baseline_trade_date, lookahead_days: int = 15) -> Optional[str]:
    """用 Tushare trade_cal 查 baseline 后的下一开市日(YYYYMMDD)。

    P0: target_trade_date 必须来自交易日历实测数据; source 不可用/字段缺失/查不到时返回 None,
    上层跳过 live prediction, 绝不按自然日臆造。
    """
    baseline = str(baseline_trade_date or "").strip()
    if not baseline:
        return None
    try:
        start = (datetime.strptime(baseline, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        end = (datetime.strptime(baseline, "%Y%m%d") + timedelta(days=lookahead_days)).strftime("%Y%m%d")
    except ValueError:
        logger.warning(f"EOD Prediction: baseline_trade_date 非 YYYYMMDD, 跳过 live prediction: {baseline!r}")
        return None

    safe_call = getattr(source, "_safe_call", None)
    if safe_call is None:
        logger.warning("EOD Prediction: Tushare source 不可用, 无法确认下一交易日, 跳过 live prediction")
        return None

    df = safe_call("trade_cal", exchange="", start_date=start, end_date=end)
    if df is None:
        logger.warning("EOD Prediction: trade_cal 返回空, 无法确认下一交易日, 跳过 live prediction")
        return None
    cols = set(getattr(df, "columns", []))
    if not {"cal_date", "is_open"}.issubset(cols):
        logger.warning(f"EOD Prediction: trade_cal 字段缺失({sorted(cols)}), 跳过 live prediction")
        return None

    try:
        records = df.sort_values("cal_date", ascending=True).to_dict("records")
    except Exception as e:
        logger.warning(f"EOD Prediction: trade_cal 解析失败, 跳过 live prediction: {str(e)[:80]}")
        return None

    for row in records:
        cal_date = str(row.get("cal_date") or "").strip()
        try:
            is_open = int(float(row.get("is_open")))
        except (TypeError, ValueError):
            is_open = 0
        if cal_date > baseline and is_open == 1:
            return cal_date
    logger.warning(f"EOD Prediction: {baseline} 后 {lookahead_days} 日内无开市日, 跳过 live prediction")
    return None



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    run_eod()
