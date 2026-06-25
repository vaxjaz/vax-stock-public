#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子计算引擎
============
计算9个核心因子 + 1个合成评分，输出一张大表：

  code, trade_date, factor_1, factor_2, ..., factor_10, ret_5d, ret_10d, ret_20d

【核心难点】股东户数按ann_date动态生效
  错误做法：直接用最新的股东户数填充所有日期 → 前瞻偏差
  正确做法：在每个trade_date，只能使用ann_date<=该trade_date的最近一份股东户数
  实现：对每只股票按时间排序，用 merge_asof 做 point-in-time 关联

【因子定义】见 config.FACTORS

【性能优化】
- 一次性把全市场K线、估值、资金流读入内存（DataFrame）
- 按股票分组计算，避免逐行循环
- 全部用 pandas 向量化操作
"""

import logging
import math
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from data_loader import DataStore

logger = logging.getLogger(__name__)


# ==================== 单股因子计算 ====================

def calc_factors_for_stock(
    code: str,
    kline_df: pd.DataFrame,
    basic_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    fina_df: pd.DataFrame,
    holder_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    单只股票的全部因子计算。

    返回：DataFrame，每行一个trade_date，包含所有因子值。
    """
    if kline_df is None or len(kline_df) < 60:
        return pd.DataFrame()

    df = kline_df.copy().sort_values("trade_date").reset_index(drop=True)
    df["trade_date"] = df["trade_date"].astype(str)

    # ===== 合并估值 =====
    if basic_df is not None and len(basic_df) > 0:
        basic_df = basic_df.copy()
        basic_df["trade_date"] = basic_df["trade_date"].astype(str)
        df = df.merge(basic_df[["trade_date", "turnover_rate", "pe_ttm", "pb", "circ_mv"]],
                     on="trade_date", how="left")
    else:
        df["turnover_rate"] = np.nan
        df["pe_ttm"] = np.nan
        df["pb"] = np.nan
        df["circ_mv"] = np.nan

    # ===== 合并资金流 =====
    if flow_df is not None and len(flow_df) > 0:
        flow_df = flow_df.copy()
        flow_df["trade_date"] = flow_df["trade_date"].astype(str)
        # net_mf_amount 单位：万元，转为元
        flow_df["main_inflow"] = flow_df["net_mf_amount"] * 10000
        df = df.merge(flow_df[["trade_date", "main_inflow"]], on="trade_date", how="left")
    else:
        df["main_inflow"] = np.nan

    # ============ 因子1: 换手率 Z-score（基于60日历史）============
    if "turnover_rate" in df.columns:
        df["turn_mean_60"] = df["turnover_rate"].rolling(60, min_periods=20).mean()
        df["turn_std_60"] = df["turnover_rate"].rolling(60, min_periods=20).std()
        df["turnover_zscore"] = (df["turnover_rate"] - df["turn_mean_60"]) / df["turn_std_60"]
    else:
        df["turnover_zscore"] = np.nan

    # ============ 因子2: 资金流斜率 ============
    df["inflow_5d"] = df["main_inflow"].rolling(5, min_periods=3).sum()
    df["inflow_10d"] = df["main_inflow"].rolling(10, min_periods=5).sum()
    df["inflow_slope"] = df["inflow_5d"] / 5 - df["inflow_10d"] / 10

    # ============ 因子2b: 10日主力净流入 / 流通市值 (归一化, 用于阈值校准对比) ============
    # 【新增 2026-06-19】验证"归一化"是否比绝对值更有预测力, 并为报告端 0.5%/0.1% 切点提供回测依据。
    #   main_inflow 单位=元 (net_mf_amount×10000, 见上方合并段)
    #   circ_mv 单位=万元 (Tushare daily_basic 官方定义) → ×10000 转元, 量纲对齐
    #   ratio = 10日累计净流入(元) / 流通市值(元) × 100 = 占流通市值百分比 (无量纲)
    #   与报告端 stock_report_enhanced.py 第1028行口径一致, 便于切点直接套用。
    if "circ_mv" in df.columns:
        circ_mv_yuan = df["circ_mv"] * 10000  # 万元 → 元
        df["inflow_10d_ratio"] = np.where(
            circ_mv_yuan > 0,
            df["inflow_10d"] / circ_mv_yuan * 100,
            np.nan
        )
    else:
        df["inflow_10d_ratio"] = np.nan

    # ============ 因子3: PE 历史百分位（过去250日）============
    df["pe_percentile_1y"] = (
        df["pe_ttm"].rolling(250, min_periods=60)
        .apply(lambda x: (x[:-1] < x.iloc[-1]).sum() / max(len(x) - 1, 1) * 100 if x.iloc[-1] > 0 else np.nan,
               raw=False)
    )

    # ============ 因子4: 20日位置 ============
    df["high_20"] = df["high"].rolling(20, min_periods=10).max()
    df["low_20"] = df["low"].rolling(20, min_periods=10).min()
    df["position_20d_pct"] = (df["close"] - df["low_20"]) / (df["high_20"] - df["low_20"]) * 100

    # ============ 因子5: MA5偏离度 ============
    df["ma5"] = df["close"].rolling(5, min_periods=3).mean()
    df["price_vs_ma5_pct"] = (df["close"] - df["ma5"]) / df["ma5"] * 100

    # ============ 因子6: RSI14 ============
    df["rsi_14"] = _calc_rsi_series(df["close"], 14)

    # ============ 因子7: 股东户数变化（point-in-time）============
    # 关键：按ann_date生效，避免前瞻偏差
    df["holder_change_pct"] = _calc_holder_change_pit(df, holder_df)

    # ============ 因子8: 净利同比（point-in-time）============
    df["np_yoy"] = _calc_npyoy_pit(df, fina_df)

    # ============ 因子9: 合成评分（你的right_side_score简化版）============
    df["right_side_score"] = _calc_synthetic_score(df)

    # ============ 未来收益(close 已为 qfq 前复权,见 data_loader.load_daily_kline)============
    for window in config.FUTURE_RETURN_WINDOWS:
        df[f"ret_{window}d"] = df["close"].shift(-window) / df["close"] - 1

    df["code"] = code

    # 输出列
    factor_cols = list(config.FACTORS.keys())
    ret_cols = [f"ret_{w}d" for w in config.FUTURE_RETURN_WINDOWS]
    out_cols = ["code", "trade_date", "close"] + factor_cols + ret_cols

    return df[[c for c in out_cols if c in df.columns]]


# ==================== 工具函数 ====================

def _calc_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """向量化RSI计算"""
    diff = close.diff()
    gain = diff.where(diff > 0, 0)
    loss = -diff.where(diff < 0, 0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _calc_holder_change_pit(kline_df: pd.DataFrame, holder_df: pd.DataFrame) -> pd.Series:
    """
    股东户数变化率（point-in-time）

    逻辑：
      对每个trade_date，只能使用 ann_date <= trade_date 的最近2份股东户数记录，
      然后算变化率 = (最新 - 上一份) / 上一份 * 100。

    实现：merge_asof 是 pandas 做时间对齐的标准工具。
    """
    if holder_df is None or len(holder_df) < 2:
        return pd.Series([np.nan] * len(kline_df), index=kline_df.index)

    h = holder_df.copy().dropna(subset=["ann_date", "holder_num"])
    h["ann_date"] = h["ann_date"].astype(str)
    h = h.sort_values("ann_date").reset_index(drop=True)
    # 计算每份与上一份的变化率
    h["holder_num_prev"] = h["holder_num"].shift(1)
    h["holder_change_pct"] = (h["holder_num"] - h["holder_num_prev"]) / h["holder_num_prev"] * 100

    # 用merge_asof做时间对齐：每个trade_date找最近的(<=)ann_date
    left = kline_df[["trade_date"]].copy()
    left["trade_date_dt"] = pd.to_datetime(left["trade_date"], format="%Y%m%d", errors="coerce")
    h["ann_date_dt"] = pd.to_datetime(h["ann_date"], format="%Y%m%d", errors="coerce")
    h_sub = h[["ann_date_dt", "holder_change_pct"]].dropna(subset=["ann_date_dt"]).sort_values("ann_date_dt")

    left_sorted = left.sort_values("trade_date_dt")
    merged = pd.merge_asof(
        left_sorted, h_sub,
        left_on="trade_date_dt", right_on="ann_date_dt",
        direction="backward"
    )
    merged = merged.sort_index()
    return merged["holder_change_pct"].reset_index(drop=True)


def _calc_npyoy_pit(kline_df: pd.DataFrame, fina_df: pd.DataFrame) -> pd.Series:
    """
    净利同比（point-in-time）
    每个trade_date使用 ann_date <= trade_date 的最近一份财报数据
    """
    if fina_df is None or len(fina_df) == 0:
        return pd.Series([np.nan] * len(kline_df), index=kline_df.index)

    f = fina_df.copy().dropna(subset=["ann_date", "netprofit_yoy"])
    if len(f) == 0:
        return pd.Series([np.nan] * len(kline_df), index=kline_df.index)

    f["ann_date_dt"] = pd.to_datetime(f["ann_date"].astype(str), format="%Y%m%d", errors="coerce")
    f = f.dropna(subset=["ann_date_dt"]).sort_values("ann_date_dt")

    left = kline_df[["trade_date"]].copy()
    left["trade_date_dt"] = pd.to_datetime(left["trade_date"], format="%Y%m%d", errors="coerce")
    left_sorted = left.sort_values("trade_date_dt")

    merged = pd.merge_asof(
        left_sorted, f[["ann_date_dt", "netprofit_yoy"]],
        left_on="trade_date_dt", right_on="ann_date_dt",
        direction="backward"
    )
    merged = merged.sort_index()
    return merged["netprofit_yoy"].reset_index(drop=True)


def _calc_synthetic_score(df: pd.DataFrame) -> pd.Series:
    """
    简化版合成评分。

    与生产版right_side_score的不同：
    - 这里全向量化，无单股最佳化（如10日累计-1亿额外扣分等长尾规则）
    - 阈值与生产版保持一致

    评分规则：
      ✅缩量上涨(量比<0.8 且涨幅>=0)               +1.0  (这里用 turnover_zscore<-0.5 近似)
      ⚠️缩量下跌                                   +0.5
      🚨换手异常(Z>2)                              -1.0
      ✅资金流斜率>0                                +1.0
      ⚠️10日重度流出(<-1亿)                         -0.5
      ✅股东强集中(<-2%)                            +1.5
      ⚠️股东轻微集中(-2~0%)                         +0.5
      🚨股东强分散(>10%)                            -0.5
      ✅站上MA5                                    +1.0
      ✅低位(20日<30%)                              +1.0
      🚨高位(20日>80%)                              -0.5
      ✅业绩正增长(>20%)                            +0.5
    """
    s = pd.Series(0.0, index=df.index)

    # ① 价量
    tz = df.get("turnover_zscore", pd.Series([np.nan] * len(df)))
    chg = df.get("pct_chg", pd.Series([np.nan] * len(df)))
    cond_shrink_up = (tz < -0.5) & (chg >= 0)
    cond_shrink_dn = (tz < -0.5) & (chg < 0)
    cond_abnormal = (tz > 2.0)
    s = s + cond_shrink_up.astype(float) * 1.0
    s = s + cond_shrink_dn.astype(float) * 0.5
    s = s - cond_abnormal.astype(float) * 1.0

    # ② 资金流斜率
    slope = df.get("inflow_slope", pd.Series([np.nan] * len(df)))
    s = s + (slope > 0).astype(float) * 1.0

    inflow_10d = df.get("inflow_10d", pd.Series([np.nan] * len(df)))
    s = s - (inflow_10d < -1e8).astype(float) * 0.5

    # ③ 股东户数（最高权重）
    hc = df.get("holder_change_pct", pd.Series([np.nan] * len(df)))
    s = s + (hc < -2).astype(float) * 1.5
    s = s + ((hc >= -2) & (hc < 0)).astype(float) * 0.5
    s = s - (hc > 10).astype(float) * 0.5

    # ④ MA5
    p_ma5 = df.get("price_vs_ma5_pct", pd.Series([np.nan] * len(df)))
    s = s + (p_ma5 > 0).astype(float) * 1.0

    # ⑤ 位置
    pos = df.get("position_20d_pct", pd.Series([np.nan] * len(df)))
    s = s + (pos < 30).astype(float) * 1.0
    s = s - (pos > 80).astype(float) * 0.5

    # ⑥ 基本面
    np_yoy = df.get("np_yoy", pd.Series([np.nan] * len(df)))
    s = s + (np_yoy > 20).astype(float) * 0.5

    # NaN处理：如果关键因子都是NaN，整行评分置NaN
    valid = (~tz.isna()) | (~hc.isna()) | (~slope.isna())
    s = s.where(valid, np.nan)
    return s


# ==================== 全市场因子计算 ====================

def calc_all_factors(store: DataStore, codes: Optional[List[str]] = None) -> pd.DataFrame:
    """
    计算整个股票池的因子矩阵。

    返回：DataFrame，列包括：
      code, trade_date, close, [10个因子], [3个未来收益]
    """
    if codes is None:
        codes = store.get_codes("stock_pool")

    logger.info(f"📊 开始计算 {len(codes)} 只股票的因子...")

    # 预读全市场数据到内存，避免逐股查询
    logger.info("  📖 加载K线数据到内存...")
    all_kline = store.query("SELECT * FROM daily_kline WHERE code IN ({})".format(
        ",".join(["?"] * len(codes))), tuple(codes))

    logger.info("  📖 加载估值数据到内存...")
    all_basic = store.query("SELECT * FROM daily_basic WHERE code IN ({})".format(
        ",".join(["?"] * len(codes))), tuple(codes))

    logger.info("  📖 加载资金流数据到内存...")
    all_flow = store.query("SELECT * FROM moneyflow WHERE code IN ({})".format(
        ",".join(["?"] * len(codes))), tuple(codes))

    logger.info("  📖 加载财务数据到内存...")
    all_fina = store.query("SELECT * FROM fina_indicator WHERE code IN ({})".format(
        ",".join(["?"] * len(codes))), tuple(codes))

    logger.info("  📖 加载股东户数到内存...")
    all_holder = store.query("SELECT * FROM holder_number WHERE code IN ({})".format(
        ",".join(["?"] * len(codes))), tuple(codes))

    # 按 code 分组
    kline_g = all_kline.groupby("code")
    basic_g = all_basic.groupby("code") if len(all_basic) > 0 else None
    flow_g = all_flow.groupby("code") if len(all_flow) > 0 else None
    fina_g = all_fina.groupby("code") if len(all_fina) > 0 else None
    holder_g = all_holder.groupby("code") if len(all_holder) > 0 else None

    results = []
    fail_count = 0
    for i, code in enumerate(codes, 1):
        try:
            if code not in kline_g.groups:
                fail_count += 1
                continue

            k_df = kline_g.get_group(code)
            b_df = basic_g.get_group(code) if (basic_g is not None and code in basic_g.groups) else None
            f_df = flow_g.get_group(code) if (flow_g is not None and code in flow_g.groups) else None
            fi_df = fina_g.get_group(code) if (fina_g is not None and code in fina_g.groups) else None
            h_df = holder_g.get_group(code) if (holder_g is not None and code in holder_g.groups) else None

            res = calc_factors_for_stock(code, k_df, b_df, f_df, fi_df, h_df)
            if len(res) > 0:
                results.append(res)

            if i % 50 == 0:
                logger.info(f"  [{i}/{len(codes)}] 已计算")
        except Exception as e:
            logger.warning(f"  ⚠️ {code} 因子计算失败: {str(e)[:80]}")
            fail_count += 1

    if not results:
        logger.error("❌ 因子计算结果为空")
        return pd.DataFrame()

    final = pd.concat(results, ignore_index=True)

    # 截取回测窗口（计算需要更长历史，但只保留回测期）
    final = final[
        (final["trade_date"] >= config.BACKTEST_START_DATE) &
        (final["trade_date"] <= config.BACKTEST_END_DATE)
    ].reset_index(drop=True)

    logger.info(f"✅ 因子计算完成: {len(final)}行, {final['code'].nunique()}只股票")
    if fail_count > 0:
        logger.warning(f"   失败 {fail_count} 只")
    return final


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    store = DataStore()
    df = calc_all_factors(store)
    out_path = os.path.join(config.DATA_DIR, "factors.parquet")
    df.to_parquet(out_path, index=False)
    logger.info(f"💾 因子矩阵已保存: {out_path}")
    store.close()
