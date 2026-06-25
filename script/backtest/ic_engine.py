#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IC计算引擎
==========
对每个因子计算：
1. 每日 Spearman Rank IC（横截面）
2. IC均值、IC标准差、ICIR、IC胜率
3. 因子方向校正：IC符号与预期方向一致

【Spearman Rank IC】
  在每个交易日，计算因子值排名与未来N日收益排名的相关系数。
  比Pearson更稳健，不受异常值和非线性关系影响。

【Winsorize】
  每个截面去除最高/最低1%极值，避免极端股票（如新股、ST、停牌恢复）拉偏IC。
"""

import logging
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

logger = logging.getLogger(__name__)


# ==================== 工具 ====================

def winsorize(series: pd.Series, lower: float = 0.01, upper: float = 0.01) -> pd.Series:
    """截尾，去除最低lower分位和最高upper分位的值"""
    if series.empty or series.isna().all():
        return series
    lo = series.quantile(lower)
    hi = series.quantile(1 - upper)
    return series.clip(lo, hi)


def daily_spearman_ic(factor: pd.Series, ret: pd.Series) -> float:
    """单日横截面Spearman IC"""
    valid = factor.notna() & ret.notna()
    if valid.sum() < 10:  # 样本不足
        return np.nan
    f = factor[valid]
    r = ret[valid]
    if f.nunique() < 2 or r.nunique() < 2:
        return np.nan
    ic, _ = stats.spearmanr(f, r)
    return ic


# ==================== 单因子IC ====================

def calc_factor_ic(
    factor_df: pd.DataFrame,
    factor_name: str,
    return_window: int,
) -> pd.DataFrame:
    """
    计算单个因子在指定收益窗口下的每日IC。

    返回：DataFrame，列 = [trade_date, ic, n_stocks]
    """
    ret_col = f"ret_{return_window}d"
    if factor_name not in factor_df.columns or ret_col not in factor_df.columns:
        return pd.DataFrame()

    ic_records = []
    for date, group in factor_df.groupby("trade_date"):
        f = group[factor_name]
        r = group[ret_col]
        # 截尾
        f_clean = winsorize(f, config.WINSORIZE_PCT, config.WINSORIZE_PCT)
        ic = daily_spearman_ic(f_clean, r)
        n = (f.notna() & r.notna()).sum()
        ic_records.append({"trade_date": date, "ic": ic, "n_stocks": n})

    return pd.DataFrame(ic_records).sort_values("trade_date").reset_index(drop=True)


# ==================== 因子统计指标 ====================

def summarize_ic(ic_series: pd.Series) -> Dict[str, float]:
    """
    汇总IC统计指标。

    Returns:
        ic_mean: 均值
        ic_std: 标准差
        icir: 均值/标准差，年化乘sqrt(252)
        ic_win_rate: IC>0的占比
        ic_t_stat: t统计量
        ic_positive_days: IC>0天数
        ic_negative_days: IC<0天数
    """
    clean = ic_series.dropna()
    if len(clean) < 10:
        return {
            "ic_mean": np.nan, "ic_std": np.nan, "icir": np.nan,
            "ic_win_rate": np.nan, "ic_t_stat": np.nan,
            "ic_positive_days": 0, "ic_negative_days": 0, "n_days": 0,
        }

    mean = clean.mean()
    std = clean.std()
    icir_annualized = mean / std * np.sqrt(252) if std > 0 else np.nan
    win_rate = (clean > 0).sum() / len(clean) * 100
    t_stat = mean / (std / np.sqrt(len(clean))) if std > 0 else np.nan
    pos_days = (clean > 0).sum()
    neg_days = (clean < 0).sum()

    return {
        "ic_mean": round(mean, 4),
        "ic_std": round(std, 4),
        "icir": round(icir_annualized, 3),
        "ic_win_rate": round(win_rate, 1),
        "ic_t_stat": round(t_stat, 2),
        "ic_positive_days": int(pos_days),
        "ic_negative_days": int(neg_days),
        "n_days": int(len(clean)),
    }


# ==================== 主流程 ====================

def run_all_factor_ic(factor_df: pd.DataFrame) -> Dict[str, Dict]:
    """
    跑全部因子在全部窗口下的IC。

    Returns:
        {
            "holder_change_pct": {
                "ret_5d":  {ic_mean, icir, ...},
                "ret_10d": {...},
                "ret_20d": {...},
                "ic_series_10d": pd.DataFrame,  # 每日IC明细
            },
            ...
        }
    """
    results = {}
    factors = list(config.FACTORS.keys())

    for fname in factors:
        if fname not in factor_df.columns:
            logger.warning(f"  ⚠️ 因子 {fname} 不在数据中，跳过")
            continue

        logger.info(f"  🧮 计算因子: {fname}")
        factor_result = {"label": config.FACTORS[fname]["label"],
                        "direction": config.FACTORS[fname]["direction"]}

        for window in config.FUTURE_RETURN_WINDOWS:
            ic_df = calc_factor_ic(factor_df, fname, window)
            if len(ic_df) == 0:
                continue

            stats_dict = summarize_ic(ic_df["ic"])
            factor_result[f"ret_{window}d"] = stats_dict

            # 保存 T+10 的详细IC序列供后续绘图
            if window == 10:
                factor_result["ic_series"] = ic_df

        results[fname] = factor_result

    return results


def print_ic_summary(results: Dict[str, Dict], primary_window: int = 10):
    """打印IC汇总表"""
    rows = []
    for fname, res in results.items():
        key = f"ret_{primary_window}d"
        if key not in res:
            continue
        stats = res[key]
        rows.append({
            "因子": res["label"],
            "code": fname,
            "方向": res["direction"],
            "IC均值": stats["ic_mean"],
            "ICIR": stats["icir"],
            "胜率%": stats["ic_win_rate"],
            "t值": stats["ic_t_stat"],
            "天数": stats["n_days"],
        })

    df = pd.DataFrame(rows)
    # 按 |IC均值| 降序
    df["abs_ic"] = df["IC均值"].abs()
    df = df.sort_values("abs_ic", ascending=False).drop(columns=["abs_ic"])
    df.insert(0, "排名", range(1, len(df) + 1))

    print(f"\n{'='*80}")
    print(f"因子IC汇总（T+{primary_window}日，按|IC|降序）")
    print(f"{'='*80}")
    print(df.to_string(index=False))
    print(f"{'='*80}\n")
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    factor_path = os.path.join(config.DATA_DIR, "factors.parquet")
    if not os.path.exists(factor_path):
        logger.error("❌ 因子矩阵不存在，请先运行 factor_calculator.py")
        sys.exit(1)

    df = pd.read_parquet(factor_path)
    logger.info(f"📊 因子矩阵: {len(df)}行")

    results = run_all_factor_ic(df)
    print_ic_summary(results, primary_window=10)
