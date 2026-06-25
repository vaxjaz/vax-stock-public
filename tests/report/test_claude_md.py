# -*- coding: utf-8 -*-
"""report.claude_md 测试(纯函数, 零网络)。

跑法: PYTHONPATH=src python3 -m pytest tests/report/test_claude_md.py
     PYTHONPATH=src python3 tests/report/test_claude_md.py   # 无 pytest
"""

from vaxstock.report.claude_md import (
    build_claude_markdown,
    compact_for_claude,
    render_track_section,
)
from vaxstock.tracks import contract


def _mock_claude_data():
    return {
        "generated_at": "2026-06-25 16:00",
        "data_sources": ["sina", "tushare"],
        "analysis_instruction": "(分析要求略)",
        "market_regime": "momentum",
        "indices": [{"name": "上证指数", "price": 3500.5, "change_pct": 0.8}],
        "market_overview": {"up_count": 3000, "down_count": 1800,
                            "limit_up_count": 40, "limit_down_count": 5},
        "north_flow": {"total_inflow": 12.3, "is_today": True,
                       "hgt_inflow": 7.0, "sgt_inflow": 5.3},
        "stocks": [{
            "name": "立讯精密", "code": "002475", "group": "持仓",
            "concepts": ["消费电子", "连接器"], "price": 35.2, "change_pct": 2.1,
            "amplitude_pct": 3.0, "ma5": 34.0, "ma10": 33.5, "ma20": 33.0, "ma60": 32.0,
            "right_side_score": 3.5, "right_side_grade": "强买入信号",
            "right_side_signals": ["✅业绩高增长"], "np_yoy": 60.0, "risk_level": "NORMAL",
            "alerts": [],
        }],
    }


def _mock_track_available_true():
    return {
        "track_name": "AI算力", "date": "2026-06-25", "available": True,
        "signals": {"sox": {"status": contract.STATUS_CONFIRMED}},
        "summary_lines": ["【海外闸门·SOX】✅开放  收5200 / MA50 5000"],
        "vetoes": [("海外闸门", "测试原因")],
        "position_ceiling": f"{contract.CEILING_OFFENSE} (赛道上限~高位, 可加)",
        "pending": [],
    }


# ① 输出不含"板块赛道"/"热门赛道"(旧段已删)
def test_no_old_sector_sections():
    md = build_claude_markdown(_mock_claude_data(), track_results=[_mock_track_available_true()])
    assert "板块赛道" not in md, "旧'板块赛道'段应已删除"
    assert "热门赛道" not in md, "旧'热门赛道'段应已删除"
    # 旧板块数据段的子标题不应出现(注: 分析引导里的"今日强势板块是否可持续"是给LLM的提问, 属正常)
    assert "今日强势板块 TOP" not in md
    assert "### 今日弱势板块" not in md


# ② 含 track_name 和 position_ceiling(赛道段已渲染)
def test_track_section_rendered():
    tr = _mock_track_available_true()
    md = build_claude_markdown(_mock_claude_data(), track_results=[tr])
    assert "AI算力" in md
    assert tr["position_ceiling"] in md
    assert "赛道择时" in md  # 新赛道落点小标题
    # track_results=None 时写"无赛道信号"
    md_none = build_claude_markdown(_mock_claude_data(), track_results=None)
    assert "无赛道信号" in md_none


# ③ render_track_section 对 available=False 的 pending 结果也能渲染出"待验证维度"
def test_render_track_section_pending():
    pend = contract.pending_result("AI算力", "2026-06-25", "SOX/景气数据缺失",
                                   pending_dims=["景气(NVDA)", "海外闸门(SOX)"])
    assert contract.validate(pend) == []  # 先确认是合规 pending 结果
    sec = render_track_section(pend)
    assert "AI算力" in sec
    assert "待验证维度" in sec
    assert contract.PENDING_CEILING in sec
    assert "无否决触发" in sec  # pending 无 veto

    # available=True 带 veto 的渲染
    sec2 = render_track_section(_mock_track_available_true())
    assert "🚫 海外闸门" in sec2
    assert "进攻档" in sec2


# compact_for_claude 删掉 sector_analysis / hot_sector_scan 两 key, 保留其余
def test_compact_drops_sector_keys():
    payload = {
        "generated_at": "2026-06-25 16:00", "data_sources": ["sina"],
        "sector_analysis": {"top_up_sectors": [{"name": "x"}]},  # 应被删
        "hot_sector_scan": {"foo": 1},                            # 应被删
        "us_market": {"vix": 18}, "macro": {"regime": "neutral"},
        "opportunity_scan": {"x": 1}, "stocks": [],
    }
    c = compact_for_claude(payload)
    assert "sector_analysis" not in c
    assert "hot_sector_scan" not in c
    # 其余数据 key 保留(SSOT, 渲染待 MR6 注入)
    assert "us_market" in c and "macro" in c and "opportunity_scan" in c


# report.claude_md 不得 import sources / analysis(分层守卫)
def test_no_sources_analysis_import():
    import sys
    bad = [m for m in sys.modules if m.startswith("vaxstock.sources") or m.startswith("vaxstock.analysis")]
    assert bad == [], f"report 层不应加载 sources/analysis: {bad}"


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
