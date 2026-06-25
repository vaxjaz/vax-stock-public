# -*- coding: utf-8 -*-
"""
ai_track_system.py — AIDC(AI数据中心)赛道独立择时体系
================================================================
定位: 独立于主体系(v1.4)的赛道择时, 管"主攻AI那部分钱", 自带风控、自负盈亏。
     不替代、不污染主体系的 macro regime。两套逻辑物理隔离。

设计原则(全部对齐 Vax 的 P0 数据完整性铁律):
  1. 借鉴 main.py 的逻辑内核(景气前瞻 + 海外闸门 + 赛道独立评估),
     但丢弃其全部毛病: 主观加权 / except:pass 静默吞错 / yfinance不可靠源 / 满仓空仓二元。
  2. 数据源全部已实测验证(2026-06-25 on VPS):
       - SOX 海外风向标:  ak.index_us_stock_sina(".SOX")          [实测✓ 值正确]
       - QVIX 本土情绪:   ak.index_option_300etf_qvix / _cyb_qvix [实测✓]
       - NVDA 景气(最高优先级): ak.stock_financial_us_report_em    [实测✓ 双源交叉验证]
         + yfinance 交叉验证(一致才采信, 不一致标待验证)
  3. 不做主观加权综合分。改"三道硬否决(veto) + 仓位梯度"门控逻辑。
  4. 缺数据 -> 标"待验证", 绝不 fallback 给中性分污染决策。
  5. 篮子成分一旦定义即为系统根基, 显式标注板块归属与可交易性。

输出: 独立的 AI 赛道日报(景气/闸门/情绪/拥挤度/三否决/赛道仓位上限),
     与主 EOD 报告并列, 不混入 macro regime。

免责: 仅供研究, 不构成投资建议。
"""
import json
import logging
import threading
import datetime as dt
from typing import Optional, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger("ai_track")

AK_CALL_TIMEOUT = 20  # AkShare 墙钟超时(秒), 沿用主体系 daemon线程+join 模式


# ============================================================
# AIDC 全产业链篮子 (依据券商研报各环节龙头, 2026-06 梳理)
#   trade: 'main'=主板可交易 / 'star'=688永久禁 / 'gem'=300创业板(2026-09前禁)
#   景气/拥挤度用【全篮子】; 仓位信号只对 trade=='main' (9月后纳入'gem')
# ============================================================
AIDC_BASKET = [
    # --- 算力·AI芯片 ---
    {"code": "688256.SH", "name": "寒武纪",   "seg": "算力·芯片", "trade": "star"},
    {"code": "688041.SH", "name": "海光信息", "seg": "算力·芯片", "trade": "star"},
    {"code": "688008.SH", "name": "澜起科技", "seg": "算力·芯片", "trade": "star"},
    # --- 算力·服务器 ---
    {"code": "601138.SH", "name": "工业富联", "seg": "算力·服务器", "trade": "main"},
    # --- 运力·光模块/CPO ---
    {"code": "300308.SZ", "name": "中际旭创", "seg": "运力·光模块", "trade": "gem"},
    {"code": "300502.SZ", "name": "新易盛",   "seg": "运力·光模块", "trade": "gem"},
    {"code": "300394.SZ", "name": "天孚通信", "seg": "运力·光模块", "trade": "gem"},
    # --- 运力·连接器 ---
    {"code": "002475.SZ", "name": "立讯精密", "seg": "运力·连接", "trade": "main"},
    # --- infra·PCB ---
    {"code": "002463.SZ", "name": "沪电股份", "seg": "infra·PCB", "trade": "main"},
    {"code": "300476.SZ", "name": "胜宏科技", "seg": "infra·PCB", "trade": "gem"},
    {"code": "002384.SZ", "name": "东山精密", "seg": "infra·PCB", "trade": "main"},
    {"code": "688183.SH", "name": "生益电子", "seg": "infra·PCB", "trade": "star"},
    {"code": "600183.SH", "name": "生益科技", "seg": "infra·覆铜板", "trade": "main"},
    # --- infra·PCB材料 ---
    {"code": "300054.SZ", "name": "鼎龙股份", "seg": "infra·材料", "trade": "gem"},
    # --- infra·HVLP高频高速铜箔 (AI服务器/高速PCB核心基材; 仅纳AIDC绑定, 锂电铜箔不计) ---
    {"code": "301217.SZ", "name": "铜冠铜箔", "seg": "infra·铜箔", "trade": "gem"},
    {"code": "301511.SZ", "name": "德福科技", "seg": "infra·铜箔", "trade": "gem"},
    {"code": "600522.SH", "name": "中天科技", "seg": "infra·铜箔", "trade": "main"},
    # --- 半导体设备 ---
    {"code": "002371.SZ", "name": "北方华创", "seg": "算力·设备", "trade": "main"},
    # --- 电力·液冷温控 ---
    {"code": "002837.SZ", "name": "英维克",   "seg": "电力·液冷", "trade": "main"},
    # --- 电力·算力电源 ---
    {"code": "002364.SZ", "name": "中恒电气", "seg": "电力·电源", "trade": "main"},
    {"code": "300540.SZ", "name": "欧陆通",   "seg": "电力·电源", "trade": "gem"},
    # --- infra·IDC运营 ---
    {"code": "300442.SZ", "name": "润泽科技", "seg": "infra·IDC", "trade": "gem"},
    {"code": "603881.SH", "name": "数据港",   "seg": "infra·IDC", "trade": "main"},
    {"code": "002929.SZ", "name": "润建股份", "seg": "infra·IDC", "trade": "main"},
    # --- 配电 ---
    {"code": "688676.SH", "name": "金盘科技", "seg": "电力·配电", "trade": "star"},
    {"code": "600875.SH", "name": "东方电气", "seg": "电力·配电", "trade": "main"},
]


def _ak_safe(fn_name: str, **kwargs):
    """AkShare 调用包装: daemon线程 + join(timeout), 真·墙钟超时。
    沿用主体系 _safe_call 模式(不用 ThreadPoolExecutor, 其 shutdown(wait=True) 会废掉超时)。
    失败/超时 -> None (上层标待验证, 不 fallback)。"""
    import akshare as ak
    box = {}

    def _run():
        try:
            box["df"] = getattr(ak, fn_name)(**kwargs)
        except Exception as e:
            box["err"] = e

    t = threading.Thread(target=_run, name=f"ak_{fn_name}", daemon=True)
    t.start()
    t.join(AK_CALL_TIMEOUT)
    if t.is_alive():
        logger.warning(f"  ⏱ ak.{fn_name} 超时>{AK_CALL_TIMEOUT}s, 放弃")
        return None
    if "err" in box:
        logger.warning(f"  ⚠️ ak.{fn_name} 失败: {str(box['err'])[:120]}")
        return None
    return box.get("df")


class AITrackSystem:
    def __init__(self, tushare_source=None):
        """tushare_source: 复用主体系的 TushareSource 实例(取A股行情/财务)。
        海外/期权数据走 AkShare(已验证)。"""
        self.ts = tushare_source

    # ========================================================
    # 景气层 (最高优先级: NVDA capex nowcast)
    # ========================================================
    def fetch_nvda_prosperity(self) -> Dict:
        """NVDA 季度营收 YoY + 加速度, 衡量海外AI capex景气。
        主源 AkShare stock_financial_us_report_em, yfinance交叉验证。
        P0: 双源不一致 -> 标待验证不采信。"""
        result = {"signal": None, "status": "待验证"}

        df = _ak_safe("stock_financial_us_report_em",
                      stock="NVDA", symbol="综合损益表", indicator="单季报")
        if df is None or len(df) == 0:
            result["note"] = "NVDA营收获取失败(ak), 景气待验证"
            return result

        # 主营收入行: STD_ITEM_CODE 004001001 (实测确认)
        try:
            rev_df = df[df["STD_ITEM_CODE"] == "004001001"].copy()
            rev_df["REPORT_DATE"] = pd.to_datetime(rev_df["REPORT_DATE"])
            rev_df = rev_df.sort_values("REPORT_DATE")
            rev = rev_df["AMOUNT"].astype(float).values
        except Exception as e:
            result["note"] = f"NVDA营收解析失败: {e}"
            return result

        if len(rev) < 5:
            result["note"] = f"NVDA季度数{len(rev)}<5, 不足算YoY, 待验证"
            return result

        yoy = rev[-1] / rev[-5] - 1
        qoq_now = rev[-1] / rev[-2] - 1
        qoq_prev = rev[-2] / rev[-3] - 1
        accel = qoq_now - qoq_prev

        # --- yfinance 交叉验证(P0: 单源不采信) ---
        cross_ok = None
        try:
            import yfinance as yf
            yrev = yf.Ticker("NVDA").quarterly_income_stmt.loc["Total Revenue"].dropna().astype(float).sort_index()
            if len(yrev) >= 1:
                latest_ak = rev[-1]
                latest_yf = float(yrev.iloc[-1])
                cross_ok = abs(latest_ak - latest_yf) / latest_ak < 0.02  # 2%容差
        except Exception:
            cross_ok = None  # yfinance不可用, 单源标注

        # --- 三态(借鉴脚本F1, 但严格化) ---
        if yoy > 0 and accel >= 0:
            sig = "✅扩张加速"
        elif yoy > 0:
            sig = "⚠️扩张走弱"
        else:
            sig = "❌景气转负"

        result.update({
            "signal": sig,
            "status": "已证实" if cross_ok else ("单源待交叉验证" if cross_ok is None else "双源冲突待验证"),
            "yoy_pct": round(yoy * 100, 1),
            "qoq_pct": round(qoq_now * 100, 1),
            "accel_pp": round(accel * 100, 1),
            "latest_rev_busd": round(rev[-1] / 1e8, 1),  # 亿美元
            "cross_validated": cross_ok,
        })
        return result

    # ========================================================
    # 海外闸门 (SOX 风向标)
    # ========================================================
    def fetch_sox_gate(self) -> Dict:
        """SOX 费城半导体: 跌破MA50 或 近1月动量转负 -> 闸门关闭(AI仓位上限砍半)。
        实测接口 index_us_stock_sina('.SOX')。"""
        result = {"gate_open": None, "status": "待验证"}

        df = _ak_safe("index_us_stock_sina", symbol=".SOX")
        if df is None or len(df) < 60:
            result["note"] = "SOX获取失败或历史不足, 闸门待验证"
            return result

        df = df.sort_values("date")
        close = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(close) < 60:
            result["note"] = "SOX有效收盘不足, 待验证"
            return result

        latest = float(close.iloc[-1])
        ma50 = float(close.tail(50).mean())
        mom_1m = float(close.iloc[-1] / close.iloc[-21] - 1)  # 近21交易日动量

        above_ma50 = latest > ma50
        mom_positive = mom_1m > 0
        # 闸门: 必须 站上MA50 AND 近1月动量为正 才开放
        gate_open = above_ma50 and mom_positive

        result.update({
            "gate_open": gate_open,
            "status": "已证实",
            "sox_close": round(latest, 1),
            "sox_ma50": round(ma50, 1),
            "above_ma50": above_ma50,
            "mom_1m_pct": round(mom_1m * 100, 1),
            "trigger": [] if gate_open else
            ([f"跌破MA50({ma50:.0f})"] if not above_ma50 else []) +
            ([f"近1月动量转负({mom_1m*100:+.1f}%)"] if not mom_positive else []),
        })
        return result

    # ========================================================
    # 本土情绪 (QVIX)
    # ========================================================
    def fetch_qvix(self) -> Dict:
        """300ETF QVIX(大盘恐慌) + 创业板QVIX(AI赛道情绪, 更敏感)。
        实测接口 index_option_300etf_qvix / index_option_cyb_qvix。"""
        result = {"status": "待验证"}

        def _latest(fn):
            df = _ak_safe(fn)
            if df is None or len(df) == 0:
                return None
            df = df.sort_values("date")
            return float(pd.to_numeric(df["close"], errors="coerce").dropna().iloc[-1])

        q300 = _latest("index_option_300etf_qvix")
        qcyb = _latest("index_option_cyb_qvix")

        if q300 is None and qcyb is None:
            result["note"] = "QVIX全部获取失败, 待验证"
            return result

        result.update({"status": "已证实", "qvix_300": q300, "qvix_cyb": qcyb})
        # 情绪标注: 创业板QVIX是AI主战场情绪
        if qcyb is not None:
            if qcyb >= 45:
                result["mood"] = "❌恐慌极端(创业板QVIX≥45)"
            elif qcyb >= 35:
                result["mood"] = "⚠️情绪偏紧(创业板QVIX≥35)"
            else:
                result["mood"] = "✅情绪平稳"
        return result

    # ========================================================
    # 篮子拥挤度 (全篮子换手率分位 + 52周位置)
    # ========================================================
    def fetch_basket_crowding(self) -> Dict:
        """全篮子(含688/300)平均换手率历史分位 + 篮子整体52周位置。
        走 Tushare daily_basic(换手率) + daily(价格)。
        P0: 任一股取数失败计入缺失数, 缺失过半标待验证。"""
        result = {"status": "待验证"}
        if self.ts is None or not getattr(self.ts, "enabled", False):
            result["note"] = "TushareSource不可用, 拥挤度待验证"
            return result

        end = dt.date.today()
        start = end - dt.timedelta(days=365 + 60)
        s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

        turn_frames, pos_list, missing = [], [], []
        for item in AIDC_BASKET:
            code = item["code"]
            db = self.ts._safe_call("daily_basic", ts_code=code, start_date=s, end_date=e,
                                    fields="trade_date,turnover_rate")
            dl = self.ts._safe_call("daily", ts_code=code, start_date=s, end_date=e,
                                    fields="trade_date,close")
            if db is None or len(db) == 0 or dl is None or len(dl) == 0:
                missing.append(item["name"])
                continue
            tr = db.set_index("trade_date")["turnover_rate"].rename(code)
            turn_frames.append(tr)
            # 52周位置
            c = pd.to_numeric(dl["close"], errors="coerce").dropna()
            if len(c) > 0:
                lo, hi = c.min(), c.max()
                if hi > lo:
                    pos_list.append((c.iloc[0] - lo) / (hi - lo))  # daily降序, iloc[0]=最新

        n_total = len(AIDC_BASKET)
        if len(missing) > n_total / 2:
            result["note"] = f"篮子取数缺失过半({len(missing)}/{n_total}): {missing[:5]}, 拥挤度待验证"
            return result

        # 换手率分位: 篮子日均换手 -> 历史分位
        turn_pctile = None
        if turn_frames:
            t = pd.concat(turn_frames, axis=1).sort_index().mean(axis=1).dropna()
            if len(t) >= 60:
                turn_pctile = float(t.rank(pct=True).iloc[-1])

        basket_pos = float(np.mean(pos_list)) if pos_list else None

        result.update({
            "status": "已证实" if not missing else f"部分缺失({len(missing)})",
            "turnover_pctile": round(turn_pctile, 3) if turn_pctile is not None else None,
            "basket_52w_pos": round(basket_pos, 3) if basket_pos is not None else None,
            "missing": missing,
        })
        return result

    # ========================================================
    # 综合: 三道硬否决 + 仓位梯度
    # ========================================================
    def evaluate(self) -> Dict:
        """产出 AI 赛道日报。三道硬veto任一触发即压仓, 非加权稀释。"""
        prosp = self.fetch_nvda_prosperity()
        gate = self.fetch_sox_gate()
        qvix = self.fetch_qvix()
        crowd = self.fetch_basket_crowding()

        vetoes = []
        # --- 否决1: 海外闸门 ---
        if gate.get("gate_open") is False:
            vetoes.append(("海外闸门", f"SOX {','.join(gate.get('trigger', []))} → AI上限砍半"))
        # --- 否决2: 拥挤度 ---
        tp = crowd.get("turnover_pctile")
        bp = crowd.get("basket_52w_pos")
        if (tp is not None and tp > 0.90) or (bp is not None and bp > 0.90):
            why = []
            if tp is not None and tp > 0.90:
                why.append(f"换手分位{tp*100:.0f}%>90")
            if bp is not None and bp > 0.90:
                why.append(f"篮子52周位置{bp*100:.0f}%>90")
            vetoes.append(("拥挤度", f"{','.join(why)} → 禁止加仓"))
        # --- 否决3: 景气证伪 ---
        if prosp.get("signal") == "❌景气转负":
            vetoes.append(("景气证伪", "NVDA营收YoY转负 → 清仓级信号"))

        # --- 仓位梯度(门控, 非加权) ---
        # 基准: 景气✅且闸门开 = 满档; 每触发一道veto降一档
        base = "禁区(0)"
        待验证项 = [k for k, v in [("景气", prosp.get("signal")),
                                   ("闸门", gate.get("gate_open")),
                                   ("情绪", qvix.get("status"))] if v is None]
        if prosp.get("signal") is None or gate.get("gate_open") is None:
            pos_ceiling = "待验证(数据缺失, 不出仓位结论)"
        elif len(vetoes) == 0 and prosp.get("signal", "").startswith("✅") and gate.get("gate_open"):
            pos_ceiling = "进攻档 (赛道上限~高位, 可加)"
        elif "景气证伪" in [v[0] for v in vetoes]:
            pos_ceiling = "清仓档 (景气破裂)"
        elif len(vetoes) >= 2:
            pos_ceiling = "防御档 (多重否决, 大幅压仓)"
        elif len(vetoes) == 1:
            pos_ceiling = "减档 (单否决, 不加且高位减)"
        else:
            pos_ceiling = "中性档 (景气走弱但无否决, 持有不加)"

        return {
            "date": str(dt.date.today()),
            "prosperity": prosp,
            "sox_gate": gate,
            "qvix": qvix,
            "crowding": crowd,
            "vetoes": vetoes,
            "position_ceiling": pos_ceiling,
            "pending": 待验证项,
        }

    # ========================================================
    # 渲染日报
    # ========================================================
    def render(self) -> str:
        r = self.evaluate()
        L = [f"# AI赛道独立择时日报  {r['date']}", "=" * 44,
             "(独立体系, 不并入 macro regime; 仅供研究)", ""]

        p = r["prosperity"]
        if p.get("signal"):
            L.append(f"【景气·NVDA capex】{p['signal']}  [{p['status']}]")
            L.append(f"  营收YoY {p.get('yoy_pct')}% | QoQ {p.get('qoq_pct')}% | "
                     f"加速度 {p.get('accel_pp')}pp | 最新季营收 {p.get('latest_rev_busd')}亿美元")
        else:
            L.append(f"【景气·NVDA capex】🚫待验证 — {p.get('note','')}")

        g = r["sox_gate"]
        if g.get("gate_open") is not None:
            状态 = "✅开放" if g["gate_open"] else "❌关闭"
            L.append(f"【海外闸门·SOX】{状态}  收{g.get('sox_close')} / MA50 {g.get('sox_ma50')} / "
                     f"近1月{g.get('mom_1m_pct')}%")
            if g.get("trigger"):
                L.append(f"  触发: {'; '.join(g['trigger'])}")
        else:
            L.append(f"【海外闸门·SOX】🚫待验证 — {g.get('note','')}")

        q = r["qvix"]
        if q.get("status") == "已证实":
            L.append(f"【本土情绪·QVIX】{q.get('mood','')}  "
                     f"300ETF {q.get('qvix_300')} / 创业板 {q.get('qvix_cyb')}")
        else:
            L.append(f"【本土情绪·QVIX】🚫待验证 — {q.get('note','')}")

        c = r["crowding"]
        if c.get("turnover_pctile") is not None or c.get("basket_52w_pos") is not None:
            tp = c.get("turnover_pctile")
            bp = c.get("basket_52w_pos")
            L.append(f"【篮子拥挤度】换手分位 {tp*100:.0f}% / 篮子52周位置 {bp*100:.0f}%  [{c.get('status')}]"
                     if tp is not None and bp is not None else
                     f"【篮子拥挤度】部分可得 换手{tp} 位置{bp} [{c.get('status')}]")
            if c.get("missing"):
                L.append(f"  缺失: {c['missing']}")
        else:
            L.append(f"【篮子拥挤度】🚫待验证 — {c.get('note','')}")

        L += ["", "—— 三道硬否决(veto) ——"]
        if r["vetoes"]:
            for name, why in r["vetoes"]:
                L.append(f"  🚫 {name}: {why}")
        else:
            L.append("  ✅ 无否决触发")

        L += ["", f"★ 赛道仓位档位: {r['position_ceiling']}"]
        if r["pending"]:
            L.append(f"  ⚠️ 待验证维度: {r['pending']}(数据不全, 结论保守)")
        L += ["", "—— 仅供研究, 不构成投资建议 ——"]
        return "\n".join(L)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import sys
    sys.path.insert(0, "/opt/stock-report")
    try:
        from tushare_source import TushareSource
        sec = json.load(open("/opt/stock-report/secrets.json"))
        ts_src = TushareSource(sec.get("tushare_token"))
    except Exception as ex:
        logger.warning(f"TushareSource 初始化失败({ex}), 拥挤度维度将标待验证")
        ts_src = None
    sys_ = AITrackSystem(ts_src)
    print(sys_.render())