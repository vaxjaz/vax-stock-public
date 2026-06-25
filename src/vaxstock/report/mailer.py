# -*- coding: utf-8 -*-
"""report 层: 邮件发送。

从 monolith stock_report_enhanced.py 迁入。改造:
  - 消除 EMAIL_CONFIG 全局, 改为入参 smtp_conf: dict(由调用方从 config.SECRETS 取了传进来)
  - HTML 已砍: 默认纯文本发(可传 claude.md 内容当 body); is_html=True 时才用 html
依赖只允许标准库(不 import config/sources/analysis, smtp_conf 由调用方传)。
"""

import logging
import smtplib
from datetime import datetime
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _normalize_emails(value) -> List[str]:
    """把字符串/列表/逗号分隔串统一规范成 list[str],去空去重保序"""
    if not value:
        return []
    raw = []
    if isinstance(value, str):
        # 支持 "a@x.com, b@y.com" 或 "a@x.com; b@y.com"
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    cleaned = []
    seen = set()
    for e in raw:
        if not e:
            continue
        s = str(e).strip()
        if s and s not in seen:
            seen.add(s)
            cleaned.append(s)
    return cleaned


def send_email(body: str,
               attachments: List[Tuple[str, str, str]],
               smtp_conf: Dict,
               subject: Optional[str] = None,
               is_html: bool = False) -> bool:
    """发送报告邮件。

    smtp_conf: {smtp_server, smtp_port, sender_email, sender_password,
                receiver_email, cc_email, bcc_email}(由调用方从 config.SECRETS 取)。
    body: 邮件正文(默认纯文本, 可直接传 claude.md 内容); is_html=True 时按 HTML 发。
    attachments: (filename, path, subtype) 列表。
    """
    if subject is None:
        today = datetime.now().strftime("%Y-%m-%d")
        subject = f"📊 股票汇总 {today}"

    # 规范化收件人列表
    to_list = _normalize_emails(smtp_conf.get("receiver_email"))
    cc_list = _normalize_emails(smtp_conf.get("cc_email"))
    bcc_list = _normalize_emails(smtp_conf.get("bcc_email"))

    if not to_list:
        logger.error("❌ 没有配置收件人(receiver_email),跳过发送")
        return False

    msg = MIMEMultipart()
    msg["From"] = Header(smtp_conf["sender_email"])
    msg["To"] = Header(", ".join(to_list))            # 多个收件人用逗号分隔
    if cc_list:
        msg["Cc"] = Header(", ".join(cc_list))        # 抄送写入邮件头
    # 注意: Bcc 不写入邮件头,否则就不"密"了,只在投递时传
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))

    for filename, path, subtype in (attachments or []):
        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", filename))
        msg.attach(part)

    # 实际投递的所有收件人 = To + Cc + Bcc
    all_recipients = to_list + cc_list + bcc_list

    try:
        smtp = smtplib.SMTP_SSL(smtp_conf["smtp_server"], smtp_conf["smtp_port"])
        smtp.login(smtp_conf["sender_email"], smtp_conf["sender_password"])
        smtp.sendmail(smtp_conf["sender_email"], all_recipients, msg.as_string())
        smtp.quit()
        logger.info(f"✅ 邮件已发送 → 收件人{len(to_list)}个 / 抄送{len(cc_list)}个 / 密送{len(bcc_list)}个")
        return True
    except Exception as e:
        logger.error(f"❌ 邮件发送失败: {e}")
        return False
