#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据加载与SQLite缓存
====================
功能：
1. 从Tushare下载沪深300成分股的：
   - 日K线（含估值PE/PB/换手）
   - 个股资金流向
   - 财务指标（ROE、净利同比等）
   - 股东户数（按ann_date公告日存储）
2. 缓存到本地SQLite，避免重复下载

设计原则：
- 数据下载只发生一次（除非用 --force-update）
- SQLite单文件部署，避免数据库依赖
- 股东户数表保存ann_date，因子计算时按公告日动态生效
"""

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

# 导入主项目配置。脚本可能放在 /opt/stock-report 根目录或 scripts/ 子目录，
# 所以优先使用 VPS 固定项目目录，其次再回退到当前文件目录/父目录。
def _resolve_project_root() -> str:
    candidates = [
        os.getenv("STOCK_REPORT_ROOT"),
        "/opt/stock-report",
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ]
    for path in candidates:
        if path and os.path.exists(os.path.join(path, "config.py")):
            return path
    # 最后兜底：保持原逻辑，便于在开发机暴露 import 错误
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PROJECT_ROOT = _resolve_project_root()
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config

logger = logging.getLogger(__name__)


# ==================== SQLite Schema ====================

SCHEMA = {
    "stock_pool": """
                  CREATE TABLE IF NOT EXISTS stock_pool (
                                                            code TEXT PRIMARY KEY,
                                                            name TEXT,
                                                            pool_name TEXT,
                                                            in_date TEXT,
                                                            out_date TEXT
                  )
                  """,
    "daily_kline": """
                   CREATE TABLE IF NOT EXISTS daily_kline (
                                                              code TEXT,
                                                              trade_date TEXT,
                                                              open REAL, high REAL, low REAL, close REAL,
                                                              volume REAL, amount REAL,
                                                              pct_chg REAL,
                                                              PRIMARY KEY (code, trade_date)
                       )
                   """,
    "daily_basic": """
                   CREATE TABLE IF NOT EXISTS daily_basic (
                                                              code TEXT,
                                                              trade_date TEXT,
                                                              turnover_rate REAL,
                                                              pe_ttm REAL, pb REAL, ps_ttm REAL,
                                                              total_mv REAL, circ_mv REAL,
                                                              PRIMARY KEY (code, trade_date)
                       )
                   """,
    "moneyflow": """
                 CREATE TABLE IF NOT EXISTS moneyflow (
                                                          code TEXT,
                                                          trade_date TEXT,
                                                          buy_sm_amount REAL, sell_sm_amount REAL,
                                                          buy_md_amount REAL, sell_md_amount REAL,
                                                          buy_lg_amount REAL, sell_lg_amount REAL,
                                                          buy_elg_amount REAL, sell_elg_amount REAL,
                                                          net_mf_amount REAL,
                                                          PRIMARY KEY (code, trade_date)
                     )
                 """,
    "fina_indicator": """
                      CREATE TABLE IF NOT EXISTS fina_indicator (
                                                                    code TEXT,
                                                                    end_date TEXT,
                                                                    ann_date TEXT,
                                                                    roe REAL, roe_dt REAL,
                                                                    grossprofit_margin REAL, netprofit_margin REAL,
                                                                    debt_to_assets REAL,
                                                                    netprofit_yoy REAL, or_yoy REAL, op_yoy REAL,
                                                                    q_npincome_yoy REAL,
                                                                    PRIMARY KEY (code, end_date)
                          )
                      """,
    "holder_number": """
                     CREATE TABLE IF NOT EXISTS holder_number (
                                                                  code TEXT,
                                                                  end_date TEXT,
                                                                  ann_date TEXT,
                                                                  holder_num INTEGER,
                                                                  PRIMARY KEY (code, end_date)
                         )
                     """,
    "fetch_log": """
                 CREATE TABLE IF NOT EXISTS fetch_log (
                                                          code TEXT,
                                                          table_name TEXT,
                                                          last_fetch_date TEXT,
                                                          row_count INTEGER,
                                                          PRIMARY KEY (code, table_name)
                     )
                 """,
}


# ==================== 数据库管理 ====================

class DataStore:
    """SQLite封装"""

    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self):
        for table_name, sql in SCHEMA.items():
            self.conn.execute(sql)
        # 索引
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline(trade_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_basic_date ON daily_basic(trade_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_flow_date ON moneyflow(trade_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_fina_ann ON fina_indicator(ann_date)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_holder_ann ON holder_number(ann_date)")
        self.conn.commit()

    def upsert_dataframe(self, table: str, df: pd.DataFrame):
        """批量 upsert。

        pandas.to_sql(if_exists="append") 在 SQLite 主键冲突时会直接报
        IntegrityError，不是真正 upsert。这里使用 INSERT OR REPLACE，
        兼容重复拉取、Tushare 返回重复行、以及 force/full 模式重跑。
        """
        if df is None or len(df) == 0:
            return 0

        df = df.copy()
        df = df.where(pd.notnull(df), None)
        columns = list(df.columns)
        placeholders = ",".join(["?"] * len(columns))
        col_sql = ",".join([f'"{c}"' for c in columns])
        sql = f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES ({placeholders})'
        self.conn.executemany(sql, df.itertuples(index=False, name=None))
        self.conn.commit()
        return len(df)

    def has_data(self, table: str, code: str) -> bool:
        cursor = self.conn.execute(f"SELECT 1 FROM {table} WHERE code=? LIMIT 1", (code,))
        return cursor.fetchone() is not None

    def get_last_date(self, table: str, code: str, date_col: str = "trade_date") -> Optional[str]:
        """查询某只股票在某表中最后一条记录的日期。用于增量更新判断起始点。"""
        try:
            cursor = self.conn.execute(
                f"SELECT MAX({date_col}) FROM {table} WHERE code=?", (code,)
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
        except sqlite3.OperationalError:
            return None

    def get_pool_metadata(self) -> Optional[dict]:
        """读取股票池元数据（最后更新日期等）"""
        try:
            cursor = self.conn.execute(
                "SELECT pool_name, MAX(in_date), COUNT(*) FROM stock_pool GROUP BY pool_name"
            )
            row = cursor.fetchone()
            if row:
                return {"pool_name": row[0], "last_updated": row[1], "count": row[2]}
        except sqlite3.OperationalError:
            pass
        return None

    def get_codes(self, table: str = "stock_pool") -> List[str]:
        cursor = self.conn.execute(f"SELECT code FROM {table}")
        return [row[0] for row in cursor.fetchall()]

    def query(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        return pd.read_sql_query(sql, self.conn, params=params)

    def get_last_date(self, table: str, code: str, date_col: str = "trade_date") -> Optional[str]:
        """查询某只股票在某张表里的最新日期（用于增量更新）"""
        cursor = self.conn.execute(
            f"SELECT MAX({date_col}) FROM {table} WHERE code=?", (code,)
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else None

    def get_pool_meta(self, pool_name: str = "hs300") -> Optional[Dict]:
        """查询股票池元信息（最后更新日期）"""
        cursor = self.conn.execute(
            "SELECT MIN(in_date), MAX(in_date), COUNT(*) FROM stock_pool WHERE pool_name=?",
            (pool_name,)
        )
        row = cursor.fetchone()
        if not row or not row[2]:
            return None
        return {"first_date": row[0], "last_date": row[1], "count": row[2]}

    def close(self):
        self.conn.close()


# ==================== Tushare 拉取 ====================

class TushareLoader:
    """从Tushare下载数据并存入SQLite"""

    def __init__(self, token: str, store: DataStore):
        import tushare as ts
        ts.set_token(token)
        self.pro = ts.pro_api()
        self.store = store
        self._call_timestamps = []

    def _rate_limit(self):
        """限流保护"""
        now = time.time()
        self._call_timestamps = [t for t in self._call_timestamps if now - t < 60]
        if len(self._call_timestamps) >= config.RATE_LIMIT_PER_MIN:
            wait = 60 - (now - self._call_timestamps[0]) + config.RATE_LIMIT_BUFFER
            if wait > 0:
                logger.debug(f"  限流，等待{wait:.1f}秒...")
                time.sleep(wait)
        self._call_timestamps.append(time.time())

    def _safe_call(self, func_name: str, **kwargs) -> Optional[pd.DataFrame]:
        try:
            self._rate_limit()
            df = getattr(self.pro, func_name)(**kwargs)
            if df is None or len(df) == 0:
                return None
            return df
        except Exception as e:
            logger.warning(f"  {func_name} 失败: {str(e)[:120]}")
            return None

    @staticmethod
    def code_to_ts(code: str) -> str:
        code = str(code).strip()
        if "." in code:
            return code
        if code.startswith(("6", "9")):
            return f"{code}.SH"
        return f"{code}.SZ"

    @staticmethod
    def ts_to_code(ts_code: str) -> str:
        return ts_code.split(".")[0] if "." in ts_code else ts_code

    # ====== 1. 沪深300成分股 ======

    # 指数池配置: pool_name → (index_code, 中文名)
    INDEX_POOL_MAP = {
        "hs300": ("000300.SH", "沪深300"),
        "zz800": ("000906.SH", "中证800"),   # 中证800 = 沪深300 + 中证500
        "zz500": ("000905.SH", "中证500"),
        "zz1000": ("000852.SH", "中证1000"),
    }

    def load_hs300_pool(self, force: bool = False, refresh_days: int = 90):
        """向后兼容入口: 沪深300。内部调用通用 load_index_pool。"""
        return self.load_index_pool("hs300", force=force, refresh_days=refresh_days)

    def load_index_pool(self, pool_name: str = "hs300",
                        force: bool = False, refresh_days: int = 90):
        """构建指定指数的【历史时变】成分池(修复幸存者偏差)。
        遍历回测窗口内多个调仓日,取成分股并集,纳入期间被调出/退市的股票,
        用 in_date/out_date 记录每只股票的成分区间。
        pool_name 见 INDEX_POOL_MAP (hs300/zz800/zz500/zz1000)。"""
        if pool_name not in self.INDEX_POOL_MAP:
            raise ValueError(f"未知股票池 {pool_name}, 可选: {list(self.INDEX_POOL_MAP)}")
        index_code, cn_name = self.INDEX_POOL_MAP[pool_name]

        meta = self.store.get_pool_meta(pool_name)
        if not force and meta:
            try:
                last_dt = datetime.strptime(meta["last_date"], "%Y%m%d")
                age_days = (datetime.now() - last_dt).days
                if age_days <= refresh_days:
                    logger.info(f"📋 {cn_name}历史成分池缓存有效 ({meta['count']}只, {age_days}天前)")
                    return [row[0] for row in
                            self.store.conn.execute(
                                "SELECT code FROM stock_pool WHERE pool_name=?", (pool_name,)).fetchall()]
                else:
                    logger.info(f"📋 {cn_name}历史成分池缓存过期({age_days}天前),重新构建")
            except Exception:
                pass

        logger.info(f"📥 构建{cn_name}历史时变成分池(修复幸存者偏差,区间查询)...")
        start = datetime.strptime(config.DATA_FETCH_START_DATE, "%Y%m%d")
        end = datetime.now()

        # index_weight 单日 trade_date 常返回空(权重非每日发布),必须用半年区间查
        seen, latest_td, ok_dates = {}, None, 0
        seg_start = start
        while seg_start < end:
            seg_end = min(seg_start + timedelta(days=180), end)
            df = self._safe_call("index_weight", index_code=index_code,
                                 start_date=seg_start.strftime("%Y%m%d"),
                                 end_date=seg_end.strftime("%Y%m%d"))
            if df is not None and len(df) > 0:
                ok_dates += 1
                for td, g in df.groupby("trade_date"):
                    for ts_code in g["con_code"]:
                        code = self.ts_to_code(ts_code)
                        if code not in seen:
                            seen[code] = {"first": td, "last": td}
                        else:
                            seen[code]["last"] = max(seen[code]["last"], td)
                            seen[code]["first"] = min(seen[code]["first"], td)
                    if latest_td is None or td > latest_td:
                        latest_td = td
            seg_start = seg_end + timedelta(days=1)

        latest_snapshot = {c for c, sp in seen.items() if sp["last"] == latest_td}

        if not seen:
            logger.error(f"❌ {cn_name}历史成分构建失败(所有调仓日均无数据)")
            if meta:
                logger.warning(f"⚠️ 降级使用过期缓存 ({meta['count']}只)")
                return [row[0] for row in
                        self.store.conn.execute(
                            "SELECT code FROM stock_pool WHERE pool_name=?", (pool_name,)).fetchall()]
            return []

        rows, codes = [], []
        for code, span in seen.items():
            codes.append(code)
            still_in = code in latest_snapshot
            rows.append({
                "code": code, "name": "", "pool_name": pool_name,
                "in_date": span["first"],
                "out_date": None if still_in else span["last"],
            })

        name_map = {}
        for st in ("L", "D", "P"):
            basic = self._safe_call("stock_basic", list_status=st, fields="ts_code,symbol,name")
            if basic is not None:
                for _, r in basic.iterrows():
                    name_map[r["symbol"]] = r["name"]
        for r in rows:
            r["name"] = name_map.get(r["code"], "")

        self.store.conn.execute("DELETE FROM stock_pool WHERE pool_name=?", (pool_name,))
        self.store.upsert_dataframe("stock_pool", pd.DataFrame(rows))
        logger.info(f"  ✅ {cn_name}历史时变成分池 {len(codes)}只 "
                    f"(成功调仓日{ok_dates}个, 最新在册{len(latest_snapshot)}只, "
                    f"含已调出/退市{len(codes)-len(latest_snapshot)}只)")
        return codes

    # ====== 2. 日K线 ======

    def load_daily_kline(self, code: str, start_date: str, end_date: str):
        ts_code = self.code_to_ts(code)
        # 【FIX】用 pro_bar 前复权(qfq)修复未复权 bug。
        # 注意:pro_bar 是 ts 模块级函数,不能走 _safe_call(那是 self.pro 的方法)
        import tushare as ts
        try:
            self._rate_limit()
            df = ts.pro_bar(ts_code=ts_code, adj="qfq",
                            start_date=start_date, end_date=end_date,
                            api=self.pro)
        except Exception as e:
            logger.warning(f"  pro_bar 失败 {code}: {str(e)[:120]}")
            df = None
        if df is None or len(df) == 0:
            return 0
        df = df.rename(columns={"vol": "volume"})
        df["code"] = code
        cols = ["code", "trade_date", "open", "high", "low", "close",
                "volume", "amount", "pct_chg"]
        df = df[[c for c in cols if c in df.columns]]
        self.store.conn.execute(
            "DELETE FROM daily_kline WHERE code=? AND trade_date>=? AND trade_date<=?",
            (code, start_date, end_date)
        )
        return self.store.upsert_dataframe("daily_kline", df)

    # ====== 3. 估值 ======

    def load_daily_basic(self, code: str, start_date: str, end_date: str):
        ts_code = self.code_to_ts(code)
        df = self._safe_call("daily_basic", ts_code=ts_code,
                             start_date=start_date, end_date=end_date,
                             fields="ts_code,trade_date,turnover_rate,pe_ttm,pb,ps_ttm,total_mv,circ_mv")
        if df is None:
            return 0
        df["code"] = code
        df = df[["code", "trade_date", "turnover_rate", "pe_ttm", "pb", "ps_ttm", "total_mv", "circ_mv"]]
        self.store.conn.execute(
            "DELETE FROM daily_basic WHERE code=? AND trade_date>=? AND trade_date<=?",
            (code, start_date, end_date)
        )
        return self.store.upsert_dataframe("daily_basic", df)

    # ====== 4. 资金流向 ======

    def load_moneyflow(self, code: str, start_date: str, end_date: str):
        ts_code = self.code_to_ts(code)
        df = self._safe_call("moneyflow", ts_code=ts_code,
                             start_date=start_date, end_date=end_date)
        if df is None:
            return 0
        df["code"] = code
        keep = ["code", "trade_date",
                "buy_sm_amount", "sell_sm_amount",
                "buy_md_amount", "sell_md_amount",
                "buy_lg_amount", "sell_lg_amount",
                "buy_elg_amount", "sell_elg_amount",
                "net_mf_amount"]
        df = df[[c for c in keep if c in df.columns]]
        self.store.conn.execute(
            "DELETE FROM moneyflow WHERE code=? AND trade_date>=? AND trade_date<=?",
            (code, start_date, end_date)
        )
        return self.store.upsert_dataframe("moneyflow", df)

    # ====== 5. 财务（按ann_date存储，覆盖3年）======

    def load_fina_indicator(self, code: str):
        ts_code = self.code_to_ts(code)
        df = self._safe_call("fina_indicator", ts_code=ts_code,
                             fields="ts_code,ann_date,end_date,roe,roe_dt,"
                                    "grossprofit_margin,netprofit_margin,debt_to_assets,"
                                    "netprofit_yoy,or_yoy,op_yoy,q_npincome_yoy")
        if df is None:
            return 0
        df["code"] = code
        keep = ["code", "end_date", "ann_date", "roe", "roe_dt",
                "grossprofit_margin", "netprofit_margin", "debt_to_assets",
                "netprofit_yoy", "or_yoy", "op_yoy", "q_npincome_yoy"]
        df = df[[c for c in keep if c in df.columns]]
        # 去重保留每个end_date最新ann_date
        df = df.sort_values(["end_date", "ann_date"], ascending=[False, False])
        df = df.drop_duplicates(subset=["code", "end_date"], keep="first")
        self.store.conn.execute("DELETE FROM fina_indicator WHERE code=?", (code,))
        return self.store.upsert_dataframe("fina_indicator", df)

    # ====== 6. 股东户数（核心：ann_date动态生效）======

    def load_holder_number(self, code: str):
        ts_code = self.code_to_ts(code)
        df = self._safe_call("stk_holdernumber", ts_code=ts_code)
        if df is None:
            return 0
        df["code"] = code
        keep = ["code", "end_date", "ann_date", "holder_num"]
        df = df[[c for c in keep if c in df.columns]]
        df = df.drop_duplicates(subset=["code", "end_date"], keep="first")
        self.store.conn.execute("DELETE FROM holder_number WHERE code=?", (code,))
        return self.store.upsert_dataframe("holder_number", df)

    # ====== 增量更新工具 ======

    def _next_date(self, date_str: str) -> str:
        """YYYYMMDD 字符串 +1 天"""
        dt = datetime.strptime(date_str, "%Y%m%d") + timedelta(days=1)
        return dt.strftime("%Y%m%d")

    def _need_update_day_data(self, code: str, table: str, end_date: str) -> Optional[str]:
        """
        判断需要增量拉取的起始日期。

        返回：
            None  → 无需更新（本地最新日期已 >= end_date）
            "YYYYMMDD" → 从这个日期开始增量拉取
        """
        last = self.store.get_last_date(table, code)
        if last is None:
            # 本地无数据，从默认起始日期全量拉
            return config.DATA_FETCH_START_DATE
        # 本地有数据，从最新日期+1开始
        start = self._next_date(last)
        # 如果起始日已超过end_date，无需更新
        return start if start <= end_date else None

    def _need_update_fundamentals(self, code: str, table: str, days_threshold: int = 30) -> bool:
        """
        判断财务/股东户数表是否需要刷新。

        策略：本地最新ann_date距今超过threshold天 → 重拉（可能有新财报披露）
        """
        cursor = self.store.conn.execute(
            f"SELECT MAX(ann_date) FROM {table} WHERE code=?", (code,)
        )
        row = cursor.fetchone()
        if not row or not row[0]:
            return True  # 无数据，必须拉
        last_ann = row[0]
        try:
            last_dt = datetime.strptime(last_ann, "%Y%m%d")
            age_days = (datetime.now() - last_dt).days
            return age_days > days_threshold
        except Exception:
            return True

    # ====== 主流程 ======

    def load_all_for_pool(self, codes: List[str],
                          start_date: str = config.DATA_FETCH_START_DATE,
                          end_date: str = config.BACKTEST_END_DATE,
                          mode: str = "incremental",
                          refresh_fundamentals: bool = False):
        """
        批量更新整个股票池的数据。

        Args:
            codes: 股票代码列表
            start_date: 全量拉取时的起始日期（仅mode="full"时生效）
            end_date: 拉取结束日期
            mode:
                "incremental" - 增量模式（推荐）。日频数据从本地最新日期+1开始拉，
                                财务/股东户数按30天阈值判断是否刷新
                "full"        - 全量模式。所有数据从start_date拉到end_date，覆盖本地
                "skip_existing" - 旧行为：已有数据的股票完全跳过
            refresh_fundamentals: True则强制重拉财务+股东户数（财报季使用）
        """
        total = len(codes)
        logger.info(f"📥 开始更新 {total} 只股票 [模式={mode}, 截止={end_date}]")

        success_count = 0
        updated_kline = updated_basic = updated_flow = updated_fina = updated_holder = 0

        for i, code in enumerate(codes, 1):
            try:
                # ---- 日频数据：K线 / 估值 / 资金流 ----
                if mode == "skip_existing" and self.store.has_data("daily_kline", code):
                    if i % 50 == 0:
                        logger.info(f"  [{i}/{total}] 已有缓存，跳过 {code}")
                    continue

                if mode == "full":
                    k_start = start_date
                    b_start = start_date
                    f_start = start_date
                else:  # incremental
                    k_start = self._need_update_day_data(code, "daily_kline", end_date)
                    b_start = self._need_update_day_data(code, "daily_basic", end_date)
                    f_start = self._need_update_day_data(code, "moneyflow", end_date)

                n_kline = self.load_daily_kline(code, k_start, end_date) if k_start else 0
                n_basic = self.load_daily_basic(code, b_start, end_date) if b_start else 0
                n_flow = self.load_moneyflow(code, f_start, end_date) if f_start else 0
                updated_kline += n_kline
                updated_basic += n_basic
                updated_flow += n_flow

                # ---- 季度数据：财务 / 股东户数 ----
                # 财务数据量小（每股5-20条），重拉成本低
                need_fina = (refresh_fundamentals or mode == "full" or
                             self._need_update_fundamentals(code, "fina_indicator"))
                need_holder = (refresh_fundamentals or mode == "full" or
                               self._need_update_fundamentals(code, "holder_number"))

                n_fina = self.load_fina_indicator(code) if need_fina else 0
                n_hold = self.load_holder_number(code) if need_holder else 0
                updated_fina += n_fina
                updated_holder += n_hold

                success_count += 1

                # 日志：增量模式有更新才打印，全量模式按进度打印
                if mode == "full":
                    if i % 10 == 0 or i == total:
                        logger.info(f"  [{i}/{total}] {code}: K{n_kline} B{n_basic} F{n_flow} 财{n_fina} 股{n_hold}")
                else:
                    has_update = any([n_kline, n_basic, n_flow, n_fina, n_hold])
                    if has_update:
                        parts = []
                        if n_kline: parts.append(f"K线+{n_kline}")
                        if n_basic: parts.append(f"估值+{n_basic}")
                        if n_flow: parts.append(f"资金+{n_flow}")
                        if n_fina: parts.append(f"财务刷新{n_fina}")
                        if n_hold: parts.append(f"股东刷新{n_hold}")
                        logger.info(f"  [{i}/{total}] {code}: {' / '.join(parts)}")
                    elif i % 50 == 0:
                        logger.info(f"  [{i}/{total}] 已最新，无需更新")

            except Exception as e:
                logger.warning(f"  ⚠️ [{i}/{total}] {code} 失败: {str(e)[:80]}")

        logger.info(
            f"✅ 数据更新完成: {success_count}/{total} 成功 | "
            f"新增 K线{updated_kline} 估值{updated_basic} 资金{updated_flow} | "
            f"刷新 财务{updated_fina} 股东{updated_holder}"
        )
        return success_count


# ==================== 入口 ====================

def load_tushare_token() -> Optional[str]:
    """读取 Tushare token。

    v2 架构下 token 只允许从 secrets.json 或环境变量读取，
    不再读取已废弃的 portfolio.json，避免敏感配置和业务配置混放。

    优先级：
      1. /opt/stock-report/secrets.json
      2. $STOCK_REPORT_ROOT/secrets.json 或 PROJECT_ROOT/secrets.json
      3. 当前脚本同目录 secrets.json
      4. 环境变量 TUSHARE_TOKEN
    """
    secret_paths = []
    for path in (
            "/opt/stock-report/secrets.json",
            os.path.join(PROJECT_ROOT, "secrets.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.json"),
    ):
        if path not in secret_paths:
            secret_paths.append(path)

    for secrets_path in secret_paths:
        if not os.path.exists(secrets_path):
            continue
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            token = cfg.get("tushare_token")
            if token:
                logger.info("✅ 已从 %s 加载 Tushare token", secrets_path)
                return str(token).strip()
            logger.warning("⚠️ %s 存在但 tushare_token 为空", secrets_path)
        except Exception as e:
            logger.warning("⚠️ 读取 %s 失败: %s", secrets_path, e)

    env_token = os.getenv("TUSHARE_TOKEN")
    if env_token:
        logger.info("✅ 已从环境变量 TUSHARE_TOKEN 加载 Tushare token")
        return env_token.strip()

    return None


def init_loader() -> tuple:
    """初始化 DataStore + TushareLoader"""
    token = load_tushare_token()
    if not token:
        raise RuntimeError(
            "Tushare token未配置：请在 /opt/stock-report/secrets.json 中配置 tushare_token，"
            "或设置环境变量 TUSHARE_TOKEN"
        )

    store = DataStore()
    loader = TushareLoader(token, store)
    return store, loader


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    store, loader = init_loader()
    codes = loader.load_hs300_pool()
    # 默认增量模式
    loader.load_all_for_pool(codes, mode="incremental")
    store.close()
