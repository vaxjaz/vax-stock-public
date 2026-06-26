# -*- coding: utf-8 -*-
"""宏观环境指标采集(indicators 层, MR-Macro 乙方案 B1+2)。

由 monolith script/macro_indicators.py 忠实迁入(逻辑零改动), 本 PR 落地骨架 + 缓存层 +
信号评级 + 轻中 5 维(维度 1/2/3/4/6); 维度 5(全市场宽度透视表)与维度 7(社融脉冲)分别留给
B3 / B4, 本 PR 不迁。

【已迁 5 维】
  1. 5 大宽基 ETF 净申赎(fund_share / fund_daily)
  2. 融资买入额 / 两市成交额 3 年百分位(margin + index_daily; 必须 SSE+SZSE 双交易所齐全)
  3. 全 A 换手率 3 年百分位(index_dailybasic 中证全指代理)
  4. 沪深 300 ERP(index_dailybasic PE + AkShare 10 年国债, 失败走 fallback 常数)
  6. M1 月度同比(cn_m)

【B1+2 去副作用 / v2 适配(只改"怎么取数"与"住哪", 不改"算什么")】
  - 取数走注入的 source(TushareSource), 顶层不连网、不建 client;
  - 删 monolith 自带的 _safe_call(_rate_limit + 3 次重试), 统一复用 source._safe_call
    (已是 daemon 线程 + join 真·墙钟超时, 单接口卡死不拖垮整体);
  - 缓存目录默认 config.CACHE_DIR(集中路径, 不再 script 同目录散落);
  - fallback 国债收益率经 config.SECRETS 收口(环境变量优先), 不硬编码;
  - AkShare 国债收益率: import 放方法内(懒导入, import 本模块不连网), 并额外加 daemon+join
    墙钟超时(AK_YIELD_TIMEOUT), 防国内 VPS 连接挂死。

维度 5 在 summary() 中暂返 available=False 占位(留 B3); 社融维度 7 不组装(留 B4)。
"""

import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from vaxstock import config

logger = logging.getLogger(__name__)

# AkShare 国债收益率墙钟超时(秒): 沿用 ai.py _yf_safe 的 daemon线程+join 模式, 防连接挂死
AK_YIELD_TIMEOUT = 20

# ==================== 标的清单(仅保留已迁 5 维所需) ====================

# 5 大宽基 ETF(选规模最大的代表)
ETF_BASKET = {
    "510300.SH": ("沪深300ETF", "华泰柏瑞"),
    "510500.SH": ("中证500ETF", "南方"),
    "159338.SZ": ("A500ETF", "华夏"),       # 2024-09 成立, 历史最短
    "512100.SH": ("中证1000ETF", "南方"),
    "510050.SH": ("上证50ETF", "华夏"),
}

# 沪深 300 PE-TTM 来源(维度 4 ERP)
HS300_INDEX = "000300.SH"


# ==================== 信号阈值表(对应 04_quant_framework.md v1.3, 原样保留全维) ====================

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
    # 维度5a: 全A 高于MA60 比例(阈值留存, 维度5方法在 B3 迁移)
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

# 维度7: 社融信贷脉冲(阈值留存, 维度7方法在 B4 迁移)
SIGNAL_THRESHOLDS["sf_pulse_yoy"] = {
    "bullish": 0.0,
    "bearish": 0.0,
}
SIGNAL_THRESHOLDS["sf_pulse_accel"] = {
    "bullish": 0.0,
    "bearish": 0.0,
}


# ==================== 信号评级(纯函数, 原样迁入) ====================

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
    """根据所有维度信号, 综合判断宏观regime
    ✅✅算2个✅, ❌❌算2个❌, 🚫忽略

    B1+2 注: 当前只喂已迁的 5 维信号(缺维度5的2个宽度信号 + 维度7社融),
    占比逻辑不依赖固定维度数, regime 仍可算; B3/B4 补齐后 regime 更全。
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


# ==================== 缓存层(parquet 增量, 原样迁入; 落 config.CACHE_DIR) ====================

class MacroCache:
    """通用增量缓存层(parquet 格式)"""

    def __init__(self, cache_dir=config.CACHE_DIR):
        self.cache_dir = str(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)

    def _path(self, name: str) -> str:
        return os.path.join(self.cache_dir, f"{name}.parquet")

    def load(self, name: str) -> Optional[pd.DataFrame]:
        """加载缓存, 不存在返回 None"""
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
        """增量追加, 以 dedup_keys 为主键去重(保留新数据)"""
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
        """返回缓存中最新一行的日期字符串(YYYYMMDD), 不存在则None"""
        df = self.load(name)
        if df is None or len(df) == 0 or date_col not in df.columns:
            return None
        return str(df[date_col].max())


# ==================== 工具函数(原样迁入) ====================

def calc_percentile(series: pd.Series, current_value: float) -> Optional[float]:
    """计算 current_value 在 series 中的百分位(0-100)"""
    if series is None or len(series) == 0 or current_value is None:
        return None
    valid = series.dropna()
    if len(valid) == 0:
        return None
    return float((valid < current_value).sum()) / len(valid) * 100


def _today_ymd() -> str:
    """自然日 YYYYMMDD。仅作增量拉取区间上界(margin/turnover/erp 的 end_date), 非交易日基准;
    多查空区间无害(Tushare 对非交易日返回空, append_unique 不写脏数据)。交易日基准一律取数据里的
    trade_date(见 CLAUDE.md §9 交易日锚定铁律)。"""
    return datetime.now().strftime("%Y%m%d")


def _ymd_minus(ymd: str, days: int) -> str:
    dt = datetime.strptime(ymd, "%Y%m%d") - timedelta(days=days)
    return dt.strftime("%Y%m%d")


# ==================== 主类 ====================

class MacroIndicator:
    """宏观环境指标采集主类(B1+2: 已迁 5 维, 维度5/7 留 B3/B4)"""

    # 全A 换手率代理指数候选(按优先级)
    # 注意: Tushare 的 index_dailybasic 不支持 .CSI 后缀, 要用 .SH
    TURNOVER_PROXY_CANDIDATES = ["000985.SH", "000300.SH"]

    def __init__(self, source, cache_dir=config.CACHE_DIR,
                 fallback_yield_10y_pct: Optional[float] = None):
        """
        source: 已初始化的 TushareSource 实例(显式注入, 同 build_stock_item 的 source); 可为 None。
        cache_dir: 缓存目录, 默认 config.CACHE_DIR(集中路径)。
        fallback_yield_10y_pct: yc_cb/AkShare 都不可用时 ERP 用的兜底 10 年国债收益率(%)。
            缺省(None)时经 config.SECRETS 收口取 yield_10y_pct(环境变量优先), 仍无则 2.30。
            注: config.SECRETS 预置该键默认 None, 故用 `or 2.30` 而非 .get(默认值)。
        """
        self.source = source
        self.pro = getattr(source, "pro", None) if (source and getattr(source, "enabled", False)) else None
        self.cache = MacroCache(cache_dir)
        if fallback_yield_10y_pct is None:
            fallback_yield_10y_pct = config.SECRETS.get("yield_10y_pct") or 2.30
        self.fallback_yield_10y_pct = fallback_yield_10y_pct

    def _check_enabled(self) -> bool:
        if self.pro is None:
            logger.warning("Tushare 未启用, 宏观指标无法获取")
            return False
        return True

    def _safe_call(self, func_name: str, **kwargs) -> Optional[pd.DataFrame]:
        """统一走注入 source 的 _safe_call(daemon线程 + join 真·墙钟超时)。

        删 monolith 自带的 _rate_limit + 3次重试版, 容错口径统一到 source 层;
        source 缺失/未启用/无该方法 -> None(P0: 取不到不臆造)。
        """
        src = self.source
        if src is None or not getattr(src, "enabled", False):
            return None
        call = getattr(src, "_safe_call", None)
        if call is None:
            return None
        return call(func_name, **kwargs)

    # ============ 维度2: 融资买入/两市成交额 ============

    def fetch_margin_to_volume(self, days: int = 3 * 252) -> Optional[pd.DataFrame]:
        """融资买入额 / 两市成交额比率, 近3年

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
            logger.info(f"  融资比缓存已最新({last_date}), 跳过拉取")
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
        # 只保留沪深两市(与分母口径一致), 排除 BSE
        margin_df = margin_df[margin_df["exchange_id"].isin(["SSE", "SZSE"])]
        # 透视: 每个交易日一行, SSE/SZSE 各一列
        pivot = margin_df.pivot_table(index="trade_date", columns="exchange_id",
                                      values="rzmre_yi", aggfunc="sum")
        # 完整性校验: 必须同时有 SSE 和 SZSE 且都非空, 否则丢弃该交易日
        need_cols = {"SSE", "SZSE"}
        if not need_cols.issubset(set(pivot.columns)):
            logger.warning(f"  margin 数据不含完整沪深两市(仅 {list(pivot.columns)}), 本次无完整新数据")
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
        返回 DataFrame[trade_date(YYYYMMDD), yield_10y_pct] 或 None(失败/超时)。

        B1+2: akshare 懒导入(放线程内, import 本模块不连网); 额外 daemon+join 墙钟超时
        (AK_YIELD_TIMEOUT), 防国内 VPS 连 AkShare 后端挂死拖垮整个宏观采集。
        """
        box: Dict[str, Any] = {}

        def _run():
            try:
                import akshare as ak
                raw = ak.bond_zh_us_rate()
                df = raw[["日期", "中国国债收益率10年"]].copy()
                df.columns = ["trade_date", "yield_10y_pct"]
                df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
                df = df.sort_values("trade_date")
                df["yield_10y_pct"] = df["yield_10y_pct"].ffill()
                df = df.dropna(subset=["yield_10y_pct"])
                box["df"] = df.reset_index(drop=True) if len(df) > 0 else None
            except Exception as e:
                box["err"] = e

        t = threading.Thread(target=_run, name="ak_bond_10y", daemon=True)
        t.start()
        t.join(AK_YIELD_TIMEOUT)
        if t.is_alive():
            logger.warning(f"  ⏱ AkShare 国债收益率超时>{AK_YIELD_TIMEOUT}s, 放弃(走 fallback)")
            return None
        if "err" in box:
            logger.warning(f"⚠️ AkShare 取国债收益率失败: {box['err']!r}")
            return None
        df = box.get("df")
        if df is not None and len(df) > 0:
            logger.info(f"  ✅ AkShare 国债收益率 {len(df)} 行, 最新 {df['yield_10y_pct'].iloc[-1]:.4f}%")
        return df

    def fetch_hs300_erp(self, days: int = 5 * 252,
                        fallback_yield_10y_pct: float = 2.30) -> Optional[pd.DataFrame]:
        """沪深300 ERP = 1/PE_TTM - 10年期国债收益率

        Tushare yc_cb 接口需要更高积分(5000+), 2000积分用户拿不到。
        本方法支持 fallback: 当 AkShare 不可用时, 使用固定的国债收益率值(默认 2.30%)。
        建议在 secrets.json 配置 yield_10y_pct, 每月手动更新一次(国债收益率变化慢)。

        返回: DataFrame columns = [trade_date, pe_ttm, yield_10y_pct, erp_pct,
                                   mean_5y, std_5y, percentile_5y, sigma_multiple,
                                   yield_source]  # "akshare" / "fallback"
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
            logger.info(f"  ERP缓存已最新({last_date}), 跳过拉取")
            return existing

        logger.info(f"  拉取沪深300 ERP数据 {start_date} → {end_date}")

        # 1. 沪深300 PE-TTM (index_dailybasic)
        pe_df = self._safe_call("index_dailybasic", ts_code=HS300_INDEX,
                                start_date=start_date, end_date=end_date,
                                fields="trade_date,pe_ttm")
        if pe_df is None or len(pe_df) == 0:
            logger.warning("index_dailybasic 返回空")
            return existing

        # 2. 10年期国债收益率(AkShare 真实时变序列优先, 失败则 fallback 常数)
        yc_df = self._fetch_cn_10y_yield_akshare()

        if yc_df is not None and len(yc_df) > 0:
            yield_source = "akshare"
        else:
            # Fallback: AkShare 也失败时, 用固定值兜底, 保证宏观层不崩
            logger.warning(f"⚠️ AkShare 不可用, 使用 fallback yield_10y_pct={fallback_yield_10y_pct}%")
            yc_df = pe_df[["trade_date"]].copy()
            yc_df["yield_10y_pct"] = fallback_yield_10y_pct
            yield_source = "fallback"

        # 3. 合并 & 计算 ERP
        merged = pe_df.merge(yc_df, on="trade_date", how="inner")
        # 异常值过滤: pe_ttm > 0 才有意义
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
        """M1月度同比, 近10年

        返回: DataFrame columns = [month, m1, m1_yoy, m1_yoy_mom_delta]
              month: YYYYMM
              m1_yoy_mom_delta: 月环比变化(pp), 用于判断加速/减速
        """
        cache_name = "m1_yoy_history"

        # M1 数据每月更新, 直接全量拉
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

    # ============ 维度1: 5大宽基ETF净申赎 ============

    def fetch_etf_net_subscription(self, days: int = 3 * 252) -> Optional[pd.DataFrame]:
        """5大宽基ETF净申赎, 近3年

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
            logger.info(f"  ETF缓存已最新({last_date}), 跳过拉取")
            return self._compute_etf_net_sub(existing)

        logger.info(f"  拉取5只ETF份额数据 {start_date} → {end_date}")

        all_etf_dfs = []
        for etf_code, (etf_name, manager) in ETF_BASKET.items():
            # 1. fund_share - 流通份额(万份)
            share_df = self._safe_call("fund_share", ts_code=etf_code,
                                       start_date=start_date, end_date=end_date)
            # 2. fund_daily - 单位净值
            daily_df = self._safe_call("fund_daily", ts_code=etf_code,
                                       start_date=start_date, end_date=end_date,
                                       fields="trade_date,close")
            if share_df is None or daily_df is None or len(share_df) == 0 or len(daily_df) == 0:
                logger.debug(f"  {etf_code} 数据缺失, 跳过")
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

    def fetch_market_turnover(self, days: int = 3 * 252) -> Optional[pd.DataFrame]:
        """全A换手率(用中证全指 000985.SH 代理, 失败回退沪深300), 近3年

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
            logger.info(f"  换手率缓存已最新({last_date}), 跳过拉取")
            return existing

        # 尝试候选指数, 直到拿到数据
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

    # ============ 综合摘要 + Regime ============

    def summary(self) -> Dict[str, Any]:
        """生成当日宏观摘要(B1+2: 已迁 5 维 1/2/3/4/6), 带信号评级和综合 regime 判断。

        维度5(全市场宽度透视表)暂返 available=False 占位(留 B3); 社融维度7不组装(留 B4)。
        逐维 try-except 隔离: 单维失败进 errors, 不崩整体。
        """
        logger.info("===== 宏观数据采集开始(B1+2: 5维) =====")

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
                    "stale": stale,  # True=今日数据未就绪, 采用历史最近完整日
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
                # 双重信号: 取较强的
                sig_pct = grade_signal(pct_5y, SIGNAL_THRESHOLDS["erp_pct_5y"])
                sig_sigma = grade_signal(sigma, SIGNAL_THRESHOLDS["erp_sigma"])
                # 综合 ERP 信号: 取两者中较强者
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

        # 维度5: 全市场宽度(MA60/MA200/MA250 BIAS)—— B3 迁移, 本 PR 占位不调用
        result["indicators"]["breadth"] = {
            "available": False,
            "pending": "维度5全市场透视表 留 B3 迁移",
        }

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
                # 综合: 绝对值为主, 环比变化加权(±0.5档)
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

        # 综合 macro regime(基于已迁 5 维信号; B3/B4 补齐后更全)
        result["macro_regime"] = combine_signals(result["signals"])
        result["bullish_count"] = result["signals"].count("✅") + 2 * result["signals"].count("✅✅")
        result["bearish_count"] = result["signals"].count("❌") + 2 * result["signals"].count("❌❌")

        logger.info(f"===== 宏观数据采集完成: {result['macro_regime']} "
                    f"(✅×{result['bullish_count']} / ❌×{result['bearish_count']}, 5维) =====")
        return result
