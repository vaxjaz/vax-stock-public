# -*- coding: utf-8 -*-
"""research.layer2_eval 测试(MR-Eval E2, 零网络, 构造 jsonl/joined)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/research/test_layer2_eval.py -q
     PYTHONPATH=src python3 tests/research/test_layer2_eval.py   # 无 pytest
"""

import pathlib
import shutil
import tempfile

import vaxstock.research.layer2_eval as l2
import vaxstock.services.eval_recorder as er


def _set_tmp(d):
    saved = (er.SNAPSHOTS_FILE, er.RESULTS_FILE)
    er.SNAPSHOTS_FILE = pathlib.Path(d) / "factor_snapshots.jsonl"
    er.RESULTS_FILE = pathlib.Path(d) / "factor_results.jsonl"
    return saved


def _restore(saved):
    er.SNAPSHOTS_FILE, er.RESULTS_FILE = saved


def _snap(code, score, regime="momentum", macro="🟢 看多", td="20260625", price=10.0):
    return {
        "schema_version": 1, "trade_date": td, "code": code, "name": code,
        "group": "watchlist", "price_at_snapshot": price,
        "metrics": {"right_side_score": score},
        "market": {"regime": regime, "macro_regime": macro},
    }


def _res(code, ret, excess, td="20260625", complete=True):
    return {"trade_date": td, "code": code, "ret": ret, "mkt_ret": {},
            "excess": excess, "complete": complete}


# ── 1. load_joined: snapshot+result join; 缺 result -> None ──
def test_load_joined():
    d = tempfile.mkdtemp(prefix="vaxl2_")
    saved = _set_tmp(d)
    try:
        er._append_jsonl(er.SNAPSHOTS_FILE, _snap("000001", 2.5))
        er._append_jsonl(er.SNAPSHOTS_FILE, _snap("000002", 0.3))   # 无对应 result
        er._append_jsonl(er.RESULTS_FILE, _res("000001", {"5": 0.05}, {"5": 0.02}))
        joined = l2.load_joined()
        assert len(joined) == 2
        by = {row["snapshot"]["code"]: row for row in joined}
        assert by["000001"]["result"] is not None
        assert by["000001"]["result"]["excess"]["5"] == 0.02
        assert by["000002"]["result"] is None       # 未回填标 None
    finally:
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


def test_load_joined_takes_latest_result():
    d = tempfile.mkdtemp(prefix="vaxl2_")
    saved = _set_tmp(d)
    try:
        er._append_jsonl(er.SNAPSHOTS_FILE, _snap("000001", 2.5))
        # 同 key 两行 results(部分→完整), 取最新(后写)
        er._append_jsonl(er.RESULTS_FILE, _res("000001", {"5": 0.05}, {"5": 0.02}, complete=False))
        er._append_jsonl(er.RESULTS_FILE, _res("000001", {"5": 0.05, "10": 0.09}, {"5": 0.02, "10": 0.03}))
        joined = l2.load_joined()
        assert joined[0]["result"]["complete"] is True
        assert "10" in joined[0]["result"]["ret"]
    finally:
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


# ── 2. tag_decision: 四档边界 + 无评分 ──
def test_tag_decision_boundaries():
    assert l2.tag_decision(_snap("x", 3.5)) == l2.DECISION_STRONG
    assert l2.tag_decision(_snap("x", 3.4)) == l2.DECISION_ENTER
    assert l2.tag_decision(_snap("x", 2.6)) == l2.DECISION_ENTER
    assert l2.tag_decision(_snap("x", 2.0)) == l2.DECISION_ENTER
    assert l2.tag_decision(_snap("x", 1.9)) == l2.DECISION_WATCH
    assert l2.tag_decision(_snap("x", 0.5)) == l2.DECISION_WATCH
    assert l2.tag_decision(_snap("x", 0.3)) == l2.DECISION_AVOID
    assert l2.tag_decision({"metrics": {}}) == l2.DECISION_NONE   # 无评分不臆造


# ── 3. bucket_key: regime + macro_regime ──
def test_bucket_key():
    assert l2.bucket_key(_snap("x", 2.5, regime="momentum", macro="🔴 强看空")) == "momentum|🔴 强看空"
    assert l2.bucket_key({"market": {}}) == "regime待验证|宏观待验证"   # 缺失诚实标注
    assert l2.bucket_key({}) == "regime待验证|宏观待验证"


# ── 4. analyze 分桶(核心): 按桶分别统计不混合; 胜率/excess 正确; <min 标不足; 未回填不计入 ──
def test_analyze_buckets_not_mixed():
    joined = [
        # 桶A momentum|🟢 看多, 决策 可考虑介入(score 2.5), 3 个已回填 + 1 个未回填
        {"snapshot": _snap("A1", 2.5, "momentum", "🟢 看多"), "result": _res("A1", {"5": 0.05}, {"5": 0.02})},
        {"snapshot": _snap("A2", 2.5, "momentum", "🟢 看多"), "result": _res("A2", {"5": 0.03}, {"5": 0.01})},
        {"snapshot": _snap("A3", 2.5, "momentum", "🟢 看多"), "result": _res("A3", {"5": -0.02}, {"5": -0.01})},
        {"snapshot": _snap("A4", 2.5, "momentum", "🟢 看多"), "result": None},   # 未回填
        # 桶B panic|🔴 强看空, 决策 可考虑介入, 仅 1 个 -> 样本不足
        {"snapshot": _snap("B1", 2.5, "panic", "🔴 强看空"), "result": _res("B1", {"5": 0.10}, {"5": 0.08})},
    ]
    stats = l2.analyze(joined, horizons=[5], min_samples=2)
    b = stats["buckets"][l2.DECISION_ENTER]
    A, B = "momentum|🟢 看多", "panic|🔴 强看空"
    assert set(b.keys()) == {A, B}                       # 两桶分开, 不合并
    # 桶A: n=3(未回填的 A4 不计入), avg_excess=(0.02+0.01-0.01)/3, 胜率 2/3
    ca = b[A]["horizons"][5]
    assert ca["n"] == 3 and ca["insufficient"] is False
    assert b[A]["unfilled"] == 1                          # A4 未回填透明计数
    assert abs(ca["avg_excess"] - (0.02 + 0.01 - 0.01) / 3) < 1e-9
    assert abs(ca["winrate"] - 2 / 3) < 1e-9
    assert abs(ca["avg_ret"] - (0.05 + 0.03 - 0.02) / 3) < 1e-9
    # 桶B: n=1 < min_samples=2 -> 样本不足, 不下结论
    cb = b[B]["horizons"][5]
    assert cb["n"] == 1 and cb["insufficient"] is True
    assert "avg_excess" not in cb                         # 不足不算均值


def test_analyze_unfilled_only_bucket():
    """整桶都未回填 -> 有 unfilled 计数, horizons 空(不拿空收益凑数)。"""
    joined = [{"snapshot": _snap("Z1", 2.5), "result": None},
              {"snapshot": _snap("Z2", 2.5), "result": None}]
    stats = l2.analyze(joined, horizons=[5], min_samples=2)
    b = stats["buckets"][l2.DECISION_ENTER]["momentum|🟢 看多"]
    assert b["unfilled"] == 2 and b["filled"] == 0
    assert b["horizons"] == {}


# ── 5. run_layer2 落盘: 生成 md 报告含表格 ──
def test_run_layer2_writes_report():
    d = tempfile.mkdtemp(prefix="vaxl2_")
    saved = _set_tmp(d)
    try:
        for i, sc in enumerate([2.5, 2.6, 2.4]):
            code = f"00000{i}"
            er._append_jsonl(er.SNAPSHOTS_FILE, _snap(code, sc))
            er._append_jsonl(er.RESULTS_FILE, _res(code, {"5": 0.02 * (i + 1)}, {"5": 0.01 * (i + 1)}))
        report = l2.run_layer2(write=True, horizons=[5], min_samples=2)
        assert "# Layer2 评估报告" in report
        assert "决策档: 可考虑介入" in report
        assert "| horizon | N |" in report           # 表头
        assert "分环境分桶" in report and "绝不全样本平均" in report
        # 落盘文件存在(跟随 SNAPSHOTS_FILE 所在 tmp 目录)
        out = pathlib.Path(d) / "layer2_report_20260625.md"
        assert out.is_file()
        assert "决策档" in out.read_text(encoding="utf-8")
    finally:
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


def test_run_layer2_empty_no_crash():
    d = tempfile.mkdtemp(prefix="vaxl2_")
    saved = _set_tmp(d)
    try:
        report = l2.run_layer2(write=False)   # 无任何 jsonl
        assert "暂无已回填样本" in report
    finally:
        _restore(saved)
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items()
                 if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
