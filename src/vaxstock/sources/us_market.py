# -*- coding: utf-8 -*-
"""
美股参考模块 v1.0
==================
每日拉取昨晚美股收盘数据，作为A股开盘前的情绪参考。

本模块从 script/us_market.py 原样搬入 sources 层(逻辑零改动)。原文件已无项目内部
import(仅依赖 logging/time/datetime/typing, yfinance 在函数内懒导入), 故无需修正 import;
import 本模块不触发任何网络请求。

数据来源: yfinance（免费，无需API key）
运行时机: 集成到 stock_report_enhanced.py [6/7] 步骤，每日盘前或盘后均可

【包含数据】
- 大盘指数: 纳斯达克/标普500/道琼斯/VIX恐慌指数
- 赛道ETF:  SOXX(半导体)/QQQ(科技)/XLV(医疗)/ARKK(AI应用)/XLE(能源)
- 关键个股: NVDA/TSLA/MRNA 及其对应A股赛道
- 自动生成参考判断文字

【使用限制】
- 时差：A股收盘(16:00)时美股当日未开盘，只能参考昨晚数据
- 相关性：A股AI链与美股相关性约0.5-0.6，仅作情绪参考，不作买卖依据
- 网络：yfinance依赖Yahoo Finance，偶发超时，已有兜底逻辑
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== 标的配置 ====================

# 大盘指数
INDICES = [
    {"symbol": "^IXIC", "name": "纳斯达克",   "emoji": "🔵"},
    {"symbol": "^GSPC", "name": "标普500",    "emoji": "🟢"},
    {"symbol": "^DJI",  "name": "道琼斯",     "emoji": "⚪"},
    {"symbol": "^VIX",  "name": "VIX恐慌指数", "emoji": "🌡️"},
]

# 赛道ETF（附对应A股赛道说明）
SECTOR_ETFS = [
    {"symbol": "SOXX",  "name": "半导体ETF",    "cn_sector": "AI算力/MLCC/光模块"},
    {"symbol": "QQQ",   "name": "纳斯达克100",   "cn_sector": "科技/AI整体"},
    {"symbol": "XLV",   "name": "医疗健康ETF",   "cn_sector": "创新药/医疗器械"},
    {"symbol": "ARKK",  "name": "ARK创新ETF",    "cn_sector": "AI应用/颠覆性创新"},
    {"symbol": "XLE",   "name": "能源ETF",       "cn_sector": "煤炭/石油"},
]

# 关键个股（附对应A股标的）
KEY_STOCKS = [
    {"symbol": "NVDA",  "name": "英伟达",   "cn_peers": "工业富联/中际旭创"},
    {"symbol": "TSLA",  "name": "特斯拉",   "cn_peers": "比亚迪/宁德时代"},
    {"symbol": "MRNA",  "name": "莫德纳",   "cn_peers": "恒瑞医药/创新药板块"},
    {"symbol": "MSFT",  "name": "微软",     "cn_peers": "AI应用/云计算"},
    {"symbol": "AMD",   "name": "超微半导体", "cn_peers": "海光信息/AI芯片"},
]

# 宏观指标
MACRO = [
    {"symbol": "^TNX",  "name": "10年美债收益率", "unit": "%"},
    {"symbol": "DX-Y.NYB", "name": "美元指数",    "unit": ""},
]

# VIX阈值
VIX_NORMAL  = 20
VIX_CAUTION = 30
VIX_PANIC   = 40


# ==================== 数据拉取 ====================

def _fetch_single(symbol: str, retries: int = 2) -> Optional[Dict[str, Any]]:
    """
    拉取单个标的最近2个交易日数据，计算昨日涨跌幅。

    Returns:
        {symbol, price, change_pct, prev_close, volume, date} 或 None
    """
    for attempt in range(retries):
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            # 拉5天保证能取到最近2个完整交易日
            hist = ticker.history(period="5d", auto_adjust=True, timeout=8)
            if hist is None or len(hist) < 2:
                return None

            latest = hist.iloc[-1]
            prev   = hist.iloc[-2]

            close      = float(latest["Close"])
            prev_close = float(prev["Close"])
            change_pct = (close - prev_close) / prev_close * 100

            return {
                "symbol":     symbol,
                "price":      round(close, 4),
                "prev_close": round(prev_close, 4),
                "change_pct": round(change_pct, 2),
                "volume":     int(latest.get("Volume", 0) or 0),
                "date":       str(hist.index[-1].date()),
            }
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                logger.debug(f"  {symbol} 拉取失败: {str(e)[:60]}")
    return None


def fetch_us_market_data() -> Dict[str, Any]:
    """
    拉取全部美股参考数据。

    Returns:
        {
            "indices":    [{name, symbol, change_pct, price, ...}],
            "etfs":       [{name, symbol, change_pct, cn_sector, ...}],
            "stocks":     [{name, symbol, change_pct, cn_peers, ...}],
            "macro":      [{name, symbol, price, unit}],
            "fetch_date": str,
            "vix":        float or None,
            "sentiment":  str,   # "risk_on"/"caution"/"risk_off"/"panic"
        }
    """
    logger.info("🌏 [6/7] 拉取美股参考数据...")
    result = {
        "indices": [], "etfs": [], "stocks": [],
        "macro": [], "fetch_date": datetime.now().strftime("%Y-%m-%d"),
        "vix": None, "sentiment": "unknown",
    }

    # 合并所有标的一次性拉，节省时间
    all_targets = (
        [(x, "index")  for x in INDICES] +
        [(x, "etf")    for x in SECTOR_ETFS] +
        [(x, "stock")  for x in KEY_STOCKS] +
        [(x, "macro")  for x in MACRO]
    )

    success = 0
    for cfg, category in all_targets:
        symbol = cfg["symbol"]
        data   = _fetch_single(symbol)
        time.sleep(0.15)  # 轻量限速，避免被 Yahoo 封

        if data is None:
            logger.debug(f"  ⚠️ {symbol} 无数据")
            continue

        row = {**cfg, **data}

        if category == "index":
            result["indices"].append(row)
            if symbol == "^VIX":
                result["vix"] = data["price"]
        elif category == "etf":
            result["etfs"].append(row)
        elif category == "stock":
            result["stocks"].append(row)
        elif category == "macro":
            result["macro"].append(row)

        success += 1

    # 综合情绪判断
    result["sentiment"] = _judge_sentiment(result)

    total = len(all_targets)
    logger.info(f"  ✅ 美股数据: {success}/{total} 个标的成功")
    if result["vix"]:
        logger.info(f"  VIX={result['vix']:.1f} | 情绪={result['sentiment']}")

    return result


# ==================== 情绪判断 ====================

def _judge_sentiment(data: Dict[str, Any]) -> str:
    """
    综合VIX + 纳斯达克 + SOXX，判断美股情绪。

    Returns: "risk_on" / "caution" / "risk_off" / "panic"
    """
    vix = data.get("vix")

    # VIX优先判断
    if vix is not None:
        if vix >= VIX_PANIC:
            return "panic"
        if vix >= VIX_CAUTION:
            return "risk_off"

    # 找纳斯达克涨跌幅
    nasdaq_chg = None
    soxx_chg   = None
    for row in data.get("indices", []):
        if row["symbol"] == "^IXIC":
            nasdaq_chg = row.get("change_pct")
    for row in data.get("etfs", []):
        if row["symbol"] == "SOXX":
            soxx_chg = row.get("change_pct")

    # 情绪矩阵
    scores = []
    if nasdaq_chg is not None:
        if nasdaq_chg >= 1.5:   scores.append(2)
        elif nasdaq_chg >= 0:   scores.append(1)
        elif nasdaq_chg >= -1.5: scores.append(-1)
        else:                   scores.append(-2)

    if soxx_chg is not None:
        if soxx_chg >= 2:    scores.append(2)
        elif soxx_chg >= 0:  scores.append(1)
        elif soxx_chg >= -2: scores.append(-1)
        else:                scores.append(-2)

    if not scores:
        return "unknown"

    avg = sum(scores) / len(scores)
    if avg >= 1.5:   return "risk_on"
    if avg >= 0:     return "caution"
    if avg >= -1.5:  return "risk_off"
    return "panic"


# ==================== 报告渲染 ====================

_SENTIMENT_TEXT = {
    "risk_on":  "✅ 风险偏好开启 — 科技/AI情绪偏暖，A股成长股短期有支撑",
    "caution":  "⚠️ 情绪中性偏谨慎 — 美股分化，需结合A股自身资金面判断",
    "risk_off": "🔴 风险偏好收缩 — 美股承压，A股科技链今日需注意回调风险",
    "panic":    "🚨 极度恐慌(VIX≥30) — 全球避险情绪升温，A股高Beta标的压力大",
    "unknown":  "❓ 数据不足，无法判断",
}

_VIX_LABEL = {
    (0,  VIX_NORMAL):  "正常",
    (VIX_NORMAL,  VIX_CAUTION): "偏高，需关注",
    (VIX_CAUTION, VIX_PANIC):   "恐慌区间",
    (VIX_PANIC,   9999):        "极度恐慌",
}


def _vix_label(vix: Optional[float]) -> str:
    if vix is None:
        return "-"
    for (lo, hi), label in _VIX_LABEL.items():
        if lo <= vix < hi:
            return f"{vix:.1f} ({label})"
    return str(vix)


def _chg_str(chg: Optional[float]) -> str:
    if chg is None:
        return "-"
    arrow = "▲" if chg >= 0 else "▼"
    return f"{arrow}{abs(chg):.2f}%"


def _cn_impact(etf_name: str, chg: Optional[float], cn_sector: str) -> str:
    """根据ETF涨跌生成对A股的简单影响描述"""
    if chg is None:
        return ""
    if chg >= 2:
        return f"→ A股{cn_sector}短期情绪利好"
    if chg <= -2:
        return f"→ A股{cn_sector}短期承压"
    return ""


def render_us_market_section(data: Dict[str, Any]) -> str:
    """生成日报中的美股参考章节（Markdown格式）"""
    if not data or (not data.get("indices") and not data.get("etfs")):
        return "## 五、美股参考\n\n⚠️ 数据拉取失败（yfinance超时或网络问题），跳过。"

    lines = [f"## 五、美股参考（昨晚{data.get('fetch_date','')}收盘）"]
    lines.append("")
    lines.append(f"> {_SENTIMENT_TEXT.get(data.get('sentiment','unknown'))}")
    lines.append("")

    # ── 大盘指数 ──
    if data.get("indices"):
        lines.append("### 大盘指数")
        lines.append("| 指数 | 收盘价 | 昨日涨跌 |")
        lines.append("|---|---|---|")
        for row in data["indices"]:
            name = row.get("name", row["symbol"])
            if row["symbol"] == "^VIX":
                price_str = _vix_label(row.get("price"))
                chg_str   = ""
            else:
                price_str = f"{row.get('price', '-'):,.2f}"
                chg_str   = _chg_str(row.get("change_pct"))
            lines.append(f"| {row.get('emoji','')} {name} | {price_str} | {chg_str} |")
        lines.append("")

    # ── 赛道ETF ──
    if data.get("etfs"):
        lines.append("### 赛道ETF → 对应A股参考")
        lines.append("| ETF | 昨日涨跌 | 对应A股赛道 | 参考含义 |")
        lines.append("|---|---|---|---|")
        for row in data["etfs"]:
            chg     = row.get("change_pct")
            chg_str = _chg_str(chg)
            impact  = _cn_impact(row["name"], chg, row.get("cn_sector",""))
            lines.append(
                f"| {row['name']} ({row['symbol']}) | {chg_str} | "
                f"{row.get('cn_sector','')} | {impact} |"
            )
        lines.append("")

    # ── 关键个股 ──
    if data.get("stocks"):
        lines.append("### 关键个股")
        lines.append("| 个股 | 昨日涨跌 | 对应A股 |")
        lines.append("|---|---|---|")
        for row in data["stocks"]:
            lines.append(
                f"| {row['name']} ({row['symbol']}) | "
                f"{_chg_str(row.get('change_pct'))} | "
                f"{row.get('cn_peers','')} |"
            )
        lines.append("")

    # ── 宏观 ──
    if data.get("macro"):
        macro_parts = []
        for row in data["macro"]:
            unit  = row.get("unit", "")
            price = row.get("price")
            chg   = row.get("change_pct")
            if price is not None:
                macro_parts.append(
                    f"{row['name']}: {price:.2f}{unit} ({_chg_str(chg)})"
                )
        if macro_parts:
            lines.append(f"**宏观**: {' | '.join(macro_parts)}")
            lines.append("")

    # ── 注意事项 ──
    lines.append(
        "> ⚠️ **使用限制**: "
        "数据为昨晚收盘，A股今日开盘后市场情绪可能已变化。"
        "美股仅作情绪参考，不作A股买卖依据。"
        "A股行情最终以国内资金面+板块轮动为准。"
    )
    return "\n".join(lines)


# ==================== 独立运行测试 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    data = fetch_us_market_data()
    print("\n" + "=" * 60)
    print(render_us_market_section(data))
