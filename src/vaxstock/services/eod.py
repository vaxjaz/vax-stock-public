# -*- coding: utf-8 -*-
"""services 层: run_eod —— EOD 端到端串联编排器(可作模块入口供 cron/systemd 调)。

MR6 PR-B: 串 collect → compact → build → store，并排队异步 D-line。AITrack 超时不在本 PR;
api/intraday/cron unit 留 PR-C。

对接 main 真实签名(已核):
  TushareSource(token)                                          sources.tushare_src
  collect_payload(source) -> (payload, track_results)           services.collect
  compact_for_claude(payload) -> claude_data                    report.claude_md
  build_research_eod_markdown(claude_data, research=) -> str   report.research_eod
  store_report(payload, claude_data, markdown) -> {paths}       report.store

铁律: 顶层取数失败不吞(应可见); A/B/C 落盘后由 D-line worker 统一生成并发送每日操作邮件。
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from vaxstock import config
from vaxstock.analysis.eod_market import build_eod_market_analysis
from vaxstock.analysis.freshness import assess_eod_freshness
from vaxstock.research.legacy_snapshot_replay import record_legacy_snapshot_trade_date
from vaxstock.report.claude_md import compact_for_claude
from vaxstock.report.research_eod import (
    build_research_eod_markdown as build_claude_markdown,
)
from vaxstock.report.store import store_report
from vaxstock.services.collect import collect_payload
from vaxstock.services.curve_refresh import run_curve_refresh
from vaxstock.services.dline_closeout import run_dline_closeout
from vaxstock.services.evidence_convergence import run_evidence_convergence
from vaxstock.services.evidence_ledger import run_evidence_ledger
from vaxstock.services.eval_recorder import SNAPSHOTS_FILE, record_and_backfill
from vaxstock.services.eod_predictor import predictions_from_payload, record_predictions
from vaxstock.services.forecast_planner import enqueue_observation_job
from vaxstock.services.forecast_evaluation_refresh import (
    run_forecast_evaluation_refresh,
)
from vaxstock.services.forecast_refresh import run_forecast_refresh
from vaxstock.services.global_anchor_refresh import (
    run_global_anchor_refresh,
)
from vaxstock.services.group_refresh import run_group_refresh
from vaxstock.services.group_outcome_refresh import run_group_outcome_refresh
from vaxstock.services.prediction_evaluator import evaluate_from_files
from vaxstock.services.research_eod_mail import send_research_eod_email
from vaxstock.services.select_refresh import run_select_refresh
from vaxstock.services.anchor_forecast_refresh import (
    run_anchor_forecast_refresh,
)
from vaxstock.sources.tushare_src import TushareSource

logger = logging.getLogger(__name__)


def _load_historical_report_payloads(
    as_of_trade_date: str,
    *,
    limit: int = 30,
) -> list[Dict[str, Any]]:
    """Read prior immutable EOD payloads for derivative/change calculations."""

    target = str(as_of_trade_date or "").strip().replace("-", "")
    if len(target) != 8 or not target.isdigit():
        return []
    rows = []
    for path in sorted(config.REPORTS_DIR.glob("*/payload.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "EOD analyst context skips unreadable payload %s: %s",
                path,
                type(exc).__name__,
            )
            continue
        if not isinstance(value, dict):
            continue
        trade_date = str(
            ((value.get("market_overview") or {}).get("trade_date")) or ""
        ).strip().replace("-", "")
        if len(trade_date) == 8 and trade_date.isdigit() and trade_date < target:
            rows.append(value)
    return rows[-max(int(limit), 0):]


def run_eod() -> Dict[str, str]:
    """EOD: collect facts, refresh research, render new report, persist data."""
    logger.info("[1/7] 初始化 Tushare 数据源...")
    source = TushareSource(config.SECRETS.get("tushare_token"))

    logger.info("[2/7] 采集 payload + 赛道...")
    payload, tracks = collect_payload(source)
    freshness = assess_eod_freshness(payload)
    payload["freshness"] = freshness
    research_summary: Dict[str, Any] = {
        "as_of_trade_date": str(
            ((payload or {}).get("market_overview") or {}).get("trade_date")
            or ""
        ).strip(),
        "status": "not_executed",
        "production_eligible": False,
        "stages": {},
    }
    if freshness["status"] != "ready":
        logger.warning(
            "EOD freshness %s: global=%s blocked_targets=%s",
            freshness["status"],
            freshness.get("critical_failures"),
            freshness.get("blocked_targets"),
        )

    analyst_trade_date = str(
        ((payload.get("market_overview") or {}).get("trade_date")) or ""
    ).strip()
    try:
        historical_payloads = _load_historical_report_payloads(
            analyst_trade_date,
        )
        payload["analyst_context"] = build_eod_market_analysis(
            payload,
            historical_payloads,
            track_results=tracks,
        )
        logger.info(
            "EOD analyst context: trade_date=%s history=%s calculation=%s",
            analyst_trade_date,
            len(historical_payloads),
            payload["analyst_context"].get("calculation_version"),
        )
    except Exception as exc:
        logger.exception("EOD analyst context recalculation failed")
        payload["analyst_context"] = {
            "schema_version": 1,
            "as_of_trade_date": analyst_trade_date or None,
            "status": "calculation_failed",
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
        }

    try:
        from vaxstock.services.regime_auditor import record_regime_audit
        record_regime_audit(payload)
    except Exception as e:
        logger.warning(f"Regime Audit 落盘失败(不影响EOD): {str(e)[:120]}")

    # MR-Eval E1: 全 watchlist 因子快照 append + 历史快照 T+k 回填(预测追踪数据地基)。
    # E4-6 要把最新 prediction 核验写进当日报告,所以 E1/E4 必须先于 markdown 渲染执行。
    logger.info("[3/7] MR-Eval 回填 + EOD Prediction 核验...")
    try:
        stats = record_and_backfill(payload, source)
        logger.info(f"MR-Eval: 快照 {stats['snapshots']} 条 / 回填 {stats['backfilled']} 条")
    except Exception as e:
        logger.warning(f"MR-Eval 快照/回填失败(不影响落盘): {str(e)[:120]}")

    # Research v2 is the only human-facing EOD analysis line.  Legacy payload
    # fields remain available to machine consumers, but the report must never
    # fall back to the old score/ranking template when this pipeline blocks.
    research_stage = "snapshot"
    try:
        research_trade_date = str(
            ((payload or {}).get("market_overview") or {}).get("trade_date") or ""
        ).strip()
        if not research_trade_date:
            raise ValueError("payload.market_overview.trade_date missing")
        research_v2 = record_legacy_snapshot_trade_date(
            research_trade_date,
            mode="live",
            snapshots_path=SNAPSHOTS_FILE,
        )
        research_summary["stages"]["snapshot"] = {
            "status": research_v2.get("status"),
            "reason": research_v2.get("reason"),
            "metrics": {
                "observations": research_v2.get("observations_written"),
                "factors": research_v2.get("factors_written"),
            },
        }
        logger.info(
            "Research v2: status=%s observations=%s factors=%s manifest=%s",
            research_v2.get("status"),
            research_v2.get("observations_written"),
            research_v2.get("factors_written"),
            research_v2.get("manifests_written"),
        )
        research_stage = "anchor"
        try:
            anchor_v2 = run_global_anchor_refresh(
                as_of_trade_date=research_trade_date,
                us_market=(payload or {}).get("us_market") or {},
                mode="live",
            )
            anchor_summary = anchor_v2.get("summary") or {}
            research_summary["stages"]["anchor"] = {
                "status": anchor_v2.get("status"),
                "reason": anchor_v2.get("reason"),
                "metrics": {
                    "anchors": len(
                        anchor_summary.get("available_anchor_keys") or []
                    ),
                    "equity_majority_direction": (
                        anchor_summary.get(
                            "equity_majority_direction"
                        )
                    ),
                    "missing_symbols": anchor_summary.get(
                        "missing_symbols"
                    ),
                },
            }
            logger.info(
                "Research v2 anchors: status=%s anchors=%s majority=%s",
                anchor_v2.get("status"),
                anchor_summary.get("available_anchor_keys"),
                anchor_summary.get("equity_majority_direction"),
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            research_summary["stages"]["anchor"] = {
                "status": "failed",
                "reason": error,
                "metrics": {},
            }
            logger.warning(
                "Research v2 anchor refresh failed (shadow only): %s",
                error,
            )
        research_stage = "curve"
        curve_v2 = run_curve_refresh(
            as_of_trade_date=research_trade_date,
            mode="live",
        )
        curve_summary = curve_v2.get("summary") or {}
        research_summary["stages"]["curve"] = {
            "status": curve_v2.get("status"),
            "reason": curve_v2.get("reason"),
            "metrics": {
                "outputs": curve_summary.get("outputs"),
                "candidate_hits": curve_summary.get("candidate_hits"),
            },
        }
        logger.info(
            "Research v2 curves: status=%s outputs=%s candidate_hits=%s",
            curve_v2.get("status"),
            (curve_v2.get("summary") or {}).get("outputs"),
            (curve_v2.get("summary") or {}).get("candidate_hits"),
        )
        research_stage = "group"
        group_v2 = run_group_refresh(
            as_of_trade_date=research_trade_date,
            mode="live",
        )
        group_summary = group_v2.get("summary") or {}
        research_summary["stages"]["group"] = {
            "status": group_v2.get("status"),
            "reason": group_v2.get("reason"),
            "metrics": {
                "stocks": group_summary.get("stock_group_vectors"),
                "memberships": group_summary.get("statistical_memberships"),
                "systemic_event_state": group_summary.get(
                    "systemic_event_state"
                ),
                "systemic_event_direction": group_summary.get(
                    "systemic_event_direction"
                ),
                "event_stock_breadth": group_summary.get(
                    "event_stock_breadth"
                ),
                "systemic_event_families": group_summary.get(
                    "systemic_event_families"
                ),
            },
        }
        logger.info(
            "Research v2 groups: status=%s stocks=%s memberships=%s "
            "event_state=%s event_breadth=%s event_families=%s labels=%s",
            group_v2.get("status"),
            (group_v2.get("summary") or {}).get("stock_group_vectors"),
            (group_v2.get("summary") or {}).get("statistical_memberships"),
            (group_v2.get("summary") or {}).get("systemic_event_state"),
            (group_v2.get("summary") or {}).get("event_stock_breadth"),
            (group_v2.get("summary") or {}).get(
                "systemic_event_families"
            ),
            (group_v2.get("summary") or {}).get("label_usage"),
        )
        research_stage = "outcome"
        group_outcomes_v2 = run_group_outcome_refresh()
        outcome_summary = group_outcomes_v2.get("summary") or {}
        outcome_stored = group_outcomes_v2.get("stored") or {}
        research_summary["stages"]["outcome"] = {
            "status": group_outcomes_v2.get("status"),
            "reason": group_outcomes_v2.get("reason"),
            "metrics": {
                "samples_ready": outcome_summary.get("samples_ready"),
                "samples_written": outcome_stored.get("written"),
            },
        }
        logger.info(
            "Research v2 group outcomes: status=%s written=%s samples=%s",
            group_outcomes_v2.get("status"),
            (group_outcomes_v2.get("stored") or {}).get("written"),
            (group_outcomes_v2.get("summary") or {}).get("samples_ready"),
        )
        research_stage = "anchor_forecast"
        try:
            anchor_forecast_v2 = run_anchor_forecast_refresh(
                as_of_trade_date=research_trade_date,
            )
            research_summary["stages"]["anchor_forecast"] = {
                "status": anchor_forecast_v2.get("status"),
                "reason": anchor_forecast_v2.get("reason"),
                "metrics": {
                    "horizons": anchor_forecast_v2.get("horizons") or {},
                    "audit_path": anchor_forecast_v2.get("audit_path"),
                },
            }
            logger.info(
                "Research v2 anchor forecast: status=%s path=%s",
                anchor_forecast_v2.get("status"),
                anchor_forecast_v2.get("audit_path"),
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            research_summary["stages"]["anchor_forecast"] = {
                "status": "failed",
                "reason": error,
                "metrics": {},
            }
            logger.warning(
                "Research v2 anchor forecast failed (shadow only): %s",
                error,
            )
        research_stage = "select"
        select_v2 = run_select_refresh(
            as_of_trade_date=research_trade_date,
        )
        logger.info(
            "Research v2 select: status=%s write=%s production=%s",
            select_v2.get("status"),
            select_v2.get("write_status"),
            select_v2.get("production_eligible"),
        )
        t1_discovery = (
            (select_v2.get("discovery_summary") or {}).get("1") or {}
        )
        research_summary["stages"]["select"] = {
            "status": select_v2.get("status"),
            "reason": select_v2.get("reason"),
            "metrics": {
                "factor_series_tested": t1_discovery.get(
                    "factor_series_tested"
                ),
                "factor_series_total": t1_discovery.get(
                    "factor_series_total"
                ),
                "candidate_tests": t1_discovery.get("candidate_tests"),
            },
        }
        logger.info(
            "Research v2 T+1 discovery: factors=%s/%s candidates=%s "
            "recent_reversals=%s direction_consistent=%s evidence=%s",
            t1_discovery.get("factor_series_tested"),
            t1_discovery.get("factor_series_total"),
            t1_discovery.get("candidate_tests"),
            t1_discovery.get("recent_reversal_count"),
            t1_discovery.get("direction_consistent_count"),
            t1_discovery.get("evidence_label"),
        )
        if not select_v2.get("audit_path"):
            research_summary.update({
                "status": "blocked",
                "blocking_stage": "select",
                "reason": (
                    select_v2.get("reason")
                    or "selection_audit_not_materialized"
                ),
            })
        else:
            research_stage = "forecast"
            forecast_v2 = run_forecast_refresh(
                as_of_trade_date=research_trade_date,
                selection_path=select_v2["audit_path"],
            )
            research_summary["stages"]["forecast"] = {
                "status": forecast_v2.get("status"),
                "reason": forecast_v2.get("reason"),
                "metrics": {},
            }
            logger.info(
                "Research v2 forecast: status=%s write=%s production=%s",
                forecast_v2.get("status"),
                forecast_v2.get("write_status"),
                forecast_v2.get("production_eligible"),
            )
            research_stage = "evaluation"
            forecast_evaluation_v2 = run_forecast_evaluation_refresh(
                as_of_trade_date=research_trade_date,
                decision_at=select_v2["decision_at"],
            )
            evaluation_summary = forecast_evaluation_v2.get("summary") or {}
            research_summary["stages"]["evaluation"] = {
                "status": forecast_evaluation_v2.get("status"),
                "reason": forecast_evaluation_v2.get("reason"),
                "metrics": {
                    "pending_forecasts": evaluation_summary.get(
                        "pending_forecasts"
                    ),
                },
            }
            production_eligible = bool(
                select_v2.get("production_eligible")
                and forecast_v2.get("production_eligible")
                and forecast_evaluation_v2.get("production_eligible")
            )
            research_summary.update({
                "status": (
                    "production_eligible"
                    if production_eligible
                    else "abstain"
                ),
                "production_eligible": production_eligible,
                "reason": (
                    None
                    if production_eligible
                    else "no_production_eligible_forecast"
                ),
            })
            logger.info(
                "Research v2 forecast evaluation: status=%s results=%s "
                "pending=%s calibration=%s production=%s",
                forecast_evaluation_v2.get("status"),
                (
                    forecast_evaluation_v2.get("stored") or {}
                ).get("written"),
                evaluation_summary.get("pending_forecasts"),
                forecast_evaluation_v2.get("calibration_status"),
                forecast_evaluation_v2.get("production_eligible"),
            )
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:240]}"
        research_summary["stages"].setdefault(research_stage, {
            "status": "failed",
            "reason": error,
            "metrics": {},
        })
        research_summary.update({
            "status": "blocked",
            "blocking_stage": research_stage,
            "reason": error,
            "production_eligible": False,
        })
        logger.warning(
            "Research v2 snapshot/curve/group/outcome/select/forecast/"
            "evaluation failed: "
            f"{str(e)[:120]}"
        )

    # D-line closeout is market-data-only and never reads user executions.
    try:
        dline_trade_date = str(
            ((payload or {}).get("market_overview") or {}).get("trade_date") or ""
        ).strip()
        if not dline_trade_date:
            raise ValueError("payload.market_overview.trade_date missing")
        dline_closeout = run_dline_closeout(trade_date=dline_trade_date)
        logger.info(
            "D-line closeout: status=%s tasks=%s triggers=%s gaps=%s errors=%s",
            dline_closeout.get("status"),
            (dline_closeout.get("evidence") or {}).get("task_count"),
            (dline_closeout.get("evidence") or {}).get("trigger_count"),
            len((dline_closeout.get("evidence") or {}).get("gaps") or []),
            len(dline_closeout.get("errors") or []),
        )
    except Exception as e:
        logger.warning(f"D-line closeout failed (A/B/C persistence is preserved): {str(e)[:120]}")
    # MR-Eval E4: 先核验已有 predictions,再基于本次 EOD 定稿 payload 生成下一交易日 live predictions。
    # 失败仅 warning,不影响报告三件套落盘/邮件/E1。
    prediction_run = _run_eod_prediction(
        payload,
        source,
        allow_live=freshness["forecast_eligible"],
        eligible_codes=freshness.get("eligible_codes"),
    )
    evidence_trade_date = str(
        ((payload or {}).get("market_overview") or {}).get("trade_date") or ""
    ).strip()
    try:
        if not evidence_trade_date:
            raise ValueError("payload.market_overview.trade_date missing")
        evidence_stats = run_evidence_ledger(as_of_trade_date=evidence_trade_date)
        logger.info(
            "Strategy evidence: roots=%s written=%s skipped=%s hydrated=%s",
            (evidence_stats.get("build") or {}).get("ready"),
            (evidence_stats.get("ledger") or {}).get("written"),
            (evidence_stats.get("ledger") or {}).get("skipped"),
            evidence_stats.get("hydrated"),
        )
    except Exception as e:
        logger.warning(f"Strategy evidence ledger failed (A/B/C persistence is preserved): {str(e)[:120]}")
    try:
        if not evidence_trade_date:
            raise ValueError("payload.market_overview.trade_date missing")
        convergence_stats = run_evidence_convergence(
            as_of_trade_date=evidence_trade_date,
            payload=payload,
        )
        logger.info(
            "Evidence convergence: status=%s mature=%s findings=%s",
            convergence_stats.get("status"),
            (convergence_stats.get("facts") or {}).get("new_matured_c_results"),
            convergence_stats.get("special_findings"),
        )
    except Exception as e:
        logger.warning(f"Evidence convergence failed (daily action falls back to pending): {str(e)[:120]}")
    # 旧 E4/T+N 仍是 D 线观察任务的内部 baseline，暂不能删除；但其现有
    # 样本与评估方法不足以支持用户决策，默认不再进入报告。
    prediction_summary = {}
    if config.SECRETS.get("legacy_prediction_report_enabled", False):
        prediction_summary = _build_prediction_summary(payload)

    logger.info("[4/7] 压缩为 claude_data + 渲染 markdown...")
    claude_data = compact_for_claude(payload)
    claude_data["freshness"] = freshness
    if prediction_summary:
        claude_data["prediction_summary"] = prediction_summary
    claude_data["research_summary"] = research_summary
    markdown = build_claude_markdown(
        claude_data,
        research_summary=research_summary,
        track_results=tracks,
    )

    logger.info("[5/7] 报告落盘(var/reports/{date}/)...")
    paths = store_report(payload, claude_data, markdown)
    try:
        mail_result = send_research_eod_email(
            trade_date=research_summary.get("as_of_trade_date"),
            markdown=markdown,
            report_paths=paths,
        )
        logger.info(
            "Research EOD mail: status=%s sent=%s target=%s reason=%s",
            mail_result.get("status"),
            mail_result.get("sent"),
            mail_result.get("target_trade_date"),
            mail_result.get("reason"),
        )
    except Exception as e:
        logger.warning(
            "Research EOD mail failed without sent marker; next EOD may retry: "
            f"{type(e).__name__}: {str(e)[:160]}"
        )
    _enqueue_d_observation_job(paths, payload, prediction_run)

    # 用户邮件由异步 D-line worker 在任务完成后统一发送。这里保留 A/B/C
    # 报告落盘与 D-line 入队契约，不再额外发送旧 EOD 摘要，避免每日两封邮件。
    logger.info("[6/7] EOD 数据已落盘；每日操作邮件等待 D-line worker...")

    # 旧 Layer2/T+N 日报已经被实测证明不能支持“effective”结论。保留代码和
    # 历史数据供回放，但默认停止每天重复生成；显式开关只用于审计旧 baseline。
    if config.SECRETS.get("legacy_daily_research_enabled", False):
        logger.info("[7/7] 旧 Layer2 / Factor review / Prediction research（审计模式）...")
        try:
            from vaxstock.research.layer2_eval import run_layer2
            run_layer2(write=True)
        except Exception as e:
            logger.warning(f"Layer2 分析跳过(不影响EOD): {str(e)[:120]}")

        try:
            from vaxstock.research.factor_weight_review import run_factor_weight_review
            run_factor_weight_review(write=True)
        except Exception as e:
            logger.warning(f"Factor weight review 分析跳过(不影响EOD): {str(e)[:120]}")

        try:
            from vaxstock.research.prediction_eval import run_prediction_layer2
            run_prediction_layer2(write=True)
        except Exception as e:
            logger.warning(f"Prediction Layer2 分析跳过(不影响EOD): {str(e)[:120]}")

        try:
            from vaxstock.research.rule_suggester import run_rule_suggestions
            run_rule_suggestions(write=True)
        except Exception as e:
            logger.warning(f"Rule suggestions 分析跳过(不影响EOD): {str(e)[:120]}")
    else:
        logger.info("[7/7] 旧 T+N 研究输出已降级为历史审计模式，跳过每日重复生成")

    return paths


def _build_prediction_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build E4-6 report summary for the just-finished EOD trade date."""
    target = (payload.get("market_overview") or {}).get("trade_date")
    try:
        from vaxstock.research.prediction_eval import summarize_prediction_check
        summary = summarize_prediction_check(target_trade_date=target)
        if summary.get("available"):
            logger.info(
                "EOD Prediction 摘要: target=%s 预测 %s 条 / 核验 %s 条 / pending %s 条",
                summary.get("target_trade_date"),
                summary.get("predictions"),
                summary.get("evaluated"),
                summary.get("pending"),
            )
        else:
            logger.info(f"EOD Prediction 摘要: target={target or '待验证'} 待积累")
        return summary
    except Exception as e:
        logger.warning(f"EOD Prediction 摘要生成失败(不影响EOD): {str(e)[:120]}")
        return {
            "available": False,
            "target_trade_date": target,
            "reason": "summary_error",
            "message": "prediction 核验摘要生成失败,待验证",
        }

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


def _run_eod_prediction(
        payload: Dict[str, Any],
        source,
        *,
        allow_live: bool = True,
        eligible_codes=None,
) -> Optional[Dict[str, Any]]:
    """E4 接入 EOD: 先核验已有 prediction, 再冻结下一交易日 live prediction。"""
    try:
        stats = evaluate_from_files()
        logger.info(f"EOD Prediction 核验: 写入 {stats['written']} 条 / 跳过 {stats['skipped']} 条")
    except Exception as e:
        logger.warning(f"EOD Prediction 核验失败(不影响EOD): {str(e)[:120]}")

    if not allow_live:
        logger.warning("EOD Prediction live: critical freshness 未通过，输出 abstain")
        return None

    try:
        baseline = (payload.get("market_overview") or {}).get("trade_date")
        if not baseline:
            logger.warning("EOD Prediction: payload 无 trade_date, 跳过 live prediction(不臆造日期)")
            return None
        target = _next_trade_date(source, baseline)
        if not target:
            return None
        prediction_payload = payload
        if eligible_codes is not None:
            allowed = {str(code) for code in eligible_codes}
            prediction_payload = dict(payload)
            prediction_payload["stocks"] = [
                stock for stock in (payload.get("stocks") or [])
                if str((stock or {}).get("code") or "") in allowed
            ]
        preds = predictions_from_payload(
            prediction_payload,
            target,
            generation_mode="live",
        )
        stats = record_predictions(preds)
        logger.info(f"EOD Prediction live: target={target} 生成 {len(preds)} 条 / 写入 {stats['written']} 条 / 跳过 {stats['skipped']} 条")
        return {
            "baseline_trade_date": str(baseline),
            "target_trade_date": str(target),
            "predictions": preds,
            "stats": stats,
        }
    except Exception as e:
        logger.warning(f"EOD Prediction live 生成失败(不影响EOD): {str(e)[:120]}")
        return None

def _enqueue_d_observation_job(paths: Dict[str, str], payload: Dict[str, Any],
                             prediction_run: Optional[Dict[str, Any]]) -> None:
    """D线: 只入队观察任务生成 job,不在 EOD 主流程同步调用 Codex。

    真正的 LLM 生成由 vaxstock.services.dline_plan 独立服务异步消费。这样 D线慢、
    超时或失败都不会阻塞 A/B/C/EOD 报告与邮件。
    """
    if not prediction_run or not prediction_run.get("target_trade_date"):
        logger.info("D线观察任务: 缺 target_trade_date, 不入队")
        return
    try:
        baseline = str((payload.get("market_overview") or {}).get("trade_date") or prediction_run.get("baseline_trade_date") or "")
        stats = enqueue_observation_job(
            paths.get("payload"),
            prediction_run["target_trade_date"],
            c_predictions=prediction_run.get("predictions") or [],
            baseline_trade_date=baseline,
            task_codes=((payload.get("freshness") or {}).get("eligible_codes")),
        )
        logger.info(
            "D线观察任务已入队: target=%s queued=%s skipped=%s job=%s",
            prediction_run["target_trade_date"],
            stats.get("queued"),
            stats.get("skipped"),
            stats.get("job_id"),
        )
    except Exception as e:
        logger.warning(f"D线观察任务入队失败(不影响EOD): {str(e)[:120]}")



if __name__ == "__main__":
    import logging as _logging
    import sys

    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        result = run_eod()
        print("EOD done:", result)
        sys.exit(0)
    except Exception:
        _logging.exception("EOD 失败")
        sys.exit(1)
