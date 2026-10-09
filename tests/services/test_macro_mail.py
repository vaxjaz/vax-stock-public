import json
from vaxstock.services.macro_mail import send_macro_email
from vaxstock.report.macro_email import build_macro_email


def test_mail_no_attachments_retry_dedupe_and_bounded_state(tmp_path):
    path = tmp_path / 'mail.json'
    calls = []
    def send(**kw):
        calls.append(kw)
        return len(calls) > 1
    kw = dict(trade_date='20260703', body='宏观 20260703', state_path=path,
              smtp_conf={'configured': True}, send_func=send)
    assert send_macro_email(**kw)['status'] == 'failed'
    assert not path.exists()
    assert send_macro_email(**kw)['status'] == 'sent'
    assert send_macro_email(**kw)['status'] == 'already_sent'
    assert calls[0]['attachments'] == []
    kw.update(trade_date='20260706', body='宏观 20260706')
    assert send_macro_email(**kw)['sent']
    assert json.loads(path.read_text()) == {'trade_date': '20260706'}


def test_missing_environment_does_not_become_neutral():
    body = build_macro_email({'market_overview': {'trade_date': '20260703'},
                             'stocks': [{'code': '600519'}]})
    assert '大盘状态: 待验证' in body
    assert '社融脉冲: 待验证' in body
    assert '600519' not in body
    assert '美股数据待验证' in body
