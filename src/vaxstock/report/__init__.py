# -*- coding: utf-8 -*-
"""呈现层: 纯渲染 / 落盘 / 发送(只吃已组装 payload, 禁 import sources/analysis)。

子模块:
    claude_md  compact_for_claude / build_claude_markdown / render_track_section(通用赛道渲染)
    store      store_report(reports/{date}/ 三件套落盘) / cleanup(按日期目录清理)
    mailer     send_email(smtp_conf 入参, 默认纯文本) / _normalize_emails

依赖只允许 util / config / tracks.contract。本 __init__ 不 re-export 子模块, 按需直接 import 子模块。
"""
