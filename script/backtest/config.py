#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测框架全局配置
================
所有可调参数集中在这里，避免散落在各模块。
"""

import os
from datetime import datetime, timedelta

# ==================== 路径 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
DB_PATH = os.path.join(DATA_DIR, "hs300_3y.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ==================== Tushare 配置 ====================
# 从主项目 portfolio.json 自动读取，避免重复维护
TUSHARE_TOKEN = None  # 由 data_loader 启动时从 portfolio.json 加载


# ==================== 回测时间窗口 ====================
# 默认最近3年。可在 main.py 通过 --start/--end 覆盖
BACKTEST_END_DATE = datetime.now().strftime("%Y%m%d")
BACKTEST_START_DATE = (datetime.now() - timedelta(days=3 * 365 + 30)).strftime("%Y%m%d")

# 因子计算需要至少250个交易日历史（用于估值百分位、52周位置等）
# 所以数据下载比回测窗口往前多拉300天
DATA_FETCH_START_DATE = (datetime.now() - timedelta(days=3 * 365 + 300)).strftime("%Y%m%d")


# ==================== 股票池 ====================
# "hs300" / "zz500" / "zz1000" / "custom"
# "hs300" / "zz800" / "zz500" / "zz1000" / "custom"
STOCK_POOL = "zz800"
CUSTOM_POOL_CODES = []  # 仅 STOCK_POOL=="custom" 时使用


# ==================== 未来收益窗口 ====================
# 同时计算3个窗口，看每个因子在哪个周期最有效
FUTURE_RETURN_WINDOWS = [5, 10, 20]


# ==================== 分组回测 ====================
QUANTILE_GROUPS = 5  # 5分位
ANNUALIZE_DAYS = 252  # 年化换算


# ==================== 待测因子定义 ====================
# 每个因子的方向：
#   "positive" = 因子值越大越好（如净利同比）
#   "negative" = 因子值越小越好（如股东户数变化、PE百分位）
#   "neutral"  = 由数据决定方向（如换手Z-score可能正负都有意义）
FACTORS = {
    "holder_change_pct":      {"direction": "negative", "label": "股东户数变化%"},
    "turnover_zscore":        {"direction": "neutral",  "label": "换手率Z-score"},
    "inflow_slope":           {"direction": "positive", "label": "资金流斜率"},
    "inflow_10d":             {"direction": "positive", "label": "10日主力净流入"},
    "inflow_10d_ratio":       {"direction": "positive", "label": "10日净流入/流通市值%"},
    "pe_percentile_1y":       {"direction": "negative", "label": "PE历史百分位"},
    "position_20d_pct":       {"direction": "negative", "label": "20日位置%"},
    "price_vs_ma5_pct":       {"direction": "positive", "label": "MA5偏离度"},
    "rsi_14":                 {"direction": "negative", "label": "RSI14"},
    "np_yoy":                 {"direction": "positive", "label": "净利同比%"},
    "right_side_score":       {"direction": "positive", "label": "右侧信号合成评分"},
}


# ==================== Tushare 接口限速 ====================
RATE_LIMIT_PER_MIN = 180
RATE_LIMIT_BUFFER = 0.5  # 限流缓冲秒数


# ==================== 性能 ====================
# 多股票并行下载（受Tushare限流约束，建议<=4）
PARALLEL_WORKERS = 1  # 串行最稳，并行容易超限


# ==================== IC计算 ====================
# Spearman Rank IC（推荐）vs Pearson IC
IC_METHOD = "spearman"

# 极值处理：每天截尾去除最高/最低1%的因子值
# 避免极端值影响IC稳定性
WINSORIZE_PCT = 0.01


# ==================== 评估阈值 ====================
IC_THRESHOLDS = {
    "weak":     0.02,   # 弱有效
    "moderate": 0.05,   # 中等
    "strong":   0.10,   # 强
}

ICIR_THRESHOLDS = {
    "moderate": 0.5,
    "good":     1.0,
}


# ==================== 交易成本 ====================
# 仅在Q5-Q1多空组合回测时使用，IC计算不涉及
COMMISSION_BPS = 5     # 双边万分之5（佣金+印花税）
SLIPPAGE_BPS = 10      # 滑点万分之10
TOTAL_COST_BPS = COMMISSION_BPS + SLIPPAGE_BPS  # 总成本万分之15


# ==================== 调试 ====================
DEBUG = False
LOG_LEVEL = "INFO"
