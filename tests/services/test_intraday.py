# -*- coding: utf-8 -*-
"""services.intraday 测试(零网络, monkeypatch seam) + 铁律校验器 + 依赖守卫(ast)。"""

import ast
import datetime as dt
import pathlib

import vaxstock.services.intraday as intra
from vaxstock.services._intraday_rules import enforce_intraday_rules

_REPO = pathlib.Path(__file__).resolve().parents[2]


# ── 铁律硬校验器(重点, 纯函数) ──
def test_enforce_flags_score():
    out = enforce_intraday_rules("趋势走弱。评分: 2.8 可介入")
    assert "[铁律校验]" in out
    assert "评分: 2.8" in out  # 原文保留可追溯
    assert "盘中未定论" in out


def test_enforce_flags_buy_price():
    out = enforce_intraday_rules("站上关键位, 建议买入价 12.50")
    assert "[铁律校验]" in out


def test_enforce_flags_fund_assertion():
    out = enforce_intraday_rules("主力大幅流入, 趋势转强")
    assert "[铁律校验]" in out


def test_enforce_clean_text_kept():
    clean = "趋势走弱, 倾向警惕, 盘中未定论"
    out = enforce_intraday_rules(clean)
    assert "[铁律校验]" not in out
    assert out == clean  # 干净且已含"盘中未定论" -> 原样不动


def test_enforce_appends_pending_when_missing():
    out = enforce_intraday_rules("趋势走弱, 倾向观察")  # 无越界但缺"盘中未定论"
    assert "[铁律校验]" not in out
    assert "盘中未定论" in out


# ── check_rule 表驱动 ──
def test_check_rule_table():
    assert intra.check_rule({"type": "price_above", "level": 69.0}, {"price": 70.0}) is True
    assert intra.check_rule({"type": "price_above", "level": 69.0}, {"price": 68.0}) is False
    assert intra.check_rule({"type": "price_below", "level": 66.0}, {"price": 65.0}) is True
    assert intra.check_rule({"type": "price_below", "level": 66.0}, {"price": 67.0}) is False
    assert intra.check_rule({"type": "pct_above", "level": 5.0}, {"change_pct": 6.0}) is True
    assert intra.check_rule({"type": "pct_below", "level": -4.0}, {"change_pct": -5.0}) is True
    assert intra.check_rule({"type": "pct_below", "level": -4.0}, {"change_pct": -3.0}) is False
    # 缺数据不误触发
    assert intra.check_rule({"type": "price_above", "level": 1.0}, {"price": None}) is False


# ── is_trading_time 边界(注入 now, 不依赖系统时钟) ──
def _weekday_date(target):  # 0=Mon..6=Sun
    d = dt.date(2026, 6, 1)
    while d.weekday() != target:
        d += dt.timedelta(days=1)
    return d


def test_is_trading_time_boundaries():
    mon = _weekday_date(0)
    sat = _weekday_date(5)
    at = lambda d, h, m: dt.datetime.combine(d, dt.time(h, m))
    assert intra.is_trading_time(now=at(mon, 10, 0)) is True     # 上午盘中
    assert intra.is_trading_time(now=at(mon, 14, 0)) is True     # 下午盘中
    assert intra.is_trading_time(now=at(mon, 9, 0)) is False     # 盘前
    assert intra.is_trading_time(now=at(mon, 12, 0)) is False    # 午休
    assert intra.is_trading_time(now=at(mon, 15, 10)) is False   # 收盘后
    assert intra.is_trading_time(now=at(sat, 10, 0)) is False    # 周末
    assert intra.is_trading_time(force=True, now=at(sat, 3, 0)) is True  # force 无视时段


# ── notify 链路: 命中 -> codex verdict 过铁律校验 -> 推送被调 ──
def test_notify_chain_verdict_through_validator():
    saved = (intra.fetch_lite, intra._codex_verdict, intra.push_wechat, intra.push_email)
    pushed = {}
    try:
        intra.fetch_lite = lambda code: {"code": code, "price": 70.0}
        # codex 故意返回越界文本(含评分), 验证 notify 用 enforce 包裹
        intra._codex_verdict = lambda snap, note: "评分: 2.8 建议买入"
        intra.push_wechat = lambda title, body, pushplus_token=None: pushed.update(wx=(title, body)) or True
        intra.push_email = lambda title, body, smtp_conf=None: pushed.update(em=(title, body)) or True

        intra.notify({"code": "002475", "name": "立讯精密", "type": "price_above",
                      "level": 69.0, "note": "站上69"},
                     {"price": 70.0, "change_pct": 2.0, "amount": 1.5e9, "amplitude_pct": 3.0})

        assert "wx" in pushed and "em" in pushed  # 两路推送都被调
        body = pushed["wx"][1]
        assert "codex盘中研判" in body
        assert "[铁律校验]" in body  # verdict 越界被校验器标注(证明经 enforce)
        assert "站上69" in body  # 原始告警 note 在
    finally:
        intra.fetch_lite, intra._codex_verdict, intra.push_wechat, intra.push_email = saved


def test_notify_no_codex_when_verdict_none():
    saved = (intra.fetch_lite, intra._codex_verdict, intra.push_wechat, intra.push_email)
    pushed = {}
    try:
        intra.fetch_lite = lambda code: {"code": code}
        intra._codex_verdict = lambda snap, note: None  # codex 不可用
        intra.push_wechat = lambda title, body, pushplus_token=None: pushed.update(wx=body) or True
        intra.push_email = lambda title, body, smtp_conf=None: True
        intra.notify({"code": "x", "name": "X", "type": "price_below", "level": 1.0, "note": "破位"},
                     {"price": 0.5, "change_pct": -5.0, "amount": 0})
        assert "codex盘中研判" not in pushed["wx"]  # 无 verdict 不附 codex 段
        assert "破位" in pushed["wx"]
    finally:
        intra.fetch_lite, intra._codex_verdict, intra.push_wechat, intra.push_email = saved


# ── 依赖守卫(ast 静态): intraday.py 不 import monolith / 东财 ──
def test_intraday_no_forbidden_imports():
    src = (_REPO / "src" / "vaxstock" / "services" / "intraday.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    tokens = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            tokens.append(node.module or "")
            tokens.extend(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            tokens.extend(a.name for a in node.names)
    forbidden = ["stock_report_enhanced", "eastmoney", "opportunity_scanner",
                 "hot_sector_scanner", "macro_indicators"]
    offenders = [t for t in tokens if any(fb in t for fb in forbidden)]
    assert offenders == [], f"intraday.py 不应 import monolith/东财: {offenders}"


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
