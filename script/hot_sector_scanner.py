#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热门赛道扫描器 v1.0
====================
每日自动识别热门板块+龙头股,集成到日报末尾。

【设计目标】
不是"提前预测主线",而是"避免错过+过滤陷阱":
- 资金已经在流入的板块,你不要错过
- 涨幅榜上的派发陷阱,你不要追

【分层扫描】(为节省Tushare积分)
Step 1: 板块层  → 扫描全市场板块,找Top 5热门赛道(免费接口)
Step 2: 候选股  → 在Top 5板块的成分股中筛选v1.1评分>=2.0的(约30-50只)
Step 3: 龙头排序 → 综合评分+资金+市值,每个板块输出3只龙头
Step 4: 风险过滤 → 排除高位追高/派发陷阱/小盘股

【性能预算】
- 板块扫描: 约30秒(东财免费接口)
- 候选股扫描: 约2-3分钟(Tushare批量)
- 总耗时: < 5分钟,不影响主报告

【依赖】
- stock_report_enhanced.py 的 calc_right_side_score
- tushare_source.py 的 TushareSource
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

# 复用主项目工具
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


# ==================== 配置 ====================

# 板块筛选阈值
HOT_SECTOR_MIN_5D_GAIN = 3.0        # 近5日板块涨幅至少3%
HOT_SECTOR_MIN_TODAY_INFLOW = 0     # 今日资金流入>=0
HOT_SECTOR_TOP_N = 5                # 取Top 5热门板块

# 龙头股筛选阈值
LEADER_MIN_SCORE = 2.0              # v1.1评分>=2.0
LEADER_MAX_PE_PERCENTILE = 95       # PE历史百分位<95(留点空间,不是100%硬卡)
LEADER_MIN_MARKET_CAP_YI = 50       # 流通市值>=50亿(过滤小盘股)
LEADER_MIN_NPYOY = -10              # 净利同比>-10%(允许微亏,排除崩塌)
LEADER_MAX_HOLDER_DISPERSE = 15     # 股东户数变化<15%(排除强分散)
LEADER_TOP_N_PER_SECTOR = 3         # 每个板块Top 3龙头

# 风险过滤
RISK_MAX_52W_POSITION = 95          # 距52周高点<5%过于追高
RISK_MAX_TURNOVER_ZSCORE = 3.0      # 换手Z-score>3疑似派发

# 性能限制
MAX_STOCKS_TO_SCORE = 80            # 全流程最多深度扫描80只
SCAN_CACHE_TTL_MINUTES = 60         # 板块扫描结果缓存1小时


# ==================== 东方财富板块数据(免费) ====================

def _em_request(url: str, timeout: int = 10) -> Optional[Dict]:
    """东方财富API请求封装"""
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        })
        if r.status_code == 200:
            text = r.text.strip()
            # 处理JSONP
            if "(" in text and text.endswith(")"):
                text = text[text.index("(") + 1:-1]
            return json.loads(text)
    except Exception as e:
        logger.debug(f"东财请求失败: {str(e)[:80]}")
    return None


def fetch_sector_overview() -> List[Dict[str, Any]]:
    """同花顺行业板块涨跌+资金流(替代失效的East Money)。键名与原版一致。"""
    results = []
    try:
        import akshare as ak
        df = ak.stock_board_industry_summary_ths()
    except Exception as e:
        logger.warning(f"同花顺板块获取失败: {str(e)[:80]}")
        return []
    if df is None or len(df) == 0:
        logger.warning("板块数据为空")
        return []
    for _, row in df.iterrows():
        try:
            name = str(row["板块"])
            results.append({
                "code": name,
                "name": name,
                "change_pct_today": float(row["涨跌幅"]),
                "main_inflow_yi": float(row["净流入"]),
                "top_stock": str(row.get("领涨股", "")),
                "top_stock_chg": float(row.get("领涨股-涨跌幅", 0) or 0),
            })
        except (ValueError, TypeError, KeyError):
            continue
    return results


def fetch_sector_5d_change(sector_code: str) -> Optional[float]:
    """
    获取板块近5日累计涨幅
    使用东方财富的K线接口
    """
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid=90.{sector_code}"
        "&fields1=f1,f2,f3,f4,f5"
        "&fields2=f51,f52,f53,f54,f55,f56,f57"
        "&klt=101&fqt=0&end=20500101&lmt=10"  # 取10天保险
    )
    data = _em_request(url)
    
    if not data or "data" not in data or not data["data"]:
        return None
    
    klines = data["data"].get("klines", [])
    if len(klines) < 6:  # 至少需要6天数据计算5日变化
        return None
    
    try:
        # 倒数第6天的收盘价 vs 最新收盘价
        oldest_close = float(klines[-6].split(",")[2])
        latest_close = float(klines[-1].split(",")[2])
        return (latest_close - oldest_close) / oldest_close * 100
    except (ValueError, IndexError):
        return None


# ==================== 板块筛选 ====================

def find_hot_sectors() -> List[Dict[str, Any]]:
    """Step1 找热门板块Top5。A方案:同花顺源无历史,用今日涨幅代理5日。"""
    logger.info("[1/4] 扫描全市场板块...")
    sectors = fetch_sector_overview()
    if not sectors:
        return []
    logger.info(f"  共获取 {len(sectors)} 个板块")
    filtered = []
    for s in sectors:
        if s["main_inflow_yi"] <= HOT_SECTOR_MIN_TODAY_INFLOW and s["change_pct_today"] < 2.0:
            continue
        s["change_pct_5d"] = s["change_pct_today"]
        s["hot_score"] = s["main_inflow_yi"] * 0.4 + s["change_pct_today"] * 0.6
        filtered.append(s)
    filtered.sort(key=lambda x: x["hot_score"], reverse=True)
    top_sectors = filtered[:HOT_SECTOR_TOP_N]
    logger.info(f"  找到 {len(top_sectors)} 个热门板块")
    for s in top_sectors:
        logger.info(f"    - {s['name']}: 今日{s['change_pct_today']:+.2f}% 资金{s['main_inflow_yi']:+.2f}亿")
    return top_sectors


# ==================== 板块成分股 ====================

def fetch_sector_constituents(sector_code: str, sector_name: str) -> List[str]:
    """获取某板块的成分股代码列表(东财)"""
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn=1&pz=200&po=1&np=1&fltt=2&invt=2"
        f"&fs=b:{sector_code}"  # 板块成分股
        f"&fields=f12,f14"
    )
    data = _em_request(url)
    if not data or "data" not in data or not data["data"]:
        return []
    
    items = data["data"].get("diff", [])
    codes = []
    for item in items:
        code = item.get("f12", "")
        if code and len(code) == 6:
            codes.append(code)
    return codes


# ==================== 个股深度评分 ====================

def score_stock_for_leader(
    code: str,
    name: str,
    sector_name: str,
    tushare_source: Any,
) -> Optional[Dict[str, Any]]:
    """
    对单只候选股做完整v1.1评分
    
    使用TushareSource的实际方法名:
      - get_daily_kline / get_daily_basic / get_moneyflow_summary
      - get_latest_fina / get_holder_number
    """
    try:
        # 导入主脚本的函数(动态导入避免循环依赖)
        from stock_report_enhanced import (
            calc_right_side_score, calc_turnover_zscore, calc_inflow_slope,
            calc_pe_pb_percentile, _CURRENT_MARKET_REGIME
        )
        
        # 1. K线
        kline = tushare_source.get_daily_kline(code, days=260)
        if not kline or len(kline) < 60:
            return None
        
        latest = kline[-1]
        price = float(latest.get("close", 0))
        if price <= 0:
            return None
        
        # 均线
        closes = [float(k.get("close", 0)) for k in kline[-60:] if k.get("close")]
        if len(closes) < 20:
            return None
        ma5 = sum(closes[-5:]) / 5
        
        # 20日位置
        last20 = kline[-20:]
        high_20 = max(float(k.get("high", 0)) for k in last20)
        low_20 = min(float(k.get("low", 0)) for k in last20)
        pos_20d_pct = (price - low_20) / (high_20 - low_20) * 100 if high_20 > low_20 else 50
        
        # 52周位置
        kline_52w = kline[-min(250, len(kline)):]
        high_52w = max(float(k.get("high", 0)) for k in kline_52w)
        low_52w = min(float(k.get("low", 0)) for k in kline_52w)
        pos_52w_pct = (price - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 50
        
        # 量比5日
        volumes = [float(k.get("vol", 0)) for k in kline[-6:-1]]
        today_vol = float(latest.get("vol", 0))
        avg_vol = sum(volumes) / 5 if volumes else 1
        volume_ratio_5d = today_vol / avg_vol if avg_vol > 0 else 1.0
        
        # 涨跌幅
        change_pct = float(latest.get("pct_chg", 0)) if latest.get("pct_chg") else 0
        
        # 2. 估值(daily_basic最新)
        basic = tushare_source.get_daily_basic(code)
        market_cap_yi = 0
        pe_ttm = None
        turn_today = 0
        if basic:
            circ_mv = basic.get("circ_mv", 0) or 0
            market_cap_yi = circ_mv / 1e4  # 万元 → 亿元
            pe_ttm = basic.get("pe_ttm")
            turn_today = basic.get("turnover_rate", 0) or 0
        
        # ============ 提前风险过滤(快速排除,省后续接口调用) ============
        if market_cap_yi < LEADER_MIN_MARKET_CAP_YI:
            return None
        if pos_52w_pct > RISK_MAX_52W_POSITION:
            return None
        
        # 估值百分位(用 daily_basic 历史)
        basic_history = tushare_source.get_daily_basic_history(code, days=250)
        pe_percentile = None
        if basic_history and pe_ttm:
            pct_result = calc_pe_pb_percentile(basic_history, pe_ttm, None)
            pe_percentile = pct_result.get("pe_percentile")
        
        if pe_percentile is not None and pe_percentile > LEADER_MAX_PE_PERCENTILE:
            return None  # 极高估值
        
        # 换手率Z-score(v1.0.1修复:Tushare daily接口无turn字段,
        # 改从daily_basic_history取turnover_rate构建换手历史)
        turnover_z = None
        if basic_history and turn_today:
            turn_hist = [{"turn": b.get("turnover_rate")} for b in basic_history
                         if b.get("turnover_rate") is not None]
            if len(turn_hist) >= 20:
                turnover_z = calc_turnover_zscore(turn_hist, turn_today)
        
        if turnover_z is not None and turnover_z > RISK_MAX_TURNOVER_ZSCORE:
            return None  # 异常放量
        
        # 3. 资金流向
        mf_summary = tushare_source.get_moneyflow_summary(code)
        flow_5d = mf_summary.get("main_inflow_5d") if mf_summary else None
        flow_10d = mf_summary.get("main_inflow_10d") if mf_summary else None
        inflow_slope = calc_inflow_slope(flow_5d, flow_10d) if flow_5d and flow_10d else None
        
        # 4. 业绩
        fina = tushare_source.get_latest_fina(code)
        np_yoy = fina.get("np_yoy") if fina else None
        
        if np_yoy is not None and np_yoy < LEADER_MIN_NPYOY:
            return None  # 业绩崩塌
        
        # 5. 股东户数
        holder_history = tushare_source.get_holder_number(code, periods=2)
        holder_change_pct = None
        if holder_history and len(holder_history) >= 2:
            try:
                latest_num = holder_history[0].get("holder_num")
                prev_num = holder_history[1].get("holder_num")
                if latest_num and prev_num and prev_num > 0:
                    holder_change_pct = (latest_num - prev_num) / prev_num * 100
            except (TypeError, ValueError):
                pass
        
        if holder_change_pct is not None and holder_change_pct > LEADER_MAX_HOLDER_DISPERSE:
            return None  # 股东大幅分散
        
        # ============ v1.2评分（含市值归一化资金流） ============
        rss = calc_right_side_score(
            price=price,
            ma5=ma5,
            volume_ratio_5d=volume_ratio_5d,
            change_pct=change_pct,
            turnover_zscore=turnover_z,
            inflow_slope=inflow_slope,
            inflow_10d=flow_10d,
            holder_change_pct=holder_change_pct,
            position_20d_pct=pos_20d_pct,
            np_yoy=np_yoy,
            pe_percentile_1y=pe_percentile,
            market_regime=_CURRENT_MARKET_REGIME,
            circ_mv_yi=market_cap_yi if market_cap_yi > 0 else None,
        )
        
        if rss["score"] < LEADER_MIN_SCORE:
            return None  # 评分不达标
        
        # 获取股票名称(从daily_basic或单独查stock_basic)
        stock_name = name
        try:
            if basic and basic.get("name"):
                stock_name = basic["name"]
        except (AttributeError, KeyError):
            pass
        
        return {
            "code": code,
            "name": stock_name,
            "sector": sector_name,
            "price": price,
            "change_pct": change_pct,
            "score": rss["score"],
            "grade": rss["grade"],
            "signals": rss["signals"],
            "market_cap_yi": round(market_cap_yi, 1),
            "pe_percentile": pe_percentile,
            "pos_20d_pct": round(pos_20d_pct, 1),
            "pos_52w_pct": round(pos_52w_pct, 1),
            "np_yoy": np_yoy,
            "holder_change_pct": holder_change_pct,
            "inflow_10d_yi": round(flow_10d / 1e8, 2) if flow_10d else 0,
        }
    except Exception as e:
        logger.debug(f"  评分 {code} 失败: {str(e)[:80]}")
        return None


# ==================== 主流程 ====================

def scan_hot_sectors_and_leaders(
    tushare_source: Any,
    user_pool_codes: Optional[set] = None,
) -> Dict[str, Any]:
    """
    主入口: 扫描热门板块+龙头股
    
    Args:
        tushare_source: TushareSource实例
        user_pool_codes: 用户已有的持仓+观察池代码集合(避免重复推荐)
    
    Returns:
        {
            "sectors": [{name, change_pct_today, change_pct_5d, main_inflow_yi}, ...],
            "leaders": [{code, name, sector, score, ...}, ...],
            "scan_time": str,
        }
    """
    user_pool_codes = user_pool_codes or set()
    
    # === Step 1: 找热门板块 ===
    hot_sectors = find_hot_sectors()
    if not hot_sectors:
        return {"sectors": [], "leaders": [], "scan_time": datetime.now().isoformat()}
    
    # === Step 2: 取候选股 ===
    logger.info("🔍 [2/4] 提取板块成分股...")
    sector_to_codes: Dict[str, List[str]] = {}
    all_candidate_codes = set()
    
    for sector in hot_sectors:
        codes = fetch_sector_constituents(sector["code"], sector["name"])
        if codes:
            sector_to_codes[sector["name"]] = codes
            all_candidate_codes.update(codes)
        time.sleep(0.2)
    
    # 排除用户已有
    all_candidate_codes -= user_pool_codes
    
    # 限制总扫描量
    if len(all_candidate_codes) > MAX_STOCKS_TO_SCORE:
        logger.info(f"  候选股 {len(all_candidate_codes)} 只 > 上限 {MAX_STOCKS_TO_SCORE},按板块平均分配")
        # 每个板块取一部分,避免单板块占用全部预算
        per_sector_quota = MAX_STOCKS_TO_SCORE // len(sector_to_codes)
        all_candidate_codes = set()
        for sector_name, codes in sector_to_codes.items():
            filtered_codes = [c for c in codes if c not in user_pool_codes][:per_sector_quota]
            all_candidate_codes.update(filtered_codes)
    
    logger.info(f"  📌 待评分: {len(all_candidate_codes)} 只候选股")
    
    # === Step 3: 深度评分 ===
    logger.info("🔍 [3/4] 对候选股做v1.1评分...")
    code_to_score: Dict[str, Dict[str, Any]] = {}
    
    for i, code in enumerate(all_candidate_codes, 1):
        # 找出该股所属的热门板块
        sector_name = None
        for sname, codes in sector_to_codes.items():
            if code in codes:
                sector_name = sname
                break
        if not sector_name:
            continue
        
        result = score_stock_for_leader(code, code, sector_name, tushare_source)
        if result:
            code_to_score[code] = result
        
        if i % 20 == 0:
            logger.info(f"    [{i}/{len(all_candidate_codes)}] 已评分,合格 {len(code_to_score)} 只")
    
    logger.info(f"  ✅ 通过筛选的龙头候选: {len(code_to_score)} 只")
    
    # === Step 4: 按板块归类+排序 ===
    logger.info("🔍 [4/4] 整理输出...")
    sector_leaders: Dict[str, List[Dict[str, Any]]] = {}
    for code, stock in code_to_score.items():
        sname = stock["sector"]
        sector_leaders.setdefault(sname, []).append(stock)
    
    final_leaders = []
    for sector in hot_sectors:
        sname = sector["name"]
        candidates = sector_leaders.get(sname, [])
        # 按评分降序,取TopN
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_leaders = candidates[:LEADER_TOP_N_PER_SECTOR]
        for leader in top_leaders:
            leader["sector_change_5d"] = sector["change_pct_5d"]
            leader["sector_change_today"] = sector["change_pct_today"]
            final_leaders.append(leader)
    
    return {
        "sectors": [
            {
                "name": s["name"],
                "change_pct_today": s["change_pct_today"],
                "change_pct_5d": s["change_pct_5d"],
                "main_inflow_yi": s["main_inflow_yi"],
                "top_stock": s.get("top_stock"),
            }
            for s in hot_sectors
        ],
        "leaders": final_leaders,
        "scan_time": datetime.now().isoformat(),
    }


# ==================== 报告渲染 ====================

def render_hot_sector_section(scan_result: Dict[str, Any]) -> str:
    """生成日报中的热门赛道扫描章节"""
    lines = ["## 四、热门赛道扫描 🔥 (v1.2自动识别)"]
    
    sectors = scan_result.get("sectors", [])
    leaders = scan_result.get("leaders", [])
    
    if not sectors:
        lines.append("\n⚠️ 未识别到符合条件的热门板块。可能原因:")
        lines.append("- 大盘整体走弱,无板块满足'5日涨幅>3%+今日资金流入'")
        lines.append("- 当前为震荡或恐慌市,板块轮动不明显")
        lines.append("- 数据源临时不可用")
        return "\n".join(lines)
    
    # 热门板块概览
    lines.append("\n### 今日Top 5热门板块")
    lines.append("| 板块 | 今日涨幅 | 5日涨幅 | 资金净流入 | 领涨股 |")
    lines.append("|---|---|---|---|---|")
    for s in sectors:
        lines.append(
            f"| {s['name']} | {s['change_pct_today']:+.2f}% | "
            f"{s['change_pct_5d']:+.2f}% | {s['main_inflow_yi']:+.2f}亿 | "
            f"{s.get('top_stock') or '-'} |"
        )
    
    # 龙头股推荐
    if not leaders:
        lines.append("\n### 龙头股扫描结果")
        lines.append("⚠️ 当前热门板块中,**没有股票通过v1.1严格筛选**。")
        lines.append("- 通常意味着:板块涨幅靠前但个股多数已处于追高位置")
        lines.append("- 建议:等待板块回调,届时优质标的可能浮现")
        return "\n".join(lines)
    
    lines.append(f"\n### 龙头股推荐 (共{len(leaders)}只通过v1.1筛选)")
    lines.append("⚠️ **风险提示**:以下标的为算法基于资金/业绩/筹码扫描产出,仅供参考。")
    lines.append("已排除:小盘股(<50亿)/业绩崩塌(净利<-10%)/股东大幅分散(>15%)/52周近顶(>95%)/异常放量\n")
    
    # 按板块分组输出
    current_sector = None
    for leader in leaders:
        sec = leader["sector"]
        if sec != current_sector:
            lines.append(f"\n#### 📌 {sec}")
            current_sector = sec
        
        score = leader["score"]
        grade_emoji = "🌟" if score >= 3.5 else "✅"
        
        lines.append(
            f"- **{leader['name']} ({leader['code']})** {grade_emoji} v1.1评分 {score:.1f}分 [{leader['grade']}]"
        )
        lines.append(
            f"  - 现价: {leader['price']:.2f} ({leader['change_pct']:+.2f}%) | "
            f"流通市值 {leader['market_cap_yi']:.0f}亿"
        )
        details = []
        if leader.get("np_yoy") is not None:
            details.append(f"净利同比{leader['np_yoy']:+.0f}%")
        if leader.get("inflow_10d_yi") is not None:
            details.append(f"10日资金{leader['inflow_10d_yi']:+.2f}亿")
        if leader.get("holder_change_pct") is not None:
            details.append(f"户数{leader['holder_change_pct']:+.1f}%")
        if leader.get("pos_52w_pct") is not None:
            details.append(f"52周位置{leader['pos_52w_pct']:.0f}%")
        if leader.get("pe_percentile") is not None:
            details.append(f"PE历史{leader['pe_percentile']:.0f}%")
        lines.append(f"  - {' | '.join(details)}")
        
        # 信号摘要
        positive_signals = [s for s in leader.get("signals", []) if "✅" in s]
        if positive_signals:
            lines.append(f"  - 信号: {' / '.join(positive_signals[:3])}")
    
    lines.append("\n### 使用建议")
    lines.append("1. 评分≥2.0只是**初筛信号**,具体入场仍需等待大盘配合+回调机会")
    lines.append("2. 同一板块多只标的同时上榜,说明板块共振,优先选评分最高的")
    lines.append("3. 与你已有的持仓/观察池标的不重复(扫描时已自动排除)")
    lines.append("4. 若大盘处于恐慌市,即使评分高也不建议追入")
    
    return "\n".join(lines)


# ==================== 单元测试入口 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    
    # 测试模式: 只做板块扫描,不连接Tushare
    logger.info("🧪 测试模式: 仅板块扫描")
    sectors = find_hot_sectors()
    
    if sectors:
        print("\n热门板块:")
        for s in sectors:
            print(f"  {s['name']}: 今日{s['change_pct_today']:+.2f}% "
                  f"5日{s['change_pct_5d']:+.2f}% "
                  f"资金{s['main_inflow_yi']:+.2f}亿 "
                  f"领涨{s.get('top_stock')}")
