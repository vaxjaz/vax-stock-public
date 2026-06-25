#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宏观环境指标采集模块 (v1.3, 2026-06-13)
======================================

【6个维度】
1. 5大宽基ETF净申赎(3年)
2. 融资买入额/两市成交额(3年百分位)
3. 全A换手率(3年百分位, 中证全指代理)
4. 沪深300 ERP(5年百分位 + σ倍数)
5. 全A宽度:高于MA60/MA200比例 + 中证全指MA250 BIAS(5年)
6. M1月度同比(10年)

【架构】
- MacroCache  : 增量缓存层(parquet),减少 Tushare 积分消耗
- MacroIndicator : 主类,集成6维度
- summary() : 当日6维度摘要 + 综合宏观regime

【依赖】
- tushare (通过 tushare_source.TushareSource 注入)
- pandas, pyarrow (parquet)

【缓存目录】
- .cache_macro/  (与 stock_report_enhanced.py 同目录下)
  ├─ etf_share_history.parquet
  ├─ margin_volume_history.parquet
  ├─ turnover_history.parquet
  ├─ hs300_erp_history.parquet
  ├─ market_breadth_history.parquet
  ├─ m1_yoy_history.parquet
  └─ stocks_daily_pivot.parquet   # 维度5用:全市场日K透视表(增量)
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache_macro")

# ==================== 标的清单 ====================

# 5大宽基ETF(选规模最大的代表)
ETF_BASKET = {
    "510300.SH": ("沪深300ETF", "华泰柏瑞"),
    "510500.SH": ("中证500ETF", "南方"),
    "159338.SZ": ("A500ETF", "华夏"),       # 2024-09 成立,历史最短
    "512100.SH": ("中证1000ETF", "南方"),
    "510050.SH": ("上证50ETF", "华夏"),
}

# 中证全指(代理万得全A,Tushare 不支持万得指数)
WHOLE_MARKET_PROXY = "000985.CSI"

# 沪深300 PE-TTM 来源
HS300_INDEX = "000300.SH"

# 国债收益率曲线类型(中债国债)
GOVT_BOND_CURVE_TYPE = "0001"
GOVT_BOND_TERM_YEARS = 10

# 沪深主要指数(取成交额)
EXCHANGE_INDEX_AMOUNT = {
    "SSE": "000001.SH",   # 上证综指
    "SZSE": "399001.SZ",  # 深证成指
}


# ==================== 信号阈值表(对应 04_quant_framework.md v1.3) ====================

SIGNAL_THRESHOLDS = {
    # 维度1: ETF净申赎(亿元)
    "etf_net_sub_5d": {
        "bullish_strong": 30,    # > +30亿: ✅✅
        "bullish": 10,           # > +10亿: ✅
        "bearish": -10,          # < -10亿: ❌
        "bearish_strong": -30,   # < -30亿: ❌❌
    },
    "etf_net_sub_20d": {
        "bullish_strong": 80,
        "bullish": 30,
        "bearish": -30,
        "bearish_strong": -80,
    },
    # 维度2: 融资买入/成交额 3年百分位
    "margin_ratio_pct_3y": {
        "bullish": 30,           # < 30% (冷清底)
        "bearish": 80,           # > 80% (过热)
        "bearish_strong": 95,    # > 95% (极端过热)
    },
    # 维度3: 全A换手率 3年百分位
    "turnover_pct_3y": {
        "bullish": 25,
        "bearish": 75,
        "bearish_strong": 90,
    },
    # 维度4: 沪深300 ERP(基于5年百分位 + σ倍数双重判断)
    # ERP 越高越便宜(股票相对债券更有吸引力)
    "erp_pct_5y": {
        "bullish_strong": 80,    # 百分位 > 80 且 σ > +1
        "bullish": 60,
        "bearish": 40,
        "bearish_strong": 20,
    },
    "erp_sigma": {
        "bullish_strong": 1.0,
        "bullish": 0.0,
        "bearish": 0.0,
        "bearish_strong": -1.0,
    },
    # 维度5a: 全A 高于MA60 比例
    "above_ma60_pct": {
        "bullish": 25,           # < 25 超跌反弹
        "bearish": 75,           # > 75 过热
    },
    # 维度5b: 全A 高于MA200 比例
    "above_ma200_pct": {
        "bullish": 30,           # < 30 长期超跌(熊末)
        "bearish": 65,           # > 65 长期过热(牛末)
    },
    # 维度5c: MA250 BIAS (%)
    "ma250_bias": {
        "bullish_strong": -10,   # < -10% 极端超跌
        "bullish": -3,           # < -3% 偏低估
        "bearish": 3,            # > +3% 偏高估
        "bearish_strong": 10,    # > +10% 极端过热
    },
    # 维度6: M1 同比(%) + 月环比变化(pp)
    "m1_yoy": {
        "bullish": 8,            # > 8 流动性宽松
        "bearish": 3,            # < 3 流动性紧
    },
    "m1_yoy_mom_delta": {
        "bullish": 0.5,          # > +0.5pp 加速
        "bearish": -0.5,         # < -0.5pp 减速
    },
}

# 维度7: 社融信贷脉冲(借鉴 main.py F3, 按P0重写: 方向型指标)
SIGNAL_THRESHOLDS["sf_pulse_yoy"] = {
    "bullish": 0.0,
    "bearish": 0.0,
}
SIGNAL_THRESHOLDS["sf_pulse_accel"] = {
    "bullish": 0.0,
    "bearish": 0.0,
}


# ==================== 信号评级 ====================

def grade_signal(value: Optional[float], thresh_dict: Dict[str, float],
                 direction: str = "higher_better") -> str:
    """根据阈值表给出 ✅✅ / ✅ / ⚠️ / ❌ / ❌❌ / 🚫(None) 信号

    direction:
      higher_better: 值越高越看多(如 ERP, 净申赎)
      lower_better:  值越低越看多(如 融资比, 换手率百分位)
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "🚫"

    bs = thresh_dict.get("bullish_strong")
    b = thresh_dict.get("bullish")
    br = thresh_dict.get("bearish")
    brs = thresh_dict.get("bearish_strong")

    if direction == "higher_better":
        if bs is not None and value >= bs:
            return "✅✅"
        if b is not None and value >= b:
            return "✅"
        if brs is not None and value <= brs:
            return "❌❌"
        if br is not None and value <= br:
            return "❌"
        return "⚠️"
    else:  # lower_better
        if bs is not None and value <= bs:
            return "✅✅"
        if b is not None and value <= b:
            return "✅"
        if brs is not None and value >= brs:
            return "❌❌"
        if br is not None and value >= br:
            return "❌"
        return "⚠️"


def combine_signals(signal_list: List[str]) -> str:
    """根据所有维度信号,综合判断宏观regime
    ✅✅算2个✅, ❌❌算2个❌, 🚫忽略
    """
    bull = signal_list.count("✅") + 2 * signal_list.count("✅✅")
    bear = signal_list.count("❌") + 2 * signal_list.count("❌❌")

    if bull >= 4 and bear <= 1:
        return "🟢 强看多"
    elif bull >= 3 and bear <= 2:
        return "🟢 看多"
    elif bear >= 4 and bull <= 1:
        return "🔴 强看空"
    elif bear >= 3 and bull <= 2:
        return "🔴 看空"
    else:
        return "🟡 中性"


# ==================== 缓存层 ====================

class MacroCache:
    """通用增量缓存层(parquet 格式)"""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, name: str) -> str:
        return os.path.join(self.cache_dir, f"{name}.parquet")

    def load(self, name: str) -> Optional[pd.DataFrame]:
        """加载缓存,不存在返回 None"""
        path = self._path(name)
        if not os.path.exists(path):
            return None
        try:
            return pd.read_parquet(path)
        except Exception as e:
            logger.warning(f"读取缓存 {name} 失败: {e}")
            return None

    def save(self, name: str, df: pd.DataFrame) -> bool:
        """保存到缓存"""
        try:
            df.to_parquet(self._path(name), index=False)
            return True
        except Exception as e:
            logger.warning(f"保存缓存 {name} 失败: {e}")
            return False

    def append_unique(self, name: str, new_rows: pd.DataFrame,
                      dedup_keys: List[str]) -> pd.DataFrame:
        """增量追加,以 dedup_keys 为主键去重(保留新数据)"""
        existing = self.load(name)
        if existing is None:
            merged = new_rows.copy()
        else:
            merged = pd.concat([existing, new_rows], ignore_index=True)
            merged = merged.drop_duplicates(subset=dedup_keys, keep="last")
        # 按第一个 dedup_key 排序
        if dedup_keys[0] in merged.columns:
            merged = merged.sort_values(dedup_keys[0]).reset_index(drop=True)
        self.save(name, merged)
        return merged

    def last_date(self, name: str, date_col: str = "trade_date") -> Optional[str]:
        """返回缓存中最新一行的日期字符串(YYYYMMDD),不存在则None"""
        df = self.load(name)
        if df is None or len(df) == 0 or date_col not in df.columns:
            return None
        return str(df[date_col].max())


# ==================== 工具函数 ====================

def calc_percentile(series: pd.Series, current_value: float) -> Optional[float]:
    """计算 current_value 在 series 中的百分位(0-100)"""
    if series is None or len(series) == 0 or current_value is None:
        return None
    valid = series.dropna()
    if len(valid) == 0:
        return None
    return float((valid < current_value).sum()) / len(valid) * 100


def calc_sigma_multiple(value: float, mean: float, std: float) -> Optional[float]:
    """计算 σ 倍数: (value - mean) / std"""
    if value is None or mean is None or std is None or std == 0:
        return None
    return (value - mean) / std


def _today_ymd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _ymd_minus(ymd: str, days: int) -> str:
    dt = datetime.strptime(ymd, "%Y%m%d") - timedelta(days=days)
    return dt.strftime("%Y%m%d")


# ==================== 主类 ====================

class MacroIndicator:
    """宏观环境6维度指标采集主类"""

    def __init__(self, tushare_source, cache_dir: str = CACHE_DIR,
                 fallback_yield_10y_pct: float = 2.30):
        """
        tushare_source: TushareSource 实例(stock_report_enhanced.py 已初始化好的 TUSHARE)
                        必须 .enabled = True
        fallback_yield_10y_pct: 当 yc_cb 接口不可用时,ERP 计算用的兜底10年国债收益率(%)
                                建议每月手动从央行/财政部网站更新一次
        """
        self.ts_src = tushare_source
        self.pro = tushare_source.pro if tushare_source and tushare_source.enabled else None
        self.cache = MacroCache(cache_dir)
        self.fallback_yield_10y_pct = fallback_yield_10y_pct

    def _check_enabled(self) -> bool:
        if self.pro is None:
            logger.warning("Tushare 未启用,宏观指标无法获取")
            return False
        return True

    def _safe_call(self, func_name: str, **kwargs) -> Optional[pd.DataFrame]:
        """通用 Tushare 调用,自动重试3次"""
        if not self._check_enabled():
            return None
        for attempt in range(3):
            try:
                self.ts_src._rate_limit()
                func = getattr(self.pro, func_name)
                df = func(**kwargs)
                return df
            except Exception as e:
                if attempt < 2:
                    logger.debug(f"{func_name} 第{attempt+1}次失败({e}),重试")
                    time.sleep(2 ** attempt)
                else:
                    logger.warning(f"{func_name} 最终失败: {e}")
                    return None
        return None

    # ============ 维度2: 融资买入/两市成交额 ============

    def fetch_margin_to_volume(self, days: int = 3 * 252) -> Optional[pd.DataFrame]:
        """融资买入额 / 两市成交额比率,近3年

        返回: DataFrame columns = [trade_date, total_rzmre_yi, total_amount_yi, ratio_pct]
              单位: 亿元
        """
        cache_name = "margin_volume_history"
        existing = self.cache.load(cache_name)

        # 决定增量起始日期
        last_date = self.cache.last_date(cache_name)
        if last_date:
            start_date = _ymd_minus(last_date, -1)  # 缓存最新日期+1天
        else:
            start_date = _ymd_minus(_today_ymd(), days + 30)

        end_date = _today_ymd()

        if start_date >= end_date:
            logger.info(f"  融资比缓存已最新({last_date}),跳过拉取")
            return existing

        logger.info(f"  拉取融资融券数据 {start_date} → {end_date}")

        # 1. 融资融券汇总(margin 接口)
        margin_df = self._safe_call("margin", start_date=start_date, end_date=end_date)
        if margin_df is None or len(margin_df) == 0:
            logger.warning("margin 接口返回空")
            return existing

        # margin 字段: trade_date, exchange_id, rzye, rzmre, rqye, rqmcl, rzrqye
        # 【修复 2026-06-19】交易所完整性校验
        #   根因: 旧代码无条件 groupby.sum(), 当某交易所数据当天未发布(如盘中早段拉取,
        #         深市/北交所融资数据尚未公布)时, 只聚合到部分交易所 → 分子腰斩 → ratio 失真。
        #         实测 6/18 仅返回 [SSE], 导致 ratio 5.43% (真实应≈10.6%), 污染3年分位序列。
        #   方案: 口径与分母(上证综指+深证成指)一致, 只用 SSE+SZSE(排除 BSE 北交所小额扰动)。
        #         要求当天必须同时有 SSE 和 SZSE, 否则视为"数据未就绪", 不写入缓存(见下方)。
        margin_df = margin_df[["trade_date", "exchange_id", "rzmre"]].copy()
        margin_df["rzmre_yi"] = margin_df["rzmre"] / 1e8  # 元 → 亿元
        # 只保留沪深两市(与分母口径一致),排除 BSE
        margin_df = margin_df[margin_df["exchange_id"].isin(["SSE", "SZSE"])]
        # 透视: 每个交易日一行, SSE/SZSE 各一列
        pivot = margin_df.pivot_table(index="trade_date", columns="exchange_id",
                                      values="rzmre_yi", aggfunc="sum")
        # 完整性校验: 必须同时有 SSE 和 SZSE 且都非空, 否则丢弃该交易日
        need_cols = {"SSE", "SZSE"}
        if not need_cols.issubset(set(pivot.columns)):
            logger.warning(f"  margin 数据不含完整沪深两市(仅 {list(pivot.columns)}),本次无完整新数据")
            return existing
        complete = pivot.dropna(subset=["SSE", "SZSE"])
        dropped = len(pivot) - len(complete)
        if dropped > 0:
            dropped_dates = pivot[pivot[["SSE", "SZSE"]].isna().any(axis=1)].index.tolist()
            logger.warning(f"  ⚠️ 丢弃 {dropped} 个交易所不完整的交易日(数据未就绪): {dropped_dates}")
        if len(complete) == 0:
            logger.warning("  margin 无任何完整交易日, 跳过写入")
            return existing
        margin_agg = complete.reset_index()
        margin_agg["total_rzmre_yi"] = margin_agg["SSE"] + margin_agg["SZSE"]
        margin_agg = margin_agg[["trade_date", "total_rzmre_yi"]]

        # 2. 两市成交额(上证综指 + 深证成指)
        sse_df = self._safe_call("index_daily", ts_code="000001.SH",
                                 start_date=start_date, end_date=end_date,
                                 fields="trade_date,amount")
        szse_df = self._safe_call("index_daily", ts_code="399001.SZ",
                                  start_date=start_date, end_date=end_date,
                                  fields="trade_date,amount")
        if sse_df is None or szse_df is None:
            logger.warning("index_daily 接口返回空")
            return existing

        # amount 单位: 千元 → 亿元 = amount / 1e5
        sse_df["sse_amount_yi"] = sse_df["amount"] / 1e5
        szse_df["szse_amount_yi"] = szse_df["amount"] / 1e5
        sse_df = sse_df[["trade_date", "sse_amount_yi"]]
        szse_df = szse_df[["trade_date", "szse_amount_yi"]]

        # 3. 合并
        merged = margin_agg.merge(sse_df, on="trade_date", how="inner")
        merged = merged.merge(szse_df, on="trade_date", how="inner")
        merged["total_amount_yi"] = merged["sse_amount_yi"] + merged["szse_amount_yi"]
        merged["ratio_pct"] = merged["total_rzmre_yi"] / merged["total_amount_yi"] * 100
        merged = merged[["trade_date", "total_rzmre_yi", "total_amount_yi", "ratio_pct"]]

        # 4. 增量保存
        return self.cache.append_unique(cache_name, merged, dedup_keys=["trade_date"])

    # ============ 维度4: 沪深300 ERP ============

    def _fetch_cn_10y_yield_akshare(self) -> Optional[pd.DataFrame]:
        """用 AkShare 取中国10年期国债收益率日频真实序列(无需 Tushare 权限)。
        返回 DataFrame[trade_date(YYYYMMDD), yield_10y_pct] 或 None(失败)。"""
        try:
            import akshare as ak
            raw = ak.bond_zh_us_rate()
            df = raw[["日期", "中国国债收益率10年"]].copy()
            df.columns = ["trade_date", "yield_10y_pct"]
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
            df = df.sort_values("trade_date")
            df["yield_10y_pct"] = df["yield_10y_pct"].ffill()
            df = df.dropna(subset=["yield_10y_pct"])
            if len(df) == 0:
                return None
            logger.info(f"  ✅ AkShare 国债收益率 {len(df)} 行,最新 {df['yield_10y_pct'].iloc[-1]:.4f}%")
            return df.reset_index(drop=True)
        except Exception as e:
            logger.warning(f"⚠️ AkShare 取国债收益率失败: {e!r}")
            return None

    def fetch_hs300_erp(self, days: int = 5 * 252,
                        fallback_yield_10y_pct: float = 2.30) -> Optional[pd.DataFrame]:
        """沪深300 ERP = 1/PE_TTM - 10年期国债收益率

        Tushare yc_cb 接口需要更高积分(5000+),2000积分用户拿不到。
        本方法支持 fallback: 当 yc_cb 不可用时,使用固定的国债收益率值(默认 2.30%)。
        建议在 secrets.json 配置 yield_10y_pct,每月手动更新一次(国债收益率变化慢)。

        返回: DataFrame columns = [trade_date, pe_ttm, yield_10y_pct, erp_pct,
                                   mean_5y, std_5y, percentile_5y, sigma_multiple,
                                   yield_source]  # "yc_cb" / "fallback"
        """
        cache_name = "hs300_erp_history"
        existing = self.cache.load(cache_name)

        last_date = self.cache.last_date(cache_name)
        if last_date:
            start_date = _ymd_minus(last_date, -1)
        else:
            start_date = _ymd_minus(_today_ymd(), days + 30)
        end_date = _today_ymd()

        if start_date >= end_date:
            logger.info(f"  ERP缓存已最新({last_date}),跳过拉取")
            return existing

        logger.info(f"  拉取沪深300 ERP数据 {start_date} → {end_date}")

        # 1. 沪深300 PE-TTM (index_dailybasic)
        pe_df = self._safe_call("index_dailybasic", ts_code=HS300_INDEX,
                                start_date=start_date, end_date=end_date,
                                fields="trade_date,pe_ttm")
        if pe_df is None or len(pe_df) == 0:
            logger.warning("index_dailybasic 返回空")
            return existing

        # 2. 10年期国债收益率(AkShare 真实时变序列优先,失败则 fallback 常数)
        yc_df = self._fetch_cn_10y_yield_akshare()

        if yc_df is not None and len(yc_df) > 0:
            yield_source = "akshare"
        else:
            # Fallback: AkShare 也失败时,用固定值兜底,保证宏观层不崩
            logger.warning(f"⚠️ AkShare 不可用,使用 fallback yield_10y_pct={fallback_yield_10y_pct}%")
            yc_df = pe_df[["trade_date"]].copy()
            yc_df["yield_10y_pct"] = fallback_yield_10y_pct
            yield_source = "fallback"

        # 3. 合并 & 计算 ERP
        merged = pe_df.merge(yc_df, on="trade_date", how="inner")
        # 异常值过滤:pe_ttm > 0 才有意义
        merged = merged[merged["pe_ttm"] > 0].copy()
        merged["erp_pct"] = (1.0 / merged["pe_ttm"]) * 100 - merged["yield_10y_pct"]
        merged["yield_source"] = yield_source

        # 4. 增量保存基础列
        base_cols = ["trade_date", "pe_ttm", "yield_10y_pct", "erp_pct", "yield_source"]
        merged_base = merged[base_cols]
        full = self.cache.append_unique(cache_name, merged_base, dedup_keys=["trade_date"])

        # 5. 重新计算5年滚动统计(全量数据上算)
        full = full.sort_values("trade_date").reset_index(drop=True)
        window = 1250  # 5年 × 250 交易日
        full["mean_5y"] = full["erp_pct"].rolling(window, min_periods=window // 2).mean()
        full["std_5y"] = full["erp_pct"].rolling(window, min_periods=window // 2).std()
        full["sigma_multiple"] = (full["erp_pct"] - full["mean_5y"]) / full["std_5y"]

        # 百分位需要逐行算
        def _rolling_pct(s: pd.Series) -> pd.Series:
            out = []
            for i in range(len(s)):
                start = max(0, i - window + 1)
                window_data = s.iloc[start:i + 1]
                if len(window_data) < window // 2:
                    out.append(np.nan)
                else:
                    cur = s.iloc[i]
                    out.append((window_data < cur).sum() / len(window_data) * 100)
            return pd.Series(out, index=s.index)

        full["percentile_5y"] = _rolling_pct(full["erp_pct"])

        # 重新保存(覆盖含统计列的完整版)
        self.cache.save(cache_name, full)
        return full

    # ============ 维度6: M1 月度同比 ============

    def fetch_m1_yoy(self, months: int = 10 * 12) -> Optional[pd.DataFrame]:
        """M1月度同比,近10年

        返回: DataFrame columns = [month, m1, m1_yoy, m1_yoy_mom_delta]
              month: YYYYMM
              m1_yoy_mom_delta: 月环比变化(pp), 用于判断加速/减速
        """
        cache_name = "m1_yoy_history"

        # M1 数据每月更新,直接全量拉
        logger.info(f"  拉取M1货币供应数据(近{months}个月)")
        cn_m_df = self._safe_call("cn_m", start_m="201501")
        if cn_m_df is None or len(cn_m_df) == 0:
            logger.warning("cn_m 返回空")
            return self.cache.load(cache_name)

        # 字段: month, m0, m0_yoy, m0_mom, m1, m1_yoy, m1_mom, m2, m2_yoy, m2_mom
        cn_m_df = cn_m_df[["month", "m1", "m1_yoy"]].copy()
        cn_m_df = cn_m_df.sort_values("month").reset_index(drop=True)
        # 月环比变化(同比的变化)
        cn_m_df["m1_yoy_mom_delta"] = cn_m_df["m1_yoy"].diff()

        self.cache.save(cache_name, cn_m_df)
        return cn_m_df

    def fetch_sf_pulse(self, months: int = 12 * 8) -> Optional[pd.DataFrame]:
        """社融信贷脉冲, 近8年(算TTM同比的二阶加速度需 12+12+缓冲 >= 36个月)。

        数据源: Tushare sf_month (社会融资规模月度), 复用 _safe_call + cache, 与 cn_m 同架构。
        返回: DataFrame columns = [month, sf_inc, sf_ttm, sf_pulse_yoy, sf_pulse_accel]
              month: YYYYMM
              sf_inc: 当月社融增量(单位以Tushare原始为准, 比例计算不受单位影响)
              sf_ttm: 12个月滚动和(去季节性)
              sf_pulse_yoy: TTM同比(%) = 信贷脉冲水平
              sf_pulse_accel: 脉冲同比的环比差分(pp) = 加速度

        P0: 字段名不臆测 — 首次运行打印真实列名供确认; 拉不到/历史不足/断月 返回 None(上层标待验证)。
        """
        cache_name = "sf_pulse_history"

        logger.info(f"  拉取社融月度数据(近{months}个月)")
        df = self._safe_call("sf_month", start_m="201501")
        if df is None or len(df) == 0:
            logger.warning("sf_month 返回空, 社融脉冲标待验证")
            return self.cache.load(cache_name)

        # --- 字段自适应探针(P0: 不臆测字段名/单位) ---
        cols = list(df.columns)
        logger.info(f"  [待确认] sf_month 实际字段: {cols}")
        month_col = "month" if "month" in cols else cols[0]
        inc_candidates = [c for c in ("inc_month", "inc_val", "sf_inc") if c in cols]
        if not inc_candidates:
            logger.warning(f"  sf_month 未识别到增量列(候选inc_month/inc_val均无), 实际列={cols}; 标待验证")
            return self.cache.load(cache_name)
        inc_col = inc_candidates[0]

        df = df[[month_col, inc_col]].copy()
        df.columns = ["month", "sf_inc"]
        df["month"] = df["month"].astype(str)
        df["sf_inc"] = pd.to_numeric(df["sf_inc"], errors="coerce")
        df = df.dropna(subset=["sf_inc"]).sort_values("month").reset_index(drop=True)

        # --- 月份连续性校验(P0: 断月不静默跳过) ---
        months_seq = pd.to_datetime(df["month"], format="%Y%m", errors="coerce")
        if months_seq.isna().any():
            logger.warning("  sf_month 月份格式异常, 标待验证")
            return self.cache.load(cache_name)
        expected = pd.period_range(months_seq.min().to_period("M"),
                                   months_seq.max().to_period("M"), freq="M")
        actual = months_seq.dt.to_period("M")
        missing = sorted(set(expected) - set(actual))
        if missing:
            logger.warning(f"  社融数据断月 {len(missing)} 个: {[str(m) for m in missing[:6]]}; "
                           f"TTM滚动和受影响, 标待验证")
            return self.cache.load(cache_name)

        # --- 计算: TTM去季节性 -> 脉冲 -> 加速度 ---
        if len(df) < 36:
            logger.warning(f"  社融历史仅{len(df)}月(<36), 不足以算二阶加速度, 标待验证")
            return self.cache.load(cache_name)

        df["sf_ttm"] = df["sf_inc"].rolling(12).sum()
        df["sf_pulse_yoy"] = df["sf_ttm"].pct_change(12) * 100
        df["sf_pulse_accel"] = df["sf_pulse_yoy"].diff()
        df = df.dropna(subset=["sf_pulse_yoy", "sf_pulse_accel"]).reset_index(drop=True)

        if len(df) == 0:
            logger.warning("  社融脉冲计算后为空, 标待验证")
            return self.cache.load(cache_name)

        self.cache.save(cache_name, df)
        logger.info(f"  ✅ 社融脉冲 {len(df)} 行, 最新脉冲YoY={df['sf_pulse_yoy'].iloc[-1]:+.2f}% "
                    f"加速度={df['sf_pulse_accel'].iloc[-1]:+.2f}pp")
        return df

    # ============ 维度1: 5大宽基ETF净申赎 ============

    def fetch_etf_net_subscription(self, days: int = 3 * 252) -> Optional[pd.DataFrame]:
        """5大宽基ETF净申赎,近3年

        返回: DataFrame columns = [trade_date, etf_code, etf_name, manager,
                                   fd_share, share_change, close, net_sub_yi]
              net_sub_yi: 净申赎金额(亿元) = (今日fd_share - 昨日fd_share) × 今日close
        """
        cache_name = "etf_share_history"
        existing = self.cache.load(cache_name)

        last_date = self.cache.last_date(cache_name)
        if last_date:
            start_date = _ymd_minus(last_date, -1)
        else:
            start_date = _ymd_minus(_today_ymd(), days + 30)
        end_date = _today_ymd()

        if start_date >= end_date:
            logger.info(f"  ETF缓存已最新({last_date}),跳过拉取")
            return self._compute_etf_net_sub(existing)

        logger.info(f"  拉取5只ETF份额数据 {start_date} → {end_date}")

        all_etf_dfs = []
        for etf_code, (etf_name, manager) in ETF_BASKET.items():
            # 1. fund_share - 流通份额(亿份)
            share_df = self._safe_call("fund_share", ts_code=etf_code,
                                       start_date=start_date, end_date=end_date)
            # 2. fund_daily - 单位净值
            daily_df = self._safe_call("fund_daily", ts_code=etf_code,
                                       start_date=start_date, end_date=end_date,
                                       fields="trade_date,close")
            if share_df is None or daily_df is None or len(share_df) == 0 or len(daily_df) == 0:
                logger.debug(f"  {etf_code} 数据缺失,跳过")
                continue

            merged = share_df[["trade_date", "fd_share"]].merge(
                daily_df, on="trade_date", how="inner"
            )
            merged["etf_code"] = etf_code
            merged["etf_name"] = etf_name
            merged["manager"] = manager
            all_etf_dfs.append(merged)

        if not all_etf_dfs:
            return self._compute_etf_net_sub(existing)

        new_data = pd.concat(all_etf_dfs, ignore_index=True)
        merged_all = self.cache.append_unique(cache_name, new_data,
                                              dedup_keys=["trade_date", "etf_code"])
        return self._compute_etf_net_sub(merged_all)

    def _compute_etf_net_sub(self, df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """从缓存数据计算每日净申赎金额

        Tushare fund_share 接口的 fd_share 字段单位是 **万份**,
        close 单位是 **元/份**,
        所以: Δshare(万份) × close(元/份) = 万元
              万元 / 10000 = 亿元 ← 我们要的单位
        """
        if df is None or len(df) == 0:
            return None
        df = df.sort_values(["etf_code", "trade_date"]).reset_index(drop=True)
        df["share_change"] = df.groupby("etf_code")["fd_share"].diff()
        # net_sub = Δshare(万份) × close(元/份) / 10000 = 亿元
        df["net_sub_yi"] = df["share_change"] * df["close"] / 10000
        return df

    # ============ 维度3: 全A换手率(中证全指代理) ============

    # 全A 换手率代理指数候选(按优先级)
    # 注意: Tushare 的 index_dailybasic 不支持 .CSI 后缀,要用 .SH
    TURNOVER_PROXY_CANDIDATES = ["000985.SH", "000300.SH"]

    def fetch_market_turnover(self, days: int = 3 * 252) -> Optional[pd.DataFrame]:
        """全A换手率(用中证全指 000985.SH 代理,失败回退沪深300),近3年

        返回: DataFrame columns = [trade_date, turnover_rate, percentile_3y, proxy_code]
        """
        cache_name = "turnover_history"
        existing = self.cache.load(cache_name)

        last_date = self.cache.last_date(cache_name)
        if last_date:
            start_date = _ymd_minus(last_date, -1)
        else:
            start_date = _ymd_minus(_today_ymd(), days + 30)
        end_date = _today_ymd()

        if start_date >= end_date:
            logger.info(f"  换手率缓存已最新({last_date}),跳过拉取")
            return existing

        # 尝试候选指数,直到拿到数据
        df = None
        proxy_used = None
        for proxy in self.TURNOVER_PROXY_CANDIDATES:
            logger.info(f"  拉取换手率数据 {proxy} {start_date} → {end_date}")
            df = self._safe_call("index_dailybasic", ts_code=proxy,
                                 start_date=start_date, end_date=end_date,
                                 fields="trade_date,turnover_rate")
            if df is not None and len(df) > 0:
                proxy_used = proxy
                logger.info(f"  ✅ 换手率使用指数: {proxy}")
                break

        if df is None or len(df) == 0:
            logger.warning(f"换手率所有候选指数 {self.TURNOVER_PROXY_CANDIDATES} 都返回空")
            return existing

        df["proxy_code"] = proxy_used
        merged = self.cache.append_unique(cache_name, df, dedup_keys=["trade_date"])

        # 计算3年滚动百分位
        merged = merged.sort_values("trade_date").reset_index(drop=True)
        window = 750
        def _rolling_pct(s: pd.Series) -> pd.Series:
            out = []
            for i in range(len(s)):
                start = max(0, i - window + 1)
                window_data = s.iloc[start:i + 1]
                if len(window_data) < window // 2:
                    out.append(np.nan)
                else:
                    cur = s.iloc[i]
                    out.append((window_data < cur).sum() / len(window_data) * 100)
            return pd.Series(out, index=s.index)

        merged["percentile_3y"] = _rolling_pct(merged["turnover_rate"])
        self.cache.save(cache_name, merged)
        return merged

    # ============ 维度5: 全A宽度(MA60/MA200/MA250 BIAS) ============

    def fetch_market_breadth(self, days: int = 5 * 252) -> Optional[Dict[str, pd.DataFrame]]:
        """全A宽度三指标
        - above_ma60_pct: 高于MA60的股票比例
        - above_ma200_pct: 高于MA200的股票比例
        - ma250_bias: 中证全指相对MA250的乖离率

        返回: {
          "breadth": DataFrame(trade_date, above_ma60_pct, above_ma200_pct,
                               above_ma60_percentile_5y, above_ma200_percentile_5y),
          "bias": DataFrame(trade_date, idx_close, ma250, bias_pct, percentile_5y)
        }

        ⚠️ 注意:全A遍历方案数据量大(5400股 × 250天 ≈ 1.3M记录),
        首次运行需要 30-60 分钟,后续每天增量约 1-3 分钟。
        简化策略:用中证全指(000985.CSI)的成分股(约 2000+ 大中盘)代替全市场。
        """
        return {
            "breadth": self._fetch_breadth_ma_ratio(days),
            "bias": self._fetch_ma250_bias(days),
        }

    def _fetch_ma250_bias(self, days: int = 5 * 252) -> Optional[pd.DataFrame]:
        """中证全指 MA250 BIAS (简单实现)"""
        cache_name = "ma250_bias_history"
        existing = self.cache.load(cache_name)

        # 需要250天的历史才能算 MA250,所以多拉一些
        last_date = self.cache.last_date(cache_name)
        if last_date:
            start_date = _ymd_minus(last_date, -1)
        else:
            start_date = _ymd_minus(_today_ymd(), days + 300)
        end_date = _today_ymd()

        logger.info(f"  拉取中证全指收盘价 {start_date} → {end_date}")
        df = self._safe_call("index_daily", ts_code=WHOLE_MARKET_PROXY,
                             start_date=start_date, end_date=end_date,
                             fields="trade_date,close")
        if df is None or len(df) == 0:
            return existing

        df = df.rename(columns={"close": "idx_close"})
        merged = self.cache.append_unique(cache_name + "_raw", df, dedup_keys=["trade_date"])
        merged = merged.sort_values("trade_date").reset_index(drop=True)

        merged["ma250"] = merged["idx_close"].rolling(250, min_periods=200).mean()
        merged["bias_pct"] = (merged["idx_close"] - merged["ma250"]) / merged["ma250"] * 100

        # 5年百分位
        window = 1250
        def _rolling_pct(s: pd.Series) -> pd.Series:
            out = []
            for i in range(len(s)):
                start = max(0, i - window + 1)
                wd = s.iloc[start:i + 1]
                if len(wd) < window // 2 or s.iloc[i] is None or pd.isna(s.iloc[i]):
                    out.append(np.nan)
                else:
                    out.append((wd < s.iloc[i]).sum() / len(wd) * 100)
            return pd.Series(out, index=s.index)

        merged["percentile_5y"] = _rolling_pct(merged["bias_pct"])
        self.cache.save(cache_name, merged)
        return merged

    def _fetch_breadth_ma_ratio(self, days: int = 5 * 252) -> Optional[pd.DataFrame]:
        """全A高于MA60/MA200比例 - v1.3.2 按交易日批量拉取(2026-06-15 优化)

        关键优化:从"按股票循环4827次API"改成"按交易日循环N次API"
        - 旧版本: for ts_code in 4827只: daily(ts_code=X) → ~10分钟/日
        - 新版本: for trade_date in N天: daily(trade_date=X) → 日常<30秒,首次回填~5分钟

        Tushare daily 接口支持 trade_date 参数,一次返回当天所有A股的日K数据。
        """
        cache_name = "market_breadth_ratio_history"
        existing = self.cache.load(cache_name)

        today_ymd = _today_ymd()

        # 1. 加载日K缓存
        kline_cache = self.cache.load("stocks_daily_pivot")

        # 2. 决定需要拉取的交易日范围
        if kline_cache is not None and len(kline_cache) > 0 and "trade_date" in kline_cache.columns:
            kline_last = str(kline_cache["trade_date"].max())
            if kline_last >= today_ymd:
                logger.info(f"  全A日K缓存已最新({kline_last}),跳过拉取")
                # 数据没新增,但仍需重算 breadth(确保最新)
                return self._compute_breadth_from_klines(kline_cache, cache_name)
            start_fetch = _ymd_minus(kline_last, -1)  # 缓存最新日期 +1
        else:
            # 首次回填: 5年 + 280天缓冲(为算 MA250 需要)
            start_fetch = _ymd_minus(today_ymd, days + 280)
            kline_last = None

        end_fetch = today_ymd
        logger.info(f"  全A日K拉取范围 {start_fetch} → {end_fetch}")

        # 3. 获取需要拉取的交易日列表(用上证综指反查交易日历)
        trade_cal_df = self._safe_call("index_daily", ts_code="000001.SH",
                                       start_date=start_fetch, end_date=end_fetch,
                                       fields="trade_date")
        if trade_cal_df is None or len(trade_cal_df) == 0:
            logger.info(f"  无新交易日 ({start_fetch}→{end_fetch}),用现有缓存")
            if kline_cache is not None and len(kline_cache) > 0:
                return self._compute_breadth_from_klines(kline_cache, cache_name)
            return existing

        trade_dates = sorted(trade_cal_df["trade_date"].astype(str).unique().tolist())
        # 排除已缓存的日期
        if kline_last:
            trade_dates = [d for d in trade_dates if d > kline_last]
        logger.info(f"  需要拉取 {len(trade_dates)} 个交易日的全A数据")

        if not trade_dates:
            logger.info(f"  无新交易日需要拉取")
            if kline_cache is not None and len(kline_cache) > 0:
                return self._compute_breadth_from_klines(kline_cache, cache_name)
            return existing

        # 4. 按交易日批量拉取(关键优化:每个交易日 1 次 API,而不是 4827 次)
        new_klines = []
        log_interval = max(1, len(trade_dates) // 20)  # 最多打 20 条进度
        for i, trade_date in enumerate(trade_dates):
            if i % log_interval == 0 or i == len(trade_dates) - 1:
                logger.info(f"  全A按日拉取进度: {i+1}/{len(trade_dates)} (日期={trade_date})")
            df = self._safe_call("daily", trade_date=trade_date,
                                 fields="ts_code,trade_date,close")
            if df is not None and len(df) > 0:
                # 过滤北交所(8字头)+ 科创板(688) — 与 v1.3 行为一致
                df = df[~df["ts_code"].str.startswith(("8", "688"))].copy()
                new_klines.append(df)

        if new_klines:
            new_df = pd.concat(new_klines, ignore_index=True)
            kline_cache = self.cache.append_unique(
                "stocks_daily_pivot", new_df, dedup_keys=["ts_code", "trade_date"]
            )
            logger.info(f"  日K增量: 新增{len(new_df)}行(覆盖{len(trade_dates)}个交易日)")

        if kline_cache is None or len(kline_cache) == 0:
            return existing

        return self._compute_breadth_from_klines(kline_cache, cache_name)

    def _compute_breadth_from_klines(self, kline_cache: pd.DataFrame,
                                     cache_name: str) -> pd.DataFrame:
        """从全A日K缓存计算 above_ma60/above_ma200 比例 + 5年百分位

        独立成方法是为了:数据缓存已最新时,可以直接跳过拉取,只重新计算指标
        """
        # 1. 透视成 wide 表(date 为 index, ts_code 为 columns, close 为值)
        logger.info("  计算 MA60/MA200 比例...")
        wide = kline_cache.pivot_table(index="trade_date", columns="ts_code",
                                       values="close", aggfunc="last")
        wide = wide.sort_index()

        ma60 = wide.rolling(60, min_periods=40).mean()
        ma200 = wide.rolling(200, min_periods=120).mean()

        # 有效股票数 = MA 非空且 close 非空的股票数
        valid_60 = (~ma60.isna() & ~wide.isna()).sum(axis=1)
        valid_200 = (~ma200.isna() & ~wide.isna()).sum(axis=1)

        # 用 where 确保只统计 MA 有效的股票
        above_ma60_mask = (wide > ma60).where(~ma60.isna() & ~wide.isna(), 0)
        above_ma200_mask = (wide > ma200).where(~ma200.isna() & ~wide.isna(), 0)

        above_ma60_count = above_ma60_mask.sum(axis=1)
        above_ma200_count = above_ma200_mask.sum(axis=1)

        breadth = pd.DataFrame({
            "trade_date": wide.index,
            "above_ma60_pct": (above_ma60_count / valid_60.replace(0, np.nan) * 100).values,
            "above_ma200_pct": (above_ma200_count / valid_200.replace(0, np.nan) * 100).values,
            "valid_count_ma60": valid_60.values,
            "valid_count_ma200": valid_200.values,
        }).reset_index(drop=True)

        # 2. 算5年滚动百分位
        breadth = breadth.sort_values("trade_date").reset_index(drop=True)
        window = 1250
        def _rolling_pct(s: pd.Series) -> pd.Series:
            out = []
            for i in range(len(s)):
                start = max(0, i - window + 1)
                wd = s.iloc[start:i + 1].dropna()
                cur = s.iloc[i]
                if len(wd) < window // 2 or pd.isna(cur):
                    out.append(np.nan)
                else:
                    out.append((wd < cur).sum() / len(wd) * 100)
            return pd.Series(out, index=s.index)

        breadth["above_ma60_percentile_5y"] = _rolling_pct(breadth["above_ma60_pct"])
        breadth["above_ma200_percentile_5y"] = _rolling_pct(breadth["above_ma200_pct"])

        self.cache.save(cache_name, breadth)
        return breadth

    # ============ 综合摘要 + Regime ============

    def summary(self) -> Dict[str, Any]:
        """生成当日6维度摘要,带信号评级和综合 regime 判断"""
        logger.info("===== 宏观6维度数据采集开始 =====")

        result: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "indicators": {},
            "signals": [],
            "macro_regime": None,
            "errors": [],
        }

        # 维度1: ETF净申赎
        try:
            etf_df = self.fetch_etf_net_subscription()
            if etf_df is not None and len(etf_df) > 0:
                # 聚合所有ETF的5日/20日净申赎
                etf_df = etf_df.sort_values("trade_date")
                daily_sum = etf_df.groupby("trade_date")["net_sub_yi"].sum()
                latest_5d = daily_sum.tail(5).sum()
                latest_20d = daily_sum.tail(20).sum()
                # 明细
                latest_date = etf_df["trade_date"].max()
                latest_details = etf_df[etf_df["trade_date"] == latest_date][
                    ["etf_code", "etf_name", "net_sub_yi"]
                ].to_dict(orient="records")
                sig_5d = grade_signal(latest_5d, SIGNAL_THRESHOLDS["etf_net_sub_5d"])
                sig_20d = grade_signal(latest_20d, SIGNAL_THRESHOLDS["etf_net_sub_20d"])
                result["indicators"]["etf_net_sub"] = {
                    "value_5d_yi": float(latest_5d),
                    "value_20d_yi": float(latest_20d),
                    "signal_5d": sig_5d,
                    "signal_20d": sig_20d,
                    "details_latest_day": latest_details,
                    "latest_date": str(latest_date),
                }
                result["signals"].extend([sig_5d, sig_20d])
            else:
                result["errors"].append("etf_net_sub: fetch_etf_net_subscription 返回空")
        except Exception as e:
            logger.warning(f"ETF净申赎采集失败: {e}")
            result["errors"].append(f"etf_net_sub: {e}")

        # 维度2: 融资比
        try:
            margin_df = self.fetch_margin_to_volume()
            if margin_df is not None and len(margin_df) > 0:
                margin_df = margin_df.sort_values("trade_date")
                latest = margin_df.iloc[-1]
                cur_ratio = float(latest["ratio_pct"])
                pct_3y = calc_percentile(margin_df["ratio_pct"].tail(750), cur_ratio)
                # lower_better: 百分位低 = 看多
                sig = grade_signal(pct_3y, SIGNAL_THRESHOLDS["margin_ratio_pct_3y"],
                                   direction="lower_better")
                # 【修复 2026-06-19】数据就绪标注:
                #   fetch_margin_to_volume 已保证只返回 SSE+SZSE 齐全的完整交易日。
                #   若最新完整日 < 今日, 说明今日融资数据未就绪, 已自动往前推到最近完整日。
                data_date = str(latest["trade_date"])
                stale = data_date < _today_ymd()
                result["indicators"]["margin_ratio"] = {
                    "ratio_pct": cur_ratio,
                    "percentile_3y": pct_3y,
                    "signal": sig,
                    "latest_date": data_date,
                    "stale": stale,  # True=今日数据未就绪,采用历史最近完整日
                }
                result["signals"].append(sig)
            else:
                result["errors"].append("margin_ratio: fetch_margin_to_volume 返回空")
        except Exception as e:
            logger.warning(f"融资比采集失败: {e}")
            result["errors"].append(f"margin_ratio: {e}")

        # 维度3: 全A换手率
        try:
            turnover_df = self.fetch_market_turnover()
            if turnover_df is not None and len(turnover_df) > 0:
                turnover_df = turnover_df.sort_values("trade_date")
                latest = turnover_df.iloc[-1]
                cur_to = float(latest["turnover_rate"])
                pct_3y = float(latest["percentile_3y"]) if not pd.isna(latest["percentile_3y"]) else None
                sig = grade_signal(pct_3y, SIGNAL_THRESHOLDS["turnover_pct_3y"],
                                   direction="lower_better")
                result["indicators"]["turnover"] = {
                    "turnover_rate": cur_to,
                    "percentile_3y": pct_3y,
                    "signal": sig,
                    "proxy_code": str(latest.get("proxy_code", "-")),
                    "latest_date": str(latest["trade_date"]),
                }
                result["signals"].append(sig)
            else:
                result["errors"].append("turnover: fetch_market_turnover 返回空(所有候选指数均不可用)")
        except Exception as e:
            logger.warning(f"换手率采集失败: {e}")
            result["errors"].append(f"turnover: {e}")

        # 维度4: 沪深300 ERP
        try:
            erp_df = self.fetch_hs300_erp(fallback_yield_10y_pct=self.fallback_yield_10y_pct)
            if erp_df is not None and len(erp_df) > 0:
                erp_df = erp_df.sort_values("trade_date")
                latest = erp_df.iloc[-1]
                cur_erp = float(latest["erp_pct"])
                pct_5y = float(latest["percentile_5y"]) if not pd.isna(latest["percentile_5y"]) else None
                sigma = float(latest["sigma_multiple"]) if not pd.isna(latest["sigma_multiple"]) else None
                pe_ttm = float(latest["pe_ttm"])
                yield_10y = float(latest["yield_10y_pct"])
                yield_source = str(latest.get("yield_source", "unknown"))
                # 双重信号:取较强的
                sig_pct = grade_signal(pct_5y, SIGNAL_THRESHOLDS["erp_pct_5y"])
                sig_sigma = grade_signal(sigma, SIGNAL_THRESHOLDS["erp_sigma"])
                # 综合 ERP 信号:取两者中较强者
                priority = {"❌❌": 0, "❌": 1, "⚠️": 2, "🚫": 2, "✅": 3, "✅✅": 4}
                final_sig = max([sig_pct, sig_sigma], key=lambda s: priority.get(s, 2))
                result["indicators"]["hs300_erp"] = {
                    "pe_ttm": pe_ttm,
                    "yield_10y_pct": yield_10y,
                    "yield_source": yield_source,
                    "erp_pct": cur_erp,
                    "percentile_5y": pct_5y,
                    "sigma_multiple": sigma,
                    "signal_by_percentile": sig_pct,
                    "signal_by_sigma": sig_sigma,
                    "signal": final_sig,
                    "latest_date": str(latest["latest_date"] if "latest_date" in latest else latest["trade_date"]),
                }
                result["signals"].append(final_sig)
            else:
                result["errors"].append("hs300_erp: fetch_hs300_erp 返回空")
        except Exception as e:
            logger.warning(f"ERP采集失败: {e}")
            result["errors"].append(f"hs300_erp: {e}")

        # 维度5: 市场宽度 + BIAS
        try:
            breadth_data = self.fetch_market_breadth()
            if breadth_data:
                breadth_df = breadth_data.get("breadth")
                bias_df = breadth_data.get("bias")

                # 5a + 5b: MA60/200 比例
                if breadth_df is not None and len(breadth_df) > 0:
                    breadth_df = breadth_df.sort_values("trade_date")
                    latest = breadth_df.iloc[-1]
                    above_ma60 = float(latest["above_ma60_pct"]) if not pd.isna(latest["above_ma60_pct"]) else None
                    above_ma200 = float(latest["above_ma200_pct"]) if not pd.isna(latest["above_ma200_pct"]) else None
                    sig_ma60 = grade_signal(above_ma60, SIGNAL_THRESHOLDS["above_ma60_pct"],
                                            direction="lower_better")
                    sig_ma200 = grade_signal(above_ma200, SIGNAL_THRESHOLDS["above_ma200_pct"],
                                             direction="lower_better")
                    result["indicators"]["above_ma60"] = {
                        "value_pct": above_ma60,
                        "valid_stocks": int(latest.get("valid_count_ma60", 0)),
                        "signal": sig_ma60,
                        "latest_date": str(latest["trade_date"]),
                    }
                    result["indicators"]["above_ma200"] = {
                        "value_pct": above_ma200,
                        "valid_stocks": int(latest.get("valid_count_ma200", 0)),
                        "signal": sig_ma200,
                        "latest_date": str(latest["trade_date"]),
                    }
                    result["signals"].extend([sig_ma60, sig_ma200])
                else:
                    result["errors"].append("market_breadth_ma: 全A宽度计算返回空")

                # 5c: MA250 BIAS
                if bias_df is not None and len(bias_df) > 0:
                    bias_df = bias_df.sort_values("trade_date")
                    latest = bias_df.iloc[-1]
                    bias = float(latest["bias_pct"]) if not pd.isna(latest["bias_pct"]) else None
                    pct_5y = float(latest["percentile_5y"]) if not pd.isna(latest["percentile_5y"]) else None
                    sig = grade_signal(bias, SIGNAL_THRESHOLDS["ma250_bias"],
                                       direction="lower_better")
                    result["indicators"]["ma250_bias"] = {
                        "bias_pct": bias,
                        "percentile_5y": pct_5y,
                        "signal": sig,
                        "latest_date": str(latest["trade_date"]),
                    }
                    result["signals"].append(sig)
                else:
                    result["errors"].append("ma250_bias: 中证全指 BIAS 计算返回空")
            else:
                result["errors"].append("market_breadth: fetch_market_breadth 返回空")
        except Exception as e:
            logger.warning(f"市场宽度采集失败: {e}")
            result["errors"].append(f"market_breadth: {e}")

        # 维度6: M1 同比
        try:
            m1_df = self.fetch_m1_yoy()
            if m1_df is not None and len(m1_df) > 0:
                m1_df = m1_df.sort_values("month")
                latest = m1_df.iloc[-1]
                cur_yoy = float(latest["m1_yoy"])
                mom_delta = float(latest["m1_yoy_mom_delta"]) if not pd.isna(latest["m1_yoy_mom_delta"]) else 0
                # 主信号 = 绝对值; 辅信号 = 月环比变化
                sig_abs = grade_signal(cur_yoy, SIGNAL_THRESHOLDS["m1_yoy"])
                sig_delta = grade_signal(mom_delta, SIGNAL_THRESHOLDS["m1_yoy_mom_delta"])
                # 综合:绝对值为主,环比变化加权(±0.5档)
                final_sig = sig_abs
                if sig_delta == "✅" and sig_abs in ("⚠️", "❌"):
                    final_sig = "⚠️" if sig_abs == "❌" else "✅"
                elif sig_delta == "❌" and sig_abs in ("⚠️", "✅"):
                    final_sig = "⚠️" if sig_abs == "✅" else "❌"
                # 10年百分位
                pct_10y = calc_percentile(m1_df["m1_yoy"].tail(120), cur_yoy)
                result["indicators"]["m1_yoy"] = {
                    "value_pct": cur_yoy,
                    "mom_delta_pp": mom_delta,
                    "percentile_10y": pct_10y,
                    "signal": final_sig,
                    "latest_month": str(latest["month"]),
                }
                result["signals"].append(final_sig)
            else:
                result["errors"].append("m1_yoy: fetch_m1_yoy 返回空")
        except Exception as e:
            logger.warning(f"M1采集失败: {e}")
            result["errors"].append(f"m1_yoy: {e}")


        # 维度7: 社融信贷脉冲
        try:
            sf_df = self.fetch_sf_pulse()
            if sf_df is not None and len(sf_df) > 0:
                sf_df = sf_df.sort_values("month")
                latest = sf_df.iloc[-1]
                pulse = float(latest["sf_pulse_yoy"])
                accel = float(latest["sf_pulse_accel"])
                if pulse > 0 and accel > 0:
                    sig = "✅"
                elif pulse > 0:
                    sig = "⚠️"
                else:
                    sig = "❌"
                result["indicators"]["sf_pulse"] = {
                    "pulse_yoy_pct": pulse,
                    "accel_pp": accel,
                    "signal": sig,
                    "latest_month": str(latest["month"]),
                }
                result["signals"].append(sig)
            else:
                result["errors"].append("sf_pulse: fetch_sf_pulse 返回空(待验证: 在Mac跑首次确认sf_month字段)")
        except Exception as e:
            logger.warning(f"社融脉冲采集失败: {e}")
            result["errors"].append(f"sf_pulse: {e}")

        # 综合 macro regime
        result["macro_regime"] = combine_signals(result["signals"])
        result["bullish_count"] = result["signals"].count("✅") + 2 * result["signals"].count("✅✅")
        result["bearish_count"] = result["signals"].count("❌") + 2 * result["signals"].count("❌❌")

        logger.info(f"===== 宏观数据采集完成: {result['macro_regime']} "
                    f"(✅×{result['bullish_count']} / ❌×{result['bearish_count']}) =====")
        return result


# ==================== 入口 ====================

def render_macro_section(macro_data: Optional[Dict[str, Any]]) -> str:
    """渲染宏观环境章节到 Claude markdown 报告

    与 hot_sector_scanner.render_hot_sector_section / opportunity_scanner.render_opportunity_section 风格保持一致
    """
    if macro_data is None:
        return ""

    indicators = macro_data.get("indicators", {})
    regime = macro_data.get("macro_regime", "🟡 中性")
    bull = macro_data.get("bullish_count", 0)
    bear = macro_data.get("bearish_count", 0)
    errors = macro_data.get("errors", []) or []

    lines = []
    lines.append("## 🌐 宏观环境 (v1.3)")
    lines.append("")
    lines.append(f"**综合 Macro Regime: {regime}** "
                 f"(✅×{bull} / ❌×{bear} / 总{len(macro_data.get('signals', []))}维度)")
    if errors:
        lines.append("")
        lines.append(f"> ⚠️ 数据缺失项 {len(errors)} 个: {', '.join(e.split(':')[0] for e in errors)}")
    lines.append("")

    # 2.1 流动性维度
    lines.append("### 1) 流动性维度")
    lines.append("")
    lines.append("| 指标 | 当前值 | 历史百分位 | 信号 |")
    lines.append("|---|---|---|---|")

    etf = indicators.get("etf_net_sub", {})
    if etf:
        v5 = etf.get("value_5d_yi")
        v20 = etf.get("value_20d_yi")
        s5 = etf.get("signal_5d", "🚫")
        s20 = etf.get("signal_20d", "🚫")
        date = etf.get("latest_date", "-")
        lines.append(f"| 5大ETF净申赎(5日累计) | **{v5:+.2f}亿** | - | {s5} |")
        lines.append(f"| 5大ETF净申赎(20日累计) | {v20:+.2f}亿 | - | {s20} |")
        # 明细
        det = etf.get("details_latest_day", [])
        if det:
            detail_str = ", ".join([f"{d['etf_name']}:{d['net_sub_yi']:+.2f}亿" for d in det])
            lines.append(f"| 当日明细({date}) | {detail_str} | - | - |")

    margin = indicators.get("margin_ratio", {})
    if margin:
        ratio = margin.get("ratio_pct")
        pct = margin.get("percentile_3y")
        sig = margin.get("signal", "🚫")
        pct_str = f"3年第{pct:.0f}%" if pct is not None else "-"
        # 【修复 2026-06-19】标注数据日期与就绪状态
        data_date = margin.get("latest_date", "")
        if margin.get("stale"):
            note = f" ⚠️采用{data_date}(今日数据未就绪)"
        else:
            note = ""
        lines.append(f"| 融资买入/两市成交额 | {ratio:.2f}% | {pct_str} | {sig}{note} |")

    turnover = indicators.get("turnover", {})
    if turnover:
        rate = turnover.get("turnover_rate")
        pct = turnover.get("percentile_3y")
        sig = turnover.get("signal", "🚫")
        pct_str = f"3年第{pct:.0f}%" if pct is not None else "-"
        lines.append(f"| 全A换手率(中证全指代理) | {rate:.2f}% | {pct_str} | {sig} |")

    m1 = indicators.get("m1_yoy", {})
    if m1:
        val = m1.get("value_pct")
        delta = m1.get("mom_delta_pp", 0)
        pct = m1.get("percentile_10y")
        sig = m1.get("signal", "🚫")
        delta_str = f"{delta:+.2f}pp vs 上月" if delta is not None else ""
        pct_str = f"10年第{pct:.0f}%" if pct is not None else "-"
        month = m1.get("latest_month", "-")
        lines.append(f"| M1月度同比({month}) | **{val:+.2f}%** {delta_str} | {pct_str} | {sig} |")

    sf = indicators.get("sf_pulse", {})
    if sf:
        pulse = sf.get("pulse_yoy_pct")
        accel = sf.get("accel_pp")
        sig = sf.get("signal", "🚫")
        mon = sf.get("latest_month", "-")
        lines.append(f"| 社融信贷脉冲(TTM同比,{mon}) | **{pulse:+.2f}%** | 加速度{accel:+.2f}pp | {sig} |")

    lines.append("")

    # 2.2 估值锚定
    lines.append("### 2) 估值锚定")
    lines.append("")
    lines.append("| 指标 | 当前值 | 5年均值/百分位 | σ倍数 | 信号 |")
    lines.append("|---|---|---|---|---|")
    erp = indicators.get("hs300_erp", {})
    if erp:
        pe = erp.get("pe_ttm")
        y10 = erp.get("yield_10y_pct")
        erpv = erp.get("erp_pct")
        pct = erp.get("percentile_5y")
        sigma = erp.get("sigma_multiple")
        sig = erp.get("signal", "🚫")
        yield_src = erp.get("yield_source", "unknown")
        pct_str = f"5年第{pct:.0f}%" if pct is not None else "-"
        sigma_str = f"{sigma:+.2f}σ" if sigma is not None else "-"
        src_label = "⚠️ fallback固定值" if yield_src == "fallback" else "Tushare yc_cb"
        lines.append(f"| 沪深300 PE-TTM | {pe:.2f} | - | - | (背景) |")
        lines.append(f"| 中债10年国债收益率 | {y10:.2f}% | 数据源:{src_label} | - | (背景) |")
        lines.append(f"| **沪深300 ERP** | **{erpv:.2f}%** | {pct_str} | {sigma_str} | {sig} |")
        lines.append("")
        lines.append("> ERP = 1/PE_TTM - 10年国债收益率。越高代表股票相对债券越便宜")
        if yield_src == "fallback":
            lines.append("> ⚠️ 国债收益率使用 secrets.json 配置的固定值。建议每月手动从公开数据(如东方财富/中国债券信息网)更新")

    lines.append("")

    # 2.3 市场宽度
    lines.append("### 3) 市场宽度")
    lines.append("")
    lines.append("| 指标 | 当前值 | 历史百分位 | 信号 |")
    lines.append("|---|---|---|---|")
    ma60 = indicators.get("above_ma60", {})
    ma200 = indicators.get("above_ma200", {})
    bias = indicators.get("ma250_bias", {})
    if ma60:
        v = ma60.get("value_pct")
        cnt = ma60.get("valid_stocks", 0)
        sig = ma60.get("signal", "🚫")
        lines.append(f"| 全A 高于MA60 比例 | **{v:.1f}%** ({cnt}只有效) | - | {sig} |")
    if ma200:
        v = ma200.get("value_pct")
        cnt = ma200.get("valid_stocks", 0)
        sig = ma200.get("signal", "🚫")
        lines.append(f"| 全A 高于MA200 比例 | {v:.1f}% ({cnt}只有效) | - | {sig} |")
    if bias:
        v = bias.get("bias_pct")
        pct = bias.get("percentile_5y")
        sig = bias.get("signal", "🚫")
        pct_str = f"5年第{pct:.0f}%" if pct is not None else "-"
        lines.append(f"| 中证全指 MA250 BIAS | **{v:+.2f}%** | {pct_str} | {sig} |")

    lines.append("")

    # 2.4 Regime叠加建议
    lines.append("### 4) 综合应对(与 v1.2 短期 regime 叠加)")
    lines.append("")
    lines.append("| 短期 v1.2 | 宏观 v1.3 | 应对策略 | 仓位建议 |")
    lines.append("|---|---|---|---|")
    lines.append("| momentum | 🟢看多 | 强势上涨期 | 加仓 60-80% |")
    lines.append("| momentum | 🟡中性 | 谨慎跟随 | 维持 40-60% |")
    lines.append("| momentum | 🔴看空 | **顶部警告** | 降至 30-40% |")
    lines.append("| value | 🟢看多 | **价值底确认** | 加仓 70-90% |")
    lines.append("| value | 🟡中性 | 选股优先 | 维持 40-60% |")
    lines.append("| value | 🔴看空 | 价值陷阱多 | 维持 30-40% |")
    lines.append("| panic | 🟢看多 | **黄金底** | 大胆加仓 80-100% |")
    lines.append("| panic | 🟡中性 | 逐步建仓 | 加仓 50-70% |")
    lines.append("| panic | 🔴看空 | 双杀,坚守现金 | **降至 20% 以下** |")
    lines.append("")

    return "\n".join(lines)


def collect_macro_indicators(tushare_source, cache_dir: str = CACHE_DIR,
                             fallback_yield_10y_pct: float = 2.30) -> Dict[str, Any]:
    """主入口:供 stock_report_enhanced.py 调用

    用法:
      from macro_indicators import collect_macro_indicators
      payload["macro"] = collect_macro_indicators(
          TUSHARE,
          fallback_yield_10y_pct=DATA_SOURCES_CONFIG.get("yield_10y_pct", 2.30)
      )
    """
    macro = MacroIndicator(tushare_source, cache_dir, fallback_yield_10y_pct)
    return macro.summary()


def cli_run():
    """命令行入口:独立运行采集(用于回填或测试)
    用法: python macro_indicators.py [--backfill]
    """
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)s - %(message)s")

    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from tushare_source import init_tushare
    except ImportError:
        logger.error("无法导入 tushare_source.py")
        return 1

    # 读取 token + fallback yield
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.json")
    token = None
    fallback_yield = 2.30
    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = json.load(f)
            token = secrets.get("tushare_token")
            fallback_yield = secrets.get("yield_10y_pct", 2.30)
        except Exception:
            pass
    if not token:
        token = os.getenv("TUSHARE_TOKEN")
    if not token:
        logger.error("未找到 tushare_token (检查 secrets.json 或环境变量 TUSHARE_TOKEN)")
        return 1

    ts_src = init_tushare(token)
    if ts_src is None or not ts_src.enabled:
        logger.error("Tushare 初始化失败")
        return 1

    result = collect_macro_indicators(ts_src, fallback_yield_10y_pct=fallback_yield)
    print("\n" + "=" * 60)
    print("宏观指标摘要")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(cli_run())