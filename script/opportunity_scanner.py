#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
机会仓扫描器 v1.0
==================
独立于主仓（v1.1框架）的短线机会识别模块。

【设计原则】
主仓 = 风险控制优先，等回调右侧介入
机会仓 = 收益优先，追主升浪，承受更高止损频率

【两类信号】
信号A：涨停板次日追板
  逻辑：今日涨停→明日竞价参与
  止损：开板即走 OR 入场价-3%（取先到者）
  预期：胜率30-40%，盈亏比1:3

信号B：板块启动初期龙头
  逻辑：板块近3日持续资金流入+今日涨>2%，在板块里找低位龙头
  止损：入场价-5%
  预期：胜率50%，盈亏比1:2

【仓位规则】
  机会仓总额 = 总资金15%（约24000元）
  单次出手   = 总资金5%（约8000元）
  最多同时持有3只
  主仓与机会仓完全隔离

【选股范围】
  全A股（非科创板）
  流通市值 > 30亿
  净利同比 > -30%（排除基本面崩塌）
  排除ST/退市风险股
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


# ==================== 机会仓配置 ====================

class OppConfig:
    # 仓位
    TOTAL_BUDGET_PCT    = 0.15   # 机会仓占总资金比例
    PER_TRADE_PCT       = 0.05   # 单次出手占总资金比例
    MAX_POSITIONS       = 3      # 最多同时持有

    # 信号A：涨停板次日
    A_STOP_LOSS_PCT     = 0.03   # 入场价跌3%止损
    A_MAX_PRICE_POS_20D = 75     # 20日位置上限（不追高位涨停）
    A_MAX_PRICE_POS_52W = 85     # 52周位置上限
    A_MIN_SECTOR_STOCKS = 2      # 板块同日涨停数下限（共振验证）
    A_MIN_NP_YOY        = -30    # 净利同比下限

    # 信号B：板块启动初期
    B_SECTOR_MIN_3D_INFLOW   = 3.0   # 板块3日累计流入下限（亿元）
    B_SECTOR_MIN_TODAY_CHG   = 2.0   # 板块今日涨幅下限
    B_STOCK_MAX_POS_20D      = 70    # 个股20日位置上限（找低位）
    B_STOCK_MIN_SCORE        = 1.5   # v1.1评分下限
    B_STOP_LOSS_PCT          = 0.05  # 入场价跌5%止损

    # 选股过滤
    MIN_MARKET_CAP_YI   = 30     # 流通市值下限（亿）
    EXCLUDE_STAR        = True   # 排除科创板
    EXCLUDE_ST          = True   # 排除ST

    # 机会仓状态文件（持久化追踪）
    STATE_FILE = os.path.join(PROJECT_ROOT, "opportunity_book.json")


# ==================== 机会仓状态管理 ====================

class OpportunityBook:
    """追踪当前机会仓持仓，计算剩余额度，提示止损"""

    def __init__(self, total_capital: float = 164000):
        self.total_capital = total_capital
        self.budget = total_capital * OppConfig.TOTAL_BUDGET_PCT
        self.per_trade = total_capital * OppConfig.PER_TRADE_PCT
        self.positions: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(OppConfig.STATE_FILE):
            try:
                with open(OppConfig.STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.positions = data.get("positions", [])
                self.total_capital = data.get("total_capital", self.total_capital)
                self.budget = self.total_capital * OppConfig.TOTAL_BUDGET_PCT
                self.per_trade = self.total_capital * OppConfig.PER_TRADE_PCT
            except Exception:
                self.positions = []

    def save(self):
        data = {
            "positions": self.positions,
            "total_capital": self.total_capital,
            "last_updated": datetime.now().isoformat(),
        }
        with open(OppConfig.STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @property
    def used_budget(self) -> float:
        return sum(p.get("cost_amount", 0) for p in self.positions)

    @property
    def remaining_budget(self) -> float:
        return self.budget - self.used_budget

    @property
    def remaining_slots(self) -> int:
        return OppConfig.MAX_POSITIONS - len(self.positions)

    def can_add(self) -> bool:
        return (self.remaining_slots > 0 and
                self.remaining_budget >= self.per_trade)

    def add_position(self, code: str, name: str, entry_price: float,
                     signal_type: str, stop_loss_price: float,
                     reason: str = "") -> bool:
        """记录入场。返回False表示被拒绝（超预算/超槽位）。"""
        if not self.can_add():
            logger.warning(f"❌ 机会仓已满或预算不足，拒绝入场 {name}({code})")
            return False
        shares = int(self.per_trade / entry_price / 100) * 100
        if shares < 100:
            # 高价股1手即超预算：允许超出20%以内，否则拒绝（v1.0.1修复：
            # 原逻辑强制凑1手，中际旭创1124元1手=11.2万，超预算13倍）
            one_lot_cost = entry_price * 100
            if one_lot_cost > self.per_trade * 1.2:
                logger.warning(
                    f"❌ {name}({code}) 1手成本{one_lot_cost:.0f}元 "
                    f"超单次预算{self.per_trade:.0f}元20%以上，拒绝入场"
                )
                return False
            shares = 100
        cost = shares * entry_price
        if cost > self.remaining_budget:
            logger.warning(f"❌ {name}({code}) 成本{cost:.0f}元超剩余预算，拒绝入场")
            return False
        self.positions.append({
            "code": code,
            "name": name,
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "shares": shares,
            "cost_amount": cost,
            "signal_type": signal_type,
            "entry_date": datetime.now().strftime("%Y-%m-%d"),
            "reason": reason,
            "status": "active",
        })
        self.save()
        return True

    def remove_position(self, code: str):
        self.positions = [p for p in self.positions if p["code"] != code]
        self.save()

    def render_summary(self, current_prices: Dict[str, float] = None) -> str:
        """渲染机会仓当前状态"""
        lines = []
        lines.append("#### 📊 机会仓当前状态")
        lines.append(f"预算: {self.budget:.0f}元 | 已用: {self.used_budget:.0f}元 | "
                    f"剩余: {self.remaining_budget:.0f}元 | "
                    f"剩余槽位: {self.remaining_slots}/{OppConfig.MAX_POSITIONS}")

        if not self.positions:
            lines.append("当前无持仓。")
        else:
            lines.append("")
            lines.append("| 股票 | 类型 | 成本价 | 止损价 | 当前价 | 盈亏 | 持仓日 |")
            lines.append("|---|---|---|---|---|---|---|")
            for p in self.positions:
                cur = (current_prices or {}).get(p["code"])
                pnl_str = "-"
                if cur:
                    pnl = (cur - p["entry_price"]) / p["entry_price"] * 100
                    pnl_str = f"{pnl:+.1f}%"
                    if cur <= p["stop_loss_price"]:
                        pnl_str += " 🚨止损触发"
                days = (datetime.now() - datetime.strptime(p["entry_date"], "%Y-%m-%d")).days
                sig_label = "涨停板" if p["signal_type"] == "A" else "板块启动"
                lines.append(
                    f"| {p['name']}({p['code']}) | {sig_label} | "
                    f"{p['entry_price']:.2f} | {p['stop_loss_price']:.2f} | "
                    f"{cur or '-'} | {pnl_str} | {days}天 |"
                )
        return "\n".join(lines)


# ==================== 东方财富数据工具 ====================

def _em_get(url: str, timeout: int = 8) -> Optional[Dict]:
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        })
        if r.status_code == 200:
            text = r.text.strip()
            if "(" in text and text.endswith(")"):
                text = text[text.index("(")+1:-1]
            return json.loads(text)
    except Exception as e:
        logger.debug(f"EM请求失败: {str(e)[:60]}")
    return None


def fetch_today_limit_up_stocks() -> List[Dict[str, Any]]:
    """
    获取今日涨停股票列表（东方财富涨停板数据）
    返回：[{code, name, change_pct, price, sector, turnover_pct, ...}]
    """
    url = (
        "https://push2ex.eastmoney.com/getTopicQQHisList?"
        "ut=7eea3edcaed734bea9cbfc24409ed989"
        "&dpt=wz.ztzt&pagesize=200&p=0&market=0&rt=15"
    )
    data = _em_get(url)
    results = []
    if not data or "data" not in data or not data["data"]:
        # 备用接口
        url2 = (
            "https://push2.eastmoney.com/api/qt/clist/get?"
            "pn=1&pz=200&po=1&np=1&fltt=2&invt=2&dect=1"
            "&fields=f12,f14,f3,f8,f9,f13,f128,f2,f22,f11,f62"
            "&fs=m:0+t:2,m:1+t:2"
            "&fid=f3&invt=2"
        )
        data = _em_get(url2)
        if not data or "data" not in data or not data["data"]:
            return []
        items = data["data"].get("diff", [])
        for item in items:
            chg = item.get("f3", 0)
            if chg and float(chg) >= 9.9:  # 涨停
                code = str(item.get("f12", ""))
                results.append({
                    "code": code,
                    "name": item.get("f14", ""),
                    "change_pct": float(chg),
                    "price": float(item.get("f2", 0)) / 100 if item.get("f2") else 0,
                    "sector": item.get("f128", ""),
                    "turnover_pct": float(item.get("f8", 0)) if item.get("f8") else 0,
                })
        return results

    items = data["data"].get("pool", [])
    for item in items:
        code = str(item.get("c", ""))
        # v1.0.2修复: 主接口 p 字段单位异常(2026-06疑似接口改版),
        # 直接除1000得元单位(经验校准: p=14400 -> 14.40元 -> 1.44元?)
        # 最稳妥: 标记 None,让上游强制用 K 线 close
        raw_p = item.get("p", 0)
        results.append({
            "code": code,
            "name": item.get("n", ""),
            "change_pct": 10.0,
            "price": None,  # ⚠️ 不可信,上游必须用 K 线 close 重写
            "_raw_p": raw_p,  # 调试保留
            "sector": item.get("hybk", ""),
            "turnover_pct": float(item.get("hs", 0)),
            "limit_up_time": item.get("fbt", ""),   # 首次涨停时间
            "open_times": item.get("lbc", 0),       # 炸板次数
            "continuous_days": item.get("days", 1), # 连板天数
        })
    return results


def fetch_sector_3d_inflow(sector_code: str) -> float:
    """获取板块近3日主力净流入（亿元）"""
    total = 0.0
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?"
        f"lmt=10&klt=101&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65"
        f"&secid=90.{sector_code}"
    )
    data = _em_get(url)
    if not data or "data" not in data or not data["data"]:
        return 0.0
    klines = data["data"].get("klines", [])
    for kline in klines[-3:]:  # 最近3天
        try:
            fields = kline.split(",")
            if len(fields) > 3:
                main_net = float(fields[3]) / 1e8  # 主力净流入，单位从元转亿
                total += main_net
        except (ValueError, IndexError):
            continue
    return round(total, 2)


def fetch_stock_basic_info(code: str) -> Optional[Dict]:
    """获取个股基本行情（用于过滤小盘/ST等）"""
    suffix = "1" if code.startswith(("6", "9")) else "0"
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get?"
        f"secid={suffix}.{code}"
        f"&fields=f57,f58,f84,f85,f116,f117,f9,f3,f43,f44,f45"
    )
    data = _em_get(url)
    if not data or "data" not in data or not data["data"]:
        return None
    d = data["data"]
    circ_mv = d.get("f117", 0)  # 流通市值（元）
    return {
        "code": code,
        "name": d.get("f58", ""),
        "market_cap_yi": float(circ_mv) / 1e8 if circ_mv else 0,
        "pe_ttm": d.get("f9"),
        "price": float(d.get("f43", 0)) / 100 if d.get("f43") else 0,
        "change_pct": float(d.get("f3", 0)) / 100 if d.get("f3") else 0,
    }


def is_st_stock(name: str, code: str) -> bool:
    """判断是否ST/退市风险股"""
    if not name:
        return False
    return bool(re.search(r'ST|退', name, re.IGNORECASE))


def is_star_market(code: str) -> bool:
    """判断是否科创板"""
    return str(code).startswith("688") or str(code).startswith("689")


# ==================== 信号A：涨停板次日 ====================

def scan_signal_a_limit_up(
    tushare_source: Any,
    user_pool_codes: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """
    扫描信号A：今日涨停，明日竞价候选

    筛选条件：
    1. 今日涨停（非高开涨停，排除高位股）
    2. 20日位置 < 75%（不追高位涨停）
    3. 52周位置 < 85%
    4. 板块今日有≥2只涨停（共振验证）
    5. 净利同比 > -30%（基本面不崩）
    6. 非ST、非科创板
    7. 流通市值 > 30亿
    8. 炸板次数 = 0（稳定封板）

    Returns:
        候选标的列表，按质量评分降序
    """
    logger.info("🎯 [信号A] 扫描今日涨停板候选...")
    user_pool_codes = user_pool_codes or set()

    limit_up_stocks = fetch_today_limit_up_stocks()
    if not limit_up_stocks:
        logger.warning("  ⚠️ 涨停数据获取失败")
        return []

    logger.info(f"  今日涨停板共 {len(limit_up_stocks)} 只")

    # 统计各板块涨停数（用于共振验证）
    sector_limit_count: Dict[str, int] = {}
    for s in limit_up_stocks:
        sec = s.get("sector", "")
        if sec:
            sector_limit_count[sec] = sector_limit_count.get(sec, 0) + 1

    candidates = []
    checked = 0
    for stock in limit_up_stocks:
        code = stock.get("code", "")
        name = stock.get("name", "")

        # 基础过滤
        if not code or len(code) != 6:
            continue
        if code in user_pool_codes:
            continue
        if is_star_market(code):
            continue
        if is_st_stock(name, code):
            continue

        # 炸板次数过滤（炸板=不稳定）
        if stock.get("open_times", 0) > 0:
            continue

        time.sleep(0.1)
        checked += 1

        # 获取K线（需要20日位置、52周位置）
        try:
            kline = tushare_source.get_daily_kline(code, days=260)
            if not kline or len(kline) < 60:
                continue

            # v1.0.2修复: 涨停板接口的 price 字段单位不可靠,
            # 强制用 K 线最新 close 作为 price (元单位,可靠)
            price = float(kline[-1].get("close", 0))
            if price <= 0:
                continue

            # 20日位置
            last20 = kline[-20:]
            h20 = max(float(k.get("high", 0)) for k in last20)
            l20 = min(float(k.get("low", 0)) for k in last20)
            pos_20d = (price - l20) / (h20 - l20) * 100 if h20 > l20 else 50

            # 52周位置
            kline_52w = kline[-min(250, len(kline)):]
            h52 = max(float(k.get("high", 0)) for k in kline_52w)
            l52 = min(float(k.get("low", 0)) for k in kline_52w)
            pos_52w = (price - l52) / (h52 - l52) * 100 if h52 > l52 else 50

            # 位置过滤
            if pos_20d > OppConfig.A_MAX_PRICE_POS_20D:
                continue
            if pos_52w > OppConfig.A_MAX_PRICE_POS_52W:
                continue

            # 流通市值过滤（从basic获取）
            basic = tushare_source.get_daily_basic(code)
            market_cap_yi = 0
            if basic:
                circ_mv = basic.get("circ_mv", 0) or 0
                market_cap_yi = circ_mv / 1e4
            if market_cap_yi < OppConfig.MIN_MARKET_CAP_YI:
                continue

            # 业绩过滤
            fina = tushare_source.get_latest_fina(code)
            np_yoy = fina.get("np_yoy") if fina else None
            if np_yoy is not None and np_yoy < OppConfig.A_MIN_NP_YOY:
                continue

            # 板块共振验证
            sector = stock.get("sector", "")
            sector_count = sector_limit_count.get(sector, 0)

            # 连板天数（连板更强但也更危险，适当加权）
            continuous_days = stock.get("continuous_days", 1)

            # 质量评分（用于排序）
            quality_score = 0
            quality_score += max(0.0, (75 - pos_20d) / 75 * 2)  # 位置越低分越高(v1.0.1修复:原公式反向)
            quality_score += min(sector_count / 3, 1.5)      # 板块共振
            if np_yoy and np_yoy > 20:
                quality_score += 1.0
            if continuous_days == 1:
                quality_score += 1.0  # 首板更纯粹
            elif continuous_days == 2:
                quality_score += 0.5  # 二连板可以
            # 三板以上不推荐（风险太大）

            # 止损价
            stop_loss = round(price * (1 - OppConfig.A_STOP_LOSS_PCT), 2)

            candidates.append({
                "code": code,
                "name": name,
                "signal_type": "A",
                "signal_label": "涨停板次日",
                "price": price,
                "pos_20d_pct": round(pos_20d, 1),
                "pos_52w_pct": round(pos_52w, 1),
                "market_cap_yi": round(market_cap_yi, 1),
                "np_yoy": np_yoy,
                "sector": sector,
                "sector_limit_count": sector_count,
                "continuous_days": continuous_days,
                "open_times": stock.get("open_times", 0),
                "turnover_pct": stock.get("turnover_pct", 0),
                "stop_loss_price": stop_loss,
                "stop_loss_pct": OppConfig.A_STOP_LOSS_PCT * 100,
                "quality_score": round(quality_score, 2),
                "entry_note": (
                    f"明日竞价参与，开板即止损或跌-{OppConfig.A_STOP_LOSS_PCT*100:.0f}%止损。"
                    f"板块{sector}今日{sector_count}只涨停，{'共振信号✅' if sector_count >= 2 else '共振弱⚠️'}"
                ),
            })

        except Exception as e:
            logger.debug(f"  {code} 处理失败: {str(e)[:60]}")
            continue

    # 排序
    candidates.sort(key=lambda x: x["quality_score"], reverse=True)

    # 过滤三板以上
    candidates = [c for c in candidates if c["continuous_days"] <= 2]

    logger.info(f"  ✅ 信号A候选: {len(candidates)} 只 (检查{checked}只)")
    return candidates[:5]  # 最多返回5只


# ==================== 信号B：板块启动初期 ====================

def scan_signal_b_sector_breakout(
    tushare_source: Any,
    user_pool_codes: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """
    扫描信号B：板块启动初期龙头

    筛选条件：
    1. 板块今日涨幅 > 2%
    2. 板块近3日主力净流入 > 3亿
    3. 个股20日位置 < 60%（不追高位）
    4. v1.1评分 >= 1.5
    5. 净利同比 > 0（正增长）
    6. 流通市值 > 30亿
    7. 非ST、非科创板

    Returns:
        候选标的列表
    """
    logger.info("🎯 [信号B] 扫描板块启动初期龙头...")
    user_pool_codes = user_pool_codes or set()

    # 获取今日强势板块
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=100&po=1&np=1&fltt=2&invt=2"
        "&fs=m:90+t:2"
        "&fields=f12,f14,f3,f62,f128,f184"
    )
    data = _em_get(url)
    if not data or "data" not in data or not data["data"]:
        logger.warning("  ⚠️ 板块数据获取失败")
        return []

    # 筛选今日涨幅>2%的板块
    strong_sectors = []
    for item in data["data"].get("diff", []):
        chg = item.get("f3")
        inflow = item.get("f62")
        if chg and inflow:
            try:
                chg_f = float(chg)
                inflow_yi = float(inflow) / 1e8
                if chg_f >= OppConfig.B_SECTOR_MIN_TODAY_CHG and inflow_yi > 0:
                    strong_sectors.append({
                        "code": item.get("f12", ""),
                        "name": item.get("f14", ""),
                        "change_pct": chg_f,
                        "inflow_today_yi": round(inflow_yi, 2),
                    })
            except (ValueError, TypeError):
                continue

    logger.info(f"  今日涨幅>2%的板块: {len(strong_sectors)} 个")

    # 验证近3日资金持续流入
    qualified_sectors = []
    for sec in strong_sectors[:15]:  # 只看前15个板块
        inflow_3d = fetch_sector_3d_inflow(sec["code"])
        time.sleep(0.15)
        if inflow_3d >= OppConfig.B_SECTOR_MIN_3D_INFLOW:
            sec["inflow_3d_yi"] = inflow_3d
            qualified_sectors.append(sec)
            logger.debug(f"  ✅ {sec['name']}: 3日流入{inflow_3d:.1f}亿")

    logger.info(f"  3日持续流入>3亿的板块: {len(qualified_sectors)} 个")

    if not qualified_sectors:
        return []

    # 在每个板块里找低位龙头
    from stock_report_enhanced import (
        calc_right_side_score, calc_turnover_zscore,
        calc_inflow_slope, calc_pe_pb_percentile,
        _CURRENT_MARKET_REGIME
    )

    candidates = []
    for sector in qualified_sectors[:3]:  # 最多扫描3个板块
        # 获取板块成分股
        url2 = (
            f"https://push2.eastmoney.com/api/qt/clist/get?"
            f"pn=1&pz=50&po=1&np=1&fltt=2&invt=2"
            f"&fs=b:{sector['code']}"
            f"&fields=f12,f14,f3,f2"
        )
        sec_data = _em_get(url2)
        if not sec_data or "data" not in sec_data or not sec_data["data"]:
            continue

        sec_stocks = sec_data["data"].get("diff", [])
        time.sleep(0.1)

        for item in sec_stocks[:20]:  # 每个板块扫描前20只
            code = str(item.get("f12", ""))
            name = item.get("f14", "")

            if not code or len(code) != 6:
                continue
            if code in user_pool_codes:
                continue
            if is_star_market(code):
                continue
            if is_st_stock(name, code):
                continue

            try:
                time.sleep(0.08)
                kline = tushare_source.get_daily_kline(code, days=260)
                if not kline or len(kline) < 60:
                    continue

                price = float(kline[-1].get("close", 0))
                if price <= 0:
                    continue

                # 均线
                closes = [float(k.get("close", 0)) for k in kline[-60:]
                          if k.get("close")]
                ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else price

                # 20日位置
                last20 = kline[-20:]
                h20 = max(float(k.get("high", 0)) for k in last20)
                l20 = min(float(k.get("low", 0)) for k in last20)
                pos_20d = (price - l20) / (h20 - l20) * 100 if h20 > l20 else 50

                # 过滤高位
                if pos_20d > OppConfig.B_STOCK_MAX_POS_20D:
                    continue

                # 流通市值
                basic = tushare_source.get_daily_basic(code)
                market_cap_yi = 0
                if basic:
                    market_cap_yi = (basic.get("circ_mv") or 0) / 1e4
                if market_cap_yi < OppConfig.MIN_MARKET_CAP_YI:
                    continue

                # 资金
                mf = tushare_source.get_moneyflow_summary(code)
                flow_5d = mf.get("main_inflow_5d") if mf else None
                flow_10d = mf.get("main_inflow_10d") if mf else None
                inflow_slope = calc_inflow_slope(flow_5d, flow_10d)

                # 换手Z(v1.0.1修复:Tushare daily无turn字段,改用daily_basic_history)
                turn = float(basic.get("turnover_rate") or 0)
                tz = None
                basic_h_for_turn = tushare_source.get_daily_basic_history(code, days=100)
                if basic_h_for_turn and turn:
                    turn_hist = [{"turn": b.get("turnover_rate")} for b in basic_h_for_turn
                                 if b.get("turnover_rate") is not None]
                    if len(turn_hist) >= 20:
                        tz = calc_turnover_zscore(turn_hist, turn)

                # 业绩
                fina = tushare_source.get_latest_fina(code)
                np_yoy = fina.get("np_yoy") if fina else None
                if np_yoy is None or np_yoy < 0:
                    continue  # 信号B要求正增长

                # 股东户数
                holder_h = tushare_source.get_holder_number(code, periods=2)
                hc_pct = None
                if holder_h and len(holder_h) >= 2:
                    try:
                        n1 = holder_h[0].get("holder_num")
                        n0 = holder_h[1].get("holder_num")
                        if n1 and n0 and n0 > 0:
                            hc_pct = (n1 - n0) / n0 * 100
                    except (TypeError, ValueError):
                        pass

                # PE百分位
                basic_h = tushare_source.get_daily_basic_history(code, days=250)
                pe_ttm = basic.get("pe_ttm") if basic else None
                pe_pct = None
                if basic_h and pe_ttm:
                    pe_pct = calc_pe_pb_percentile(
                        basic_h, pe_ttm, None)["pe_percentile"]

                # v1.2评分（含市值归一化资金流）
                rss = calc_right_side_score(
                    price=price, ma5=ma5,
                    volume_ratio_5d=None, change_pct=None,
                    turnover_zscore=tz, inflow_slope=inflow_slope,
                    inflow_10d=flow_10d, holder_change_pct=hc_pct,
                    position_20d_pct=pos_20d, np_yoy=np_yoy,
                    pe_percentile_1y=pe_pct,
                    market_regime=_CURRENT_MARKET_REGIME,
                    circ_mv_yi=market_cap_yi if market_cap_yi > 0 else None,
                )

                if rss["score"] < OppConfig.B_STOCK_MIN_SCORE:
                    continue

                stop_loss = round(price * (1 - OppConfig.B_STOP_LOSS_PCT), 2)

                candidates.append({
                    "code": code,
                    "name": name,
                    "signal_type": "B",
                    "signal_label": "板块启动",
                    "price": price,
                    "pos_20d_pct": round(pos_20d, 1),
                    "market_cap_yi": round(market_cap_yi, 1),
                    "np_yoy": np_yoy,
                    "sector": sector["name"],
                    "sector_change_pct": sector["change_pct"],
                    "sector_inflow_3d": sector["inflow_3d_yi"],
                    "score": rss["score"],
                    "signals": rss["signals"],
                    "stop_loss_price": stop_loss,
                    "stop_loss_pct": OppConfig.B_STOP_LOSS_PCT * 100,
                    "quality_score": rss["score"],
                    "entry_note": (
                        f"板块{sector['name']}今日+{sector['change_pct']:.1f}%，"
                        f"3日流入{sector['inflow_3d_yi']:.1f}亿。"
                        f"个股低位({pos_20d:.0f}%)，止损-{OppConfig.B_STOP_LOSS_PCT*100:.0f}%。"
                    ),
                })

            except Exception as e:
                logger.debug(f"  {code} 处理失败: {str(e)[:60]}")
                continue

    candidates.sort(key=lambda x: x["quality_score"], reverse=True)
    logger.info(f"  ✅ 信号B候选: {len(candidates)} 只")
    return candidates[:5]


# ==================== 主扫描入口 ====================

def scan_opportunities(
    tushare_source: Any,
    total_capital: float = 164000,
    user_pool_codes: Optional[set] = None,
) -> Dict[str, Any]:
    """
    主扫描入口，同时运行信号A和信号B

    Returns:
        {
            "signal_a": [...],  # 涨停板次日候选
            "signal_b": [...],  # 板块启动初期候选
            "book": OpportunityBook,  # 机会仓状态
            "scan_time": str,
        }
    """
    user_pool_codes = user_pool_codes or set()
    book = OpportunityBook(total_capital=total_capital)

    result_a = []
    result_b = []

    if book.can_add():
        result_a = scan_signal_a_limit_up(tushare_source, user_pool_codes)
        result_b = scan_signal_b_sector_breakout(tushare_source, user_pool_codes)
    else:
        logger.info("  机会仓已满（3/3），跳过扫描")

    return {
        "signal_a": result_a,
        "signal_b": result_b,
        "book": book,
        "scan_time": datetime.now().isoformat(),
        "can_add": book.can_add(),
        "remaining_slots": book.remaining_slots,
        "remaining_budget": book.remaining_budget,
    }


# ==================== 报告渲染 ====================

def render_opportunity_section(
    scan_result: Dict[str, Any],
    total_capital: float = 164000,
) -> str:
    """渲染机会仓章节（集成到日报末尾）"""
    lines = ["## 七、机会仓扫描 ⚡ (短线机会，独立止损)"]
    lines.append("")
    lines.append("> **机会仓规则**：总额度15%（约"
                 f"{total_capital*0.15:.0f}元），单次出手5%（约"
                 f"{total_capital*0.05:.0f}元），最多同时持有3只。"
                 "**亏损不影响主仓，止损必须执行。**")
    lines.append("")

    book: OpportunityBook = scan_result.get("book")
    if book:
        # v1.0.1: 尝试用持仓代码拉实时价,失败则显示"-"
        cur_prices = {}
        for p in book.positions:
            info = fetch_stock_basic_info(p["code"])
            if info and info.get("price"):
                cur_prices[p["code"]] = info["price"]
        lines.append(book.render_summary(cur_prices))
        lines.append("")

    # ── 信号A：涨停板次日 ──
    signal_a = scan_result.get("signal_a", [])
    lines.append("### 📌 信号A：涨停板次日追板候选")
    if not signal_a:
        lines.append("今日无符合条件的涨停板候选。")
        lines.append("（条件：20日位置<75% + 52周位置<85% + 板块共振 + 首板/二连板 + 封板稳定）")
    else:
        lines.append("明日竞价参与，开板即走或跌-3%止损，不恋战。")
        lines.append("")
        for c in signal_a:
            resonance = "✅共振" if c.get("sector_limit_count", 0) >= 2 else "⚠️共振弱"
            days_label = f"{'首板' if c['continuous_days'] == 1 else str(c['continuous_days'])+'连板'}"
            lines.append(
                f"- **{c['name']} ({c['code']})** | {days_label} | {resonance} | "
                f"质量评分{c['quality_score']:.1f}"
            )
            lines.append(
                f"  - 现价 {c['price']:.2f} | 20日位置{c['pos_20d_pct']:.0f}% | "
                f"52周位置{c['pos_52w_pct']:.0f}% | 市值{c['market_cap_yi']:.0f}亿"
            )
            if c.get("np_yoy") is not None:
                lines.append(f"  - 净利同比 {c['np_yoy']:+.1f}% | 板块 {c['sector']}")
            lines.append(f"  - 🎯 {c['entry_note']}")
            lines.append(f"  - 止损价: **{c['stop_loss_price']:.2f}**（-{c['stop_loss_pct']:.0f}%）")
            lines.append("")

    # ── 信号B：板块启动初期 ──
    signal_b = scan_result.get("signal_b", [])
    lines.append("### 📌 信号B：板块启动初期低位龙头")
    if not signal_b:
        lines.append("今日无符合条件的板块启动候选。")
        lines.append("（条件：板块今日涨>2% + 3日流入>3亿 + 个股20日位置<70% + v1.1评分≥1.5 + 净利正增长）")
    else:
        lines.append("收盘后决策，次日开盘可参与，跌-5%止损。")
        lines.append("")
        for c in signal_b:
            lines.append(
                f"- **{c['name']} ({c['code']})** | {c['sector']} | "
                f"v1.1评分{c['score']:.1f}分"
            )
            lines.append(
                f"  - 现价 {c['price']:.2f} | 20日位置{c['pos_20d_pct']:.0f}% | "
                f"市值{c['market_cap_yi']:.0f}亿 | 净利同比{c.get('np_yoy', 0):+.1f}%"
            )
            lines.append(
                f"  - 板块3日流入{c['sector_inflow_3d']:.1f}亿 | "
                f"板块今日+{c['sector_change_pct']:.1f}%"
            )
            pos_signals = [s for s in c.get("signals", []) if "✅" in s]
            if pos_signals:
                lines.append(f"  - 信号: {' | '.join(pos_signals[:3])}")
            lines.append(f"  - 🎯 {c['entry_note']}")
            lines.append(f"  - 止损价: **{c['stop_loss_price']:.2f}**（-{c['stop_loss_pct']:.0f}%）")
            lines.append("")

    # ── 重要提醒 ──
    lines.append("### ⚠️ 机会仓使用提醒")
    lines.append("1. **主仓和机会仓完全隔离**：机会仓亏损不影响主仓决策")
    lines.append("2. **止损必须执行**：信号A开板即走，信号B跌5%即走，不手软")
    lines.append("3. **胜率约30-50%**：亏损是正常成本，不要因为亏损调整规则")
    lines.append("4. **仓位固定**：每次只出总资金5%，盈利不加仓，亏损不补仓")
    lines.append("5. **追踪已入场**：在 `opportunity_book.json` 中手动记录入场")

    return "\n".join(lines)


# ==================== 机会仓操作命令 ====================

def print_book_commands():
    """打印机会仓操作命令帮助"""
    print("""
机会仓操作命令（在 Python 脚本里调用）：

from opportunity_scanner import OpportunityBook

book = OpportunityBook(total_capital=164000)

# 记录入场
book.add_position(
    code="000636", name="风华高科",
    entry_price=64.30, signal_type="A",
    stop_loss_price=62.37,
    reason="涨停板次日，首板，板块共振"
)

# 移除（止损/止盈后）
book.remove_position("000636")

# 查看状态
print(book.render_summary(current_prices={"000636": 67.0}))
""")


# ==================== 单元测试 ====================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    # 测试机会仓状态管理
    logger.info("测试机会仓状态管理...")
    book = OpportunityBook(total_capital=164000)
    logger.info(f"预算: {book.budget:.0f}元，单次: {book.per_trade:.0f}元")
    logger.info(f"剩余槽位: {book.remaining_slots}，可入场: {book.can_add()}")

    # 模拟入场
    book.add_position("000636", "风华高科", 64.30, "A", 62.37, "测试")
    logger.info(f"入场后剩余: {book.remaining_budget:.0f}元")
    logger.info(book.render_summary({"000636": 67.5}))

    # 清理测试数据
    book.remove_position("000636")
    logger.info("测试完成，已清理")
