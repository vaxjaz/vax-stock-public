# -*- coding: utf-8 -*-
"""Tushare 数据源(2000积分专业版)。

本模块整合自 script/tushare_source.py(原样搬运, 逻辑零改动), 并把单体脚本
script/stock_report_enhanced.py 中的 get_history_kline 搬入本层。

搬运时的唯一行为相关调整:
    get_history_kline 原依赖模块全局 TUSHARE, 现改为显式接收 source 参数
    (一个已初始化的 TushareSource 实例或 None)。这是为遵守"import 无副作用 /
    不在导入时初始化 client"所做的最小签名调整, 函数体逻辑完全不变。

容错说明: _safe_call 的 daemon 线程 + join(timeout) 真·墙钟超时机制原样保留。
缓存目录 CACHE_DIR 暂保持模块相对(.cache_tushare, 已被 .gitignore 忽略),
仅在 token 有效时于 __init__ 内创建, import 本模块不产生任何文件/网络副作用。

覆盖接口:
- daily / daily_basic / index_daily     行情与估值
- moneyflow                              个股资金流向(4档)
- moneyflow_hsgt                         北向资金
- fina_indicator                         财务指标(80+字段)
- forecast / express                     业绩预告/快报
- stk_holdernumber                       股东户数
- concept_detail                         概念板块

设计原则:
- 本地缓存,减少积分消耗
- 限流保护
- 任何失败返回None,不抛异常
"""

import json
import logging
import os
import time
import threading
import concurrent.futures as _futures
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from vaxstock.config import HISTORY_DAYS
from vaxstock.util import safe_float

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache_tushare")

CACHE_TTL = {
    "stock_basic": 30, "concept_list": 30, "stock_concepts": 14,
    "daily": 1, "daily_basic": 1,
    "moneyflow": 1, "moneyflow_hsgt": 1,
    "fina_indicator": 30, "forecast": 7, "express": 7,
    "holder_number": 30, "index_daily": 1, "top_list": 1,
}

_call_timestamps: List[float] = []
_RATE_LIMIT_PER_MIN = 180
_rate_lock = threading.Lock()   # 并发下保护 _call_timestamps
# 单次 Tushare 接口墙钟超时(秒): 防单接口卡死拖垮整请求。环境变量 TUSHARE_CALL_TIMEOUT 可覆盖。
TUSHARE_CALL_TIMEOUT = int(os.environ.get("TUSHARE_CALL_TIMEOUT", "12"))


class TushareSource:
    def __init__(self, token: Optional[str] = None):
        self.pro = None
        self.token = token
        self.enabled = False
        self.points_level = 0

        if not token:
            logger.info("ℹ️ Tushare token未配置")
            return

        try:
            import tushare as ts
            ts.set_token(token)
            self.pro = ts.pro_api()
            test = self.pro.stock_basic(list_status="L", limit=1)
            if test is None or len(test) == 0:
                logger.warning("⚠️ Tushare token可能无效")
                return

            self.enabled = True
            self.points_level = 120

            # 探测2000积分(用fina_indicator标准接口)
            try:
                test_df = self.pro.fina_indicator(ts_code="600519.SH",
                                                  period="20240930",
                                                  fields="ts_code,end_date,roe")
                if test_df is not None and len(test_df) > 0:
                    self.points_level = 2000
            except Exception:
                pass

            # 探测5000积分(用真正5000分专属的 _vip 接口,且必须能返回多行)
            try:
                vip_df = self.pro.fina_indicator_vip(period="20240930",
                                                     fields="ts_code,end_date,roe",
                                                     limit=10)
                # 严格判定: 必须返回 >=2 行才算真的有vip权限
                if vip_df is not None and len(vip_df) >= 2:
                    self.points_level = 5000
            except Exception:
                pass

            os.makedirs(CACHE_DIR, exist_ok=True)
            logger.info(f"✅ Tushare已就绪 [积分≥{self.points_level}] token末4位:...{token[-4:]}")
        except ImportError:
            logger.warning("⚠️ tushare包未安装")
        except Exception as e:
            logger.warning(f"⚠️ Tushare初始化失败: {str(e)[:120]}")

    # ============ 工具 ============

    def _rate_limit(self):
        global _call_timestamps
        with _rate_lock:
            now = time.time()
            _call_timestamps = [t for t in _call_timestamps if now - t < 60]
            if len(_call_timestamps) >= _RATE_LIMIT_PER_MIN:
                wait = 60 - (now - _call_timestamps[0]) + 0.5
                if wait > 0:
                    logger.info(f"  ⏸ 限流保护,等待{wait:.1f}秒...")
                    time.sleep(wait)
            _call_timestamps.append(time.time())

    def _cache_path(self, key):
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)
        return os.path.join(CACHE_DIR, f"{safe}.json")

    def _cache_get(self, key, ttl_days):
        path = self._cache_path(key)
        if not os.path.exists(path):
            return None
        try:
            age = (time.time() - os.path.getmtime(path)) / 86400
            if age > ttl_days:
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _cache_set(self, key, data):
        try:
            with open(self._cache_path(key), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except Exception as e:
            logger.debug(f"缓存写入失败: {e}")

    @staticmethod
    def code_to_ts(code):
        code = str(code).strip()
        if "." in code:
            return code
        if code.startswith(("6", "9")):
            return f"{code}.SH"
        return f"{code}.SZ"

    def _safe_call(self, func_name, **kwargs):
        if not self.enabled:
            return None
        self._rate_limit()
        # 用 daemon 线程 + join(timeout) 实现真·墙钟超时。
        # 不能用 `with ThreadPoolExecutor`: 其退出时 shutdown(wait=True) 会反过来
        # 等卡死线程跑完, 令 future 超时形同虚设。daemon 线程超时后主线程直接放弃,
        # 孤儿线程随底层 socket 自行结束, 不阻塞本请求, 进程退出也不被它拖住。
        box = {}

        def _run():
            try:
                box["df"] = getattr(self.pro, func_name)(**kwargs)
            except Exception as e:
                box["err"] = e

        t = threading.Thread(target=_run, name=f"ts_{func_name}", daemon=True)
        t.start()
        t.join(TUSHARE_CALL_TIMEOUT)
        if t.is_alive():
            logger.warning(f"  ⏱ {func_name} 超时>{TUSHARE_CALL_TIMEOUT}s, 放弃本次(后台线程随socket结束)")
            return None
        if "err" in box:
            err = str(box["err"])[:120]
            if "积分" in err or "permission" in err.lower():
                logger.debug(f"  ℹ️ {func_name} 积分不足: {err}")
            else:
                logger.debug(f"  ⚠️ {func_name} 失败: {err}")
            return None
        df = box.get("df")
        if df is None or len(df) == 0:
            return None
        return df

    # ============ 行情 ============

    def get_daily_kline(self, code, days=250):
        today = datetime.now().strftime("%Y%m%d")
        cache_key = f"daily_{code}_{days}_{today}"
        cached = self._cache_get(cache_key, CACHE_TTL["daily"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 100)).strftime("%Y%m%d")
        df = self._safe_call("daily", ts_code=ts_code, start_date=start, end_date=end)
        if df is None:
            return None

        df = df.sort_values("trade_date", ascending=True).tail(days)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    def get_daily_basic(self, code):
        today = datetime.now().strftime("%Y%m%d")
        cache_key = f"basic_{code}_{today}"
        cached = self._cache_get(cache_key, CACHE_TTL["daily_basic"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")
        df = self._safe_call("daily_basic", ts_code=ts_code, start_date=start, end_date=end)
        if df is None:
            return None

        row = df.sort_values("trade_date", ascending=False).iloc[0].to_dict()
        self._cache_set(cache_key, row)
        return row

    def get_daily_basic_history(self, code, days=250):
        today = datetime.now().strftime("%Y%m%d")
        cache_key = f"basic_hist_{code}_{days}_{today}"
        cached = self._cache_get(cache_key, CACHE_TTL["daily_basic"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 100)).strftime("%Y%m%d")
        df = self._safe_call("daily_basic", ts_code=ts_code, start_date=start, end_date=end,
                             fields="trade_date,turnover_rate,pe,pe_ttm,pb,ps,ps_ttm,dv_ttm,total_mv,circ_mv")
        if df is None:
            return None

        df = df.sort_values("trade_date", ascending=True).tail(days)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    # ============ 资金流向 (2000分) ============

    def get_moneyflow(self, code, days=10):
        if self.points_level < 2000:
            return None
        today = datetime.now().strftime("%Y%m%d")
        cache_key = f"moneyflow_{code}_{days}_{today}"
        cached = self._cache_get(cache_key, CACHE_TTL["moneyflow"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")
        df = self._safe_call("moneyflow", ts_code=ts_code, start_date=start, end_date=end)
        if df is None:
            return None

        df = df.sort_values("trade_date", ascending=True).tail(days)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    def get_moneyflow_summary(self, code):
        """主力净流入汇总。

        【口径】主力净流入 = net_mf_amount(Tushare净流入额字段),与回测/IC因子完全一致。
        【修复 2026-06-19】
          旧实现: (大单+特大单买) − (大单+特大单卖) 手动加总, 且 ×1000。两处错误:
            (1) 字段错: 该分档加总与涨跌相关仅0.147(噪音); net_mf_amount 相关0.871(可信)。
            (2) 单位错: net_mf_amount 及各档 amount 官方单位为"万元", 应 ×10000, 旧代码误用 ×1000。
          现统一改用 net_mf_amount × 10000, 与 factor_calculator.py 第78行 IC 回测口径一致。
          分档明细单位同步修正为 ×10000, 仅供资金结构(吸筹/派发)展示, 不参与评分。
        """
        flow = self.get_moneyflow(code, days=10)
        if not flow:
            return None

        # 主力净流入 = net_mf_amount(万元) × 10000 → 元。与回测IC口径一致。
        def main_inflow(row):
            v = row.get("net_mf_amount")
            return v * 10000 if v is not None else None

        # 多日累加: 跳过缺失日(None), 保证求和稳健
        def _sum_window(rows):
            vals = [main_inflow(r) for r in rows]
            vals = [x for x in vals if x is not None]
            return sum(vals) if vals else None

        today_row = flow[-1] if flow else {}
        today_main = main_inflow(today_row) if today_row else None
        d5_sum = _sum_window(flow[-5:]) if len(flow) >= 5 else None
        d10_sum = _sum_window(flow[-10:]) if len(flow) >= 10 else None

        return {
            "main_inflow_today": today_main,        # net_mf_amount×10000(元), 评分主口径
            "main_inflow_today_ts": today_main,      # 兼容旧键名, 现与 today 同源
            "main_inflow_5d": d5_sum,
            "main_inflow_10d": d10_sum,
            "latest_trade_date": today_row.get("trade_date"),
            # —— 分档明细(单位元), 仅供资金结构展示, 不进评分 ——
            "buy_elg_amount": (today_row.get("buy_elg_amount") or 0) * 10000,
            "sell_elg_amount": (today_row.get("sell_elg_amount") or 0) * 10000,
            "buy_lg_amount": (today_row.get("buy_lg_amount") or 0) * 10000,
            "sell_lg_amount": (today_row.get("sell_lg_amount") or 0) * 10000,
        }

    def get_hsgt_flow(self, days=5):
        if self.points_level < 2000:
            return None
        today = datetime.now().strftime("%Y%m%d")
        cache_key = f"hsgt_{days}_{today}"
        cached = self._cache_get(cache_key, CACHE_TTL["moneyflow_hsgt"])
        if cached:
            return cached

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")
        df = self._safe_call("moneyflow_hsgt", start_date=start, end_date=end)
        if df is None:
            return None

        df = df.sort_values("trade_date", ascending=True).tail(days)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    # ============ 财务 (2000分) ============

    def get_fina_indicator(self, code, periods=4):
        if self.points_level < 2000:
            return None
        cache_key = f"fina_{code}_{periods}"
        cached = self._cache_get(cache_key, CACHE_TTL["fina_indicator"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        df = self._safe_call("fina_indicator", ts_code=ts_code,
                             fields="ts_code,ann_date,end_date,eps,roe,roe_dt,"
                                    "grossprofit_margin,netprofit_margin,debt_to_assets,"
                                    "q_npincome_yoy,q_op_yoy,q_sales_yoy,q_profit_yoy,"
                                    "ocfps,bps,or_yoy,op_yoy,netprofit_yoy")
        if df is None:
            return None

        df = df.sort_values("end_date", ascending=False).head(periods)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    def get_latest_fina(self, code):
        records = self.get_fina_indicator(code, periods=1)
        return records[0] if records else None

    # ============ 业绩预告/快报 (2000分) ============

    def get_forecast(self, code, periods=4):
        """业绩预告 — 只取最近12个月内的最新预告(避免历史污染)"""
        if self.points_level < 2000:
            return None
        cache_key = f"forecast_{code}_{periods}"
        cached = self._cache_get(cache_key, CACHE_TTL["forecast"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        df = self._safe_call("forecast", ts_code=ts_code)
        if df is None:
            return None

        # 只保留最近12个月内 end_date 的预告
        # end_date 格式: '20251231' 这种 YYYYMMDD
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")

        df = df[df["end_date"] >= cutoff] if "end_date" in df.columns else df
        if len(df) == 0:
            self._cache_set(cache_key, [])
            return []

        # 按 ann_date(公告日)降序,取最新一份
        # 一个 end_date 可能对应多个预告版本(原始+修订),取公告最新的
        if "ann_date" in df.columns:
            df = df.sort_values(["end_date", "ann_date"], ascending=[False, False])
            # 去重:同一个 end_date 只保留最新公告的那条
            df = df.drop_duplicates(subset=["end_date"], keep="first")
        else:
            df = df.sort_values("end_date", ascending=False)

        df = df.head(periods)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    def get_express(self, code, periods=4):
        if self.points_level < 2000:
            return None
        cache_key = f"express_{code}_{periods}"
        cached = self._cache_get(cache_key, CACHE_TTL["express"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        df = self._safe_call("express", ts_code=ts_code)
        if df is None:
            return None

        df = df.sort_values("end_date", ascending=False).head(periods)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    # ============ 股东户数 (2000分) ============

    def get_holder_number(self, code, periods=4):
        if self.points_level < 2000:
            return None
        cache_key = f"holder_{code}_{periods}"
        cached = self._cache_get(cache_key, CACHE_TTL["holder_number"])
        if cached:
            return cached

        ts_code = self.code_to_ts(code)
        df = self._safe_call("stk_holdernumber", ts_code=ts_code)
        if df is None:
            return None

        df = df.sort_values("end_date", ascending=False).head(periods)
        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records

    # ============ 概念 (120分) ============

    def get_stock_concepts(self, code):
        cache_key = f"concepts_{code}"
        cached = self._cache_get(cache_key, CACHE_TTL["stock_concepts"])
        if cached is not None:
            return cached

        ts_code = self.code_to_ts(code)
        df = self._safe_call("concept_detail", ts_code=ts_code)
        if df is None:
            self._cache_set(cache_key, [])
            return []

        if "concept_name" in df.columns:
            concepts = df["concept_name"].dropna().unique().tolist()
        elif "name" in df.columns:
            concepts = df["name"].dropna().unique().tolist()
        else:
            concepts = []

        self._cache_set(cache_key, concepts)
        return concepts

    # ============ 指数 ============

    def get_index_daily(self, index_code):
        today = datetime.now().strftime("%Y%m%d")
        cache_key = f"idx_{index_code}_{today}"
        cached = self._cache_get(cache_key, CACHE_TTL["index_daily"])
        if cached:
            return cached

        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=15)).strftime("%Y%m%d")
        df = self._safe_call("index_daily", ts_code=index_code, start_date=start, end_date=end)
        if df is None:
            return None

        row = df.sort_values("trade_date", ascending=False).iloc[0].to_dict()
        self._cache_set(cache_key, row)
        return row

    # ============ 全市场单日 (用于涨跌家数/涨跌停聚合) ============

    def get_market_daily(self, trade_date, fields="ts_code,pct_chg"):
        """一次取全市场某交易日 daily(默认只取 ts_code,pct_chg 以减小负载)。

        走 _safe_call(daemon线程 + join 真·墙钟超时)容错; 按 trade_date 缓存(收盘后不变)。
        失败返回 None(由调用方按"待验证"处理, 不臆造)。
        """
        today = datetime.now().strftime("%Y%m%d")
        cache_key = f"market_daily_{trade_date}_{today}"
        cached = self._cache_get(cache_key, CACHE_TTL["daily"])
        if cached:
            return cached

        df = self._safe_call("daily", trade_date=str(trade_date), fields=fields)
        if df is None:
            return None

        records = df.to_dict("records")
        self._cache_set(cache_key, records)
        return records


# ============ 单例 ============

_instance: Optional[TushareSource] = None


def init_tushare(token):
    global _instance
    _instance = TushareSource(token)
    return _instance


def get_tushare():
    if _instance and _instance.enabled:
        return _instance
    return None


def clear_cache(older_than_days=30):
    if not os.path.exists(CACHE_DIR):
        return
    cutoff = time.time() - older_than_days * 86400
    removed = 0
    for f in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, f)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except Exception:
            pass
    logger.info(f"清理过期缓存: {removed}个")


# ============ 历史K线 (从单体脚本搬入, 纯Tushare) ============

def get_history_kline(source: Optional[TushareSource], code: str, days: int = HISTORY_DAYS) -> Optional[List[Dict[str, Any]]]:
    """获取历史K线 + 估值,完全使用Tushare数据源。
    返回字段统一: date, open, high, low, close, volume, amount, pctChg, turn, peTTM, pbMRQ, psTTM, pcfNcfTTM

    数据合并策略:
    1. daily 接口: 行情(开高低收量额)
    2. daily_basic 接口: 估值(PE/PB/PS/换手)
    3. 按 trade_date 精确匹配(全部强制 str 化避免类型问题)
    4. 最新一天若匹配不到,再用 daily_basic 单点接口兜底

    搬运调整: 原依赖模块全局 TUSHARE, 现改为显式接收 source(TushareSource 实例或 None),
    逻辑与单体脚本完全一致。
    """
    if source is None:
        logger.warning(f"  ⚠️ {code} Tushare未启用,无法获取历史数据")
        return None

    try:
        kline = source.get_daily_kline(code, days=days)
        if not kline:
            return None

        # 合并历史估值数据(daily_basic_history),用于PE/PB百分位计算
        basic_history = source.get_daily_basic_history(code, days=days)
        basic_map = {}
        if basic_history:
            for r in basic_history:
                # 强制 str + 取数字部分,适配各种pandas返回类型(int/str/numpy.int64)
                d_raw = r.get("trade_date")
                if d_raw is None:
                    continue
                d_str = str(d_raw).strip()
                # 去除可能的 .0 后缀(numpy float转str时会出现)
                if d_str.endswith(".0"):
                    d_str = d_str[:-2]
                basic_map[d_str] = r

        # 调试日志
        if basic_history:
            sample_basic = next(iter(basic_history), {})
            logger.debug(f"  📊 {code} basic_history共{len(basic_history)}条, 示例日期: {sample_basic.get('trade_date')!r}")
        if kline:
            sample_kline = kline[0]
            logger.debug(f"  📊 {code} kline共{len(kline)}条, 示例日期: {sample_kline.get('trade_date')!r}")

        # 同时拉取最新daily_basic(单点),作为最新一天的兜底
        latest_basic = source.get_daily_basic(code)

        records = []
        for row in kline:
            vol = safe_float(row.get("vol"), None)
            amt = safe_float(row.get("amount"), None)
            d_raw = row.get("trade_date")
            trade_date = str(d_raw).strip() if d_raw is not None else ""
            if trade_date.endswith(".0"):
                trade_date = trade_date[:-2]

            rec = {
                "date": trade_date,
                "open": safe_float(row.get("open"), None),
                "high": safe_float(row.get("high"), None),
                "low": safe_float(row.get("low"), None),
                "close": safe_float(row.get("close"), None),
                "volume": vol * 100 if vol is not None else None,
                "amount": amt * 1000 if amt is not None else None,
                "pctChg": safe_float(row.get("pct_chg"), None),
                "turn": None,
                "peTTM": None,
                "pbMRQ": None,
                "psTTM": None,
                "pcfNcfTTM": None,
            }

            basic_row = basic_map.get(trade_date)
            if basic_row:
                rec["turn"] = safe_float(basic_row.get("turnover_rate"), None)
                rec["peTTM"] = safe_float(basic_row.get("pe_ttm"), None)
                rec["pbMRQ"] = safe_float(basic_row.get("pb"), None)
                rec["psTTM"] = safe_float(basic_row.get("ps_ttm"), None)

            records.append(rec)

        # 最新一天兜底: 如果末尾记录的peTTM还是空,用latest_basic填
        if records and latest_basic:
            last_rec = records[-1]
            if last_rec["peTTM"] is None:
                last_rec["peTTM"] = safe_float(latest_basic.get("pe_ttm"), None)
            if last_rec["pbMRQ"] is None:
                last_rec["pbMRQ"] = safe_float(latest_basic.get("pb"), None)
            if last_rec["psTTM"] is None:
                last_rec["psTTM"] = safe_float(latest_basic.get("ps_ttm"), None)
            if last_rec["turn"] is None:
                last_rec["turn"] = safe_float(latest_basic.get("turnover_rate"), None)

        matched = sum(1 for r in records if r["peTTM"] is not None)
        logger.info(f"  ✅ {code} K线{len(records)}条, 估值匹配{matched}条")
        return records
    except Exception as e:
        logger.warning(f"  ⚠️ {code} K线获取失败: {str(e)[:120]}")
        return None


# ============ 个股资金流 (MR3: 删除东财兜底, 仅走 Tushare) ============

def get_stock_moneyflow(source: Optional[TushareSource], code: str) -> Optional[Dict[str, Any]]:
    """个股资金流(主力净流入汇总), 替代原东财 get_em_money_flow 的角色。

    【MR3 减法】彻底移除东财兜底分支, 资金流只走 Tushare(get_moneyflow_summary)。
    source 为空 / Tushare 无权限或取不到时, 直接返回 None —— 由上游按 P0 标"待验证"处理,
    不再 fallback 东财、不臆造数据。

    返回结构同 TushareSource.get_moneyflow_summary:
      {main_inflow_today, main_inflow_today_ts, main_inflow_5d, main_inflow_10d,
       latest_trade_date, buy_elg_amount, sell_elg_amount, buy_lg_amount, sell_lg_amount}
    """
    if source is None:
        return None
    return source.get_moneyflow_summary(code)
