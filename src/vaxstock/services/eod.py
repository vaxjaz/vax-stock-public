# -*- coding: utf-8 -*-
"""services 层: run_eod —— EOD 端到端串联编排器(可作模块入口供 cron/systemd 调)。

MR6 PR-B: 串 collect → compact → build → store → mail 五步。AITrack 超时不在本 PR;
api/intraday/cron unit 留 PR-C。

对接 main 真实签名(已核):
  TushareSource(token)                                          sources.tushare_src
  collect_payload(source) -> (payload, track_results)           services.collect
  compact_for_claude(payload) -> claude_data                    report.claude_md
  build_claude_markdown(claude_data, track_results=) -> str     report.claude_md
  store_report(payload, claude_data, markdown) -> {paths}       report.store
  send_email(body, attachments, smtp_conf, subject=, is_html=)  report.mailer

铁律: 顶层取数失败不吞(应可见); 仅 send_email 自身 try, 失败不影响已完成的落盘。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from vaxstock import config
from vaxstock.report.claude_md import build_claude_markdown, build_email_digest, compact_for_claude
from vaxstock.report.mailer import send_email
from vaxstock.report.store import store_report
from vaxstock.services.collect import collect_payload
from vaxstock.services.eval_recorder import record_and_backfill
from vaxstock.services.eod_predictor import predictions_from_payload, record_predictions
from vaxstock.services.prediction_evaluator import evaluate_from_files
from vaxstock.sources.tushare_src import TushareSource

logger = logging.getLogger(__name__)


def run_eod() -> Dict[str, str]:
    """EOD 全流程: 采集 → 评估回填 → compact → markdown → 落盘 → (门控)邮件。"""
    logger.info("[1/7] 初始化 Tushare 数据源...")
    source = TushareSource(config.SECRETS.get("tushare_token"))

    logger.info("[2/7] 采集 payload + 赛道...")
    payload, tracks = collect_payload(source)

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

    # MR-Eval E4: 先核验已有 predictions,再基于本次 EOD 定稿 payload 生成下一交易日 live predictions。
    # 失败仅 warning,不影响报告三件套落盘/邮件/E1。
    _run_eod_prediction(payload, source)
    prediction_summary = _build_prediction_summary(payload)

    logger.info("[4/7] 压缩为 claude_data + 注入 prediction_summary + 渲染 markdown...")
    claude_data = compact_for_claude(payload)
    if prediction_summary:
        claude_data["prediction_summary"] = prediction_summary
    markdown = build_claude_markdown(claude_data, track_results=tracks)

    logger.info("[5/7] 报告落盘(var/reports/{date}/)...")
    paths = store_report(payload, claude_data, markdown)

    logger.info("[6/7] 邮件门控 + 发送...")
    # 邮件正文 = 精简摘要(大盘/宏观/赛道/持仓详情/观察池高分清单); 完整 markdown(claude.md)
    # 与全量 payload.json 走附件。原 markdown 仍 store 落盘 + 作附件, 不变(见 CLAUDE.md §9.8)。
    digest = build_email_digest(claude_data, track_results=tracks)
    attachments = [
        ("claude.md", paths["claude_md"], "octet-stream"),
        ("payload.json", paths["payload"], "octet-stream"),
    ]
    _maybe_send_email(digest, attachments)

    # MR-Eval E2: Layer2 离线分析(分环境分桶前瞻收益/超额)。纯读 E1 两 jsonl,
    # 失败仅 warning 不影响 EOD。Layer2 不按样本数屏蔽统计值; N 直接展示。
    logger.info("[7/7] Layer2 / Prediction Layer2 / Rule suggestions 离线分析...")
    try:
        from vaxstock.research.layer2_eval import run_layer2
        run_layer2(write=True)
    except Exception as e:
        logger.warning(f"Layer2 分析跳过(不影响EOD): {str(e)[:120]}")

    # MR-Eval E4-5: Prediction Layer2 离线分桶评估。只读 eod_predictions/eod_prediction_results,
    # pending 样本只透明计数,不进入命中率/收益统计; 失败 warning-only。
    try:
        from vaxstock.research.prediction_eval import run_prediction_layer2
        run_prediction_layer2(write=True)
    except Exception as e:
        logger.warning(f"Prediction Layer2 分析跳过(不影响EOD): {str(e)[:120]}")

    # MR-Eval E4-7: Rule suggestions 只输出离线建议,不改 prediction 原文/生产规则。
    try:
        from vaxstock.research.rule_suggester import run_rule_suggestions
        run_rule_suggestions(write=True)
    except Exception as e:
        logger.warning(f"Rule suggestions 分析跳过(不影响EOD): {str(e)[:120]}")

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


def _run_eod_prediction(payload: Dict[str, Any], source) -> None:
    """E4 接入 EOD: 先核验已有 prediction, 再冻结下一交易日 live prediction。"""
    try:
        stats = evaluate_from_files()
        logger.info(f"EOD Prediction 核验: 写入 {stats['written']} 条 / 跳过 {stats['skipped']} 条")
    except Exception as e:
        logger.warning(f"EOD Prediction 核验失败(不影响EOD): {str(e)[:120]}")

    try:
        baseline = (payload.get("market_overview") or {}).get("trade_date")
        if not baseline:
            logger.warning("EOD Prediction: payload 无 trade_date, 跳过 live prediction(不臆造日期)")
            return
        target = _next_trade_date(source, baseline)
        if not target:
            return
        preds = predictions_from_payload(payload, target, generation_mode="live")
        stats = record_predictions(preds)
        logger.info(f"EOD Prediction live: target={target} 生成 {len(preds)} 条 / 写入 {stats['written']} 条 / 跳过 {stats['skipped']} 条")
    except Exception as e:
        logger.warning(f"EOD Prediction live 生成失败(不影响EOD): {str(e)[:120]}")


def _maybe_send_email(body: str, attachments) -> None:
    """邮件门控: SECRETS 凭据齐才发; SECRETS 键 → send_email 的 smtp_conf 键适配(发信固定 QQ)。
    body = 精简摘要(build_email_digest); send_email 失败仅 warning, 不影响已完成的落盘。"""
    S = config.SECRETS
    if S.get("email_enabled") and S.get("email_user") and S.get("email_authcode") and S.get("email_to"):
        smtp_conf: Dict[str, Any] = {
            "smtp_server": S.get("smtp_server", "smtp.qq.com"),
            "smtp_port": S.get("smtp_port", 465),
            "sender_email": S["email_user"],
            "sender_password": S["email_authcode"],
            "receiver_email": S["email_to"],   # 整串透传, mailer._normalize_emails 负责拆逗号/分号多人
            "cc_email": S.get("email_cc"),      # 整串透传, 同上
            "bcc_email": None,                  # 本次不启用 BCC
        }
        try:
            send_email(body, attachments, smtp_conf, is_html=False)  # v2 无 HTML, 纯文本发摘要
        except Exception as e:
            logger.warning(f"邮件发送失败(不影响落盘): {str(e)[:120]}")
    else:
        logger.info("邮件未启用或缺凭据, 跳过发送")


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
