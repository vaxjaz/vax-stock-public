# -*- coding: utf-8 -*-
"""盘中推送(report 层): PushPlus 微信 + QQ邮箱。从 monolith intraday_watch.py 迁。

两者各自 try, 失败仅 logger.warning 返 False, 互不影响; 未配凭据则跳过返 False。
smtp_conf 复用 mailer 同款键: smtp_server / smtp_port / sender_email / sender_password / receiver_email。
"""

import logging
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


def push_wechat(title: str, content: str, *, pushplus_token: Optional[str]) -> bool:
    """PushPlus 微信推送; 未配 token 返 False 跳过。成功返 True。"""
    if not pushplus_token:
        return False
    try:
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json={"token": pushplus_token, "title": title, "content": content, "template": "txt"},
            timeout=10,
        )
        rj = resp.json()
        if rj.get("code") != 200:
            logger.warning(f"PushPlus 返回异常: {rj.get('msg')}")
            return False
        return True
    except Exception as e:
        logger.warning(f"微信推送失败: {str(e)[:120]}")
        return False


def push_email(title: str, content: str, *, smtp_conf: Optional[Dict]) -> bool:
    """QQ邮箱 SMTP 纯文本推送; 未启用/缺凭据返 False 跳过。成功返 True。"""
    if not smtp_conf:
        return False
    sender = smtp_conf.get("sender_email")
    pwd = smtp_conf.get("sender_password")
    recv = smtp_conf.get("receiver_email")
    if not (sender and pwd and recv):
        return False

    import smtplib
    from email.header import Header
    from email.mime.text import MIMEText

    # receiver 支持单串或逗号/分号分隔多人
    to_list = [x.strip() for x in str(recv).replace(";", ",").split(",") if x.strip()]
    try:
        msg = MIMEText(content, "plain", "utf-8")
        msg["From"] = sender
        msg["To"] = ", ".join(to_list)
        msg["Subject"] = Header(title, "utf-8")
        srv = smtplib.SMTP_SSL(smtp_conf.get("smtp_server", "smtp.qq.com"),
                               int(smtp_conf.get("smtp_port", 465)), timeout=12)
        srv.login(sender, pwd)
        srv.sendmail(sender, to_list, msg.as_string())
        srv.quit()
        return True
    except Exception as e:
        logger.warning(f"邮件推送失败: {str(e)[:120]}")
        return False
