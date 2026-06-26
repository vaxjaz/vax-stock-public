# -*- coding: utf-8 -*-
"""research 离线分析层: Layer2 评估器(MR-Eval E2)。

基于 E1 已积累的 factor_snapshots.jsonl + factor_results.jsonl, 做
"按 EOD 策略模拟操作 → 分环境分桶 → 前瞻收益/超额统计"。纯读两个 jsonl 离线分析,
零网络零取数, 不碰 Tushare。可独立手动跑(看历史), 也由 run_eod 末尾顺带触发
(record_and_backfill 之后, Layer2 读已回填到最新的 results)。

【铁律】
  - Layer2 是 E1 之上的"解读层", **绝不改 snapshots/results(只读)**。
  - 模拟决策用 snapshots 已有的 right_side_score(zz800 校准评分)打标签, **非新算**;
    阈值镜像 indicators/scoring.py 的评分分档(≥3.5/≥2.0/≥0.5/<0.5)。
  - **分环境分桶是硬性**(防混合平均掩盖状态依赖): 每条样本带 market 环境, 按桶分别统计,
    绝不全样本平均。
  - 样本 < min_samples 的组合标"样本不足"不下结论(诚实, 不拿小样本说事)。
  - result 未回填的样本不计入统计(不拿空收益凑数)。
  - 政策维度第一版不做(走将来 policy_context 接口), 分桶先用 regime + macro_regime。

路径/读取复用 services.eval_recorder 的常量与 _read_jsonl(单一真相: E1 是 owner);
以模块属性方式引用(er.SNAPSHOTS_FILE 等), 便于测试 monkeypatch 到 tmp。
"""

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from vaxstock.services import eval_recorder as er

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = (1, 3, 5, 10, 20, 30)
MIN_SAMPLES = 20

# 决策档(镜像 indicators/scoring.py 的评分分档, 不新算; 见 scoring 的 grade 块)
DECISION_STRONG = "强买入信号"   # >= 3.5
DECISION_ENTER = "可考虑介入"    # >= 2.0
DECISION_WATCH = "观察等待"      # >= 0.5
DECISION_AVOID = "回避"          # <  0.5
DECISION_NONE = "无评分"         # 评分缺失(不臆造决策)

_DECISION_ORDER = [DECISION_ENTER, DECISION_STRONG, DECISION_WATCH, DECISION_AVOID, DECISION_NONE]


# ==================== A. join ====================

def load_joined() -> List[Dict[str, Any]]:
    """读 snapshots + results, 按 (trade_date, code) join。

    每条 = {"snapshot": <因子+market+price>, "result": <ret/excess/complete> 或 None(未回填)}。
    results 同 key 多行取最新(文件后写覆盖, 与 backfill 一致)。
    """
    snaps = er._read_jsonl(er.SNAPSHOTS_FILE)
    results_by_key: Dict[tuple, dict] = {}
    for r in er._read_jsonl(er.RESULTS_FILE):
        results_by_key[(str(r.get("trade_date")), r.get("code"))] = r  # 后写覆盖=最新
    joined = []
    for s in snaps:
        key = (str(s.get("trade_date")), s.get("code"))
        joined.append({"snapshot": s, "result": results_by_key.get(key)})
    return joined


# ==================== B. 模拟决策标签(EOD T日收盘评分定) ====================

def tag_decision(snapshot: Dict[str, Any]) -> str:
    """按 right_side_score(取自 metrics)打模拟决策标签, 阈值镜像 scoring。

    这就是"按 EOD 策略模拟操作"的决策(T日收盘评分定, 非盘中)。评分缺失 -> 无评分(不臆造)。
    """
    score = (snapshot.get("metrics") or {}).get("right_side_score")
    if score is None:
        return DECISION_NONE
    if score >= 3.5:
        return DECISION_STRONG
    if score >= 2.0:
        return DECISION_ENTER
    if score >= 0.5:
        return DECISION_WATCH
    return DECISION_AVOID


# ==================== C. 环境分桶键 ====================

def bucket_key(snapshot: Dict[str, Any]) -> str:
    """从 market 提环境分桶键。第一版: regime + macro_regime(如 'momentum|🔴 强看空')。

    预留扩展(将来加 ai_track 闸门 / breadth 档 / 政策); 缺失维度诚实标"待验证", 不臆造。
    """
    m = snapshot.get("market") or {}
    regime = m.get("regime") or "regime待验证"
    macro = m.get("macro_regime") or "宏观待验证"
    return f"{regime}|{macro}"


# ==================== D. 分桶统计 ====================

def analyze(joined: List[Dict[str, Any]], horizons=DEFAULT_HORIZONS,
            min_samples: int = MIN_SAMPLES) -> Dict[str, Any]:
    """对每个 (决策档, 环境桶, horizon) 统计已回填样本: N / 平均ret / 平均excess / 胜率(excess>0占比)。

    样本 < min_samples 标 insufficient; 未回填(result=None)不计入(只累计未回填计数供透明)。
    返回 {"buckets": {dec: {bkt: {"filled","unfilled","horizons": {k: cell}}}}, "min_samples", "horizons"}。
    """
    pairs: Dict[tuple, List[tuple]] = defaultdict(list)        # (dec,bkt,k) -> [(ret_k, excess_k)]
    counts: Dict[tuple, Dict[str, int]] = defaultdict(lambda: {"filled": 0, "unfilled": 0})

    for row in joined:
        s = row.get("snapshot") or {}
        res = row.get("result")
        dec = tag_decision(s)
        bkt = bucket_key(s)
        if res is None:
            counts[(dec, bkt)]["unfilled"] += 1   # 未回填: 透明计数, 不进统计
            continue
        counts[(dec, bkt)]["filled"] += 1
        ret = res.get("ret") or {}
        exc = res.get("excess") or {}
        for k in horizons:
            ks = str(k)
            if ks in ret and ret[ks] is not None:
                pairs[(dec, bkt, k)].append((ret[ks], exc.get(ks)))  # excess 可能 None(指数缺)

    buckets: Dict[str, Dict[str, Any]] = {}
    for (dec, bkt), cnt in counts.items():
        buckets.setdefault(dec, {})[bkt] = {
            "filled": cnt["filled"], "unfilled": cnt["unfilled"], "horizons": {},
        }
    for (dec, bkt, k), plist in pairs.items():
        n = len(plist)
        hcell = buckets[dec][bkt]["horizons"]
        if n < min_samples:
            hcell[k] = {"n": n, "insufficient": True}
            continue
        rets = [p[0] for p in plist]
        excs = [p[1] for p in plist if p[1] is not None]
        hcell[k] = {
            "n": n, "insufficient": False,
            "avg_ret": sum(rets) / len(rets),
            "avg_excess": (sum(excs) / len(excs)) if excs else None,
            "winrate": (sum(1 for e in excs if e > 0) / len(excs)) if excs else None,
            "n_excess": len(excs),
        }
    return {"buckets": buckets, "min_samples": min_samples, "horizons": list(horizons)}


# ==================== E. 渲染报告 ====================

def _pct(v: Optional[float]) -> str:
    return f"{v * 100:+.2f}%" if v is not None else "指数缺"


def render_report(stats: Dict[str, Any]) -> str:
    """markdown 表格(决策档 × 环境桶 × horizon → N/ret/excess/胜率)。未回填/样本不足诚实标注。"""
    horizons = stats.get("horizons", list(DEFAULT_HORIZONS))
    min_samples = stats.get("min_samples", MIN_SAMPLES)
    buckets = stats.get("buckets", {})

    lines = ["# Layer2 评估报告(样本外 · 用户 universe · 分环境)", ""]
    lines.append(f"> 决策档按 EOD T日收盘 right_side_score 模拟(≥3.5强买入/≥2.0可考虑介入/≥0.5观察/<0.5回避);")
    lines.append(f"> **分环境分桶(regime|macro_regime)统计前瞻 excess, 绝不全样本平均**; "
                 f"样本<{min_samples} 标样本不足, 未回填不计入。")
    lines.append("")
    if not buckets:
        lines.append("(暂无已回填样本, 数据攒厚后自然有结论)")
        return "\n".join(lines)

    decs = [d for d in _DECISION_ORDER if d in buckets] + [d for d in buckets if d not in _DECISION_ORDER]
    for dec in decs:
        focus = " ⭐(策略核心: 验'评分≥2介入'前瞻力)" if dec == DECISION_ENTER else ""
        lines.append(f"## 决策档: {dec}{focus}")
        for bkt in sorted(buckets[dec]):
            meta = buckets[dec][bkt]
            note = f"(已回填 {meta['filled']} / 未回填 {meta['unfilled']})"
            lines.append(f"### 环境桶: {bkt}  {note}")
            lines.append("| horizon | N | 平均ret | 平均excess | 胜率(excess>0) |")
            lines.append("|---|---|---|---|---|")
            for k in horizons:
                cell = meta["horizons"].get(k)
                if cell is None:
                    continue
                if cell.get("insufficient"):
                    lines.append(f"| T+{k} | {cell['n']} | 样本不足 | 样本不足 | 样本不足 |")
                else:
                    wr = f"{cell['winrate'] * 100:.0f}%" if cell["winrate"] is not None else "-"
                    lines.append(f"| T+{k} | {cell['n']} | {_pct(cell['avg_ret'])} | "
                                 f"{_pct(cell['avg_excess'])} | {wr} |")
            lines.append("")
    lines.append("> zz800 对照位: 该档评分在 zz800 的预期超额 vs 实测 —— 接入待办(第一版不臆造)。")
    return "\n".join(lines)


# ==================== F. 编排 ====================

def _latest_trade_date(joined: List[Dict[str, Any]]) -> Optional[str]:
    tds = [str((row.get("snapshot") or {}).get("trade_date")) for row in joined]
    tds = [t for t in tds if t and t != "None"]
    return max(tds) if tds else None


def run_layer2(write: bool = True, horizons=DEFAULT_HORIZONS,
               min_samples: int = MIN_SAMPLES) -> str:
    """load_joined → analyze → render_report; write=True 落 eval/ 目录(供查看)。返回报告字符串。"""
    joined = load_joined()
    stats = analyze(joined, horizons=horizons, min_samples=min_samples)
    report = render_report(stats)
    if write:
        td = _latest_trade_date(joined) or "nodate"
        # 输出目录跟随 snapshots(同 eval/ 目录; 测试 monkeypatch SNAPSHOTS_FILE 时自动落 tmp)
        out = Path(er.SNAPSHOTS_FILE).parent / f"layer2_report_{td}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        logger.info(f"Layer2 报告落盘: {out}")
    return report
