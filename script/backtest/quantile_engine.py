#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分组回测引擎
============
对每个因子做 N 分位（默认5分位）回测，输出：
- 每组的平均收益
- Q5-Q1 多空组合的累计收益曲线
- 年化收益、最大回撤、夏普比率

【与IC的区别】
  IC告诉你"因子有相关性"，但不能直接换算成赚多少钱。
  分位回测告诉你"按因子排序选股能赚多少"。

【方向校正】
  因子方向为negative（如股东户数变化%）的，Q1=最低=最好（应该买Q1做多）
  因子方向为positive的，Q5=最高=最好（应该买Q5做多）
  统一定义"多空组合 = 好的一组 - 差的一组"，便于横向对比
"""

import logging
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

logger = logging.getLogger(__name__)


# ==================== 分位回测 ====================

def assign_quantiles(group: pd.DataFrame, factor: str, n_groups: int = 5) -> pd.Series:
    """每个交易日截面分位"""
    f = group[factor]
    valid = f.notna()
    if valid.sum() < n_groups * 2:
        return pd.Series([np.nan] * len(group), index=group.index)
    try:
        # qcut分5组：0,1,2,3,4
        labels = pd.qcut(f.where(valid), q=n_groups, labels=False, duplicates="drop")
        return labels
    except (ValueError, KeyError):
        return pd.Series([np.nan] * len(group), index=group.index)


def calc_quantile_returns(
    factor_df: pd.DataFrame,
    factor_name: str,
    return_window: int = 10,
    n_groups: int = 5,
) -> pd.DataFrame:
    """
    分位回测。

    返回：DataFrame，列 = [trade_date, q0_ret, q1_ret, ..., q4_ret, n_stocks]
    """
    ret_col = f"ret_{return_window}d"
    if factor_name not in factor_df.columns or ret_col not in factor_df.columns:
        return pd.DataFrame()

    rows = []
    for date, group in factor_df.groupby("trade_date"):
        labels = assign_quantiles(group, factor_name, n_groups)
        if labels.isna().all():
            continue
        group = group.copy()
        group["q"] = labels

        row = {"trade_date": date, "n_stocks": len(group)}
        for q in range(n_groups):
            mask = group["q"] == q
            ret = group.loc[mask, ret_col].mean() if mask.any() else np.nan
            row[f"q{q}_ret"] = ret
        rows.append(row)

    return pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)


# ==================== 长短组合 ====================

def build_long_short_returns(
    q_df: pd.DataFrame,
    direction: str,
    n_groups: int = 5,
) -> pd.DataFrame:
    """
    根据因子方向构建多空组合收益。

    direction="positive": 多Q4(最高分位) 空Q0
    direction="negative": 多Q0(最低分位) 空Q4
    direction="neutral":  默认按positive处理
    """
    if len(q_df) == 0:
        return pd.DataFrame()

    high_q = f"q{n_groups - 1}_ret"
    low_q = "q0_ret"

    df = q_df.copy()
    if direction == "negative":
        df["long_ret"] = df[low_q]
        df["short_ret"] = df[high_q]
    else:
        df["long_ret"] = df[high_q]
        df["short_ret"] = df[low_q]

    df["ls_ret"] = df["long_ret"] - df["short_ret"]
    return df


# ==================== 评估指标 ====================

def evaluate_long_short(ls_df: pd.DataFrame, return_window: int = 10) -> Dict[str, float]:
    """
    评估多空组合表现。

    注意：每个trade_date的ret是T+N日收益，不能直接相加（会重复计数）。
    这里做近似处理：取每N天采样一次，避免重叠。
    """
    if len(ls_df) == 0:
        return {}

    # 不重叠采样：每 return_window 天取一次
    sampled = ls_df.iloc[::return_window].copy()
    rets = sampled["ls_ret"].dropna()

    if len(rets) < 5:
        return {}

    # 扣除交易成本（每次调仓双边成本）
    cost = config.TOTAL_COST_BPS / 10000.0
    rets_after_cost = rets - cost

    # 累计收益
    cum_return = (1 + rets_after_cost).prod() - 1

    # 年化收益
    n_periods = len(rets_after_cost)
    holding_days = n_periods * return_window
    if holding_days > 0:
        annual_return = (1 + cum_return) ** (252 / holding_days) - 1
    else:
        annual_return = np.nan

    # 年化波动率
    annual_vol = rets_after_cost.std() * np.sqrt(252 / return_window) if rets_after_cost.std() > 0 else np.nan

    # 夏普
    sharpe = annual_return / annual_vol if annual_vol and annual_vol > 0 else np.nan

    # 最大回撤
    cum = (1 + rets_after_cost).cumprod()
    running_max = cum.cummax()
    drawdown = (cum - running_max) / running_max
    max_drawdown = drawdown.min()

    # 胜率
    win_rate = (rets_after_cost > 0).sum() / len(rets_after_cost) * 100

    return {
        "cum_return": round(cum_return * 100, 2),
        "annual_return": round(annual_return * 100, 2) if annual_return is not None else None,
        "annual_vol": round(annual_vol * 100, 2) if annual_vol is not None else None,
        "sharpe": round(sharpe, 2) if sharpe else None,
        "max_drawdown": round(max_drawdown * 100, 2) if max_drawdown is not None else None,
        "win_rate": round(win_rate, 1),
        "n_periods": int(n_periods),
    }


# ==================== 主流程 ====================

def run_all_quantile_backtest(
    factor_df: pd.DataFrame,
    return_window: int = 10,
) -> Dict[str, Dict]:
    """
    跑全部因子的分位回测。

    Returns:
        {
            "holder_change_pct": {
                "quantile_returns": {"q0": -0.5, "q1": ..., "q4": +0.8},  # 平均每期收益%
                "long_short_metrics": {"annual_return": 12.5, "sharpe": 1.2, ...},
                "cum_curve": pd.DataFrame,  # 累计收益曲线
            },
            ...
        }
    """
    results = {}
    factors = list(config.FACTORS.keys())

    for fname in factors:
        if fname not in factor_df.columns:
            continue

        logger.info(f"  📊 分位回测: {fname}")
        direction = config.FACTORS[fname]["direction"]
        label = config.FACTORS[fname]["label"]

        q_df = calc_quantile_returns(factor_df, fname, return_window, config.QUANTILE_GROUPS)
        if len(q_df) == 0:
            continue

        # 每组平均收益（百分比）
        q_means = {}
        for q in range(config.QUANTILE_GROUPS):
            col = f"q{q}_ret"
            if col in q_df.columns:
                q_means[f"q{q}"] = round(q_df[col].mean() * 100, 3)

        # 多空组合
        ls_df = build_long_short_returns(q_df, direction, config.QUANTILE_GROUPS)
        metrics = evaluate_long_short(ls_df, return_window)

        # 累计曲线（用于绘图）
        sampled = ls_df.iloc[::return_window].copy()
        sampled["ls_ret_clean"] = sampled["ls_ret"].fillna(0) - config.TOTAL_COST_BPS / 10000.0
        sampled["cum_ret"] = (1 + sampled["ls_ret_clean"]).cumprod() - 1

        results[fname] = {
            "label": label,
            "direction": direction,
            "quantile_returns": q_means,
            "long_short_metrics": metrics,
            "cum_curve": sampled[["trade_date", "cum_ret"]].copy(),
        }

    return results


def print_quantile_summary(results: Dict[str, Dict]):
    """打印分位回测汇总"""
    rows = []
    for fname, res in results.items():
        m = res.get("long_short_metrics", {})
        if not m:
            continue
        row = {
            "因子": res["label"],
            "方向": res["direction"],
            "年化%": m.get("annual_return"),
            "波动%": m.get("annual_vol"),
            "夏普": m.get("sharpe"),
            "最大回撤%": m.get("max_drawdown"),
            "胜率%": m.get("win_rate"),
            "调仓次数": m.get("n_periods"),
        }
        # 加5个分位平均收益
        q = res.get("quantile_returns", {})
        for k in ["q0", "q1", "q2", "q3", "q4"]:
            row[k] = q.get(k)
        rows.append(row)

    df = pd.DataFrame(rows)
    if len(df) > 0:
        df = df.sort_values("年化%", ascending=False, na_position="last")
        df.insert(0, "排名", range(1, len(df) + 1))

    print(f"\n{'='*100}")
    print(f"分位回测汇总（多空组合，已扣除交易成本{config.TOTAL_COST_BPS}bps/次）")
    print(f"{'='*100}")
    print(df.to_string(index=False))
    print(f"{'='*100}\n")
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    factor_path = os.path.join(config.DATA_DIR, "factors.parquet")
    if not os.path.exists(factor_path):
        logger.error("❌ 请先运行 factor_calculator.py")
        sys.exit(1)

    df = pd.read_parquet(factor_path)
    results = run_all_quantile_backtest(df, return_window=10)
    print_quantile_summary(results)
