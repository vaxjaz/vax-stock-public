# -*- coding: utf-8 -*-
"""TrackResult 契约测试。

可用 pytest 跑: PYTHONPATH=src python3 -m pytest tests/tracks/test_contract.py
也可无 pytest 直接跑: PYTHONPATH=src python3 tests/tracks/test_contract.py
"""

from vaxstock.tracks.contract import (
    PENDING_CEILING,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_SINGLE_SOURCE,
    is_valid_ceiling,
    is_valid_status,
    pending_result,
    validate,
)


def _valid_available_true():
    """一个合法的 available=True 结果(各测试在其上做最小改动)。"""
    return {
        "track_name": "AI算力",
        "date": "2026-06-25",
        "available": True,
        "signals": {
            "sox": {"status": STATUS_CONFIRMED, "value": 1.2, "source": "us_market"},
            "north": {"status": STATUS_SINGLE_SOURCE},
            "vol": {"status": "部分缺失(2)"},
        },
        "summary_lines": ["SOX +1.2% 已证实", "北向 单源待交叉验证"],
        "vetoes": [("SOX急跌", "隔夜-3%")],
        "position_ceiling": "进攻档(≤30%)",
        "pending": [],
    }


# ① 合法 available=True
def test_valid_available_true():
    assert validate(_valid_available_true()) == []


# ② pending_result 工厂产物合法
def test_pending_result_factory_valid():
    r = pending_result("人形机器人", "2026-06-25", "SOX/北向数据缺失",
                       pending_dims=["SOX隔夜", "北向资金"])
    assert validate(r) == []
    assert r["available"] is False
    assert r["position_ceiling"] == PENDING_CEILING
    assert r["pending"] == ["SOX隔夜", "北向资金"]
    # 不给 pending_dims 时, 用 reason 兜底保证 pending 非空, 仍合法
    r2 = pending_result("光模块", "2026-06-25", "全维度无数据")
    assert validate(r2) == []
    assert r2["pending"] == ["全维度无数据"]
    assert r2["position_ceiling"] == PENDING_CEILING


# ③ available=False 但档位非 PENDING(应被拦)
def test_available_false_with_active_ceiling_rejected():
    r = _valid_available_true()
    r["available"] = False  # 档位仍是 "进攻档(≤30%)", pending 仍为空
    errs = validate(r)
    assert any("position_ceiling 必须为 PENDING_CEILING" in e for e in errs), errs
    assert any("pending 必须非空" in e for e in errs), errs


# ④ 信号缺 status(应被拦)
def test_signal_missing_status_rejected():
    r = _valid_available_true()
    r["signals"] = {"sox": {"value": 1.0}}  # 无 status
    errs = validate(r)
    assert any("缺非空 status" in e for e in errs), errs

    # status 为空串也拦
    r["signals"] = {"sox": {"status": "  "}}
    assert any("缺非空 status" in e for e in validate(r))

    # status 非词表内也拦
    r["signals"] = {"sox": {"status": "瞎编状态"}}
    assert any("status 非法" in e for e in validate(r))


# ⑤ 缺字段(应被拦)
def test_missing_field_rejected():
    r = _valid_available_true()
    del r["position_ceiling"]
    errs = validate(r)
    assert any("缺字段: position_ceiling" in e for e in errs), errs

    r2 = _valid_available_true()
    del r2["signals"]
    assert any("缺字段: signals" in e for e in validate(r2))


# —— 扩展用例 ——

def test_available_true_pending_ceiling_rejected():
    r = _valid_available_true()
    r["position_ceiling"] = PENDING_CEILING
    assert any("不能是 PENDING_CEILING" in e for e in validate(r))


def test_available_true_invalid_ceiling_rejected():
    r = _valid_available_true()
    r["position_ceiling"] = "随便档(乱写)"
    assert any("有效档位前缀" in e for e in validate(r))


def test_all_ceiling_prefixes_accepted():
    for pc in ["进攻档", "中性档(≤15%)", "减档", "防御档(≤5%)", "清仓档", "禁区(688不可交易)"]:
        r = _valid_available_true()
        r["position_ceiling"] = pc
        assert validate(r) == [], (pc, validate(r))


def test_status_and_ceiling_helpers():
    assert is_valid_status(STATUS_CONFIRMED)
    assert is_valid_status(STATUS_CONFLICT)
    assert is_valid_status("部分缺失(5)")
    assert not is_valid_status("")
    assert not is_valid_status("乱编")
    assert is_valid_ceiling("进攻档(≤30%)")
    assert not is_valid_ceiling(PENDING_CEILING)
    assert not is_valid_ceiling("待验证档")


def test_bad_date_rejected():
    r = _valid_available_true()
    r["date"] = "2026/06/25"
    assert any("YYYY-MM-DD" in e for e in validate(r))
    r["date"] = "2026-13-40"
    assert any("YYYY-MM-DD" in e for e in validate(r))


def test_vetoes_type_enforced():
    r = _valid_available_true()
    r["vetoes"] = [["名", "因"]]  # list 不是 tuple
    assert any("vetoes" in e for e in validate(r))
    r["vetoes"] = [("名",)]  # 长度不对
    assert any("vetoes" in e for e in validate(r))


def test_non_dict_result():
    assert validate(None) == ["result 必须是 dict / TrackResult"]
    assert validate("x") == ["result 必须是 dict / TrackResult"]


def test_available_false_pending_empty_rejected():
    # available=False + 正确 PENDING 档位, 但 pending 为空 -> 应拦
    r = {
        "track_name": "X", "date": "2026-06-25", "available": False,
        "signals": {}, "summary_lines": [], "vetoes": [],
        "position_ceiling": PENDING_CEILING, "pending": [],
    }
    assert any("pending 必须非空" in e for e in validate(r))


# —— 无 pytest 时的运行器 ——
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
