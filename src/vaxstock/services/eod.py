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
from typing import Any, Dict

from vaxstock import config
from vaxstock.report.claude_md import build_claude_markdown, build_email_digest, compact_for_claude
from vaxstock.report.mailer import send_email
from vaxstock.report.store import store_report
from vaxstock.services.collect import collect_payload
from vaxstock.services.eval_recorder import record_and_backfill
from vaxstock.sources.tushare_src import TushareSource

logger = logging.getLogger(__name__)


def run_eod() -> Dict[str, str]:
    """EOD 全流程: 采集 → compact → markdown → 落盘 → (门控)邮件。返回落盘三件套路径。"""
    logger.info("[1/5] 初始化 Tushare 数据源...")
    source = TushareSource(config.SECRETS.get("tushare_token"))

    logger.info("[2/5] 采集 payload + 赛道...")
    payload, tracks = collect_payload(source)

    logger.info("[3/5] 压缩为 claude_data + 渲染 markdown...")
    claude_data = compact_for_claude(payload)
    markdown = build_claude_markdown(claude_data, track_results=tracks)

    logger.info("[4/5] 报告落盘(var/reports/{date}/)...")
    paths = store_report(payload, claude_data, markdown)

    logger.info("[5/5] 邮件门控 + 发送...")
    # 邮件正文 = 精简摘要(大盘/宏观/赛道/持仓详情/观察池高分清单); 完整 markdown(claude.md)
    # 与全量 payload.json 走附件。原 markdown 仍 store 落盘 + 作附件, 不变(见 CLAUDE.md §9.8)。
    digest = build_email_digest(claude_data, track_results=tracks)
    attachments = [
        ("claude.md", paths["claude_md"], "octet-stream"),
        ("payload.json", paths["payload"], "octet-stream"),
    ]
    _maybe_send_email(digest, attachments)

    # MR-Eval E1: 全 watchlist 因子快照 append + 历史快照 T+k 回填(预测追踪数据地基)。
    # 失败仅 warning, 不影响已完成的落盘/邮件(记录是反哺地基, 非主流程)。
    try:
        stats = record_and_backfill(payload, source)
        logger.info(f"MR-Eval: 快照 {stats['snapshots']} 条 / 回填 {stats['backfilled']} 条")
    except Exception as e:
        logger.warning(f"MR-Eval 快照/回填失败(不影响落盘): {str(e)[:120]}")

    # MR-Eval E2: Layer2 离线分析(分环境分桶前瞻收益/超额)。必须在 record_and_backfill 之后
    # (读已回填到最新的 results)。纯读 E1 两 jsonl, 失败仅 warning 不影响 EOD。
    # 早期样本少, 报告会大量"样本不足", 正常——数据攒厚自然有结论。
    try:
        from vaxstock.research.layer2_eval import run_layer2
        run_layer2(write=True)
    except Exception as e:
        logger.warning(f"Layer2 分析跳过(不影响EOD): {str(e)[:120]}")

    return paths


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
