# -*- coding: utf-8 -*-
"""ai.py — AIDC(AI数据中心)赛道独立择时(MR-Track #2)。

由 monolith script/ai_track_system.py 迁入新包并改造成符合 tracks/contract.py 契约:
  - 类 AITrackSystem -> AITrack, 构造参数 tushare_source -> source(沿用包内显式传参, 无全局)
  - evaluate 拆成可测三段: _fetch_all(网络) / _assemble(纯函数, 不碰网络) / evaluate(粘合)
  - _assemble 严格产出 contract.TrackResult: 档位用 contract 常量(不硬编码字符串),
    关键信号缺失走 contract.pending_result(不臆造档位), 信号自带合法 status(P0 可追溯)
  - 删除 monolith 底部 `from tushare_source import TushareSource` 老 import 与硬路径 secrets

分层: ai 是赛道取数+算结论层, 可依赖 sources.tushare_src 与 akshare/pandas/numpy(运行依赖);
      只有 contract.py 是叶子, 契约不反向依赖 ai。
重依赖(numpy/pandas/akshare/yfinance)一律方法内懒导入, 故 import 本模块不连网、不需要这些包,
保证 _assemble 纯函数可零依赖单测。

设计原则(对齐 P0): 三道硬否决(veto) + 仓位梯度门控, 不做主观加权; 缺数据标"待验证"不 fallback。
免责: 仅供研究, 不构成投资建议。
"""

import datetime as dt
import logging
import threading
from typing import Dict, List, Optional

from vaxstock.sources.tushare_src import TushareSource
from vaxstock.tracks import contract

logger = logging.getLogger("ai_track")

TRACK_NAME = "AI算力"
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


# ============================================================
# 纯函数 seam: summary_lines 与 _assemble (零网络, 可单测)
# ============================================================

def _summary_lines(prosp: Dict, gate: Dict, qvix: Dict, crowd: Dict) -> List[str]:
    """四段每信号显示行(从旧 render 抽出)。

    只产信号显示行——标题/三否决块/档位/pending 等外框不在此(归 report 层 MR5)。
    """
    lines: List[str] = []

    # 【景气·NVDA capex】
    p = prosp or {}
    if p.get("signal"):
        lines.append(f"【景气·NVDA capex】{p['signal']}  [{p.get('status')}]")
        lines.append(f"  营收YoY {p.get('yoy_pct')}% | QoQ {p.get('qoq_pct')}% | "
                     f"加速度 {p.get('accel_pp')}pp | 最新季营收 {p.get('latest_rev_busd')}亿美元")
    else:
        lines.append(f"【景气·NVDA capex】🚫待验证 — {p.get('note', '')}")

    # 【海外闸门·SOX】
    g = gate or {}
    if g.get("gate_open") is not None:
        状态 = "✅开放" if g["gate_open"] else "❌关闭"
        lines.append(f"【海外闸门·SOX】{状态}  收{g.get('sox_close')} / MA50 {g.get('sox_ma50')} / "
                     f"近1月{g.get('mom_1m_pct')}%")
        if g.get("trigger"):
            lines.append(f"  触发: {'; '.join(g['trigger'])}")
    else:
        lines.append(f"【海外闸门·SOX】🚫待验证 — {g.get('note', '')}")

    # 【本土情绪·QVIX】
    q = qvix or {}
    if q.get("status") == "已证实":
        lines.append(f"【本土情绪·QVIX】{q.get('mood', '')}  "
                     f"300ETF {q.get('qvix_300')} / 创业板 {q.get('qvix_cyb')}")
    else:
        lines.append(f"【本土情绪·QVIX】🚫待验证 — {q.get('note', '')}")

    # 【篮子拥挤度】
    c = crowd or {}
    tp = c.get("turnover_pctile")
    bp = c.get("basket_52w_pos")
    if tp is not None or bp is not None:
        if tp is not None and bp is not None:
            lines.append(f"【篮子拥挤度】换手分位 {tp*100:.0f}% / 篮子52周位置 {bp*100:.0f}%  [{c.get('status')}]")
        else:
            lines.append(f"【篮子拥挤度】部分可得 换手{tp} 位置{bp} [{c.get('status')}]")
        if c.get("missing"):
            lines.append(f"  缺失: {c['missing']}")
    else:
        lines.append(f"【篮子拥挤度】🚫待验证 — {c.get('note', '')}")

    return lines


def _assemble(signals: Dict, date: str) -> "contract.TrackResult":
    """纯函数: 三道硬否决 + 仓位梯度 + pending + summary_lines, 组装成 contract.TrackResult。

    不碰网络。档位全部用 contract 常量(数据缺失=PENDING_CEILING 精确相等; 其余=档位前缀)。
    关键信号(景气 signal / 闸门 gate_open)缺失 -> 走 contract.pending_result, 不臆造档位。
    """
    prosp = signals.get("prosperity") or {}
    gate = signals.get("sox_gate") or {}
    qvix = signals.get("qvix") or {}
    crowd = signals.get("crowding") or {}

    summary = _summary_lines(prosp, gate, qvix, crowd)

    # ---- 关键信号缺失 -> pending(available=False, 档位强制 PENDING_CEILING, 不臆造)----
    if prosp.get("signal") is None or gate.get("gate_open") is None:
        miss: List[str] = []
        if prosp.get("signal") is None:
            miss.append("景气(NVDA)")
        if gate.get("gate_open") is None:
            miss.append("海外闸门(SOX)")
        reason = "关键信号缺失(" + " / ".join(miss) + "), 不出仓位结论"
        result = contract.pending_result(TRACK_NAME, date, reason,
                                         pending_dims=miss, signals=signals)
        # 仍展示已取到的四段信号行(report 用), 替换 pending_result 默认的 reason 行
        result["summary_lines"] = summary
        return result

    # ---- 三道硬否决(veto), 任一触发即压仓(非加权稀释)----
    vetoes: List = []
    # 否决1: 海外闸门
    if gate.get("gate_open") is False:
        vetoes.append(("海外闸门", f"SOX {','.join(gate.get('trigger', []))} → AI上限砍半"))
    # 否决2: 拥挤度
    tp = crowd.get("turnover_pctile")
    bp = crowd.get("basket_52w_pos")
    if (tp is not None and tp > 0.90) or (bp is not None and bp > 0.90):
        why = []
        if tp is not None and tp > 0.90:
            why.append(f"换手分位{tp*100:.0f}%>90")
        if bp is not None and bp > 0.90:
            why.append(f"篮子52周位置{bp*100:.0f}%>90")
        vetoes.append(("拥挤度", f"{','.join(why)} → 禁止加仓"))
    # 否决3: 景气证伪
    if prosp.get("signal") == "❌景气转负":
        vetoes.append(("景气证伪", "NVDA营收YoY转负 → 清仓级信号"))

    veto_names = [v[0] for v in vetoes]

    # ---- 仓位档位梯度(门控, 非加权; 用 contract 档位常量前缀, 后缀括号说明)----
    if len(vetoes) == 0 and prosp.get("signal", "").startswith("✅") and gate.get("gate_open"):
        pos_ceiling = f"{contract.CEILING_OFFENSE} (赛道上限~高位, 可加)"
    elif "景气证伪" in veto_names:
        pos_ceiling = f"{contract.CEILING_LIQUIDATE} (景气破裂)"
    elif len(vetoes) >= 2:
        pos_ceiling = f"{contract.CEILING_DEFENSE} (多重否决, 大幅压仓)"
    elif len(vetoes) == 1:
        pos_ceiling = f"{contract.CEILING_REDUCE} (单否决, 不加且高位减)"
    else:
        pos_ceiling = f"{contract.CEILING_NEUTRAL} (景气走弱但无否决, 持有不加)"

    pending = [name for name, v in [("景气", prosp.get("signal")),
                                    ("海外闸门", gate.get("gate_open")),
                                    ("本土情绪", qvix.get("status"))] if v is None]

    return {
        "track_name": TRACK_NAME,
        "date": date,
        "available": pos_ceiling != contract.PENDING_CEILING,
        "signals": signals,
        "summary_lines": summary,
        "vetoes": vetoes,
        "position_ceiling": pos_ceiling,
        "pending": pending,
    }


# ============================================================
# AITrack: 取数(网络)层
# ============================================================

class AITrack:
    def __init__(self, source: Optional[TushareSource] = None):
        """source: TushareSource 实例(取A股行情/财务, 用于篮子拥挤度)。
        海外/期权数据走 AkShare(已验证)。沿用包内显式传参, 无全局态。"""
        self.source = source

    # ---- 景气层 (最高优先级: NVDA capex nowcast) ----
    def fetch_nvda_prosperity(self) -> Dict:
        """NVDA 季度营收 YoY + 加速度, 衡量海外AI capex景气。
        主源 AkShare stock_financial_us_report_em, yfinance交叉验证。
        P0: 双源不一致 -> 标待验证不采信。"""
        import pandas as pd
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

    # ---- 海外闸门 (SOX 风向标) ----
    def fetch_sox_gate(self) -> Dict:
        """SOX 费城半导体: 跌破MA50 或 近1月动量转负 -> 闸门关闭(AI仓位上限砍半)。
        实测接口 index_us_stock_sina('.SOX')。"""
        import pandas as pd
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

    # ---- 本土情绪 (QVIX) ----
    def fetch_qvix(self) -> Dict:
        """300ETF QVIX(大盘恐慌) + 创业板QVIX(AI赛道情绪, 更敏感)。
        实测接口 index_option_300etf_qvix / index_option_cyb_qvix。"""
        import pandas as pd
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

    # ---- 篮子拥挤度 (全篮子换手率分位 + 52周位置) ----
    def fetch_basket_crowding(self) -> Dict:
        """全篮子(含688/300)平均换手率历史分位 + 篮子整体52周位置。
        走 Tushare daily_basic(换手率) + daily(价格)。
        P0: 任一股取数失败计入缺失数, 缺失过半标待验证。"""
        import numpy as np
        import pandas as pd
        result = {"status": "待验证"}
        if self.source is None or not getattr(self.source, "enabled", False):
            result["note"] = "TushareSource不可用, 拥挤度待验证"
            return result

        end = dt.date.today()
        start = end - dt.timedelta(days=365 + 60)
        s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

        turn_frames, pos_list, missing = [], [], []
        for item in AIDC_BASKET:
            code = item["code"]
            db = self.source._safe_call("daily_basic", ts_code=code, start_date=s, end_date=e,
                                        fields="trade_date,turnover_rate")
            dl = self.source._safe_call("daily", ts_code=code, start_date=s, end_date=e,
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

    # ---- 三段式 evaluate ----
    def _fetch_all(self) -> Dict:
        """调四个 fetch_*(网络)。"""
        return {
            "prosperity": self.fetch_nvda_prosperity(),
            "sox_gate": self.fetch_sox_gate(),
            "qvix": self.fetch_qvix(),
            "crowding": self.fetch_basket_crowding(),
        }

    def evaluate(self) -> "contract.TrackResult":
        """产出 AI 赛道 TrackResult。= _assemble(self._fetch_all(), 今日)。"""
        return _assemble(self._fetch_all(), str(dt.date.today()))


if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        logger.warning("未设置环境变量 TUSHARE_TOKEN, 篮子拥挤度维度将标待验证")
    src = TushareSource(token) if token else None
    track = AITrack(source=src)
    result = track.evaluate()

    print("\n".join(result["summary_lines"]))
    print(f"\n★ 赛道仓位档位: {result['position_ceiling']}  (available={result['available']})")
    if result["vetoes"]:
        for nm, why in result["vetoes"]:
            print(f"  🚫 {nm}: {why}")
    if result["pending"]:
        print(f"  ⚠️ 待验证维度: {result['pending']}")

    errs = contract.validate(result)
    print(f"\ncontract.validate(result) -> {errs if errs else '[] (合规)'}")
