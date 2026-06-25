# -*- coding: utf-8 -*-
"""东方财富数据源。

从单体脚本 script/stock_report_enhanced.py 原样搬运, 逻辑零改动。
搬运时的调整(均不改变行为):
    - logger 改用 logging.getLogger(__name__)
    - EM_HEADERS 改为引用 config.EM_HEADERS
    - safe_float / safe_int 改为从 vaxstock.util 显式导入
    - 函数内重复出现的东财 ut 参数抽成模块常量 EM_UT_QUOTE / EM_UT_CLIST
      (这是东财公开接口的固定值, 非个人密钥)

注意: import 本模块不触发任何网络请求(顶层只定义常量与函数)。
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from vaxstock import config
from vaxstock.util import safe_float, safe_int

logger = logging.getLogger(__name__)

# 东财公开接口固定 ut 值(非个人密钥), 抽成常量供各函数引用:
#   EM_UT_QUOTE —— 个股行情/资金 (/api/qt/stock/get、fflow/daykline)
#   EM_UT_CLIST —— 列表类接口   (/api/qt/clist/get: 板块排行、大盘涨跌统计)
EM_UT_QUOTE = "fa5fd1943c7b386f172d6893dbfba10b"
EM_UT_CLIST = "bd1d9ddb04089700cf9c27f6f7426281"

# 东财备用域名(VPS网络偶尔到主域名不稳)
EM_HOSTS = [
    "https://push2.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://20.push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
]


def code_to_eastmoney(code: str) -> str:
    """东方财富用1.前缀代表沪市,0.前缀代表深市"""
    if code.startswith(("6", "9")):
        return f"1.{code}"
    return f"0.{code}"


def _em_get(path: str, params: Dict[str, Any], timeout: int = 8, retries: int = 3) -> Optional[Dict[str, Any]]:
    """东财通用GET,自动切换主备域名 + 重试 + 容忍非JSON"""
    last_err = None
    for attempt in range(retries):
        host = EM_HOSTS[attempt % len(EM_HOSTS)]
        url = host + path
        try:
            r = requests.get(url, params=params, headers=config.EM_HEADERS, timeout=timeout)
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
        "ut": EM_UT_QUOTE,
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
            "ut": EM_UT_QUOTE,
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        }
        # 这个接口在 push2his.eastmoney.com,直接调用一次
        try:
            r2 = requests.get("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get",
                              params=p2, headers=config.EM_HEADERS, timeout=8)
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
            "ut": EM_UT_CLIST,
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
                "ut": EM_UT_CLIST,
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
