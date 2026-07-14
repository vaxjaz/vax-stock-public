# -*- coding: utf-8 -*-
"""services.intraday 测试(零网络, monkeypatch seam) + 铁律校验器 + 依赖守卫(ast)。"""

import ast
import datetime as dt
import json
import pathlib
import sys
import tempfile
import types

# The bundled test Python may not have project runtime deps installed.  The
# intraday tests monkeypatch push functions and never call real HTTP, so provide
# a tiny requests module before importing report.notify through intraday.
sys.modules.setdefault("requests", types.SimpleNamespace(
    post=lambda *a, **k: types.SimpleNamespace(json=lambda: {"code": 200})
))

import vaxstock.services.intraday as intra
from vaxstock.services._intraday_rules import enforce_intraday_rules

_REPO = pathlib.Path(__file__).resolve().parents[2]


class _FakeResp:
    """urllib 响应替身(支持 with ... as r: r.read()), 零网络。"""

    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


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


def test_enforce_t1_qualifier_whitelist():
    # 带"昨日/T-1/EOD/基准"限定词的评分/资金引用 = 合法(定稿值), 放行不标注
    assert "[铁律校验]" not in enforce_intraday_rules("昨日EOD评分2.5可介入, 今日放量站稳")
    assert "[铁律校验]" not in enforce_intraday_rules("T-1基准10日资金净流入明显, 今日跟随")
    # 无限定词的盘中新评分/资金断言 = 越界, 仍拦
    assert "[铁律校验]" in enforce_intraday_rules("盘中评分2.8, 可介入")
    assert "[铁律校验]" in enforce_intraday_rules("主力大幅流入, 趋势转强")
    # 买卖价一律拦(不分限定词)
    assert "[铁律校验]" in enforce_intraday_rules("昨日基准上, 建议买入价 12.50")


def test_parse_codex_json():
    ok = intra._parse_codex_json('{"verdict":"确认","direction":"看多","confidence":0.7}')
    assert ok and ok["verdict"] == "确认"
    # markdown 围栏包裹也能解析
    fenced = intra._parse_codex_json('```json\n{"verdict":"噪音"}\n```')
    assert fenced and fenced["verdict"] == "噪音"
    # 非 JSON / 空 -> None
    assert intra._parse_codex_json("抱歉无法解析") is None
    assert intra._parse_codex_json(None) is None


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


# ── notify 链路(C线): codex JSON -> reasoning 过铁律校验 -> 渲染推送 + 冻结 forecast ──
_NOTIFY_SEAMS = ("fetch_lite", "fetch_market_ctx", "_get_concepts", "_codex_verdict",
                 "load_t1_baseline", "record_forecast", "push_wechat", "push_email",
                 "_maybe_autocommit_intraday_forecast")


def _save_notify():
    return {n: getattr(intra, n) for n in _NOTIFY_SEAMS}


def _restore_notify(saved):
    for n, v in saved.items():
        setattr(intra, n, v)


def test_notify_json_verdict_render_and_freeze():
    saved = _save_notify()
    pushed, fc = {}, {}
    try:
        intra.fetch_lite = lambda code: {"code": code, "price": 70.0, "as_of": "14:30:00"}
        intra.fetch_market_ctx = lambda: {"regime": "momentum", "overview": {}}
        intra._get_concepts = lambda code: ["消费电子"]   # 在概念池 -> 写 forecast
        intra.load_t1_baseline = lambda code: {"score": 2.5, "grade": "可考虑介入",
            "position_20d_pct": 80, "main_inflow_10d": 1e8, "np_yoy": 30, "baseline_date": "2026-06-25"}
        # codex 出 JSON; reasoning 含无限定词资金断言(越界) -> enforce 标注
        intra._codex_verdict = lambda snap, note, **kw: (
            '{"verdict":"确认","direction":"看多","confidence":0.7,"horizon":"3日",'
            '"thesis_tags":["放量突破"],"falsify_if":"跌破MA20","news_refs":[],'
            '"reasoning":"主力大幅流入, 趋势转强"}')
        intra.record_forecast = lambda *a, **k: fc.update(called=True, args=a) or True
        intra._maybe_autocommit_intraday_forecast = lambda: fc.update(autocommit=True) or {"status": "test"}
        intra.push_wechat = lambda title, body, pushplus_token=None: pushed.update(wx=(title, body)) or True
        intra.push_email = lambda title, body, smtp_conf=None: pushed.update(em=(title, body)) or True

        intra.notify({"code": "002475", "name": "立讯精密", "type": "price_above",
                      "level": 69.0, "note": "站上69"},
                     {"price": 70.0, "change_pct": 2.0, "amount": 1.5e9, "amplitude_pct": 3.0,
                      "trade_date": "2026-06-26"})

        assert "wx" in pushed and "em" in pushed
        body = pushed["wx"][1]
        assert "盘中研判" in body
        assert "状态: 确认" in body and "方向: 看多" in body and "置信: 70%" in body
        assert "[铁律校验]" in body          # reasoning 无限定词资金断言被标注
        assert "站上69" in body              # 原始告警 note 在
        # forecast 被冻结: trade_date 锚 quote.trade_date(非 now), inputs_ref 冻结 t1+快照+regime
        assert fc.get("called") is True
        code_a, td_a, note_a, inputs_ref, structured, reasoning, falsify = fc["args"]
        assert code_a == "002475" and td_a == "2026-06-26"
        assert inputs_ref["t1_baseline"]["baseline_date"] == "2026-06-25"
        assert inputs_ref["lite_snapshot"]["code"] == "002475"
        assert inputs_ref["regime"] == "momentum"
        assert structured["verdict"] == "确认" and falsify == "跌破MA20"
        assert fc.get("autocommit") is True
    finally:
        _restore_notify(saved)


def test_notify_no_research_when_codex_none():
    saved = _save_notify()
    pushed, fc = {}, {}
    try:
        intra.fetch_lite = lambda code: {"code": code}
        intra.fetch_market_ctx = lambda: {"regime": None, "overview": {}}
        intra._get_concepts = lambda code: []
        intra.load_t1_baseline = lambda code: None
        intra._codex_verdict = lambda snap, note, **kw: None        # codex 不可用
        intra.record_forecast = lambda *a, **k: fc.update(called=True) or True
        intra.push_wechat = lambda title, body, pushplus_token=None: pushed.update(wx=body) or True
        intra.push_email = lambda title, body, smtp_conf=None: True
        intra.notify({"code": "x", "name": "X", "type": "price_below", "level": 1.0, "note": "破位"},
                     {"price": 0.5, "change_pct": -5.0, "amount": 0, "trade_date": "2026-06-26"})
        assert "盘中研判" not in pushed["wx"]      # 无 verdict 不附研判段
        assert "破位" in pushed["wx"]
        assert fc.get("called") is not True        # 无结构化预测 -> 不写 forecast
    finally:
        _restore_notify(saved)


def test_notify_pool_outsider_no_forecast():
    """池外票(无 T-1 基准 且 不在概念池): 技术面研判照出, 但不写 forecast(防回测污染)。"""
    saved = _save_notify()
    pushed, fc = {}, {}
    try:
        intra.fetch_lite = lambda code: {"code": code, "price": 9.9}
        intra.fetch_market_ctx = lambda: {"regime": "value", "overview": {}}
        intra._get_concepts = lambda code: []        # 不在概念池
        intra.load_t1_baseline = lambda code: None    # 无 T-1 基准
        intra._codex_verdict = lambda snap, note, **kw: (
            '{"verdict":"噪音","direction":"中性","confidence":0.3,"horizon":"日内",'
            '"thesis_tags":[],"falsify_if":"放量破位","news_refs":[],"reasoning":"小幅波动, 倾向观察"}')
        intra.record_forecast = lambda *a, **k: fc.update(called=True) or True
        intra.push_wechat = lambda title, body, pushplus_token=None: pushed.update(wx=body) or True
        intra.push_email = lambda title, body, smtp_conf=None: True
        intra.notify({"code": "999999", "name": "临时票", "type": "pct_above", "level": 5.0, "note": "异动"},
                     {"price": 9.9, "change_pct": 6.0, "amount": 1e8, "trade_date": "2026-06-26"})
        assert "盘中研判" in pushed["wx"]           # 研判照出
        assert "状态: 噪音" in pushed["wx"]
        assert fc.get("called") is not True         # 池外 guard: 不写 forecast
    finally:
        _restore_notify(saved)


def test_notify_codex_nonjson_degrades():
    """codex 返回非 JSON -> 降级纯价位告警(无研判段, 不崩, 不写 forecast)。"""
    saved = _save_notify()
    pushed, fc = {}, {}
    try:
        intra.fetch_lite = lambda code: {"code": code, "price": 70.0}
        intra.fetch_market_ctx = lambda: {"regime": "momentum", "overview": {}}
        intra._get_concepts = lambda code: ["消费电子"]
        intra.load_t1_baseline = lambda code: None
        intra._codex_verdict = lambda snap, note, **kw: "抱歉我无法解析(自由文本, 非JSON)"
        intra.record_forecast = lambda *a, **k: fc.update(called=True) or True
        intra.push_wechat = lambda title, body, pushplus_token=None: pushed.update(wx=body) or True
        intra.push_email = lambda title, body, smtp_conf=None: True
        intra.notify({"code": "002475", "name": "立讯", "type": "price_above", "level": 69.0, "note": "站上69"},
                     {"price": 70.0, "change_pct": 2.0, "amount": 1e9, "trade_date": "2026-06-26"})
        assert "盘中研判" not in pushed["wx"]   # 解析失败 -> 无研判段
        assert "站上69" in pushed["wx"]          # 价位告警仍在
        assert fc.get("called") is not True      # 不写 forecast
    finally:
        _restore_notify(saved)


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


# ── C2b: fetch_market_ctx 走 /market 缓存(消费者), 解析 / 失败降级 ──
def test_fetch_market_ctx_parses():
    saved = intra.request
    try:
        intra.request = types.SimpleNamespace(urlopen=lambda url, timeout=None: _FakeResp(
            {"regime": "tech_bull",
             "overview": {"up_count": 3000, "down_count": 1500,
                          "limit_up_count": 40, "limit_down_count": 5}}))
        ctx = intra.fetch_market_ctx()
        assert ctx["regime"] == "tech_bull"
        assert ctx["overview"]["up_count"] == 3000
        assert ctx["overview"]["limit_down_count"] == 5
    finally:
        intra.request = saved


def test_fetch_market_ctx_degrades_on_error():
    saved = intra.request

    def _boom(*a, **k):
        raise OSError("connection refused")

    try:
        intra.request = types.SimpleNamespace(urlopen=_boom)
        ctx = intra.fetch_market_ctx()
        assert ctx == {"regime": None, "overview": {}}  # 降级, 不臆造
    finally:
        intra.request = saved


# ── C2b: _codex_verdict 上下文注入(口径铁律: regime 标实时, 涨跌家数标T日收盘滞后) ──
def test_codex_verdict_injects_context_labels():
    saved = (intra.call_codex, intra._CODEX_ENABLED, intra._CODEX_TOKEN)
    cap = {}
    try:
        intra._CODEX_ENABLED, intra._CODEX_TOKEN = True, "TK"
        intra.call_codex = lambda system, user, **kw: cap.update(user=user) or "盘中倾向: 观察"
        out = intra._codex_verdict(
            {"code": "002475", "price": 70.0}, "站上69",
            market_ctx={"regime": "tech_bull",
                        "overview": {"up_count": 3000, "down_count": 1500,
                                     "limit_up_count": 40, "limit_down_count": 5}},
            concepts=["消费电子", "AI硬件"], fire_count=2)
        assert out == "盘中倾向: 观察"
        um = cap["user"]
        # 口径铁律(P0): 这两条标注一字不可省, 否则 codex 误读为实时大盘
        assert "T日收盘聚合, 盘中滞后" in um
        assert "新浪指数实时算" in um
        assert "涨3000/跌1500/涨停40/跌停5" in um
        assert "tech_bull" in um
        assert "消费电子" in um and "AI硬件" in um
        assert "今日第2次触发" in um
        assert "站上69" in um and "002475" in um
    finally:
        intra.call_codex, intra._CODEX_ENABLED, intra._CODEX_TOKEN = saved


def test_codex_verdict_degrades_missing_ctx_to_pending():
    saved = (intra.call_codex, intra._CODEX_ENABLED, intra._CODEX_TOKEN)
    cap = {}
    try:
        intra._CODEX_ENABLED, intra._CODEX_TOKEN = True, "TK"
        intra.call_codex = lambda system, user, **kw: cap.update(user=user) or "ok"
        intra._codex_verdict({"code": "x"}, "破位",
                             market_ctx={"regime": None, "overview": {}},
                             concepts=[], fire_count=None)
        um = cap["user"]
        assert "待获取" in um        # regime 缺失不臆造
        assert "今日第1次触发" in um  # fire_count None -> 1
        assert "无标注" in um        # 无概念标签
    finally:
        intra.call_codex, intra._CODEX_ENABLED, intra._CODEX_TOKEN = saved


def test_codex_verdict_none_when_disabled():
    saved = (intra.call_codex, intra._CODEX_ENABLED, intra._CODEX_TOKEN)
    called = {"v": False}
    try:
        intra._CODEX_TOKEN = None  # 无 token -> 早退, 不调 codex
        intra.call_codex = lambda *a, **k: called.__setitem__("v", True) or "x"
        assert intra._codex_verdict({"code": "x"}, "n", market_ctx={"regime": "m"}) is None
        assert called["v"] is False
    finally:
        intra.call_codex, intra._CODEX_ENABLED, intra._CODEX_TOKEN = saved


# ── C2b: _get_concepts 惰性加载 + 进程级缓存 + 失败降级 ──
def test_get_concepts_lazy_loads_and_caches():
    import vaxstock.config as cfg
    saved_map, saved_load, saved_holdings = intra._concepts_map, cfg.load_watchlist, cfg.load_holdings
    calls = {"n": 0}
    try:
        intra._concepts_map = None  # 复位惰性缓存

        def _load():
            calls["n"] += 1
            return {"002475": "立讯"}, {"002475": ["消费电子", "AI硬件"]}

        cfg.load_watchlist = _load
        cfg.load_holdings = lambda: {}
        assert intra._get_concepts("002475") == ["消费电子", "AI硬件"]
        assert intra._get_concepts("000001") == []          # 未标注 -> 空
        assert intra._get_concepts("002475") == ["消费电子", "AI硬件"]
        assert calls["n"] == 1                               # 惰性: 只读一次(进程级缓存)
    finally:
        intra._concepts_map, cfg.load_watchlist, cfg.load_holdings = saved_map, saved_load, saved_holdings


def test_get_concepts_prefers_holding_concepts_and_keeps_holding_only_symbols():
    import vaxstock.config as cfg
    saved_map, saved_load, saved_holdings = intra._concepts_map, cfg.load_watchlist, cfg.load_holdings
    try:
        intra._concepts_map = None
        cfg.load_watchlist = lambda: ({"600000": "watch"}, {"600000": ["watch"]})
        cfg.load_holdings = lambda: {
            "600000": {"concepts": ["holding"]},
            "600001": {"concepts": ["holding-only"]},
        }
        assert intra._get_concepts("600000") == ["holding"]
        assert intra._get_concepts("600001") == ["holding-only"]
    finally:
        intra._concepts_map, cfg.load_watchlist, cfg.load_holdings = saved_map, saved_load, saved_holdings


def test_get_concepts_degrades_to_empty_on_error():
    import vaxstock.config as cfg
    saved_map, saved_load, saved_holdings = intra._concepts_map, cfg.load_watchlist, cfg.load_holdings
    try:
        intra._concepts_map = None

        def _boom():
            raise OSError("watchlist.json 损坏")

        cfg.load_watchlist = _boom
        assert intra._get_concepts("002475") == []  # 加载失败 -> 空, 不臆造概念
        assert intra._concepts_map == {}             # 缓存空 dict, 不反复重试
    finally:
        intra._concepts_map, cfg.load_watchlist, cfg.load_holdings = saved_map, saved_load, saved_holdings



# ---- D-line current_tasks consumer ----

def _sample_dline_task(target="20260706"):
    return {
        "task_id": f"20260703_{target}_002475_d_observe_llm_v2",
        "line": "D",
        "code": "002475",
        "name": "立讯精密",
        "baseline_trade_date": "20260703",
        "target_trade_date": target,
        "plan_version": "d_observe_llm_v2",
        "observation": {
            "observe_intent": "验证C线watch是否被盘中价格修复证实",
            "primary_risk": "继续弱于MA20",
            "trigger_blueprints": [
                {
                    "trigger_type": "breakdown_confirm",
                    "severity": "high",
                    "condition": {"all": [{"field": "price_vs_ma20_pct", "op": "<", "value": -2.0}], "any": []},
                    "why": "盘中价格继续低于MA20超过2%",
                    "expected_feedback_to_c": "watch -> avoid_review",
                }
            ],
            "c_line_feedback_focus": "action/confidence",
            "falsify_if": "重新站回MA20",
        },
        "evidence_pack": {
            "A_eod": {"metrics": {"ma5": 98.0, "ma20": 100.0, "ma60": 110.0, "volume_ratio_5d": 1.1, "rsi_14": 45.0}},
            "C_prediction": {"prediction": {"action": "watch", "direction": "up", "confidence": 0.6}},
            "B_prediction_history_summary": {
                "available": True, "evaluated": 6, "avg_ret": 0.0039,
                "positive_ret_count": 3,
            },
            "E_context": {"earnings": {
                "latest_report": {"period": "20260331", "net_profit_yoy": 20.24},
                "next_report": {"period": "20260630", "expected_ann_date": "20260820", "status": "scheduled"},
            }},
        },
    }


def test_load_rules_missing_file_disables_legacy_defaults():
    saved = intra.WATCH_RULES_FILE
    with tempfile.TemporaryDirectory(prefix="vax_intra_rules_") as d:
        try:
            intra.WATCH_RULES_FILE = str(pathlib.Path(d) / "missing_watch_rules.json")
            assert intra.load_rules() == []
        finally:
            intra.WATCH_RULES_FILE = saved


def test_load_dline_tasks_filters_target_and_requires_blueprints():
    saved = intra.DLINE_TASKS_FILE
    with tempfile.TemporaryDirectory(prefix="vax_dline_tasks_") as d:
        p = pathlib.Path(d) / "current_tasks.json"
        p.write_text(json.dumps({"tasks": [
            _sample_dline_task("20260706"),
            _sample_dline_task("20260707"),
            {"code": "600000", "target_trade_date": "20260706", "observation": {"trigger_blueprints": []}},
        ]}, ensure_ascii=False), encoding="utf-8")
        try:
            intra.DLINE_TASKS_FILE = str(p)
            rows = intra.load_dline_tasks("20260706")
            assert [r["code"] for r in rows] == ["002475"]
        finally:
            intra.DLINE_TASKS_FILE = saved


def test_check_dline_task_recomputes_live_ma_deviation():
    task = _sample_dline_task()
    idx, bp, values = intra.check_dline_task(task, {"price": 96.0, "change_pct": -1.5, "amplitude_pct": 3.2, "amount": 2e8})
    assert idx == 0
    assert bp["trigger_type"] == "breakdown_confirm"
    assert round(values["price_vs_ma20_pct"], 2) == -4.0
    assert values["change_pct"] == -1.5
    assert values["amount_yi"] == 2.0


def test_notify_dline_freezes_forecast_and_pushes():
    saved = (intra.record_forecast, intra.start_trigger_evolution,
             intra.push_wechat, intra.push_email,
             intra._maybe_autocommit_intraday_forecast)
    out = {}
    try:
        intra.record_forecast = lambda *a, **k: out.update(forecast=a) or True
        intra.start_trigger_evolution = lambda *a, **k: out.update(evolution=True) or {"status": "written"}
        intra._maybe_autocommit_intraday_forecast = lambda: out.update(autocommit=True) or {"status": "test"}
        intra.push_wechat = lambda title, body, pushplus_token=None: out.update(wx=(title, body)) or True
        intra.push_email = lambda title, body, smtp_conf=None: out.update(email=(title, body)) or True
        task = _sample_dline_task()
        quote = {"code": "002475", "name": "立讯精密", "price": 96.0, "change_pct": -1.5,
                 "amplitude_pct": 3.2, "amount": 2e8, "trade_date": "20260706", "trade_time": "10:00:00"}
        idx, bp, values = intra.check_dline_task(task, quote)
        intra.notify_dline(task, quote, bp, values, fire_count=1)
        assert "wx" in out and "email" in out
        assert "[D线]" in out["wx"][0]
        body = out["wx"][1]
        assert "【真实历史结果】" in body
        assert "live已核验6次，平均收益+0.39%，3/6次收益为正" in body
        assert "【公司财报】" in body
        assert "预计披露 2026-08-20" in body
        assert "【今日策略】" in body
        assert "【实时行情】" in body
        assert "现价: 96.00" in body
        assert "涨跌幅: -1.50%" in body
        assert "振幅: 3.20%" in body
        assert "成交额: 2.00亿" in body
        assert "MA偏离: MA5 -2.04%" in body
        assert "MA20 -4.00%" in body
        assert "MA60 -12.73%" in body
        assert "【C线原始动作/方向/置信度】" in body
        assert "action=watch" in body
        assert "direction=up" in body
        assert "confidence=60%" in body
        assert "【LLM客观评价】" in body
        assert "【C线反哺线索】" in body
        args = out["forecast"]
        assert args[0] == "002475"
        assert args[1] == "20260706"
        assert args[3]["dline_task_id"] == task["task_id"]
        assert args[4]["source"] == "dline_task_blueprint"
        assert out.get("autocommit") is True
    finally:
        (intra.record_forecast, intra.start_trigger_evolution, intra.push_wechat,
         intra.push_email, intra._maybe_autocommit_intraday_forecast) = saved


def test_run_consumes_dline_current_tasks():
    saved = (intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes, intra.notify_dline,
             intra.record_task_observation, intra.record_evolution_observation,
             intra.restore_active_evolutions, intra.load_dline_trigger_facts,
             intra.run_market_health_check, intra.notify_market_health, intra.request)
    calls = []
    coverage_calls = []
    health_calls = []
    health_notifications = []
    try:
        intra.load_rules = lambda: []
        intra.load_dline_tasks = lambda: [_sample_dline_task()]
        intra.record_task_observation = lambda task, quote, **kwargs: (
            coverage_calls.append((task["code"], quote["trade_date"])) or {"status": "written"}
        )
        intra.record_evolution_observation = lambda *args, **kwargs: {"status": "no_active", "written": 0}
        intra.restore_active_evolutions = lambda *args, **kwargs: {"written": 0, "duplicates": 0, "skipped": 0}
        intra.run_market_health_check = lambda **kwargs: (
            health_calls.append(kwargs) or {
                "status": "written",
                "notifications": [{"event_type": "portfolio_synchronized_drop"}],
            }
        )
        intra.notify_market_health = lambda events: health_notifications.extend(events)
        intra.load_dline_trigger_facts = lambda *args, **kwargs: {}
        intra.fetch_quotes = lambda codes: {"002475": {"code": "002475", "name": "立讯精密", "price": 96.0,
            "change_pct": -1.5, "amplitude_pct": 3.2, "amount": 2e8, "trade_date": "20260706"}}
        intra.notify_dline = lambda task, quote, bp, values, fire_count=None: calls.append((task["code"], bp["trigger_type"], fire_count))
        intra.request = types.SimpleNamespace(urlopen=lambda *a, **k: _FakeResp({"regime": "x"}))
        intra.run(once=True, force=True)
        assert calls == [("002475", "breakdown_confirm", 1)]
        assert coverage_calls == [("002475", "20260706")]
        assert len(health_calls) == 1
        assert health_calls[0]["force"] is True
        assert health_calls[0]["quotes"]["002475"]["price"] == 96.0
        assert health_notifications == [{"event_type": "portfolio_synchronized_drop"}]
    finally:
        (intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes, intra.notify_dline,
         intra.record_task_observation, intra.record_evolution_observation,
             intra.restore_active_evolutions, intra.load_dline_trigger_facts,
             intra.run_market_health_check, intra.notify_market_health, intra.request) = saved
# ── C2b: run() 今日触发计数 —— 同 code 多规则递增; 跨日清零 ──
def test_run_fire_count_increments_per_code():
    saved = (intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes, intra.notify,
             intra.record_task_observation, intra.record_evolution_observation,
             intra.restore_active_evolutions, intra.load_dline_trigger_facts,
             intra.run_market_health_check, intra.notify_market_health, intra.request)
    calls = []
    coverage_calls = []
    try:
        intra.load_rules = lambda: [
            {"code": "002475", "name": "立讯", "type": "price_above", "level": 69.0, "note": "a"},
            {"code": "002475", "name": "立讯", "type": "pct_above", "level": 1.0, "note": "b"},
        ]
        intra.load_dline_tasks = lambda: []
        intra.record_task_observation = lambda *args, **kwargs: {"status": "written"}
        intra.record_evolution_observation = lambda *args, **kwargs: {"status": "no_active", "written": 0}
        intra.restore_active_evolutions = lambda *args, **kwargs: {"written": 0, "duplicates": 0, "skipped": 0}
        intra.run_market_health_check = lambda **kwargs: {"status": "no_change", "notifications": []}
        intra.notify_market_health = lambda events: None
        intra.load_dline_trigger_facts = lambda *args, **kwargs: {}
        intra.fetch_quotes = lambda codes: {"002475": {"name": "立讯", "price": 70.0, "change_pct": 2.0}}
        intra.notify = lambda rule, quote, fire_count=None: calls.append((rule["type"], fire_count))
        intra.request = types.SimpleNamespace(urlopen=lambda *a, **k: _FakeResp({"regime": "x"}))
        intra.run(once=True, force=True)
        # 同 code 两条规则同轮均触发 -> 计数 1,2
        assert sorted(fc for _, fc in calls) == [1, 2]
    finally:
        (intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes, intra.notify,
         intra.record_task_observation, intra.record_evolution_observation,
             intra.restore_active_evolutions, intra.load_dline_trigger_facts,
             intra.run_market_health_check, intra.notify_market_health, intra.request) = saved


def test_run_fire_count_resets_on_new_day():
    _Stop = type("_Stop", (Exception,), {})
    saved = (intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes, intra.notify,
             intra.record_task_observation, intra.record_evolution_observation,
             intra.restore_active_evolutions, intra.load_dline_trigger_facts,
             intra.run_market_health_check, intra.notify_market_health, intra.request,
             intra.dt, intra.time)
    calls = []
    rule_a = {"code": "002475", "name": "立讯", "type": "price_above", "level": 69.0, "note": "a"}
    rule_b = {"code": "002475", "name": "立讯", "type": "pct_above", "level": 1.0, "note": "b"}
    ls = {"n": 0}

    def _load():  # call1(loop前)=A; call2(iter1热重载)=A; call3(iter2热重载)=A+B
        ls["n"] += 1
        return [dict(rule_a)] if ls["n"] <= 2 else [dict(rule_a), dict(rule_b)]

    dates = [dt.date(2026, 6, 25), dt.date(2026, 6, 26), dt.date(2026, 6, 26)]
    di = {"i": 0}

    def _today():
        v = dates[min(di["i"], len(dates) - 1)]
        di["i"] += 1
        return v

    sl = {"n": 0}

    def _sleep(_s):
        sl["n"] += 1
        if sl["n"] >= 2:  # iter1、iter2 各处理完后各 sleep 一次, 第2次后停
            raise _Stop()

    try:
        intra.load_rules = _load
        intra.load_dline_tasks = lambda: []
        intra.record_task_observation = lambda *args, **kwargs: {"status": "written"}
        intra.record_evolution_observation = lambda *args, **kwargs: {"status": "no_active", "written": 0}
        intra.restore_active_evolutions = lambda *args, **kwargs: {"written": 0, "duplicates": 0, "skipped": 0}
        intra.run_market_health_check = lambda **kwargs: {"status": "no_change", "notifications": []}
        intra.notify_market_health = lambda events: None
        intra.load_dline_trigger_facts = lambda *args, **kwargs: {}
        intra.fetch_quotes = lambda codes: {"002475": {"name": "立讯", "price": 70.0, "change_pct": 2.0}}
        intra.notify = lambda rule, quote, fire_count=None: calls.append((rule["type"], fire_count))
        intra.request = types.SimpleNamespace(urlopen=lambda *a, **k: _FakeResp({"regime": "x"}))
        intra.dt = types.SimpleNamespace(
            date=types.SimpleNamespace(today=_today),
            datetime=dt.datetime, time=dt.time, timedelta=dt.timedelta)
        intra.time = types.SimpleNamespace(sleep=_sleep)
        try:
            intra.run(once=False, force=True)
        except _Stop:
            pass
        # iter1(6/25): A=1; iter2(6/26): A重新生效=1，随后B=2。
        assert calls[-2:] == [("price_above", 1), ("pct_above", 2)]
    finally:
        (intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes, intra.notify,
         intra.record_task_observation, intra.record_evolution_observation,
             intra.restore_active_evolutions, intra.load_dline_trigger_facts,
             intra.run_market_health_check, intra.notify_market_health, intra.request,
         intra.dt, intra.time) = saved


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

def test_close_review_target_requires_one_consistent_task_date():
    assert intra._close_review_target([
        {"target_trade_date": "20260713"},
        {"target_trade_date": "20260713"},
    ]) == "20260713"
    assert intra._close_review_target([
        {"target_trade_date": "20260713"},
        {"target_trade_date": "20260714"},
    ]) is None
    assert intra._close_review_target([]) is None


def test_run_close_review_delegates_to_idempotent_service():
    from vaxstock.services import daily_action
    saved = (daily_action.refresh_and_send_close_review, intra.finalize_evolutions,
             intra.finalize_observation_coverage)
    calls = []
    try:
        intra.finalize_evolutions = lambda *args, **kwargs: {"status": "finalized", "written": 1}
        intra.finalize_observation_coverage = lambda *args, **kwargs: {"status": "finalized", "written": 1}
        daily_action.refresh_and_send_close_review = lambda **kwargs: (
            calls.append(kwargs) or {
                "action": {"status": "written"},
                "mail": {"status": "sent"},
            }
        )
        result = intra._run_close_review([
            {"target_trade_date": "20260713"},
            {"target_trade_date": "20260713"},
        ])
        assert result["mail"]["status"] == "sent"
        assert len(calls) == 1
        assert calls[0]["target_trade_date"] == "20260713"
        assert callable(calls[0]["reference_quote_loader"])
    finally:
        (daily_action.refresh_and_send_close_review, intra.finalize_evolutions,
         intra.finalize_observation_coverage) = saved

def test_matching_dline_triggers_returns_every_matching_type():
    task = {
        "observation": {"trigger_blueprints": [
            {"trigger_type": "reclaim_confirm", "condition": {}},
            {"trigger_type": "breakdown_confirm", "condition": {}},
        ]},
        "evidence_pack": {"A_eod": {"metrics": {}}},
    }
    matches = intra.matching_dline_triggers(task, {"price": 10.0})
    assert [row[1]["trigger_type"] for row in matches] == [
        "reclaim_confirm", "breakdown_confirm",
    ]


def test_existing_dline_fired_keys_restores_each_frozen_trigger_type():
    saved = intra.load_dline_trigger_facts
    task = {
        "task_id": "task_601138", "code": "601138",
        "target_trade_date": "20260713",
    }
    try:
        intra.load_dline_trigger_facts = lambda target: {"601138": [
            {"task_id": "task_601138", "trigger_type": "reclaim_confirm"},
            {"task_id": "task_601138", "trigger_type": "breakdown_confirm"},
            {"task_id": "different_task", "trigger_type": "noise_filter"},
        ]}
        restored, counts = intra._existing_dline_runtime_state([task])
    finally:
        intra.load_dline_trigger_facts = saved
    assert restored == {
        ("dline", "task_601138", "reclaim_confirm"),
        ("dline", "task_601138", "breakdown_confirm"),
    }
    assert counts == {"601138": 2}


def test_run_restores_fired_keys_when_tasks_appear_after_startup():
    saved = (
        intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes,
        intra.notify_dline, intra.record_task_observation,
        intra.record_evolution_observation, intra.restore_active_evolutions,
        intra.load_dline_trigger_facts, intra.run_market_health_check,
        intra.notify_market_health, intra.request,
    )
    task = _sample_dline_task()
    loads = [[], [task]]
    notifications = []
    try:
        intra.load_rules = lambda: []
        intra.load_dline_tasks = lambda: loads.pop(0) if loads else [task]
        intra.record_evolution_observation = lambda *args, **kwargs: {"status": "no_active", "written": 0}
        intra.restore_active_evolutions = lambda *args, **kwargs: {"written": 0, "duplicates": 0, "skipped": 0}
        intra.run_market_health_check = lambda **kwargs: {"status": "no_change", "notifications": []}
        intra.notify_market_health = lambda events: None
        intra.load_dline_trigger_facts = lambda target: {"002475": [{
            "task_id": task["task_id"], "trigger_type": "reclaim_confirm",
        }]}
        intra.record_task_observation = lambda *args, **kwargs: {"status": "written"}
        intra.fetch_quotes = lambda codes: {"002475": {
            "code": "002475", "price": 96.0, "change_pct": -1.5,
            "amplitude_pct": 3.2, "amount": 2e8, "trade_date": "20260706",
        }}
        intra.notify_dline = lambda task, quote, bp, values, fire_count=None: (
            notifications.append((bp["trigger_type"], fire_count))
        )
        intra.request = types.SimpleNamespace(
            urlopen=lambda *args, **kwargs: _FakeResp({"regime": "x"})
        )
        intra.run(once=True, force=True)
        assert notifications == [("breakdown_confirm", 2)]
    finally:
        (
            intra.load_rules, intra.load_dline_tasks, intra.fetch_quotes,
            intra.notify_dline, intra.record_task_observation,
            intra.record_evolution_observation, intra.restore_active_evolutions,
            intra.load_dline_trigger_facts, intra.run_market_health_check,
            intra.notify_market_health, intra.request,
        ) = saved
