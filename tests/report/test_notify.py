# -*- coding: utf-8 -*-
"""report.notify 测试(零网络, monkeypatch 推送底层)。"""

import smtplib

import vaxstock.report.notify as notify


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


# ── push_wechat ──
def test_push_wechat_skips_without_token():
    # 未配 token 直接返 False, 不应触网
    called = {"v": False}
    saved = notify.requests.post
    try:
        notify.requests.post = lambda *a, **k: called.__setitem__("v", True) or _Resp({"code": 200})
        assert notify.push_wechat("t", "c", pushplus_token="") is False
        assert notify.push_wechat("t", "c", pushplus_token=None) is False
        assert called["v"] is False  # 未触发任何 post
    finally:
        notify.requests.post = saved


def test_push_wechat_success_and_failure():
    saved = notify.requests.post
    try:
        notify.requests.post = lambda *a, **k: _Resp({"code": 200})
        assert notify.push_wechat("t", "c", pushplus_token="TK") is True
        notify.requests.post = lambda *a, **k: _Resp({"code": 500, "msg": "bad"})
        assert notify.push_wechat("t", "c", pushplus_token="TK") is False
    finally:
        notify.requests.post = saved


# ── push_email ──
def test_push_email_skips_without_conf():
    assert notify.push_email("t", "c", smtp_conf=None) is False
    assert notify.push_email("t", "c", smtp_conf={}) is False
    # 缺字段也跳过
    assert notify.push_email("t", "c", smtp_conf={"sender_email": "a@qq.com"}) is False


def test_push_email_success():
    sent = {"to": None, "from": None}

    class _FakeSMTP:
        def __init__(self, server, port, timeout=None):
            sent["server"] = server
            sent["port"] = port

        def login(self, user, pwd):
            sent["from"] = user

        def sendmail(self, sender, to_list, msg):
            sent["to"] = to_list

        def quit(self):
            pass

    saved = smtplib.SMTP_SSL
    try:
        smtplib.SMTP_SSL = _FakeSMTP
        conf = {"sender_email": "s@qq.com", "sender_password": "pw",
                "receiver_email": "a@163.com, b@163.com"}  # 逗号多人
        ok = notify.push_email("标题", "正文", smtp_conf=conf)
        assert ok is True
        assert sent["from"] == "s@qq.com"
        assert sent["to"] == ["a@163.com", "b@163.com"]  # 已拆分
        assert sent["server"] == "smtp.qq.com" and sent["port"] == 465  # 缺省
    finally:
        smtplib.SMTP_SSL = saved


def test_push_email_failure_returns_false():
    class _BoomSMTP:
        def __init__(self, *a, **k):
            raise OSError("smtp 连接失败")

    saved = smtplib.SMTP_SSL
    try:
        smtplib.SMTP_SSL = _BoomSMTP
        conf = {"sender_email": "s@qq.com", "sender_password": "pw", "receiver_email": "a@163.com"}
        assert notify.push_email("t", "c", smtp_conf=conf) is False
    finally:
        smtplib.SMTP_SSL = saved


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn(); print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1; print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1; print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
