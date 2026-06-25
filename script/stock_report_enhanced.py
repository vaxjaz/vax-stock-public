#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票每日汇总脚本 - 增强版(Tushare 2000积分专业版)
=====================================================

【数据源架构】
- 新浪财经    : 实时行情 + 大盘指数
- 东方财富    : 板块涨跌幅 + 大盘涨跌家数(无替代方案,保留)
- Tushare Pro : 历史K线 + 估值 + 财务 + 资金流 + 业绩预告 + 股东户数 + 北向资金

【核心数据维度】
1. 行情/均线: MA5/10/20/60 + 趋势判断 + 量比 + 振幅
2. 区间位置: 20日位置 + 52周位置 + 周期涨幅(5d/20d/YTD)
3. 估值: PE/PB/PS + 1年历史百分位(关键!)
4. 技术指标: MACD + RSI
5. 资金流向: 主力净流入(今日/5日/10日) + 4档明细(特大单/大单/中单/小单)
6. 财务: ROE + 毛利率 + 净利率 + 净利同比 + 单季同比 + 资产负债率
7. 业绩预告: 类型(预增/预减/扭亏) + 净利变动幅度 + 原因
8. 股东户数: 季度变化(筹码集中度)
9. 概念标签: 手动 + Tushare自动合并
10. 板块赛道: 强弱榜 + 主力净流入

【依赖】
    pip install requests tushare pandas

【配置 - v2 双源单职责架构 (2026-06-13)】
    watchlist.json: 观察池+赛道列表 (VPS 唯一标的源,所有标的不分持仓/观察)
    secrets.json:   tushare_token 等敏感配置 (chmod 600, 不上传 Claude project)

【架构说明】
    持仓真相由 Claude 端本地的 holdings.json 维护,VPS 不存
    持仓股的 code 必须也存在于 watchlist.json,否则当日报告无指标
    Claude 会在每次分析前自动校验持仓股是否在 VPS 报告中
"""

import html
import json
import logging
import math
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

# ==================== 配置区域 ====================

# 持仓格式: code -> (名称, 成本价, 持仓股数)  股数可选,填None表示不算
# ==================== 配置加载 ====================

# 默认 watchlist (仅在 watchlist.json 完全缺失时兜底使用)
_DEFAULT_WATCHLIST = {
    "601138": "工业富联",
    "600276": "恒瑞医药",
    "600900": "长江电力",
    "002463": "沪电股份",
}

_DEFAULT_STOCK_CONCEPTS = {
    "601138": ["AI算力", "AI服务器", "PCB", "工业互联网"],
    "600276": ["医药", "创新药", "化学制药"],
    "600900": ["水电", "高股息", "防御"],
    "002463": ["AI算力", "PCB", "服务器"],
}

_DEFAULT_HOT_SECTORS = [
    "AI算力", "人形机器人", "光模块", "半导体", "存储",
    "PCB", "液冷", "特高压", "创新药", "新能源车", "光伏",
    "商业航天", "稳定币", "数字货币", "稀土", "煤炭",
]


def _load_secrets():
    """从 secrets.json 加载敏感配置;失败则尝试环境变量;再失败返回默认空值。

    secrets.json 应与本脚本在同一目录,建议 chmod 600,绝对不上传 Claude project 或 git。
    支持字段: tushare_token / tushare_enabled / auto_concept_sync / cleanup_keep_days
    """
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.json")
    default_secrets = {
        "tushare_token": None,
        "tushare_enabled": False,
        "auto_concept_sync": False,
        "cleanup_keep_days": 7,
    }

    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                secrets = json.load(f)
            # 移除 _说明 等下划线开头的元字段
            secrets = {k: v for k, v in secrets.items() if not k.startswith("_")}
            merged = {**default_secrets, **secrets}
            # 不打印 token,防止 cron.log 泄露
            has_token = bool(merged.get("tushare_token"))
            print(f"✅ 已从 secrets.json 加载敏感配置 (token: {'已配置' if has_token else '缺失'})")
            return merged
        except Exception as e:
            print(f"⚠️ 加载 secrets.json 失败({e}),fallback 环境变量")

    # Fallback 1: 环境变量
    env_token = os.getenv("TUSHARE_TOKEN")
    if env_token:
        print(f"✅ 从环境变量 TUSHARE_TOKEN 加载 token")
        return {
            "tushare_token": env_token,
            "tushare_enabled": True,
            "auto_concept_sync": True,
            "cleanup_keep_days": int(os.getenv("CLEANUP_KEEP_DAYS", "7")),
        }

    # Fallback 2: 全部为空(tushare 数据将不可用)
    print("⚠️ 未找到 secrets.json 或 TUSHARE_TOKEN 环境变量,tushare 数据将不可用")
    return default_secrets


def _load_watchlist_config():
    """从 watchlist.json 加载观察池配置。

    架构 v2 (2026-06-13): VPS 只管 watchlist,不存持仓真相。
    所有需要每日跑指标的标的(包括用户的持仓股 code)都在此文件。
    持仓的 cost/shares 由 Claude 端 holdings.json 维护,本脚本不读取也不需要。
    """
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")

    # 迁移期兼容: watchlist.json 不存在时回退老的 portfolio.json
    if not os.path.exists(config_path):
        legacy_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")
        if os.path.exists(legacy_path):
            print(f"⚠️ 未找到 watchlist.json,回退使用旧的 portfolio.json (请尽快迁移到新架构)")
            config_path = legacy_path
        else:
            print(f"⚠️ watchlist.json 和 portfolio.json 均不存在,使用默认配置")
            return _DEFAULT_WATCHLIST, _DEFAULT_STOCK_CONCEPTS, _DEFAULT_HOT_SECTORS

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        # 解析 watchlist: { code: {name, concepts} } → { code: name }
        watchlist = {}
        concepts_map = {}
        for code, info in (cfg.get("watchlist") or {}).items():
            watchlist[code] = info.get("name", "")
            if info.get("concepts"):
                concepts_map[code] = info["concepts"]

        # 热门赛道
        hot_sectors = cfg.get("hot_sectors") or _DEFAULT_HOT_SECTORS

        # 校验:至少要有一个标的
        if not watchlist:
            print(f"⚠️ {os.path.basename(config_path)} 的 watchlist 字段为空,使用默认配置")
            return _DEFAULT_WATCHLIST, _DEFAULT_STOCK_CONCEPTS, _DEFAULT_HOT_SECTORS

        # 兼容性检查: 如果 watchlist.json 里还残留旧的 holdings 字段,警告但忽略
        if cfg.get("holdings"):
            print(f"⚠️ {os.path.basename(config_path)} 中残留 holdings 字段"
                  f"({len(cfg.get('holdings', {}))}只),按 v2 架构应删除"
                  f"(持仓由本地 holdings.json 维护)。本次忽略此字段。")

        # 兼容性检查: 如果 watchlist.json 里还有 data_sources 字段,警告(应该拆到 secrets.json)
        if cfg.get("data_sources"):
            print(f"⚠️ {os.path.basename(config_path)} 中残留 data_sources 字段,"
                  f"按 v2 架构应拆到 secrets.json。token 等敏感配置不应上传 Claude project。")

        print(f"✅ 已从 {os.path.basename(config_path)} 加载: 观察{len(watchlist)}只 / 赛道{len(hot_sectors)}个")
        return watchlist, concepts_map, hot_sectors
    except Exception as e:
        print(f"⚠️ 加载 {os.path.basename(config_path)} 失败({e}),使用默认配置")
        return _DEFAULT_WATCHLIST, _DEFAULT_STOCK_CONCEPTS, _DEFAULT_HOT_SECTORS


# ==================== 全局变量 ====================

# v2 架构: HOLDINGS 永远是空字典(持仓由 Claude 端 holdings.json 维护,VPS 不存)
# 保留此变量名是为兼容下游代码 (L2344/L2363/L2392 等 HOLDINGS.items()/.keys() 调用)
HOLDINGS: Dict[str, Tuple[str, Optional[float], Optional[int]]] = {}

WATCHLIST, STOCK_CONCEPTS, HOT_SECTORS_FOCUS = _load_watchlist_config()
DATA_SOURCES_CONFIG = _load_secrets()


# ==================== 初始化外部数据源(Tushare) ====================
TUSHARE = None
try:
    if DATA_SOURCES_CONFIG.get("tushare_enabled") and DATA_SOURCES_CONFIG.get("tushare_token"):
        from tushare_source import init_tushare
        TUSHARE = init_tushare(DATA_SOURCES_CONFIG["tushare_token"])
        if not TUSHARE.enabled:
            TUSHARE = None
except ImportError:
    print("ℹ️ tushare_source.py 模块未找到,跳过Tushare集成")
except Exception as e:
    print(f"⚠️ Tushare初始化异常: {e}")
    TUSHARE = None

# 东方财富板块代码映射(板块名 -> 板块代码,部分常用板块)
EM_SECTOR_CODES = {
    "AI算力": "BK1095",
    "人形机器人": "BK1167",
    "光模块": "BK1077",
    "半导体": "BK1036",
    "存储芯片": "BK1107",
    "PCB": "BK0489",
    "液冷": "BK1175",
    "特高压": "BK0917",
    "创新药": "BK0727",
    "新能源车": "BK1029",
    "光伏": "BK1031",
    "商业航天": "BK1158",
    "稀土": "BK0578",
    "煤炭": "BK0437",
}

EMAIL_CONFIG = {
    "smtp_server": "smtp.qq.com",
    "smtp_port": 465,
    "sender_email": "506050341@qq.com",
    "sender_password": "byqezkdkezicbjdf",
    # 收件人支持三种写法:
    #   单个字符串:   "17743250029@163.com"
    #   列表(推荐):  ["17743250029@163.com", "another@qq.com"]
    #   逗号分隔串:   "17743250029@163.com, another@qq.com"
    "receiver_email": [
        "17743250029@163.com",
        "949809085@qq.com",
        # 在这里继续加邮箱,例如:
        # "another@qq.com",
        # "third@gmail.com",
    ],
    # 抄送(所有人都能看到名单),不需要就留空列表
    "cc_email": [],
    # 密送(收件人看不到彼此),不需要就留空列表
    "bcc_email": [],
}

ALERT_RULES = {
    "price_change_pct": 3.0,
    "amplitude_pct": 5.0,
    "volume_ratio": 1.8,
    "position_high_pct": 85.0,
    "position_low_pct": 15.0,
    "main_inflow_yi": 1.0,        # 主力净流入超过1亿提示
    "main_outflow_yi": -1.0,      # 主力净流出超过1亿提示
}

HISTORY_DAYS = 250  # 扩展到一年,以便算52周高低和3年估值百分位
REQUEST_SLEEP_SECONDS = 0.25

INDEX_LIST = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000688", "科创50"),
    ("sz399300", "沪深300"),
]

SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
}

EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==================== 基础工具 ====================

def safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None or value == "" or value == "-":
            return default
        v = float(value)
        if math.isnan(v):
            return default
        return v
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "" or value == "-":
            return default
        return int(float(value))
    except Exception:
        return default


def fmt_num(value: Optional[float], digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}{suffix}"


def fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "-"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def fmt_amount_yi(amount: Optional[float]) -> str:
    if amount is None:
        return "-"
    return f"{amount / 100000000:.2f}亿"


def code_to_sina(code: str) -> str:
    if code.startswith(("sh", "sz")):
        return code
    prefix = "sh" if code.startswith(("6", "9")) else "sz"
    return f"{prefix}{code}"


def code_to_eastmoney(code: str) -> str:
    """东方财富用1.前缀代表沪市,0.前缀代表深市"""
    if code.startswith(("6", "9")):
        return f"1.{code}"
    return f"0.{code}"


# ==================== 东方财富数据 ====================

# 东财备用域名(VPS网络偶尔到主域名不稳)
EM_HOSTS = [
    "https://push2.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://20.push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
]


def _em_get(path: str, params: Dict[str, Any], timeout: int = 8, retries: int = 3) -> Optional[Dict[str, Any]]:
    """东财通用GET,自动切换主备域名 + 重试 + 容忍非JSON"""
    last_err = None
    for attempt in range(retries):
        host = EM_HOSTS[attempt % len(EM_HOSTS)]
        url = host + path
        try:
            r = requests.get(url, params=params, headers=EM_HEADERS, timeout=timeout)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}"
                continue
            text = r.text.strip()
            if not text or not text.startswith("{"):
                last_err = f"非JSON响应({len(text)}字节)"
                time.sleep(0.5)
                continue
            return r.json()
        except requests.Timeout:
            last_err = "timeout"
            time.sleep(0.5 + attempt)
        except Exception as e:
            last_err = str(e)[:80]
            time.sleep(0.5)
    logger.debug(f"  ⚠️ 东财调用失败({path}): {last_err}")
    return None


def get_em_money_flow(code: str) -> Optional[Dict[str, Any]]:
    """获取个股资金流向(今日+5日+10日) - 东财兜底
    Tushare 2000+分时优先用 TUSHARE.get_moneyflow_summary;否则用本函数。
    """
    em_code = code_to_eastmoney(code)
    result = {
        "main_inflow_today": None, "main_inflow_today_pct": None,
        "super_large_inflow": None, "large_inflow": None,
        "medium_inflow": None, "small_inflow": None,
        "main_inflow_5d": None, "main_inflow_10d": None,
    }

    # 主接口
    params = {
        "secid": em_code,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fltt": "2", "invt": "2",
        "fields": "f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f164,f166,f168,f170,f172,f174",
    }
    rj = _em_get("/api/qt/stock/get", params, timeout=8, retries=2)
    if rj:
        d = rj.get("data") or {}
        for src, dst in [("f62", "main_inflow_today"), ("f184", "main_inflow_today_pct"),
                         ("f66", "super_large_inflow"), ("f72", "large_inflow"),
                         ("f78", "medium_inflow"), ("f84", "small_inflow"),
                         ("f164", "main_inflow_5d"), ("f174", "main_inflow_10d")]:
            v = safe_float(d.get(src), None)
            if v is not None and v != 0:
                result[dst] = v

    # Fallback 日线接口
    need_fallback = (result["main_inflow_today"] is None or
                     result["main_inflow_5d"] is None or
                     (result["main_inflow_today"] is not None and abs(result["main_inflow_today"]) < 100))

    if need_fallback:
        p2 = {
            "secid": em_code,
            "lmt": "10", "klt": "101",
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        }
        # 这个接口在 push2his.eastmoney.com,直接调用一次
        try:
            r2 = requests.get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                              params=p2, headers=EM_HEADERS, timeout=8)
            d2 = (r2.json() or {}).get("data") or {}
            klines = d2.get("klines") or []
            if klines:
                today_row = klines[-1].split(",")
                if len(today_row) >= 6:
                    today_val = safe_float(today_row[1], None)
                    if today_val is not None and (result["main_inflow_today"] is None or abs(result["main_inflow_today"]) < 100):
                        result["main_inflow_today"] = today_val
                if len(klines) >= 5 and result["main_inflow_5d"] is None:
                    total = 0.0
                    valid = 0
                    for row in klines[-5:]:
                        parts = row.split(",")
                        if len(parts) >= 2:
                            v = safe_float(parts[1], None)
                            if v is not None:
                                total += v
                                valid += 1
                    if valid >= 3:
                        result["main_inflow_5d"] = total
                if len(klines) >= 10 and result["main_inflow_10d"] is None:
                    total = 0.0
                    valid = 0
                    for row in klines[-10:]:
                        parts = row.split(",")
                        if len(parts) >= 2:
                            v = safe_float(parts[1], None)
                            if v is not None:
                                total += v
                                valid += 1
                    if valid >= 7:
                        result["main_inflow_10d"] = total
        except Exception as e:
            logger.debug(f"  ⚠️ {code} 备用资金流接口失败: {str(e)[:80]}")

    if all(v is None for v in result.values()):
        return None
    return result


def get_em_sector_ranking(direction: str = "desc", top_n: int = 10) -> List[Dict[str, Any]]:
    """获取板块涨跌幅排行
    A股行业板块总共~90个,一次拉全后本地排序,避免接口反向排序不可靠的问题。
    direction=desc取涨幅前N,asc取跌幅前N。
    """
    try:
        params = {
            "pn": 1,
            "pz": 200,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fs": "m:90+t:2",
            "fields": "f3,f12,f14,f62,f104,f105,f128,f136",
        }
        rj = _em_get("/api/qt/clist/get", params, timeout=10, retries=3)
        if not rj:
            return []

        diff = (rj.get("data") or {}).get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())

        all_sectors = []
        for it in diff:
            chg = safe_float(it.get("f3"), None)
            if chg is None:
                continue
            all_sectors.append({
                "code": it.get("f12"),
                "name": it.get("f14"),
                "change_pct": chg,
                "main_inflow": safe_float(it.get("f62"), None),
                "up_count": safe_int(it.get("f104")),
                "down_count": safe_int(it.get("f105")),
                "leader_name": it.get("f128"),
                "leader_change_pct": safe_float(it.get("f136"), None),
            })

        if direction == "desc":
            all_sectors.sort(key=lambda x: x["change_pct"], reverse=True)
        else:
            all_sectors.sort(key=lambda x: x["change_pct"])

        return all_sectors[:top_n]
    except Exception as e:
        logger.warning(f"  ⚠️ 板块排行获取失败: {str(e)[:120]}")
        return []


def get_em_market_overview() -> Dict[str, Any]:
    """获取大盘综合数据:涨跌家数、涨跌停统计
    东方财富对未授权请求单页pz最多约80,所以即使设大也只返回少量。
    策略: 强制分页拉取,直到没有新数据或达到 total。
    """
    try:
        all_diff = []
        page_size = 80
        max_pages = 100
        total_from_api = None
        consecutive_failures = 0

        for page in range(1, max_pages + 1):
            params = {
                "pn": page,
                "pz": page_size,
                "po": 1, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2, "invt": 2,
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f3,f12",
            }
            rj = _em_get("/api/qt/clist/get", params, timeout=8, retries=2)
            if not rj:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.warning(f"  ⚠️ 大盘涨跌家数: 连续3次失败,提前结束(已获取{len(all_diff)}只)")
                    break
                continue
            consecutive_failures = 0

            data = rj.get("data") or {}
            diff = data.get("diff") or []
            if isinstance(diff, dict):
                diff = list(diff.values())

            if page == 1 and data.get("total"):
                total_from_api = safe_int(data.get("total"), 0)

            if not diff:
                break

            all_diff.extend(diff)

            if total_from_api and len(all_diff) >= total_from_api:
                break
            if page > 1 and len(diff) < page_size:
                break

        if not all_diff:
            logger.warning("  ⚠️ 大盘综合数据为空")
            return {}

        seen_codes = set()
        unique = []
        for x in all_diff:
            c = x.get("f12")
            if c and c not in seen_codes:
                seen_codes.add(c)
                unique.append(x)

        up = down = flat = limit_up = limit_down = 0
        for x in unique:
            chg = safe_float(x.get("f3"), None)
            if chg is None:
                continue
            if chg >= 9.8:
                limit_up += 1
                up += 1
            elif chg <= -9.8:
                limit_down += 1
                down += 1
            elif chg > 0:
                up += 1
            elif chg < 0:
                down += 1
            else:
                flat += 1

        total = up + down + flat
        logger.info(f"  ✅ 大盘涨跌统计: 总{total}(接口total={total_from_api}) 涨{up} 跌{down} 平{flat} 涨停{limit_up} 跌停{limit_down}")

        return {
            "up_count": up,
            "down_count": down,
            "flat_count": flat,
            "limit_up_count": limit_up,
            "limit_down_count": limit_down,
            "total": total,
            "api_total": total_from_api,
        }
    except Exception as e:
        logger.warning(f"  ⚠️ 大盘综合数据获取失败: {str(e)[:120]}")
        return {}


# ==================== 新浪实时数据(保持原样) ====================

def get_sina_realtime(code: str, expected_name: str = "") -> Optional[Dict[str, Any]]:
    try:
        symbol = code_to_sina(code)
        url = f"https://hq.sinajs.cn/list={symbol}"
        response = requests.get(url, headers=SINA_HEADERS, timeout=8)
        response.encoding = "gbk"
        text = response.text
        if '"' not in text:
            return None

        data_str = text.split('"')[1]
        fields = data_str.split(",")
        if len(fields) < 32 or not fields[0]:
            return None

        open_price = safe_float(fields[1])
        pre_close = safe_float(fields[2])
        current_price = safe_float(fields[3])
        high = safe_float(fields[4])
        low = safe_float(fields[5])

        if not current_price or current_price <= 0:
            current_price = pre_close

        change_amount = current_price - pre_close if current_price is not None and pre_close else 0.0
        change_pct = change_amount / pre_close * 100 if pre_close else 0.0
        amplitude_pct = (high - low) / pre_close * 100 if high and low and pre_close else 0.0

        return {
            "code": code,
            "symbol": symbol,
            "name": fields[0] or expected_name,
            "open": open_price,
            "pre_close": pre_close,
            "price": current_price,
            "high": high,
            "low": low,
            "volume": safe_int(fields[8]),
            "amount": safe_float(fields[9]),
            "change_amount": change_amount,
            "change_pct": change_pct,
            "amplitude_pct": amplitude_pct,
            "trade_date": fields[30] if len(fields) > 30 else "",
            "trade_time": fields[31] if len(fields) > 31 else "",
            "source": "sina",
        }
    except Exception as e:
        logger.warning(f"  ⚠️ {code} 新浪实时数据获取失败: {str(e)[:80]}")
        return None


def get_sina_index(symbol: str, name: str) -> Optional[Dict[str, Any]]:
    try:
        url = f"https://hq.sinajs.cn/list=s_{symbol}"
        response = requests.get(url, headers=SINA_HEADERS, timeout=8)
        response.encoding = "gbk"
        text = response.text
        if '"' not in text:
            return None

        data_str = text.split('"')[1]
        fields = data_str.split(",")
        if len(fields) < 4:
            return None

        return {
            "symbol": symbol,
            "name": name,
            "price": safe_float(fields[1]),
            "change_amount": safe_float(fields[2]),
            "change_pct": safe_float(fields[3]),
            "volume": safe_float(fields[4]) if len(fields) > 4 else None,
            "amount": safe_float(fields[5]) if len(fields) > 5 else None,
            "source": "sina",
        }
    except Exception as e:
        logger.warning(f"  ⚠️ {name} 指数获取失败: {str(e)[:80]}")
        return None


# ==================== 历史K线(纯Tushare) ====================

def get_history_kline(code: str, days: int = HISTORY_DAYS) -> Optional[List[Dict[str, Any]]]:
    """获取历史K线 + 估值,完全使用Tushare数据源。
    返回字段统一: date, open, high, low, close, volume, amount, pctChg, turn, peTTM, pbMRQ, psTTM, pcfNcfTTM

    数据合并策略:
    1. daily 接口: 行情(开高低收量额)
    2. daily_basic 接口: 估值(PE/PB/PS/换手)
    3. 按 trade_date 精确匹配(全部强制 str 化避免类型问题)
    4. 最新一天若匹配不到,再用 daily_basic 单点接口兜底
    """
    if TUSHARE is None:
        logger.warning(f"  ⚠️ {code} Tushare未启用,无法获取历史数据")
        return None

    try:
        kline = TUSHARE.get_daily_kline(code, days=days)
        if not kline:
            return None

        # 合并历史估值数据(daily_basic_history),用于PE/PB百分位计算
        basic_history = TUSHARE.get_daily_basic_history(code, days=days)
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
        latest_basic = TUSHARE.get_daily_basic(code)

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


# ==================== 技术指标计算 ====================

def calc_ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(alpha * v + (1 - alpha) * ema[-1])
    return ema


def calc_macd(closes: List[float], short: int = 12, long: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
    if len(closes) < long + signal:
        return {"dif": None, "dea": None, "macd": None}
    ema_short = calc_ema(closes, short)
    ema_long = calc_ema(closes, long)
    dif = [a - b for a, b in zip(ema_short, ema_long)]
    dea = calc_ema(dif, signal)
    macd = [(d - de) * 2 for d, de in zip(dif, dea)]
    return {
        "dif": round(dif[-1], 3),
        "dea": round(dea[-1], 3),
        "macd": round(macd[-1], 3),
    }


def calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def calc_pe_pb_percentile(history: List[Dict[str, Any]], current_pe: Optional[float], current_pb: Optional[float]) -> Dict[str, Optional[float]]:
    """计算PE/PB在历史中的百分位(用过去250个交易日,约1年)"""
    if not history or len(history) < 60:
        return {"pe_percentile": None, "pb_percentile": None}

    pe_values = [safe_float(x.get("peTTM"), None) for x in history]
    pe_values = [x for x in pe_values if x is not None and x > 0]
    pb_values = [safe_float(x.get("pbMRQ"), None) for x in history]
    pb_values = [x for x in pb_values if x is not None and x > 0]

    def percentile(val, arr):
        if not val or not arr:
            return None
        sorted_arr = sorted(arr)
        below = sum(1 for x in sorted_arr if x < val)
        return round(below / len(sorted_arr) * 100, 1)

    return {
        "pe_percentile": percentile(current_pe, pe_values),
        "pb_percentile": percentile(current_pb, pb_values),
    }


# ==================== 量化新增指标(v1.0 2026-06-09) ====================

def calc_turnover_zscore(history: Optional[List[Dict[str, Any]]], current_turn: Optional[float]) -> Optional[float]:
    """换手率 Z-score：今日换手率相对过去60日历史均值的标准差倍数。
    Z > 2.0  = 异常放量，大量筹码易手，高位警惕派发
    Z < -1.0 = 缩量，结合价格判断方向
    用Z-score替代绝对值，消除不同股票换手率基准差异。
    """
    if not history or current_turn is None:
        return None
    turns = []
    for x in history[-60:]:
        v = x.get("turn")
        if v is not None:
            try:
                f = float(v)
                if f > 0:
                    turns.append(f)
            except (ValueError, TypeError):
                pass
    if len(turns) < 20:
        return None
    mean = sum(turns) / len(turns)
    variance = sum((t - mean) ** 2 for t in turns) / len(turns)
    std = math.sqrt(variance)
    if std < 1e-6:
        return 0.0
    return round((current_turn - mean) / std, 2)


def calc_inflow_slope(inflow_5d: Optional[float], inflow_10d: Optional[float]) -> Optional[float]:
    """资金流动量斜率 = 近5日日均流入 - 近10日日均流入（元/日）。
    正值 = 资金流在改善（近期流入速度 > 长期均速），比10日累计早1-3天捕捉转折。
    负值 = 资金流在恶化。
    """
    if inflow_5d is None or inflow_10d is None:
        return None
    return round(inflow_5d / 5 - inflow_10d / 10, 2)


# 全局市场环境（v1.1新增）
# 由 collect_payload 在拉取大盘数据后设置，build_stock_item 调用 calc_right_side_score 时使用
_CURRENT_MARKET_REGIME = "momentum"


def detect_market_regime(indices: List[Dict[str, Any]], market_overview: Dict[str, Any]) -> str:
    """
    市场环境自动分类器 v1.2（含平滑逻辑）

    v1.2变化: 单日判断噪音大(创业板单日跑赢2%就切momentum),
    改为状态平滑——momentum/value互切需连续2日同向原始信号;
    panic安全优先,单日立即生效;panic解除也需连续2日非panic。

    - "momentum": 动量市,创业板/科创跑赢主板>=2%。反转因子失效。
    - "value":    价值市,主板跑赢。反转因子启用。
    - "panic":    恐慌市,跌停>50。优质低位股豁免,其余观望。
    """
    # ---- 第一步: 计算今日原始信号(与v1.1逻辑相同) ----
    limit_down = (market_overview or {}).get("limit_down_count", 0)
    if limit_down and limit_down > 50:
        raw = "panic"
    else:
        chg_map = {}
        for idx in indices or []:
            name = idx.get("name", "")
            chg = idx.get("change_pct")
            if chg is not None:
                chg_map[name] = chg
        sh = chg_map.get("上证指数", 0)
        cyb = chg_map.get("创业板指", 0)
        kc50 = chg_map.get("科创50", 0)
        growth_avg = (cyb + kc50) / 2 if (cyb or kc50) else 0
        if growth_avg - sh >= 2.0:
            raw = "momentum"
        elif sh - growth_avg >= 1.0:
            raw = "value"
        else:
            raw = "momentum"  # 默认动量市(A股近年偏成长)

    # ---- 第二步: 状态平滑 ----
    state_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "regime_history.json")
    history = []
    current = "momentum"
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            history = state.get("raw_history", [])[-4:]  # 保留最近4条
            current = state.get("current_regime", "momentum")
    except Exception:
        pass

    today = datetime.now().strftime("%Y-%m-%d")
    # 防止同日重复运行污染历史: 同日只保留最后一次
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "raw": raw})

    # 切换规则
    if raw == "panic":
        new_regime = "panic"  # 恐慌单日立即生效(安全优先)
    elif current == "panic":
        # 恐慌解除: 需连续2日非panic
        recent = [h["raw"] for h in history[-2:]]
        if len(recent) >= 2 and all(r != "panic" for r in recent):
            new_regime = raw
        else:
            new_regime = "panic"
    elif raw != current:
        # momentum<->value互切: 需连续2日同向
        recent = [h["raw"] for h in history[-2:]]
        if len(recent) >= 2 and all(r == raw for r in recent):
            new_regime = raw
        else:
            new_regime = current  # 维持原状态,防单日噪音
    else:
        new_regime = current

    # 保存状态
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "current_regime": new_regime,
                "raw_history": history,
                "last_updated": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"regime状态保存失败: {e}")

    if new_regime != raw:
        logger.info(f"  📊 regime平滑: 今日原始信号={raw}, 维持={new_regime}(待连续确认)")

    return new_regime


def calc_right_side_score(
        price: Optional[float],
        ma5: Optional[float],
        volume_ratio_5d: Optional[float],
        change_pct: Optional[float],
        turnover_zscore: Optional[float],
        inflow_slope: Optional[float],  # v1.1: 保留参数但不再使用
        inflow_10d: Optional[float],
        holder_change_pct: Optional[float],
        position_20d_pct: Optional[float],  # 价值市/恐慌豁免时使用
        np_yoy: Optional[float],
        pe_percentile_1y: Optional[float] = None,
        market_regime: str = "momentum",  # "momentum" / "value" / "panic"
        circ_mv_yi: Optional[float] = None,  # v1.2新增: 流通市值(亿),用于资金流归一化
) -> Dict[str, Any]:
    """右侧确认信号综合评分 v1.2

    v1.2 变化（2026-06-12）:
      ① 资金流市值归一化分档: 10日净流入/流通市值,大小盘公平比较
         (v1.1的二值逻辑作为无市值数据时的回退)
      ② 恐慌市优质豁免: 业绩>20%+PE历史<20%+20日低位<30% 三条件同时满足时
         恐慌惩罚归零(解决"恐慌底系统性回避"的设计矛盾)
      ⚠️ 分档阈值为逻辑设定,待9月回测验证后再校准

    评分阈值:
      >= 3.5 强买入信号 | >= 2.0 可考虑介入 | >= 0.5 观察等待 | < 0.5 回避
    """
    score = 0.0
    signals = []

    # ① 核心因子1: 10日主力净流入（v1.4 回测校准分档）
    # 【校准 2026-06-19】阈值由 zz800(1080只)回测确定, 替换旧拍脑袋值 0.5%/0.1%。
    #   依据: inflow_10d_ratio 10分位收益, 区分力集中在最高档(>1.28%收益跳升至1.0%);
    #         0.13%~1.28%温和(0.56-0.60%); 0~0.13%各档差异小且全为正。
    #   改为加分制: 回测显示净流出档未来收益仍为正(bin0=0.51%), 故流出不扣分(旧版误扣-1.0)。
    #   注: 该因子全市场多空仅+1.49%(非最强), 净利同比+4.70%才是最强; 但大盘股样本仍有效。
    if inflow_10d is not None:
        if circ_mv_yi and circ_mv_yi > 0:
            # 归一化: 流入占流通市值百分比
            ratio_pct = inflow_10d / (circ_mv_yi * 1e8) * 100
            if ratio_pct >= 1.28:
                score += 1.5
                signals.append(f"✅10日强流入+{inflow_10d/1e8:.2f}亿(占市值{ratio_pct:.2f}%)")
            elif ratio_pct >= 0.13:
                score += 1.0
                signals.append(f"✅10日中等流入+{inflow_10d/1e8:.2f}亿(占{ratio_pct:.2f}%)")
            elif ratio_pct > 0:
                score += 0.5
                signals.append(f"➕10日弱流入+{inflow_10d/1e8:.2f}亿(占{ratio_pct:.2f}%)")
            else:
                # 净流出: 回测显示流出档收益仍为正, 不扣分, 仅标注
                signals.append(f"➖10日净流出{inflow_10d/1e8:+.2f}亿(占{ratio_pct:.2f}%,中性不扣分)")
        else:
            # 回退逻辑（无市值数据时, 无法归一化, 仅按方向给弱信号）
            if inflow_10d > 0:
                score += 0.5
                signals.append(f"➕10日主力净流入+{inflow_10d/1e8:.2f}亿(无市值数据,弱信号)")
            else:
                signals.append(f"➖10日资金流{inflow_10d/1e8:+.2f}亿(无市值数据,中性)")

    # ① 核心因子2: 净利同比（第2强因子,IC=0.0201）
    if np_yoy is not None:
        if np_yoy > 50:
            score += 1.5
            signals.append(f"✅业绩大幅增长 净利同比+{np_yoy:.0f}%")
        elif np_yoy > 20:
            score += 1.0
            signals.append(f"✅业绩高增长 净利同比+{np_yoy:.0f}%")
        elif np_yoy > 0:
            score += 0.3
            signals.append(f"➕业绩微增 净利同比+{np_yoy:.0f}%")
        elif np_yoy < -20:
            score -= 0.5
            signals.append(f"🚨业绩恶化 净利同比{np_yoy:.0f}%")

    # ① 核心因子3: 股东户数变化（ICIR最稳定2.77）
    if holder_change_pct is not None:
        if holder_change_pct < -2:
            score += 1.0
            signals.append(f"✅股东强集中{holder_change_pct:+.1f}%")
        elif holder_change_pct < 0:
            score += 0.5
            signals.append(f"⚠️股东轻微集中{holder_change_pct:+.1f}%")
        elif holder_change_pct > 10:
            score -= 0.5
            signals.append(f"🚨股东强分散{holder_change_pct:+.1f}%")
        else:
            signals.append(f"➖股东基本稳定{holder_change_pct:+.1f}%")

    # ② 辅助因子: MA5偏离度（v1.1方向反转,低于MA5是低吸机会）
    if price and ma5 and ma5 > 0:
        ma5_dev = (price - ma5) / ma5 * 100
        if ma5_dev < -3:
            score += 0.5
            signals.append(f"✅低于MA5 {ma5_dev:.1f}%(低吸机会)")
        elif ma5_dev > 5:
            signals.append(f"⚠️高于MA5 {ma5_dev:.1f}%(注意追高)")

    # ② 辅助因子: 换手异常
    if turnover_zscore is not None:
        if turnover_zscore > 2.0:
            score -= 1.0
            signals.append(f"🚨换手异常Z={turnover_zscore:.1f}(警惕派发)")

    # ③ 市场环境过滤（regime filter, v1.2含恐慌豁免）
    if market_regime == "value":
        if pe_percentile_1y is not None and pe_percentile_1y < 30:
            score += 0.5
            signals.append(f"✅PE历史低位{pe_percentile_1y:.0f}%(价值市)")
        if position_20d_pct is not None and position_20d_pct < 30:
            score += 0.5
            signals.append(f"✅20日低位{position_20d_pct:.0f}%(价值市)")
    elif market_regime == "panic":
        # v1.2: 优质低位股豁免恐慌惩罚
        is_quality_dip = (
                np_yoy is not None and np_yoy > 20
                and pe_percentile_1y is not None and pe_percentile_1y < 20
                and position_20d_pct is not None and position_20d_pct < 30
        )
        if is_quality_dip:
            signals.append("💎恐慌市优质低位(业绩+估值+位置三重确认),左侧关注")
        else:
            score -= 1.0
            signals.append("⚠️恐慌市,建议观望")
    # else: 动量市,反转因子不参与评分

    score = round(score, 1)

    if score >= 3.5:
        grade = "强买入信号"
    elif score >= 2.0:
        grade = "可考虑介入"
    elif score >= 0.5:
        grade = "观察等待"
    else:
        grade = "回避"

    return {"score": score, "signals": signals, "grade": grade}


# ==================== 指标计算(增强版) ====================

def calc_derived_metrics(
        realtime: Optional[Dict[str, Any]],
        history: Optional[List[Dict[str, Any]]],
        cost_price: Optional[float],
        shares: Optional[int] = None,
        money_flow: Optional[Dict[str, Any]] = None,
        quarterly: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "ma5": None, "ma10": None, "ma20": None, "ma60": None,
        "price_vs_ma5_pct": None, "price_vs_ma10_pct": None,
        "price_vs_ma20_pct": None, "price_vs_ma60_pct": None,
        "ma_trend": None,  # bullish/bearish/neutral
        "volume_ratio_5d": None, "volume_ratio_20d": None,
        "turnover_pct": None,
        "pe_ttm": None, "pb_mrq": None, "ps_ttm": None, "pcf_ncf_ttm": None,
        "pe_percentile_1y": None, "pb_percentile_1y": None,
        "range_20d_high": None, "range_20d_low": None, "position_20d_pct": None,
        "range_52w_high": None, "range_52w_low": None, "position_52w_pct": None,
        "recent_5d_change_pct": None, "recent_20d_change_pct": None, "ytd_change_pct": None,
        "macd_dif": None, "macd_dea": None, "macd_hist": None,
        "rsi_14": None,
        "pnl_pct": None, "pnl_amount": None,
        # 资金流向
        "main_inflow_today": None, "main_inflow_today_pct": None,
        "main_inflow_5d": None, "main_inflow_10d": None,
        # 量化新增指标(v1.0)
        "turnover_zscore": None,
        "inflow_slope": None,
        "right_side_score": None,
        "right_side_signals": [],
        "right_side_grade": None,
        # 业绩
        "revenue_yoy": None, "np_yoy": None, "roe_avg": None,
        "gross_margin": None, "report_date": None,
        "risk_level": "UNKNOWN", "alerts": [],
    }

    if not realtime:
        metrics["alerts"].append("实时行情获取失败")
        metrics["risk_level"] = "DATA_MISSING"
        return metrics

    price = realtime.get("price")
    if cost_price and price:
        metrics["pnl_pct"] = (price - cost_price) / cost_price * 100
        if shares:
            metrics["pnl_amount"] = (price - cost_price) * shares

    if history:
        closes = [safe_float(x.get("close"), None) for x in history]
        closes = [x for x in closes if x is not None]
        volumes = [safe_float(x.get("volume"), None) for x in history]
        volumes = [x for x in volumes if x is not None]
        highs = [safe_float(x.get("high"), None) for x in history]
        highs = [x for x in highs if x is not None]
        lows = [safe_float(x.get("low"), None) for x in history]
        lows = [x for x in lows if x is not None]

        def avg_last(n: int, arr: List[float]) -> Optional[float]:
            if len(arr) < n:
                return None
            return sum(arr[-n:]) / n

        metrics["ma5"] = avg_last(5, closes)
        metrics["ma10"] = avg_last(10, closes)
        metrics["ma20"] = avg_last(20, closes)
        metrics["ma60"] = avg_last(60, closes)

        for key in ["ma5", "ma10", "ma20", "ma60"]:
            ma = metrics[key]
            if ma and price:
                metrics[f"price_vs_{key}_pct"] = (price - ma) / ma * 100

        # 均线趋势判断
        if all(metrics[k] is not None for k in ["ma5", "ma10", "ma20", "ma60"]):
            if metrics["ma5"] > metrics["ma10"] > metrics["ma20"] > metrics["ma60"]:
                metrics["ma_trend"] = "强多头(多头排列)"
            elif metrics["ma5"] < metrics["ma10"] < metrics["ma20"] < metrics["ma60"]:
                metrics["ma_trend"] = "强空头(空头排列)"
            elif metrics["ma5"] > metrics["ma20"] and metrics["ma20"] > metrics["ma60"]:
                metrics["ma_trend"] = "弱多头"
            elif metrics["ma5"] < metrics["ma20"] and metrics["ma20"] < metrics["ma60"]:
                metrics["ma_trend"] = "弱空头"
            else:
                metrics["ma_trend"] = "震荡"

        avg_volume_5 = avg_last(5, volumes)
        avg_volume_20 = avg_last(20, volumes)
        if avg_volume_5 and realtime.get("volume"):
            metrics["volume_ratio_5d"] = realtime["volume"] / avg_volume_5
        if avg_volume_20 and realtime.get("volume"):
            metrics["volume_ratio_20d"] = realtime["volume"] / avg_volume_20

        # 20日区间
        if highs and lows:
            high_20 = max(highs[-20:])
            low_20 = min(lows[-20:])
            metrics["range_20d_high"] = high_20
            metrics["range_20d_low"] = low_20
            if high_20 > low_20 and price:
                metrics["position_20d_pct"] = (price - low_20) / (high_20 - low_20) * 100

        # 52周(250个交易日)区间
        if len(highs) >= 200:
            high_52w = max(highs[-250:])
            low_52w = min(lows[-250:])
            metrics["range_52w_high"] = high_52w
            metrics["range_52w_low"] = low_52w
            if high_52w > low_52w and price:
                metrics["position_52w_pct"] = (price - low_52w) / (high_52w - low_52w) * 100

        # 近期涨跌幅
        if len(closes) >= 6:
            metrics["recent_5d_change_pct"] = (closes[-1] - closes[-6]) / closes[-6] * 100 if closes[-6] else None
        if len(closes) >= 21:
            metrics["recent_20d_change_pct"] = (closes[-1] - closes[-21]) / closes[-21] * 100 if closes[-21] else None

        # YTD: 年初首个交易日收盘价
        if history:
            year_start = datetime.now().strftime("%Y-01")
            year_first_close = None
            for h in history:
                d = h.get("date", "")
                if d.startswith(year_start) or d.startswith(datetime.now().strftime("%Y-02")):
                    year_first_close = safe_float(h.get("close"), None)
                    if year_first_close:
                        break
            if year_first_close and price:
                metrics["ytd_change_pct"] = (price - year_first_close) / year_first_close * 100

        # MACD / RSI
        macd = calc_macd(closes)
        metrics["macd_dif"] = macd["dif"]
        metrics["macd_dea"] = macd["dea"]
        metrics["macd_hist"] = macd["macd"]
        metrics["rsi_14"] = calc_rsi(closes, 14)

        # 估值
        last = history[-1]
        metrics["turnover_pct"] = safe_float(last.get("turn"), None)
        metrics["pe_ttm"] = safe_float(last.get("peTTM"), None)
        metrics["pb_mrq"] = safe_float(last.get("pbMRQ"), None)
        metrics["ps_ttm"] = safe_float(last.get("psTTM"), None)
        metrics["pcf_ncf_ttm"] = safe_float(last.get("pcfNcfTTM"), None)

        # 估值历史百分位
        percentiles = calc_pe_pb_percentile(history, metrics["pe_ttm"], metrics["pb_mrq"])
        metrics["pe_percentile_1y"] = percentiles["pe_percentile"]
        metrics["pb_percentile_1y"] = percentiles["pb_percentile"]

    # 资金流向
    if money_flow:
        metrics["main_inflow_today"] = money_flow.get("main_inflow_today")
        metrics["main_inflow_today_pct"] = money_flow.get("main_inflow_today_pct")
        metrics["main_inflow_5d"] = money_flow.get("main_inflow_5d")
        metrics["main_inflow_10d"] = money_flow.get("main_inflow_10d")

    # 量化新增指标(v1.0) —— holder_change_pct 在 build_stock_item 层回填，此处先算无需户数的部分
    if history:
        metrics["turnover_zscore"] = calc_turnover_zscore(history, metrics.get("turnover_pct"))
    metrics["inflow_slope"] = calc_inflow_slope(
        metrics.get("main_inflow_5d"),
        metrics.get("main_inflow_10d"),
    )
    # right_side_score 先算一次（无户数版），build_stock_item 拿到 holder_change 后会重算
    _rss = calc_right_side_score(
        price=price,
        ma5=metrics.get("ma5"),
        volume_ratio_5d=metrics.get("volume_ratio_5d"),
        change_pct=realtime.get("change_pct") if realtime else None,
        turnover_zscore=metrics.get("turnover_zscore"),
        inflow_slope=metrics.get("inflow_slope"),
        inflow_10d=metrics.get("main_inflow_10d"),
        holder_change_pct=None,
        position_20d_pct=metrics.get("position_20d_pct"),
        np_yoy=metrics.get("np_yoy"),
        pe_percentile_1y=metrics.get("pe_percentile_1y"),
        market_regime="momentum",  # 默认动量市,build_stock_item 层会用真实regime重算
    )
    metrics["right_side_score"] = _rss["score"]
    metrics["right_side_signals"] = _rss["signals"]
    metrics["right_side_grade"] = _rss["grade"]

    # 业绩
    if quarterly:
        metrics["np_yoy"] = quarterly.get("np_yoy")
        metrics["roe_avg"] = quarterly.get("roe_avg")
        metrics["gross_margin"] = quarterly.get("gross_margin")
        metrics["report_date"] = quarterly.get("stat_date")

    # 警报
    alerts: List[str] = []
    if abs(realtime.get("change_pct") or 0) >= ALERT_RULES["price_change_pct"]:
        alerts.append(f"单日涨跌幅{fmt_pct(realtime.get('change_pct'))}")
    if (realtime.get("amplitude_pct") or 0) >= ALERT_RULES["amplitude_pct"]:
        alerts.append(f"日内振幅{fmt_num(realtime.get('amplitude_pct'), 2, '%')}")
    if metrics.get("volume_ratio_5d") and metrics["volume_ratio_5d"] >= ALERT_RULES["volume_ratio"]:
        alerts.append(f"放量{metrics['volume_ratio_5d']:.2f}倍(5日)")
    if metrics.get("position_20d_pct") is not None:
        if metrics["position_20d_pct"] >= ALERT_RULES["position_high_pct"]:
            alerts.append(f"接近20日高位({metrics['position_20d_pct']:.0f}%)")
        elif metrics["position_20d_pct"] <= ALERT_RULES["position_low_pct"]:
            alerts.append(f"接近20日低位({metrics['position_20d_pct']:.0f}%)")
    # 资金流向警报
    if metrics.get("main_inflow_today"):
        inflow_yi = metrics["main_inflow_today"] / 1e8
        if inflow_yi >= ALERT_RULES["main_inflow_yi"]:
            alerts.append(f"主力净流入{inflow_yi:.2f}亿")
        elif inflow_yi <= ALERT_RULES["main_outflow_yi"]:
            alerts.append(f"主力净流出{abs(inflow_yi):.2f}亿")
    # 估值历史位置警报
    if metrics.get("pe_percentile_1y") is not None:
        if metrics["pe_percentile_1y"] >= 90:
            alerts.append(f"PE历史高位({metrics['pe_percentile_1y']:.0f}%)")
        elif metrics["pe_percentile_1y"] <= 10:
            alerts.append(f"PE历史低位({metrics['pe_percentile_1y']:.0f}%)")
    # MACD金叉死叉提示
    if metrics.get("macd_hist") is not None:
        if metrics["macd_hist"] > 0 and metrics.get("macd_dif", 0) > metrics.get("macd_dea", 0):
            pass  # 多头不重复提示
        elif metrics["macd_hist"] < -0.5:
            alerts.append("MACD空头加速")
    # RSI 超买超卖
    if metrics.get("rsi_14"):
        if metrics["rsi_14"] >= 80:
            alerts.append(f"RSI超买({metrics['rsi_14']:.0f})")
        elif metrics["rsi_14"] <= 20:
            alerts.append(f"RSI超卖({metrics['rsi_14']:.0f})")
    # XD除息
    if realtime.get("name") and "XD" in realtime["name"]:
        alerts.append("今日除息XD")
    # 持仓盈亏
    if cost_price is not None and metrics.get("pnl_pct") is not None:
        alerts.append(f"持仓盈亏{fmt_pct(metrics['pnl_pct'])}")

    metrics["alerts"] = alerts
    if any("涨跌幅" in x or "振幅" in x or "放量" in x or "净流入" in x or "净流出" in x for x in alerts):
        metrics["risk_level"] = "HIGH_ATTENTION"
    elif alerts:
        metrics["risk_level"] = "WATCH"
    else:
        metrics["risk_level"] = "NORMAL"

    return metrics


# ==================== 个股汇总 ====================

def build_stock_item(group: str, code: str, name: str, cost: Optional[float], shares: Optional[int]) -> Dict[str, Any]:
    import concurrent.futures as _f

    has_ts = TUSHARE is not None and TUSHARE.points_level >= 2000
    use_concepts = (TUSHARE is not None
                    and DATA_SOURCES_CONFIG.get("auto_concept_sync", False))

    # ---- 并发拉取所有相互独立的数据源 ----
    # 原实现串行 8~9 次网络调用(冷缓存可达 90s 超时)。各调用彼此独立、无共享状态,
    # 改为并发后墙钟≈最慢单项。⚠️ Tushare 并发安全性需在 VPS 上 `--once` 实测确认无误后再常驻。
    tasks = {}
    with _f.ThreadPoolExecutor(max_workers=8) as ex:
        tasks["realtime"] = ex.submit(get_sina_realtime, code, name)
        tasks["history"]  = ex.submit(get_history_kline, code)
        if has_ts:
            tasks["money_flow"]  = ex.submit(TUSHARE.get_moneyflow_summary, code)
            tasks["fina"]        = ex.submit(TUSHARE.get_fina_indicator, code, 4)
            tasks["forecast"]    = ex.submit(TUSHARE.get_forecast, code, 2)
            tasks["holder"]      = ex.submit(TUSHARE.get_holder_number, code, 2)
            tasks["daily_basic"] = ex.submit(TUSHARE.get_daily_basic, code)
        if use_concepts:
            tasks["concepts"] = ex.submit(TUSHARE.get_stock_concepts, code)

        def _res(key, default=None):
            fut = tasks.get(key)
            if fut is None:
                return default
            try:
                return fut.result()
            except Exception as e:
                logger.debug(f"  ⚠️ {code} {key} 取数失败: {e}")
                return default

        realtime    = _res("realtime")
        history     = _res("history")
        money_flow  = _res("money_flow")
        fina_recs   = _res("fina")
        forecasts   = _res("forecast")
        holders     = _res("holder")
        daily_basic = _res("daily_basic")
        ts_concepts = _res("concepts")

    # 资金流向: Tushare 无数据时 fallback 东财
    if money_flow is None:
        money_flow = get_em_money_flow(code)

    # 业绩: 复用 periods=4 首条(去掉原先 periods=1 的重复拉取, 字段完全一致)
    quarterly = None
    if fina_recs:
        lf = fina_recs[0]
        quarterly = {
            "stat_date": lf.get("end_date"),
            "pub_date": lf.get("ann_date"),
            "roe_avg": _to_float(lf.get("roe")),
            "roe_dt": _to_float(lf.get("roe_dt")),
            "gross_margin": _to_float(lf.get("grossprofit_margin")),
            "net_margin": _to_float(lf.get("netprofit_margin")),
            "debt_to_assets": _to_float(lf.get("debt_to_assets")),
            "eps": _to_float(lf.get("eps")),
            "ocfps": _to_float(lf.get("ocfps")),
            "np_yoy": _to_float(lf.get("netprofit_yoy")),
            "or_yoy": _to_float(lf.get("or_yoy")),
            "op_yoy": _to_float(lf.get("op_yoy")),
            "q_np_yoy": _to_float(lf.get("q_npincome_yoy")),
            "q_or_yoy": _to_float(lf.get("q_sales_yoy")),
        }

    metrics = calc_derived_metrics(realtime, history, cost, shares, money_flow, quarterly)

    # 业绩预告
    forecast_info = None
    if forecasts:
        latest = forecasts[0]
        forecast_info = {
            "end_date": latest.get("end_date"),
            "ann_date": latest.get("ann_date"),
            "type": latest.get("type"),
            "p_change_min": _to_float(latest.get("p_change_min")),
            "p_change_max": _to_float(latest.get("p_change_max")),
            "net_profit_min_wan": _to_float(latest.get("net_profit_min")),
            "net_profit_max_wan": _to_float(latest.get("net_profit_max")),
            "summary": latest.get("summary"),
        }

    # 股东户数变化(筹码集中度)
    holder_change = None
    if holders and len(holders) >= 2:
        latest_count = _to_float(holders[0].get("holder_num"))
        prev_count = _to_float(holders[1].get("holder_num"))
        if latest_count and prev_count:
            holder_change = {
                "latest_date": holders[0].get("end_date"),
                "latest_count": latest_count,
                "prev_date": holders[1].get("end_date"),
                "prev_count": prev_count,
                "change_pct": (latest_count - prev_count) / prev_count * 100,
                "interpretation": "筹码集中(利好)" if latest_count < prev_count else "筹码分散(警惕)",
            }

    # 财务4期历史(带报告期口径标签)
    fina_history = None
    if fina_recs:
        fina_history = []
        for r in fina_recs:
            end_date = str(r.get("end_date") or "")
            quarter_label = "?"
            if len(end_date) >= 8:
                mmdd = end_date[4:8]
                quarter_label = {
                    "0331": "Q1(单季)",
                    "0630": "H1(累计)",
                    "0930": "Q1-Q3(累计)",
                    "1231": "全年(累计)",
                }.get(mmdd, "?")
            fina_history.append({
                "end_date": end_date,
                "period_type": quarter_label,
                "roe": _to_float(r.get("roe")),
                "gross_margin": _to_float(r.get("grossprofit_margin")),
                "net_margin": _to_float(r.get("netprofit_margin")),
                "np_yoy": _to_float(r.get("netprofit_yoy")),
                "or_yoy": _to_float(r.get("or_yoy")),
                "q_np_yoy": _to_float(r.get("q_npincome_yoy")),
            })

    # 概念标签: 手动 + Tushare合并
    manual_concepts = STOCK_CONCEPTS.get(code, [])
    final_concepts = list(manual_concepts)
    tushare_concepts_count = 0
    if ts_concepts:
        for c in ts_concepts:
            if c and c not in final_concepts:
                final_concepts.append(c)
                tushare_concepts_count += 1

    # 资金流分档明细注入metrics(供报告渲染)
    if money_flow and isinstance(money_flow, dict):
        for k in ["buy_elg_amount", "sell_elg_amount", "buy_lg_amount", "sell_lg_amount"]:
            if k in money_flow:
                metrics[k] = money_flow[k]

    hc_pct = holder_change.get("change_pct") if holder_change else None

    # v1.2: 流通市值(亿), 来自已并发取回的 daily_basic
    circ_mv_yi = None
    if daily_basic and daily_basic.get("circ_mv"):
        try:
            circ_mv_yi = float(daily_basic["circ_mv"]) / 1e4  # 万元→亿元
            metrics["circ_mv_yi"] = round(circ_mv_yi, 1)
        except Exception:
            pass

    _rss_final = calc_right_side_score(
        price=realtime.get("price") if realtime else None,
        ma5=metrics.get("ma5"),
        volume_ratio_5d=metrics.get("volume_ratio_5d"),
        change_pct=realtime.get("change_pct") if realtime else None,
        turnover_zscore=metrics.get("turnover_zscore"),
        inflow_slope=metrics.get("inflow_slope"),
        inflow_10d=metrics.get("main_inflow_10d"),
        holder_change_pct=hc_pct,
        position_20d_pct=metrics.get("position_20d_pct"),
        np_yoy=metrics.get("np_yoy"),
        pe_percentile_1y=metrics.get("pe_percentile_1y"),
        market_regime=_CURRENT_MARKET_REGIME,
        circ_mv_yi=circ_mv_yi,
    )
    metrics["right_side_score"] = _rss_final["score"]
    metrics["right_side_signals"] = _rss_final["signals"]
    metrics["right_side_grade"] = _rss_final["grade"]

    return {
        "group": group,
        "code": code,
        "configured_name": name,
        "cost_price": cost,
        "shares": shares,
        "concepts": final_concepts,
        "concepts_manual_count": len(manual_concepts),
        "concepts_tushare_count": tushare_concepts_count,
        "realtime": realtime,
        "metrics": metrics,
        "forecast": forecast_info,
        "holder_change": holder_change,
        "fina_history": fina_history,
        "history_tail": history[-5:] if history else [],
    }


def _to_float(v):
    """安全转float"""
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return None if (f != f) else f  # 排除NaN
    except (ValueError, TypeError):
        return None


# ==================== 赛道分析 ====================

def build_sector_analysis() -> Dict[str, Any]:
    """构建赛道分析:涨幅前5、跌幅前5、资金流入前5"""
    logger.info("[赛道] 获取板块涨跌幅排行...")
    top_up = get_em_sector_ranking("desc", 8)
    time.sleep(REQUEST_SLEEP_SECONDS)
    top_down = get_em_sector_ranking("asc", 5)
    time.sleep(REQUEST_SLEEP_SECONDS)

    return {
        "top_up_sectors": top_up,
        "top_down_sectors": top_down,
        "focus_sectors": HOT_SECTORS_FOCUS,
    }


# ==================== HTML 渲染 ====================

def render_index_table(indices: List[Dict[str, Any]], market: Dict[str, Any], north: Optional[Dict[str, Any]]) -> str:
    rows = []
    for idx in indices:
        if "error" in idx:
            continue
        change_pct = idx.get("change_pct")
        color = "#d32f2f" if (change_pct or 0) > 0 else "#388e3c" if (change_pct or 0) < 0 else "#666"
        rows.append(f"""
        <tr>
          <td><b>{html.escape(idx.get('name', ''))}</b></td>
          <td style="text-align:right">{fmt_num(idx.get('price'))}</td>
          <td style="text-align:right; color:{color}">{fmt_pct(change_pct)}</td>
          <td style="text-align:right">{fmt_num(idx.get('change_amount'))}</td>
        </tr>""")

    market_info = ""
    if market:
        market_info = f"""
        <div style="margin-top:8px; padding:8px; background:#f9f9f9; border-radius:4px; font-size:13px;">
          全市场: 上涨 <b style="color:#d32f2f">{market.get('up_count', 0)}</b> 家 |
          下跌 <b style="color:#388e3c">{market.get('down_count', 0)}</b> 家 |
          涨停 <b style="color:#d32f2f">{market.get('limit_up_count', 0)}</b> |
          跌停 <b style="color:#388e3c">{market.get('limit_down_count', 0)}</b>
        </div>"""

    north_info = ""
    if north:
        total = north.get("total_inflow")
        data_date = north.get("trade_date", "")
        is_today = north.get("is_today", True)
        staleness = "" if is_today else f" <span style='color:#f57c00;font-size:11px'>⚠️延迟({data_date})</span>"
        if total is not None:
            color = "#d32f2f" if total > 0 else "#388e3c"
            north_info = f"""
        <div style="margin-top:4px; padding:8px; background:#f9f9f9; border-radius:4px; font-size:13px;">
          北向资金: 总净流入 <b style="color:{color}">{total:+.2f}亿</b>
          (沪{north.get('hgt_inflow') or 0:.1f}亿 | 深{north.get('sgt_inflow') or 0:.1f}亿){staleness}
        </div>"""
        elif north.get("note"):
            north_info = f"""
        <div style="margin-top:4px; padding:8px; background:#fff3e0; border-radius:4px; font-size:12px; color:#666;">
          ℹ️ 北向资金: {html.escape(north.get('note', ''))}
        </div>"""

    return f"""
    <h3>📈 大盘指数</h3>
    <table style="width:100%; border-collapse: collapse;">
      <thead>
        <tr style="background:#f0f0f0;">
          <th style="padding:6px; text-align:left">指数</th>
          <th style="padding:6px; text-align:right">点位</th>
          <th style="padding:6px; text-align:right">涨跌幅</th>
          <th style="padding:6px; text-align:right">涨跌点</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    {market_info}
    {north_info}
    """


def render_sector_section(sector: Dict[str, Any]) -> str:
    """渲染赛道分析模块"""
    def render_list(items, title, key_color):
        rows = []
        for it in items[:8]:
            color = "#d32f2f" if (it.get("change_pct") or 0) > 0 else "#388e3c"
            inflow = it.get("main_inflow")
            inflow_str = f"{inflow/1e8:.1f}亿" if inflow else "-"
            inflow_color = "#d32f2f" if (inflow or 0) > 0 else "#388e3c"
            rows.append(f"""
            <tr>
              <td style="padding:5px"><b>{html.escape(it.get('name', ''))}</b></td>
              <td style="padding:5px; color:{color}; text-align:right">{fmt_pct(it.get('change_pct'))}</td>
              <td style="padding:5px; color:{inflow_color}; text-align:right">{inflow_str}</td>
              <td style="padding:5px; font-size:12px; color:#666">{html.escape(it.get('leader_name', ''))} {fmt_pct(it.get('leader_change_pct'))}</td>
            </tr>""")
        return f"""
        <div style="margin-bottom:12px;">
          <div style="padding:6px; background:{key_color}; color:white; font-weight:bold; border-radius:4px 4px 0 0;">{title}</div>
          <table style="width:100%; border-collapse:collapse; border:1px solid #ddd;">
            <thead style="background:#f5f5f5;">
              <tr>
                <th style="padding:5px; text-align:left">板块</th>
                <th style="padding:5px; text-align:right">涨跌幅</th>
                <th style="padding:5px; text-align:right">主力净流入</th>
                <th style="padding:5px; text-align:left">领涨股</th>
              </tr>
            </thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>"""

    up_section = render_list(sector.get("top_up_sectors", []), "🔥 今日强势板块 TOP", "#d32f2f")
    down_section = render_list(sector.get("top_down_sectors", []), "❄️ 今日弱势板块", "#388e3c")

    return f"""
    <h3>🌟 板块赛道分析</h3>
    {up_section}
    {down_section}
    """


def render_stock_table(title: str, stocks: List[Dict[str, Any]]) -> str:
    if not stocks:
        return ""

    rows = []
    for item in stocks:
        rt = item.get("realtime") or {}
        mt = item.get("metrics") or {}
        concepts = item.get("concepts", [])

        change_pct = rt.get("change_pct")
        color = "#d32f2f" if (change_pct or 0) > 0 else "#388e3c" if (change_pct or 0) < 0 else "#666"

        pnl_str = ""
        if item.get("cost_price"):
            pnl = mt.get("pnl_pct")
            pnl_color = "#d32f2f" if (pnl or 0) > 0 else "#388e3c"
            pnl_str = f"<br><span style='font-size:12px; color:{pnl_color}'>盈亏 {fmt_pct(pnl)}</span>"

        # 资金流向
        inflow = mt.get("main_inflow_today")
        inflow_str = "-"
        inflow_color = "#666"
        if inflow is not None:
            inflow_yi = inflow / 1e8
            inflow_color = "#d32f2f" if inflow_yi > 0 else "#388e3c"
            inflow_str = f"{inflow_yi:+.2f}亿"

        # PE百分位
        pe_pct = mt.get("pe_percentile_1y")
        pe_pct_str = f"{pe_pct:.0f}%" if pe_pct is not None else "-"

        # 概念标签
        concepts_str = " ".join(f'<span style="background:#e3f2fd; color:#1976d2; padding:1px 5px; margin:1px; border-radius:3px; font-size:11px">{html.escape(c)}</span>' for c in concepts[:3])

        # 风险等级
        risk = mt.get("risk_level", "")
        risk_colors = {"HIGH_ATTENTION": "#d32f2f", "WATCH": "#f57c00", "NORMAL": "#388e3c"}
        risk_color = risk_colors.get(risk, "#666")

        alerts = mt.get("alerts") or []
        alerts_str = "<br>".join(f"• {html.escape(a)}" for a in alerts) if alerts else "-"

        rows.append(f"""
        <tr>
          <td style="padding:6px; border-bottom:1px solid #eee;">
            <b>{html.escape(item.get('configured_name', ''))}</b><br>
            <span style="font-size:11px; color:#999">{html.escape(item.get('code', ''))}</span>
            {pnl_str}
          </td>
          <td style="padding:6px; border-bottom:1px solid #eee; text-align:right">
            {fmt_num(rt.get('price'))}<br>
            <span style="color:{color}">{fmt_pct(change_pct)}</span>
          </td>
          <td style="padding:6px; border-bottom:1px solid #eee; text-align:right; color:{inflow_color}">
            {inflow_str}
          </td>
          <td style="padding:6px; border-bottom:1px solid #eee; font-size:12px">
            MA趋势: {mt.get('ma_trend') or '-'}<br>
            20日位置: {fmt_num(mt.get('position_20d_pct'), 0, '%')}<br>
            52周位置: {fmt_num(mt.get('position_52w_pct'), 0, '%')}
          </td>
          <td style="padding:6px; border-bottom:1px solid #eee; font-size:12px">
            PE: {fmt_num(mt.get('pe_ttm'), 1)} ({pe_pct_str})<br>
            RSI: {fmt_num(mt.get('rsi_14'), 0)}<br>
            量比: {fmt_num(mt.get('volume_ratio_5d'), 2, 'x')}
          </td>
          <td style="padding:6px; border-bottom:1px solid #eee;">
            {concepts_str}
          </td>
          <td style="padding:6px; border-bottom:1px solid #eee; font-size:12px;">
            <span style="color:{risk_color}; font-weight:bold">{risk}</span><br>
            {alerts_str}
          </td>
        </tr>""")

    return f"""
    <h3>{title}</h3>
    <table style="width:100%; border-collapse:collapse; font-size:13px;">
      <thead>
        <tr style="background:#f0f0f0;">
          <th style="padding:6px; text-align:left">股票</th>
          <th style="padding:6px; text-align:right">现价/涨幅</th>
          <th style="padding:6px; text-align:right">主力净流入</th>
          <th style="padding:6px; text-align:left">趋势位置</th>
          <th style="padding:6px; text-align:left">估值/技术</th>
          <th style="padding:6px; text-align:left">概念</th>
          <th style="padding:6px; text-align:left">风险等级/提示</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


def render_html_report(payload: Dict[str, Any]) -> str:
    holdings = [s for s in payload.get("stocks", []) if s.get("group") == "holding"]
    watchlist = [s for s in payload.get("stocks", []) if s.get("group") == "watchlist"]
    sector = payload.get("sector_analysis", {})

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, "Segoe UI", Arial, sans-serif; background:#f5f5f5; margin:0; padding:20px; }}
.container {{ max-width:1200px; margin:0 auto; background:white; padding:25px; border-radius:8px; }}
h2 {{ color:#1976d2; }}
h3 {{ color:#333; border-left:4px solid #1976d2; padding-left:10px; margin-top:25px; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:6px; }}
.summary {{ display:flex; gap:15px; margin:15px 0; }}
.summary > div {{ flex:1; padding:15px; background:#f0f7ff; border-radius:6px; text-align:center; }}
.muted {{ color:#999; font-size:12px; }}
.footer {{ margin-top:20px; padding:15px; background:#f9f9f9; border-radius:4px; font-size:12px; color:#666; }}
</style></head><body><div class="container">
<h2>📊 股票每日汇总 {payload.get('generated_at', '')}</h2>
<div class="summary">
  <div><b>{len(holdings)}</b><br><span class="muted">持仓</span></div>
  <div><b>{len(watchlist)}</b><br><span class="muted">观察池</span></div>
  <div><b>{len(sector.get('top_up_sectors', []))}</b><br><span class="muted">强势板块</span></div>
  <div><b>{sum(1 for s in payload.get('stocks', []) if (s.get('metrics') or {}).get('risk_level') == 'HIGH_ATTENTION')}</b><br><span class="muted">高关注</span></div>
</div>
{render_index_table(payload.get('indices', []), payload.get('market_overview', {}), payload.get('north_flow'))}
{render_sector_section(sector)}
{render_stock_table('💼 持仓股票', holdings)}
{render_stock_table('👀 观察池', watchlist)}
<div class="footer">
<b>说明:</b><br>
1. 资金流向:今日主力(超大单+大单)净流入。亿元为单位。<br>
2. 20日位置/52周位置:价格在区间中的相对位置。100%为接近顶部,0%为接近底部。<br>
3. PE历史百分位:1年内的相对位置,100%为历史最贵,0%为历史最便宜。<br>
4. RSI:14日,&gt;80超买,&lt;20超卖。<br>
5. MA趋势:多头排列为强势,空头排列为弱势。<br>
6. 附件JSON/Markdown已按Claude易识别格式整理,可上传给Claude深度分析。
</div>
</div></body></html>"""


# ==================== Claude 附件(增强) ====================

def compact_for_claude(payload: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        "generated_at": payload["generated_at"],
        "data_sources": payload["data_sources"],
        "tushare_points_level": payload.get("tushare_points_level", 0),
        "analysis_instruction": (
            "你是一名专业的A股分析师。基于以下结构化数据,做一份**决策导向**的分析报告。\n"
            "\n"
            "【量化框架 v1.4 — 沪深300扩展379只/745日回测(2026-06-16重跑,修幸存者偏差+前复权)】\n"
            "因子有效性排名（IC回测验证）:\n"
            "  🥇 净利同比      (IC=0.0240, ICIR=2.56) - IC最高\n"
            "  🥇 10日主力净流入 (IC=0.0229, ICIR=2.44) - 实战最强(多空+12.89%/夏普0.90)\n"
            "  🥈 股东户数变化  (IC=-0.0219, ICIR=-3.56) - 最稳定(负向)\n"
            "  🥈 右侧合成评分  (IC=0.0202, ICIR=3.13) - 排序强但多空仅+0.77%,作下限过滤非alpha\n"
            "  ❌ 无效/已删: 20日位置/PE百分位/RSI/换手Z/MA5偏离度/资金流斜率\n"
            "\n"
            "【市场环境过滤(regime filter)】\n"
            "- 动量市: 反转因子(PE百分位/20日位置/RSI)失效,以资金流+业绩+户数为准\n"
            "- 价值市: 反转因子启用,可考虑低位价值股\n"
            "- 恐慌市: 建议观望,提高现金\n"
            "看 market_regime 字段判断当前环境。\n"
            "\n"
            "【个股评分使用】\n"
            "每只股票已经计算 right_side_score (v1.1新公式):\n"
            "  >= 3.5 强买入信号\n"
            "  >= 2.0 可考虑介入\n"
            "  >= 0.5 观察等待\n"
            "  <  0.5 回避\n"
            "right_side_signals 字段是评分明细,直接引用。\n"
            "\n"
            "【输出要求】\n"
            "1. 大盘+板块整体判断,明确指出当前是哪种 regime\n"
            "2. **宏观环境(v1.3新增)**:综合判断 Macro Regime,与短期 regime 叠加给仓位建议\n"
            "3. 每只持仓做风险评估,以v1.1评分为准,辅以业绩/股东户数趋势\n"
            "4. 每只观察池做介入判断,优先看 right_side_score >= 2.0 的标的\n"
            "5. 给出明日3-5个具体观察重点\n"
            "6. 不要给具体买卖价格指令,只做风险评估+方向判断"
        ),
        "indices": payload.get("indices", []),
        "market_overview": payload.get("market_overview", {}),
        "market_regime": payload.get("market_regime", "momentum"),  # v1.1: 市场环境
        "north_flow": payload.get("north_flow"),
        "hsgt_flow_history": payload.get("hsgt_flow_history"),  # 北向资金近5日(Tushare)
        "sector_analysis": payload.get("sector_analysis", {}),
        "hot_sector_scan": payload.get("hot_sector_scan"),  # v1.2: 热门赛道+龙头股
        "us_market": payload.get("us_market"),              # v1.2: 美股参考
        "opportunity_scan": payload.get("opportunity_scan"), # v1.2: 机会仓
        "macro": payload.get("macro"),                       # v1.3: 宏观6维度
        "stocks": [],
    }
    for item in payload.get("stocks", []):
        rt = item.get("realtime") or {}
        mt = item.get("metrics") or {}
        result["stocks"].append({
            "group": item.get("group"),
            "code": item.get("code"),
            "name": rt.get("name") or item.get("configured_name"),
            "concepts": item.get("concepts", []),
            "cost_price": item.get("cost_price"),
            "shares": item.get("shares"),
            # === 实时行情 ===
            "price": rt.get("price"),
            "change_pct": rt.get("change_pct"),
            "amplitude_pct": rt.get("amplitude_pct"),
            "amount_yuan": rt.get("amount"),
            "open": rt.get("open"),
            "high": rt.get("high"),
            "low": rt.get("low"),
            # === 均线/趋势 ===
            "ma5": mt.get("ma5"), "ma10": mt.get("ma10"),
            "ma20": mt.get("ma20"), "ma60": mt.get("ma60"),
            "price_vs_ma5_pct": mt.get("price_vs_ma5_pct"),
            "price_vs_ma20_pct": mt.get("price_vs_ma20_pct"),
            "price_vs_ma60_pct": mt.get("price_vs_ma60_pct"),
            "ma_trend": mt.get("ma_trend"),
            # === 量价 ===
            "volume_ratio_5d": mt.get("volume_ratio_5d"),
            "volume_ratio_20d": mt.get("volume_ratio_20d"),
            "turnover_pct": mt.get("turnover_pct"),
            # === 估值(含历史百分位) ===
            "pe_ttm": mt.get("pe_ttm"),
            "pb_mrq": mt.get("pb_mrq"),
            "ps_ttm": mt.get("ps_ttm"),
            "pe_percentile_1y": mt.get("pe_percentile_1y"),
            "pb_percentile_1y": mt.get("pb_percentile_1y"),
            # === 区间位置 ===
            "range_20d_high": mt.get("range_20d_high"),
            "range_20d_low": mt.get("range_20d_low"),
            "position_20d_pct": mt.get("position_20d_pct"),
            "range_52w_high": mt.get("range_52w_high"),
            "range_52w_low": mt.get("range_52w_low"),
            "position_52w_pct": mt.get("position_52w_pct"),
            # === 周期涨幅 ===
            "recent_5d_change_pct": mt.get("recent_5d_change_pct"),
            "recent_20d_change_pct": mt.get("recent_20d_change_pct"),
            "ytd_change_pct": mt.get("ytd_change_pct"),
            # === 技术指标 ===
            "macd_dif": mt.get("macd_dif"),
            "macd_dea": mt.get("macd_dea"),
            "macd_hist": mt.get("macd_hist"),
            "rsi_14": mt.get("rsi_14"),
            # === 量化新增指标(v1.0) ===
            "turnover_zscore": mt.get("turnover_zscore"),
            "inflow_slope": mt.get("inflow_slope"),
            "right_side_score": mt.get("right_side_score"),
            "right_side_grade": mt.get("right_side_grade"),
            "right_side_signals": mt.get("right_side_signals"),
            # === 资金流向(Tushare 2000分,4档明细) ===
            "main_inflow_today_yuan": mt.get("main_inflow_today"),
            "main_inflow_today_pct": mt.get("main_inflow_today_pct"),
            "main_inflow_5d_yuan": mt.get("main_inflow_5d"),
            "main_inflow_10d_yuan": mt.get("main_inflow_10d"),
            "buy_elg_amount_yuan": mt.get("buy_elg_amount"),     # 特大单买入
            "sell_elg_amount_yuan": mt.get("sell_elg_amount"),    # 特大单卖出
            "buy_lg_amount_yuan": mt.get("buy_lg_amount"),       # 大单买入
            "sell_lg_amount_yuan": mt.get("sell_lg_amount"),     # 大单卖出
            # === 基本面 ===
            "np_yoy": mt.get("np_yoy"),                     # 净利同比%
            "or_yoy": mt.get("or_yoy"),                     # 营收同比%
            "q_np_yoy": mt.get("q_np_yoy"),                 # 单季净利同比%
            "roe_avg": mt.get("roe_avg"),                   # ROE%
            "roe_dt": mt.get("roe_dt"),                     # 扣非ROE%
            "gross_margin": mt.get("gross_margin"),         # 毛利率%
            "net_margin": mt.get("net_margin"),             # 净利率%
            "debt_to_assets": mt.get("debt_to_assets"),     # 资产负债率%
            "eps": mt.get("eps"),                           # EPS
            "ocfps": mt.get("ocfps"),                       # 每股经营现金流
            "report_date": mt.get("report_date"),
            # === Tushare独家数据 ===
            "forecast": item.get("forecast"),               # 业绩预告
            "holder_change": item.get("holder_change"),     # 股东户数变化
            "fina_history": item.get("fina_history"),       # 财务4期历史
            # === 持仓 ===
            "pnl_pct": mt.get("pnl_pct"),
            "pnl_amount": mt.get("pnl_amount"),
            # === 风险 ===
            "risk_level": mt.get("risk_level"),
            "alerts": mt.get("alerts"),
        })
    return result


def build_claude_markdown(claude_data: Dict[str, Any]) -> str:
    lines = []
    lines.append("# 股票日报结构化指标(增强版)")
    lines.append("")
    lines.append(f"生成时间: {claude_data['generated_at']}")
    lines.append("")
    lines.append("## 分析要求")
    lines.append(claude_data["analysis_instruction"])
    lines.append("")

    # 大盘
    lines.append("## 一、大盘环境")

    # v1.1: 市场环境分类（动量市/价值市/恐慌市）
    regime = claude_data.get("market_regime", "momentum")
    regime_label = {
        "momentum": "📈 **动量市** (成长股占优,反转因子失效,建议关注资金流+业绩+筹码)",
        "value":    "💰 **价值市** (主板占优,反转因子启用,可考虑低位价值股)",
        "panic":    "🚨 **恐慌市** (跌停超50个,建议观望,提高现金比例)"
    }.get(regime, regime)
    lines.append(f"- {regime_label}")

    for idx in claude_data.get("indices", []):
        if "error" not in idx:
            lines.append(f"- {idx.get('name')}: {fmt_num(idx.get('price'))} {fmt_pct(idx.get('change_pct'))}")

    mo = claude_data.get("market_overview", {})
    if mo:
        lines.append(f"- 全市场涨跌: 涨{mo.get('up_count', 0)} / 跌{mo.get('down_count', 0)} / 涨停{mo.get('limit_up_count', 0)} / 跌停{mo.get('limit_down_count', 0)}")
    nf = claude_data.get("north_flow")
    if nf:
        if nf.get("total_inflow") is not None:
            freshness = "今日" if nf.get("is_today") else f"延迟({nf.get('trade_date','')})"
            lines.append(f"- 北向资金({freshness}): {nf['total_inflow']:+.2f}亿 (沪{nf.get('hgt_inflow') or 0:.1f} / 深{nf.get('sgt_inflow') or 0:.1f})")
        elif nf.get("note"):
            lines.append(f"- 北向资金: ℹ️ {nf['note']}")
    lines.append("")

    # v1.3新增: 宏观环境(6维度) - 位于大盘环境后,板块赛道前
    macro_data = claude_data.get("macro")
    if macro_data:
        try:
            from macro_indicators import render_macro_section
            lines.append(render_macro_section(macro_data))
            lines.append("")
        except ImportError:
            pass

    # 赛道分析
    lines.append("## 二、板块赛道")
    sa = claude_data.get("sector_analysis", {})
    lines.append("### 今日强势板块 TOP")
    for s in sa.get("top_up_sectors", [])[:8]:
        infl = s.get("main_inflow", 0) or 0
        lines.append(f"- {s.get('name')}: {fmt_pct(s.get('change_pct'))} | 主力净流入 {infl/1e8:.2f}亿 | 领涨 {s.get('leader_name')} {fmt_pct(s.get('leader_change_pct'))}")
    lines.append("")
    lines.append("### 今日弱势板块")
    for s in sa.get("top_down_sectors", [])[:5]:
        infl = s.get("main_inflow", 0) or 0
        lines.append(f"- {s.get('name')}: {fmt_pct(s.get('change_pct'))} | 主力净流入 {infl/1e8:.2f}亿")
    lines.append("")

    lines.append("### 关注的热门赛道(供参考)")
    lines.append(f"  {', '.join(sa.get('focus_sectors', []))}")
    lines.append("")

    # 个股
    lines.append("## 三、个股指标")
    for s in claude_data.get("stocks", []):
        lines.append(f"### {s.get('name')} ({s.get('code')}) - {s.get('group')}")
        concepts = s.get("concepts", [])
        if concepts:
            lines.append(f"- 概念: {', '.join(concepts[:10])}")  # 概念太多截断
        lines.append(f"- 行情: 现价 {fmt_num(s.get('price'))} | 涨跌幅 {fmt_pct(s.get('change_pct'))} | 振幅 {fmt_num(s.get('amplitude_pct'), 2, '%')}")
        lines.append(f"- 均线: MA5/10/20/60 = {fmt_num(s.get('ma5'))}/{fmt_num(s.get('ma10'))}/{fmt_num(s.get('ma20'))}/{fmt_num(s.get('ma60'))}")
        lines.append(f"- 趋势: {s.get('ma_trend') or '-'} | vs MA20: {fmt_pct(s.get('price_vs_ma20_pct'))} | vs MA60: {fmt_pct(s.get('price_vs_ma60_pct'))}")
        lines.append(f"- 位置: 20日 {fmt_num(s.get('position_20d_pct'), 0, '%')} | 52周 {fmt_num(s.get('position_52w_pct'), 0, '%')}")
        lines.append(f"- 区间: 20日 [{fmt_num(s.get('range_20d_low'))} - {fmt_num(s.get('range_20d_high'))}] | 52周 [{fmt_num(s.get('range_52w_low'))} - {fmt_num(s.get('range_52w_high'))}]")
        lines.append(f"- 涨幅: 5日 {fmt_pct(s.get('recent_5d_change_pct'))} | 20日 {fmt_pct(s.get('recent_20d_change_pct'))} | 年初至今 {fmt_pct(s.get('ytd_change_pct'))}")
        lines.append(f"- 量价: 量比5日 {fmt_num(s.get('volume_ratio_5d'), 2, 'x')} | 换手 {fmt_num(s.get('turnover_pct'), 2, '%')}")

        # 资金流向(主力+4档明细)
        infl_today = s.get("main_inflow_today_yuan")
        infl_5d = s.get("main_inflow_5d_yuan")
        infl_10d = s.get("main_inflow_10d_yuan")
        if infl_today is not None:
            line = f"- 资金流向: 今日主力 {infl_today/1e8:+.2f}亿"
            if infl_5d is not None:
                line += f" | 5日 {infl_5d/1e8:+.2f}亿"
            if infl_10d is not None:
                line += f" | 10日 {infl_10d/1e8:+.2f}亿"
            lines.append(line)
            # 4档明细(特大单/大单)
            buy_elg = s.get("buy_elg_amount_yuan")
            sell_elg = s.get("sell_elg_amount_yuan")
            buy_lg = s.get("buy_lg_amount_yuan")
            sell_lg = s.get("sell_lg_amount_yuan")
            if buy_elg is not None and sell_elg is not None:
                elg_net = buy_elg - sell_elg
                lg_net = (buy_lg or 0) - (sell_lg or 0)
                lines.append(f"  • 特大单净额 {elg_net/1e8:+.2f}亿 (买{buy_elg/1e8:.2f}/卖{sell_elg/1e8:.2f})")
                lines.append(f"  • 大单净额 {lg_net/1e8:+.2f}亿 (买{(buy_lg or 0)/1e8:.2f}/卖{(sell_lg or 0)/1e8:.2f})")

        # 估值
        pe_pct = s.get("pe_percentile_1y")
        pb_pct = s.get("pb_percentile_1y")
        lines.append(f"- 估值: PE-TTM {fmt_num(s.get('pe_ttm'), 1)} (历史{fmt_num(pe_pct, 0, '%') if pe_pct is not None else '-'}) | PB {fmt_num(s.get('pb_mrq'), 2)} (历史{fmt_num(pb_pct, 0, '%') if pb_pct is not None else '-'})")

        # 技术指标
        lines.append(f"- 技术: MACD({s.get('macd_dif')}/{s.get('macd_dea')}/{s.get('macd_hist')}) | RSI14 {fmt_num(s.get('rsi_14'), 0)}")

        # 量化新增指标(v1.0)
        rss = s.get("right_side_score")
        rsg = s.get("right_side_grade") or "-"
        rssigs = s.get("right_side_signals") or []
        if rss is not None:
            lines.append(f"- 🎯 右侧信号评分: {rss:.1f}分 [{rsg}]")
            for sig in rssigs:
                lines.append(f"  {sig}")
        tz = s.get("turnover_zscore")
        if tz is not None:
            lines.append(f"- 换手Z-score: {tz:.2f} (>2异常放量/<-1缩量)")
        slope = s.get("inflow_slope")
        if slope is not None:
            lines.append(f"- 资金斜率: {slope/1e4:+.1f}万/日 ({'改善↑' if slope > 0 else '恶化↓'})")

        # 业绩(扩展版,加入扣非ROE/单季同比)
        if s.get("np_yoy") is not None or s.get("roe_avg") is not None:
            biz_line = f"- 业绩({s.get('report_date', '-')}): "
            parts = []
            if s.get("np_yoy") is not None:
                parts.append(f"净利同比 {fmt_pct(s.get('np_yoy'))}")
            if s.get("or_yoy") is not None:
                parts.append(f"营收同比 {fmt_pct(s.get('or_yoy'))}")
            if s.get("q_np_yoy") is not None:
                parts.append(f"单季净利同比 {fmt_pct(s.get('q_np_yoy'))}")
            if s.get("roe_avg") is not None:
                parts.append(f"ROE {fmt_pct(s.get('roe_avg'))}")
            if s.get("roe_dt") is not None:
                parts.append(f"扣非ROE {fmt_pct(s.get('roe_dt'))}")
            if s.get("gross_margin") is not None:
                parts.append(f"毛利率 {fmt_pct(s.get('gross_margin'))}")
            if s.get("net_margin") is not None:
                parts.append(f"净利率 {fmt_pct(s.get('net_margin'))}")
            if s.get("debt_to_assets") is not None:
                parts.append(f"资产负债率 {fmt_pct(s.get('debt_to_assets'))}")
            biz_line += " | ".join(parts)
            lines.append(biz_line)

        # 业绩预告(Tushare独家)
        fc = s.get("forecast")
        if fc and fc.get("type"):
            line = f"- 🎯 业绩预告({fc.get('end_date')}): {fc.get('type')}"
            pmin = fc.get("p_change_min")
            pmax = fc.get("p_change_max")
            if pmin is not None and pmax is not None:
                line += f" | 净利变动 {pmin:.1f}% ~ {pmax:.1f}%"
            elif pmin is not None:
                line += f" | 净利变动 {pmin:.1f}%+"
            if fc.get("summary"):
                summary = fc["summary"][:80]
                line += f"\n  • 原因: {summary}"
            lines.append(line)

        # 股东户数变化(Tushare独家)
        hc = s.get("holder_change")
        if hc and hc.get("change_pct") is not None:
            chg = hc["change_pct"]
            arrow = "↓" if chg < 0 else "↑"
            lines.append(f"- 👥 股东户数: {hc.get('prev_date')}→{hc.get('latest_date')} 变化 {chg:+.2f}% {arrow} ({hc.get('interpretation')})")

        # 财务历史(看趋势)
        fh = s.get("fina_history")
        if fh and len(fh) >= 2:
            # 显示每一期的"期间标签",防止单季vs累计比较失真
            # 同时增加 q_np_yoy (单季净利同比, 可跨期对比) 作为更准确的趋势指标
            period_seq = " → ".join(
                f"{(r.get('end_date') or '')[:6]}({r.get('period_type','?')})" for r in reversed(fh)
            )
            roe_trend = " → ".join(
                f"{r.get('roe', 0):.1f}" if r.get("roe") is not None else "-"
                for r in reversed(fh)
            )
            np_yoy_trend = " → ".join(
                f"{r.get('np_yoy', 0):+.0f}%" if r.get("np_yoy") is not None else "-"
                for r in reversed(fh)
            )
            q_np_yoy_trend = " → ".join(
                f"{r.get('q_np_yoy', 0):+.0f}%" if r.get("q_np_yoy") is not None else "-"
                for r in reversed(fh)
            )
            lines.append(f"- 📈 财务趋势(老→新):")
            lines.append(f"    报告期: {period_seq}")
            lines.append(f"    ROE(%): {roe_trend}  ⚠️不同报告期口径不同,见报告期标签")
            lines.append(f"    累计净利同比: {np_yoy_trend}")
            lines.append(f"    单季净利同比(可跨期对比): {q_np_yoy_trend}")

        # 持仓
        if s.get("cost_price") is not None:
            lines.append(f"- 持仓: 成本 {s.get('cost_price')} | 盈亏 {fmt_pct(s.get('pnl_pct'))}" + (f" ({s.get('pnl_amount'):+.0f}元)" if s.get('pnl_amount') else ""))

        # 风险
        lines.append(f"- 风险等级: {s.get('risk_level')}")
        lines.append(f"- 提示: {'; '.join(s.get('alerts') or []) or '无'}")
        lines.append("")

    # v1.2新增: 热门赛道扫描 + 龙头股识别
    scan_result = claude_data.get("hot_sector_scan")
    if scan_result:
        try:
            from hot_sector_scanner import render_hot_sector_section
            lines.append("")
            lines.append(render_hot_sector_section(scan_result))
            lines.append("")
        except ImportError:
            pass

    # v1.2新增: 美股参考
    us_data = claude_data.get("us_market")
    if us_data:
        try:
            from us_market import render_us_market_section
            lines.append("")
            lines.append(render_us_market_section(us_data))
            lines.append("")
        except ImportError:
            pass

    # v1.2新增: 机会仓扫描
    opp_data = claude_data.get("opportunity_scan")
    if opp_data:
        try:
            from opportunity_scanner import render_opportunity_section
            lines.append("")
            lines.append(render_opportunity_section(opp_data, total_capital=164000))
            lines.append("")
        except ImportError:
            pass

    # 分析方向引导
    lines.append("## 六、请重点分析以下方向")
    lines.append("")
    lines.append("1. **大盘环境**:今天是普涨还是结构性?涨跌家数比例是否健康?北向资金态度?当前是哪种regime(动量/价值/恐慌)?")
    lines.append("2. **🌐 宏观环境(v1.3新增)**:")
    lines.append("   - 综合 Macro Regime(看多/中性/看空)是什么?基于哪几个 ✅/❌ 信号?")
    lines.append("   - ERP 当前在历史什么位置?σ倍数说明什么?")
    lines.append("   - M1 同比和环比变化是加速还是减速?对市场流动性的判断")
    lines.append("   - 全A宽度(MA60/MA200)反映短期/长期市场是超跌还是过热?")
    lines.append("   - **与短期v1.2 regime 叠加,给出仓位建议**(见上方Regime叠加表)")
    lines.append("3. **美股参考**:结合美股数据,判断今日A股科技/医疗/AI链的外部情绪是顺风还是逆风")
    lines.append("3. **板块轮动**:")
    lines.append("   - 今日强势板块是否可持续?是新主线还是短期题材?")
    lines.append("   - 持仓/观察池所在板块的相对强弱?")
    lines.append("4. **个股层面**:")
    lines.append("   - 持仓:用v1.1评分为主+业绩/股东户数趋势辅助,判断止盈/止损/加仓")
    lines.append("   - 观察池:优先看 right_side_score >= 2.0 的标的")
    lines.append("5. **🔥 热门赛道+龙头股(v1.2新增)**:")
    lines.append("   - 算法已自动扫描5个热门板块+龙头候选(见上方'四、热门赛道扫描')")
    lines.append("   - 结合美股赛道ETF表现,判断这些龙头是真主线还是高位风险")
    lines.append("   - 哪些可加入观察池跟踪")
    lines.append("6. **风险预警**:")
    lines.append("   - 高位高估值+主力流出的标的(警惕)")
    lines.append("   - 跌破关键均线+空头排列的标的(趋势恶化)")
    return "\n".join(lines)


def write_attachments(payload: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    claude_data = compact_for_claude(payload)

    json_name = f"claude_stock_metrics_{ts}.json"
    md_name = f"claude_stock_prompt_{ts}.md"

    with open(json_name, "w", encoding="utf-8") as f:
        json.dump(claude_data, f, ensure_ascii=False, indent=2)

    with open(md_name, "w", encoding="utf-8") as f:
        f.write(build_claude_markdown(claude_data))

    logger.info(f"📝 Claude附件已生成: {json_name}, {md_name}")
    return [(json_name, json_name, "json"), (md_name, md_name, "markdown")]


# ==================== 主流程 ====================

def collect_payload() -> Dict[str, Any]:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_sources = ["sina_realtime", "eastmoney_sectors_market", "eastmoney_moneyflow_fallback"]
    if TUSHARE is not None:
        data_sources.append(f"tushare_pro_lv{TUSHARE.points_level}")

    payload: Dict[str, Any] = {
        "generated_at": generated_at,
        "data_sources": data_sources,
        "tushare_points_level": TUSHARE.points_level if TUSHARE else 0,
        "indices": [],
        "stocks": [],
        "market_overview": {},
        "north_flow": None,
        "hsgt_flow_history": None,
        "sector_analysis": {},
    }

    logger.info("[1/5] 获取大盘指数...")
    for symbol, name in INDEX_LIST:
        idx = get_sina_index(symbol, name)
        if idx:
            payload["indices"].append(idx)
        time.sleep(REQUEST_SLEEP_SECONDS)

    logger.info("[2/5] 获取大盘综合数据(涨跌家数)...")
    payload["market_overview"] = get_em_market_overview()

    # v1.1: 检测市场环境（动量市/价值市/恐慌市），影响后续个股评分
    global _CURRENT_MARKET_REGIME
    _CURRENT_MARKET_REGIME = detect_market_regime(
        payload["indices"], payload["market_overview"]
    )
    payload["market_regime"] = _CURRENT_MARKET_REGIME
    regime_label = {"momentum": "动量市(成长股占优)",
                    "value": "价值市(主板占优)",
                    "panic": "恐慌市(警惕)"}.get(_CURRENT_MARKET_REGIME, _CURRENT_MARKET_REGIME)
    logger.info(f"  📊 当前市场环境: {regime_label}")

    # 北向资金: 仅Tushare(2000分能拿到每日数据)
    logger.info("[3/5] 获取北向资金...")
    if TUSHARE is not None and TUSHARE.points_level >= 2000:
        hsgt = TUSHARE.get_hsgt_flow(days=10)  # 多拉几天，应对T+1延迟
        if hsgt:
            # ── 单位修正 ──────────────────────────────────────────────────
            # Tushare moneyflow_hsgt 字段单位：万元（不是百万元）
            # 转亿元：万元 / 10000 = 亿元
            # 历史bug：原代码用 /100，导致数值虚高100倍
            def to_yi(v):
                f = _to_float(v)
                return round(f / 10000, 2) if f is not None else None

            # ── 日期有效性校验 ─────────────────────────────────────────────
            # 2024-08起交易所停止实时披露，Tushare可能返回延迟或空数据
            # 取最近一条非空记录，并记录其日期供Claude判断新鲜度
            today_str = datetime.now().strftime("%Y%m%d")
            latest = None
            for row in reversed(hsgt):
                total_v = to_yi(row.get("north_money"))
                hgt_v = to_yi(row.get("hgt"))
                sgt_v = to_yi(row.get("sgt"))
                # 至少有一个字段有实际数值才算有效
                if any(v is not None and v != 0 for v in [total_v, hgt_v, sgt_v]):
                    latest = row
                    break

            if latest:
                total_yi = to_yi(latest.get("north_money"))
                hgt_yi = to_yi(latest.get("hgt"))
                sgt_yi = to_yi(latest.get("sgt"))

                if total_yi is None and (hgt_yi is not None or sgt_yi is not None):
                    total_yi = round((hgt_yi or 0) + (sgt_yi or 0), 2)

                data_date = str(latest.get("trade_date") or "")
                is_today = data_date == today_str
                staleness_note = None if is_today else f"数据日期{data_date}(非今日,交易所延迟披露)"

                # 有效性合理区间校验：单日北向资金通常在 ±500亿以内
                if total_yi is not None and abs(total_yi) > 500:
                    logger.warning(f"  ⚠️ 北向资金数值异常({total_yi:.1f}亿)，可能单位仍有误，置为None")
                    total_yi = hgt_yi = sgt_yi = None
                    staleness_note = f"数据异常({total_yi})，已屏蔽"

                payload["north_flow"] = {
                    "total_inflow": total_yi,
                    "hgt_inflow": hgt_yi,
                    "sgt_inflow": sgt_yi,
                    "trade_date": data_date,
                    "is_today": is_today,
                    "note": staleness_note,
                    "source": "tushare",
                }

                # 历史趋势（近10日，去除空值）
                hsgt_history_converted = []
                for row in hsgt:
                    t_yi = to_yi(row.get("north_money"))
                    h_yi = to_yi(row.get("hgt"))
                    s_yi = to_yi(row.get("sgt"))
                    if any(v is not None for v in [t_yi, h_yi, s_yi]):
                        hsgt_history_converted.append({
                            "trade_date": row.get("trade_date"),
                            "north_money_yi": t_yi,
                            "hgt_yi": h_yi,
                            "sgt_yi": s_yi,
                        })
                payload["hsgt_flow_history"] = hsgt_history_converted

                if total_yi is not None:
                    freshness = "今日" if is_today else f"延迟({data_date})"
                    logger.info(f"  ✅ 北向资金({freshness}): {total_yi:+.2f}亿 | 沪{hgt_yi or 0:.1f} 深{sgt_yi or 0:.1f}")
                else:
                    logger.warning(f"  ⚠️ 北向资金字段均为空(日期:{data_date})")
            else:
                payload["north_flow"] = {
                    "total_inflow": None, "hgt_inflow": None, "sgt_inflow": None,
                    "note": "Tushare返回数据均为空值(2024-08后交易所已停止实时披露)"
                }
        else:
            payload["north_flow"] = {
                "total_inflow": None, "hgt_inflow": None, "sgt_inflow": None,
                "note": "Tushare北向资金接口返回空"
            }
    else:
        payload["north_flow"] = {
            "total_inflow": None, "hgt_inflow": None, "sgt_inflow": None,
            "note": "Tushare未启用,北向资金数据不可用"
        }

    logger.info("[4/5] 获取板块赛道分析...")
    payload["sector_analysis"] = build_sector_analysis()

    logger.info("[5/5] 获取持仓与观察池...")
    for code, info in HOLDINGS.items():
        name = info[0]
        cost = info[1] if len(info) > 1 else None
        shares = info[2] if len(info) > 2 else None
        item = build_stock_item("holding", code, name, cost, shares)
        payload["stocks"].append(item)
        logger.info(f"  ✅ 持仓 {code} {name}")
        time.sleep(REQUEST_SLEEP_SECONDS)

    for code, name in WATCHLIST.items():
        item = build_stock_item("watchlist", code, name, None, None)
        payload["stocks"].append(item)
        logger.info(f"  ✅ 观察 {code} {name}")
        time.sleep(REQUEST_SLEEP_SECONDS)

    # v1.2新增: 热门赛道扫描 + 龙头股识别
    logger.info("[6/7] 热门赛道扫描+龙头股识别...")
    try:
        from hot_sector_scanner import scan_hot_sectors_and_leaders
        user_pool = set(HOLDINGS.keys()) | set(WATCHLIST.keys())
        scan_result = scan_hot_sectors_and_leaders(TUSHARE, user_pool_codes=user_pool)
        payload["hot_sector_scan"] = scan_result
        n_sectors = len(scan_result.get("sectors", []))
        n_leaders = len(scan_result.get("leaders", []))
        logger.info(f"  ✅ 识别 {n_sectors} 个热门板块, {n_leaders} 只龙头股候选")
    except ImportError:
        logger.warning("  ⚠️ hot_sector_scanner.py 未安装,跳过扫描")
        payload["hot_sector_scan"] = None
    except Exception as e:
        logger.warning(f"  ⚠️ 热门赛道扫描失败: {str(e)[:120]}")
        payload["hot_sector_scan"] = None

    # v1.2新增: 美股参考数据
    logger.info("[7/7] 拉取美股参考数据...")
    try:
        from us_market import fetch_us_market_data
        payload["us_market"] = fetch_us_market_data()
    except ImportError:
        logger.warning("  ⚠️ us_market.py 未安装,跳过")
        payload["us_market"] = None
    except Exception as e:
        logger.warning(f"  ⚠️ 美股数据失败: {str(e)[:80]}")
        payload["us_market"] = None

    # v1.2新增: 机会仓扫描
    logger.info("[8/8] 机会仓扫描...")
    try:
        from opportunity_scanner import scan_opportunities
        user_pool = set(HOLDINGS.keys()) | set(WATCHLIST.keys())
        total_cap = payload.get("total_capital", 164000)
        opp_result = scan_opportunities(
            TUSHARE, total_capital=total_cap, user_pool_codes=user_pool
        )
        # OpportunityBook对象不能JSON序列化，转为可序列化的dict
        book = opp_result.get("book")
        if book:
            opp_result["book_summary"] = book.render_summary()
            opp_result["book_positions"] = book.positions
            opp_result["book_budget"] = book.budget
            opp_result["book_used"] = book.used_budget
            opp_result["book_remaining"] = book.remaining_budget
            opp_result["book_slots"] = book.remaining_slots
        opp_result.pop("book", None)  # 移除不可序列化的对象
        payload["opportunity_scan"] = opp_result
        na = len(opp_result.get("signal_a", []))
        nb = len(opp_result.get("signal_b", []))
        logger.info(f"  ✅ 信号A: {na}只，信号B: {nb}只")
    except ImportError:
        logger.warning("  ⚠️ opportunity_scanner.py 未安装,跳过")
        payload["opportunity_scan"] = None
    except Exception as e:
        logger.warning(f"  ⚠️ 机会仓扫描失败: {str(e)[:120]}")
        payload["opportunity_scan"] = None

    # v1.3新增: 宏观6维度采集(ETF净申赎/融资比/全A换手/ERP/全A宽度/M1同比)
    logger.info("[9/10] 宏观环境采集(6维度)...")
    try:
        from macro_indicators import collect_macro_indicators
        # 当 yc_cb 接口无权限时,使用 secrets.json 的 yield_10y_pct 作为 ERP 计算的兜底
        yield_fb = float(DATA_SOURCES_CONFIG.get("yield_10y_pct", 2.30))
        payload["macro"] = collect_macro_indicators(TUSHARE, fallback_yield_10y_pct=yield_fb)
        regime = payload["macro"].get("macro_regime", "未知")
        bull = payload["macro"].get("bullish_count", 0)
        bear = payload["macro"].get("bearish_count", 0)
        n_err = len(payload["macro"].get("errors", []) or [])
        logger.info(f"  ✅ Macro Regime: {regime} (✅×{bull} / ❌×{bear}, 错误×{n_err})")
        if n_err > 0:
            for err in payload["macro"]["errors"]:
                logger.warning(f"     - 宏观采集错误: {err}")
    except ImportError:
        logger.warning("  ⚠️ macro_indicators.py 未安装,跳过宏观采集")
        payload["macro"] = None
    except Exception as e:
        logger.warning(f"  ⚠️ 宏观采集失败: {str(e)[:120]}")
        payload["macro"] = None

    return payload


def _normalize_emails(value) -> List[str]:
    """把字符串/列表/逗号分隔串统一规范成 list[str],去空去重保序"""
    if not value:
        return []
    raw = []
    if isinstance(value, str):
        # 支持 "a@x.com, b@y.com" 或 "a@x.com; b@y.com"
        raw = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    cleaned = []
    seen = set()
    for e in raw:
        if not e:
            continue
        s = str(e).strip()
        if s and s not in seen:
            seen.add(s)
            cleaned.append(s)
    return cleaned


def send_email(html_content: str, attachments: List[Tuple[str, str, str]]) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"📊 股票汇总(增强版) {today}"

    # 规范化收件人列表
    to_list = _normalize_emails(EMAIL_CONFIG.get("receiver_email"))
    cc_list = _normalize_emails(EMAIL_CONFIG.get("cc_email"))
    bcc_list = _normalize_emails(EMAIL_CONFIG.get("bcc_email"))

    if not to_list:
        logger.error("❌ 没有配置收件人(receiver_email),跳过发送")
        return False

    msg = MIMEMultipart()
    msg["From"] = Header(EMAIL_CONFIG["sender_email"])
    msg["To"] = Header(", ".join(to_list))            # 多个收件人用逗号分隔
    if cc_list:
        msg["Cc"] = Header(", ".join(cc_list))        # 抄送写入邮件头
    # 注意: Bcc 不写入邮件头,否则就不"密"了,只在投递时传
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    for filename, path, subtype in attachments:
        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", filename))
        msg.attach(part)

    # 实际投递的所有收件人 = To + Cc + Bcc
    all_recipients = to_list + cc_list + bcc_list

    try:
        smtp = smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
        smtp.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
        smtp.sendmail(EMAIL_CONFIG["sender_email"], all_recipients, msg.as_string())
        smtp.quit()
        logger.info(f"✅ 邮件已发送 → 收件人{len(to_list)}个 / 抄送{len(cc_list)}个 / 密送{len(bcc_list)}个")
        return True
    except Exception as e:
        logger.error(f"❌ 邮件发送失败: {e}")
        return False


def cleanup_old_files(days_to_keep: int = 7, dry_run: bool = False) -> Dict[str, int]:
    """清理脚本生成的旧文件
    - 保留最近 days_to_keep 天的报告/JSON/MD/HTML
    - 清理 .cache_tushare 中超过30天的缓存
    - 清理 logs/ 和 cron.log 中超过30天的日志(只清内容,不删文件)

    可独立调用: python -c "from stock_report_enhanced import cleanup_old_files; cleanup_old_files()"
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    now = time.time()
    cutoff_reports = now - days_to_keep * 86400
    cutoff_cache = now - 30 * 86400

    stats = {
        "json_removed": 0,
        "md_removed": 0,
        "html_removed": 0,
        "cache_removed": 0,
        "kb_freed": 0,
    }

    # 1. 清理报告类文件(JSON/MD/HTML)
    patterns = [
        ("claude_stock_metrics_", ".json", "json_removed"),
        ("claude_stock_prompt_", ".md", "md_removed"),
        ("stock_report_", ".html", "html_removed"),
    ]
    for prefix, suffix, stat_key in patterns:
        for f in os.listdir(script_dir):
            if not (f.startswith(prefix) and f.endswith(suffix)):
                continue
            path = os.path.join(script_dir, f)
            try:
                mtime = os.path.getmtime(path)
                if mtime < cutoff_reports:
                    size_kb = os.path.getsize(path) / 1024
                    if not dry_run:
                        os.remove(path)
                    stats[stat_key] += 1
                    stats["kb_freed"] += size_kb
            except Exception as e:
                logger.debug(f"清理 {f} 失败: {e}")

    # 2. 清理缓存目录中30天前的文件
    cache_dir = os.path.join(script_dir, ".cache_tushare")
    if os.path.isdir(cache_dir):
        for f in os.listdir(cache_dir):
            path = os.path.join(cache_dir, f)
            try:
                if os.path.getmtime(path) < cutoff_cache:
                    size_kb = os.path.getsize(path) / 1024
                    if not dry_run:
                        os.remove(path)
                    stats["cache_removed"] += 1
                    stats["kb_freed"] += size_kb
            except Exception:
                pass

    # 3. 清理 cron.log (只保留最近1000行,避免无限增长)
    cron_log = os.path.join(script_dir, "cron.log")
    if os.path.exists(cron_log) and not dry_run:
        try:
            with open(cron_log, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if len(lines) > 1000:
                with open(cron_log, "w", encoding="utf-8") as f:
                    f.writelines(lines[-1000:])
                logger.debug(f"cron.log已裁剪: {len(lines)} → 1000行")
        except Exception:
            pass

    action = "将删除(试运行)" if dry_run else "已清理"
    logger.info(
        f"🧹 {action}: JSON{stats['json_removed']}个 / "
        f"MD{stats['md_removed']}个 / HTML{stats['html_removed']}个 / "
        f"缓存{stats['cache_removed']}个 / 释放{stats['kb_freed']:.1f}KB"
    )
    return stats


def main() -> int:
    logger.info("=" * 60)
    logger.info("开始生成股票报告(增强版)")
    if TUSHARE is not None:
        logger.info(f"📊 数据源: 新浪(实时)+东财(板块/大盘)+Tushare Lv{TUSHARE.points_level}(已启用)")
    else:
        logger.error("❌ Tushare未启用,核心功能(K线/估值/财务/资金流)将不可用!")
        logger.error("   请检查 secrets.json 的 tushare_token 配置 (或环境变量 TUSHARE_TOKEN)")
    logger.info("=" * 60)

    try:
        payload = collect_payload()
        html_report = render_html_report(payload)
        attachments = write_attachments(payload)

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        html_backup = f"stock_report_{ts}.html"
        with open(html_backup, "w", encoding="utf-8") as f:
            f.write(html_report)
        logger.info(f"📝 HTML备份: {html_backup}")

        send_email(html_report, attachments)

        # 任务完成后自动清理旧文件(从配置读 cleanup_keep_days,默认7天)
        keep_days = DATA_SOURCES_CONFIG.get("cleanup_keep_days", 7)
        if keep_days and keep_days > 0:
            cleanup_old_files(days_to_keep=keep_days)

        logger.info("✅ 任务完成")
        return 0
    except Exception as e:
        logger.exception(f"❌ 任务异常: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())