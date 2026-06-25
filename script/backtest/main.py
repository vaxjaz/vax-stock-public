#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子IC回测框架 — 主入口
========================

更新模式说明：
  incremental  默认: 日频数据接着本地最新日期往后拉,财务/股东户数仅在30天未更新时才刷
  smart        智能更新(同上)
  full         全量重拉(慎用,Tushare积分消耗大)
  fundamentals 强制重拉所有公司的财务指标+股东户数(财报季后用)
  none         跳过数据更新,直接用缓存

典型用法：
  # 首次部署(全量下载,约15-30分钟)
  python main.py --update full

  # 每个交易日盘后(增量更新+回测,约1-2分钟)
  python main.py

  # 财报季后(4月/8月/10月)强制刷新基本面
  python main.py --update fundamentals --skip-backtest

  # 只重算因子+回测(不动数据)
  python main.py --update none --recalc

  # 自定义时间窗口
  python main.py --start 20240101 --end 20251231

  # 只看数据状态(不下载不回测)
  python main.py --status
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from data_loader import DataStore, init_loader
from factor_calculator import calc_all_factors
from ic_engine import run_all_factor_ic, print_ic_summary
from quantile_engine import run_all_quantile_backtest, print_quantile_summary
from report_generator import generate_html_report

logger = logging.getLogger(__name__)


def setup_logging():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


# ==================== 数据状态检查 ====================

def show_data_status():
    """打印当前缓存状态,帮助判断是否需要更新"""
    store = DataStore()
    pool = store.get_pool_metadata()
    codes = store.get_codes("stock_pool")

    print(f"\n{'='*70}")
    print(f"📦 本地数据状态")
    print(f"{'='*70}")

    if not pool:
        print("⚠️ 无股票池数据,请先运行: python main.py --update full")
        store.close()
        return

    print(f"股票池: {pool['pool_name']} ({pool['count']}只)")
    print(f"池更新日: {pool['last_updated']}")
    try:
        age = (datetime.now() - datetime.strptime(pool['last_updated'], "%Y%m%d")).days
        print(f"池更新距今: {age}天 {'⚠️建议刷新' if age > 90 else '✅'}")
    except Exception:
        pass

    # 抽样几只股票的最新日期
    if len(codes) >= 10:
        sample_codes = codes[:3] + codes[len(codes)//2:len(codes)//2+2] + codes[-2:]
    else:
        sample_codes = codes
    print(f"\n各表最新日期(抽样{len(sample_codes)}只):")
    print(f"{'代码':<10} {'K线':<12} {'估值':<12} {'资金流':<12} {'财务公告':<12} {'股东公告':<12}")
    print("-" * 78)
    for code in sample_codes:
        k = store.get_last_date("daily_kline", code) or "-"
        b = store.get_last_date("daily_basic", code) or "-"
        f = store.get_last_date("moneyflow", code) or "-"
        fi = store.get_last_date("fina_indicator", code, "ann_date") or "-"
        h = store.get_last_date("holder_number", code, "ann_date") or "-"
        print(f"{code:<10} {k:<12} {b:<12} {f:<12} {fi:<12} {h:<12}")

    # 统计总条数
    n_kline = store.conn.execute("SELECT COUNT(*) FROM daily_kline").fetchone()[0]
    n_basic = store.conn.execute("SELECT COUNT(*) FROM daily_basic").fetchone()[0]
    n_flow = store.conn.execute("SELECT COUNT(*) FROM moneyflow").fetchone()[0]
    n_fina = store.conn.execute("SELECT COUNT(*) FROM fina_indicator").fetchone()[0]
    n_holder = store.conn.execute("SELECT COUNT(*) FROM holder_number").fetchone()[0]
    print(f"\n总记录: K线{n_kline:,} | 估值{n_basic:,} | 资金流{n_flow:,} | 财务{n_fina:,} | 股东{n_holder:,}")

    if os.path.exists(config.DB_PATH):
        size_mb = os.path.getsize(config.DB_PATH) / 1024 / 1024
        print(f"数据库大小: {size_mb:.1f} MB")

    # 因子矩阵
    factor_path = os.path.join(config.DATA_DIR, "factors.parquet")
    if os.path.exists(factor_path):
        mtime = datetime.fromtimestamp(os.path.getmtime(factor_path)).strftime("%Y-%m-%d %H:%M")
        size_mb = os.path.getsize(factor_path) / 1024 / 1024
        print(f"因子矩阵: {size_mb:.1f} MB, 最后生成: {mtime}")
    else:
        print("因子矩阵: 未生成")

    print(f"{'='*70}\n")
    store.close()


# ==================== 数据更新 ====================

def step_update_data(mode: str = "incremental", refresh_pool: bool = False):
    """更新数据"""
    logger.info("=" * 60)
    logger.info(f"步骤1: 更新数据 [模式: {mode}]")
    logger.info("=" * 60)

    store, loader = init_loader()

    # 股票池处理
    codes = store.get_codes("stock_pool")
    if not codes or refresh_pool:
        logger.info(f"📋 刷新股票池成分股 ({config.STOCK_POOL})...")
        codes = loader.load_index_pool(config.STOCK_POOL)
    else:
        # 自动判断池子是否过期(>90天)
        pool = store.get_pool_metadata()
        if pool and pool.get("last_updated"):
            try:
                age = (datetime.now() - datetime.strptime(pool["last_updated"], "%Y%m%d")).days
                if age > 90:
                    logger.info(f"⚠️ 股票池已{age}天未更新,自动刷新...")
                    codes = loader.load_index_pool(config.STOCK_POOL)
                else:
                    logger.info(f"📋 使用缓存股票池: {len(codes)}只 (距上次{age}天)")
            except Exception:
                logger.info(f"📋 使用缓存股票池: {len(codes)}只")

    # 映射mode → loader参数
    if mode == "full":
        loader.load_all_for_pool(codes, mode="full")
    elif mode == "fundamentals":
        loader.load_all_for_pool(codes, mode="incremental", refresh_fundamentals=True)
    else:  # incremental / smart
        loader.load_all_for_pool(codes, mode="incremental", refresh_fundamentals=False)

    store.close()


# ==================== 因子计算与回测 ====================

def step_calc_factors():
    logger.info("=" * 60)
    logger.info("步骤2: 计算因子")
    logger.info("=" * 60)

    store = DataStore()
    df = calc_all_factors(store)
    store.close()

    if len(df) == 0:
        logger.error("❌ 因子矩阵为空,请检查数据是否下载完整")
        sys.exit(1)

    out_path = os.path.join(config.DATA_DIR, "factors.parquet")
    df.to_parquet(out_path, index=False)
    logger.info(f"💾 因子矩阵已保存: {out_path}")
    return df


def step_ic_backtest(df):
    logger.info("=" * 60)
    logger.info("步骤3: IC回测")
    logger.info("=" * 60)
    results = run_all_factor_ic(df)
    print_ic_summary(results, primary_window=10)
    return results


def step_quantile_backtest(df):
    logger.info("=" * 60)
    logger.info("步骤4: 分位回测")
    logger.info("=" * 60)
    results = run_all_quantile_backtest(df, return_window=10)
    print_quantile_summary(results)
    return results


def step_report(ic_results, q_results, df):
    logger.info("=" * 60)
    logger.info("步骤5: 生成HTML报告")
    logger.info("=" * 60)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = os.path.join(config.REPORT_DIR, f"ic_report_{ts}.html")
    generate_html_report(ic_results, q_results, df, out_path)
    return out_path


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(
        description="因子IC回测框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--update", "-u",
        choices=["incremental", "smart", "full", "fundamentals", "none"],
        default="incremental",
        help="数据更新模式 (默认incremental)"
    )
    parser.add_argument("--refresh-pool", action="store_true",
                        help="强制刷新沪深300成分股名单")
    parser.add_argument("--recalc", action="store_true",
                        help="重新计算因子矩阵")
    parser.add_argument("--skip-backtest", action="store_true",
                        help="只更新数据,不跑回测(适合财报季快速刷新)")
    parser.add_argument("--status", action="store_true",
                        help="只显示数据状态,不执行任何操作")
    parser.add_argument("--start", type=str, default=None,
                        help="回测起始日期 (YYYYMMDD)")
    parser.add_argument("--end", type=str, default=None,
                        help="回测结束日期 (YYYYMMDD)")

    args = parser.parse_args()
    setup_logging()

    # --status: 只看不做
    if args.status:
        show_data_status()
        return

    if args.start:
        config.BACKTEST_START_DATE = args.start
    if args.end:
        config.BACKTEST_END_DATE = args.end

    logger.info(f"\n{'#'*60}")
    logger.info(f"# 因子IC回测框架 v1.0")
    logger.info(f"# 数据更新: {args.update} | 回测: {'跳过' if args.skip_backtest else '执行'}")
    logger.info(f"# 回测期: {config.BACKTEST_START_DATE} ~ {config.BACKTEST_END_DATE}")
    logger.info(f"{'#'*60}\n")

    # 步骤1: 数据更新
    if args.update == "none":
        logger.info("📦 跳过数据更新 (--update none)")
        store = DataStore()
        if len(store.get_codes("stock_pool")) == 0:
            store.close()
            logger.error("❌ 本地无数据,请先: python main.py --update full")
            sys.exit(1)
        store.close()
    else:
        step_update_data(mode=args.update, refresh_pool=args.refresh_pool)

    # 仅更新数据
    if args.skip_backtest:
        logger.info("✅ 仅更新数据,跳过回测 (--skip-backtest)")
        return

    # 步骤2: 因子计算
    factor_path = os.path.join(config.DATA_DIR, "factors.parquet")
    need_recalc = args.recalc or args.update not in ("none",) or not os.path.exists(factor_path)
    if need_recalc:
        df = step_calc_factors()
    else:
        logger.info(f"📊 读取已有因子矩阵: {factor_path}")
        df = pd.read_parquet(factor_path)

    # 步骤3-4: 回测
    ic_results = step_ic_backtest(df)
    q_results = step_quantile_backtest(df)

    # 步骤5: 报告
    report_path = step_report(ic_results, q_results, df)

    logger.info(f"\n{'='*60}")
    logger.info(f"✅ 全部完成")
    logger.info(f"📄 报告: {report_path}")
    logger.info(f"{'='*60}\n")


if __name__ == "__main__":
    main()
