#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML回测报告生成器
==================
将IC和分位回测结果输出为可读的HTML报告，包含：
1. 因子IC排名表（T+5/T+10/T+20三个窗口）
2. 分位回测汇总表
3. 每个因子的IC时序曲线和累计收益曲线（base64嵌入PNG）
4. 评估结论
"""

import base64
import io
import logging
import os
import sys
from datetime import datetime
from typing import Dict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config

logger = logging.getLogger(__name__)


# ==================== 可选 matplotlib ====================

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    PLOT_OK = True
except ImportError:
    PLOT_OK = False
    logger.warning("⚠️ matplotlib未安装，图表功能禁用")


def fig_to_base64(fig) -> str:
    """将matplotlib figure转为base64字符串"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=80, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    plt.close(fig)
    return f"data:image/png;base64,{encoded}"


def plot_ic_series(ic_df: pd.DataFrame, factor_label: str) -> str:
    """绘制IC时序曲线 + 累计IC"""
    if not PLOT_OK or len(ic_df) == 0:
        return ""

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5), sharex=True)
    ic = ic_df["ic"].dropna()
    x = range(len(ic))

    # 上：每日IC柱状图
    colors = ["#d32f2f" if v > 0 else "#388e3c" for v in ic]
    ax1.bar(x, ic, color=colors, alpha=0.6, width=1.0)
    ax1.axhline(0, color="black", linewidth=0.5)
    ax1.axhline(ic.mean(), color="blue", linestyle="--", linewidth=1, label=f"均值={ic.mean():.3f}")
    ax1.set_ylabel("每日IC")
    ax1.set_title(f"{factor_label} — Spearman IC时序")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(True, alpha=0.3)

    # 下：累计IC（验证因子持续性）
    cum_ic = ic.cumsum()
    ax2.plot(x, cum_ic.values, color="#1976d2", linewidth=1.5)
    ax2.fill_between(x, cum_ic.values, alpha=0.2)
    ax2.set_ylabel("累计IC")
    ax2.set_xlabel("交易日序号")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig_to_base64(fig)


def plot_cum_curve(cum_df: pd.DataFrame, factor_label: str) -> str:
    """绘制多空组合累计收益曲线"""
    if not PLOT_OK or len(cum_df) == 0:
        return ""

    fig, ax = plt.subplots(figsize=(9, 3.5))
    cum_df = cum_df.dropna(subset=["cum_ret"])
    x = range(len(cum_df))
    ax.plot(x, cum_df["cum_ret"].values * 100, color="#d32f2f", linewidth=1.8)
    ax.fill_between(x, cum_df["cum_ret"].values * 100, alpha=0.2, color="#d32f2f")
    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xlabel("调仓次数")
    ax.set_ylabel("累计收益 %")
    ax.set_title(f"{factor_label} — 多空组合累计收益（已扣除交易成本）")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig_to_base64(fig)


# ==================== 评级 ====================

def grade_factor(ic_mean: float, icir: float) -> tuple:
    """根据IC和ICIR给因子评级"""
    abs_ic = abs(ic_mean) if ic_mean else 0
    abs_icir = abs(icir) if icir else 0

    if abs_ic >= config.IC_THRESHOLDS["strong"] and abs_icir >= config.ICIR_THRESHOLDS["good"]:
        return "🌟 优秀", "#d32f2f"
    if abs_ic >= config.IC_THRESHOLDS["moderate"] and abs_icir >= config.ICIR_THRESHOLDS["moderate"]:
        return "✅ 较强", "#f57c00"
    if abs_ic >= config.IC_THRESHOLDS["weak"]:
        return "⚠️ 弱有效", "#888"
    return "❌ 无效", "#999"


# ==================== 主渲染 ====================

def generate_html_report(
    ic_results: Dict,
    quantile_results: Dict,
    factor_df: pd.DataFrame,
    output_path: str,
) -> str:
    """生成HTML报告"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_days = factor_df["trade_date"].nunique()
    n_stocks = factor_df["code"].nunique()
    date_range = f"{factor_df['trade_date'].min()} ~ {factor_df['trade_date'].max()}"

    # ===== 顶部汇总表（多窗口对比）=====
    summary_rows = []
    for fname, res in ic_results.items():
        row = {"因子": res["label"], "方向": res["direction"]}
        for w in config.FUTURE_RETURN_WINDOWS:
            key = f"ret_{w}d"
            if key in res:
                row[f"IC_{w}d"] = res[key]["ic_mean"]
                row[f"ICIR_{w}d"] = res[key]["icir"]
                row[f"胜率_{w}d"] = res[key]["ic_win_rate"]
        # T+10评级
        if "ret_10d" in res:
            grade, color = grade_factor(res["ret_10d"]["ic_mean"], res["ret_10d"]["icir"])
            row["评级"] = grade
            row["color"] = color
        summary_rows.append(row)

    # 按|IC_10d|降序
    summary_rows.sort(key=lambda x: abs(x.get("IC_10d") or 0), reverse=True)

    # ===== 渲染每个因子详情 =====
    detail_blocks = []
    for fname, res in ic_results.items():
        if "ret_10d" not in res:
            continue

        ic_10d = res["ret_10d"]
        grade, color = grade_factor(ic_10d["ic_mean"], ic_10d["icir"])

        ic_chart = ""
        if "ic_series" in res:
            ic_chart = plot_ic_series(res["ic_series"], res["label"])

        cum_chart = ""
        q_metrics = {}
        if fname in quantile_results:
            qres = quantile_results[fname]
            q_metrics = qres.get("long_short_metrics", {})
            cum_chart = plot_cum_curve(qres.get("cum_curve", pd.DataFrame()), res["label"])

        # 多窗口对比表
        window_rows = []
        for w in config.FUTURE_RETURN_WINDOWS:
            key = f"ret_{w}d"
            if key in res:
                s = res[key]
                window_rows.append(f"""
                <tr>
                  <td>T+{w}日</td>
                  <td>{s['ic_mean']}</td>
                  <td>{s['icir']}</td>
                  <td>{s['ic_win_rate']}%</td>
                  <td>{s['ic_t_stat']}</td>
                  <td>{s['n_days']}</td>
                </tr>""")

        # 分位收益表
        q_rets = quantile_results.get(fname, {}).get("quantile_returns", {})
        q_row_html = ""
        if q_rets:
            cells = "".join(f"<td>{q_rets.get(f'q{i}', '-')}</td>" for i in range(5))
            q_row_html = f"""
            <h4>分位平均收益 (T+10日，单位%)</h4>
            <table class="data">
              <thead><tr><th>Q0(最低)</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4(最高)</th></tr></thead>
              <tbody><tr>{cells}</tr></tbody>
            </table>"""

        # 多空指标
        ls_html = ""
        if q_metrics:
            ls_html = f"""
            <h4>多空组合表现 (已扣除{config.TOTAL_COST_BPS}bps交易成本)</h4>
            <table class="data">
              <thead><tr><th>年化收益</th><th>年化波动</th><th>夏普</th><th>最大回撤</th><th>胜率</th><th>调仓次数</th></tr></thead>
              <tbody><tr>
                <td><b>{q_metrics.get('annual_return', '-')}%</b></td>
                <td>{q_metrics.get('annual_vol', '-')}%</td>
                <td><b>{q_metrics.get('sharpe', '-')}</b></td>
                <td style="color:#d32f2f">{q_metrics.get('max_drawdown', '-')}%</td>
                <td>{q_metrics.get('win_rate', '-')}%</td>
                <td>{q_metrics.get('n_periods', '-')}</td>
              </tr></tbody>
            </table>"""

        detail_blocks.append(f"""
        <section class="factor-block">
          <h3>{res['label']} <span style="color:{color}; font-size:14px">[{grade}]</span></h3>
          <p class="muted">因子代码: <code>{fname}</code> | 预期方向: {res['direction']}</p>

          <h4>多窗口IC对比</h4>
          <table class="data">
            <thead><tr><th>窗口</th><th>IC均值</th><th>ICIR</th><th>胜率</th><th>t值</th><th>样本天数</th></tr></thead>
            <tbody>{''.join(window_rows)}</tbody>
          </table>

          {q_row_html}
          {ls_html}

          {f'<div class="chart"><img src="{ic_chart}" alt="IC时序"/></div>' if ic_chart else ''}
          {f'<div class="chart"><img src="{cum_chart}" alt="累计收益"/></div>' if cum_chart else ''}
        </section>""")

    # ===== 顶部汇总表HTML =====
    summary_html_rows = []
    for i, row in enumerate(summary_rows, 1):
        cells = f"""
        <td>{i}</td>
        <td><b>{row['因子']}</b></td>
        <td>{row['方向']}</td>"""
        for w in config.FUTURE_RETURN_WINDOWS:
            ic_val = row.get(f"IC_{w}d", "-")
            icir_val = row.get(f"ICIR_{w}d", "-")
            ic_color = "#d32f2f" if (ic_val and abs(ic_val) >= 0.05) else "#666"
            cells += f"<td style='color:{ic_color}'>{ic_val}</td><td>{icir_val}</td>"
        cells += f"<td style='color:{row.get('color','#888')}'><b>{row.get('评级','-')}</b></td>"
        summary_html_rows.append(f"<tr>{cells}</tr>")

    summary_table_header = "<th>排名</th><th>因子</th><th>方向</th>"
    for w in config.FUTURE_RETURN_WINDOWS:
        summary_table_header += f"<th>IC_T+{w}</th><th>ICIR_T+{w}</th>"
    summary_table_header += "<th>评级</th>"

    # ===== 结论文字 =====
    top_factor = summary_rows[0] if summary_rows else None
    weak_factors = [r for r in summary_rows if "❌" in (r.get("评级") or "")]
    conclusion_text = ""
    if top_factor:
        conclusion_text = f"""
        <p><b>🏆 最强因子</b>: {top_factor['因子']} (T+10 IC={top_factor.get('IC_10d')})</p>
        <p><b>❌ 无效因子</b>: {', '.join(r['因子'] for r in weak_factors) or '无'}</p>
        <p><b>💡 建议</b>: 实战中重点参考评级"优秀/较强"的因子,降低"弱有效/无效"因子的权重。</p>"""

    # ===== HTML =====
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>因子IC回测报告 {timestamp}</title>
  <style>
    body {{ font-family: -apple-system, "Segoe UI", "PingFang SC", Arial, sans-serif;
           background: #f5f5f5; margin: 0; padding: 20px; color: #333; }}
    .container {{ max-width: 1200px; margin: 0 auto; background: white;
                 padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    h1 {{ color: #1976d2; border-bottom: 3px solid #1976d2; padding-bottom: 10px; }}
    h2 {{ color: #333; border-left: 5px solid #1976d2; padding-left: 12px; margin-top: 30px; }}
    h3 {{ color: #333; margin-top: 24px; }}
    h4 {{ color: #555; margin-top: 18px; margin-bottom: 6px; }}
    .summary-box {{ display: flex; gap: 20px; margin: 20px 0; }}
    .summary-box > div {{ flex: 1; padding: 15px; background: #e3f2fd;
                         border-radius: 6px; text-align: center; }}
    .summary-box b {{ font-size: 20px; color: #1976d2; }}
    table.data {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }}
    table.data th, table.data td {{ padding: 8px 12px; text-align: center;
                                    border-bottom: 1px solid #eee; }}
    table.data thead {{ background: #f0f0f0; font-weight: bold; }}
    table.data tbody tr:hover {{ background: #fafafa; }}
    .muted {{ color: #888; font-size: 12px; }}
    code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}
    .chart {{ margin: 14px 0; text-align: center; }}
    .chart img {{ max-width: 100%; border: 1px solid #eee; border-radius: 4px; }}
    .factor-block {{ background: #fafafa; padding: 18px; margin: 20px 0;
                     border-radius: 6px; border-left: 4px solid #1976d2; }}
    .conclusion {{ background: #fff3e0; padding: 15px; border-radius: 6px;
                  border-left: 4px solid #f57c00; margin: 20px 0; }}
  </style>
</head>
<body>
<div class="container">

<h1>🧪 因子IC回测报告</h1>
<p class="muted">生成时间: {timestamp} | 框架版本: v1.0</p>

<div class="summary-box">
  <div><b>{n_stocks}</b><br><span class="muted">股票数量</span></div>
  <div><b>{n_days}</b><br><span class="muted">交易日数</span></div>
  <div><b>{len(ic_results)}</b><br><span class="muted">测试因子</span></div>
  <div><b>{date_range}</b><br><span class="muted">回测期间</span></div>
</div>

<h2>📊 因子IC汇总（按|T+10 IC|降序）</h2>
<table class="data">
  <thead><tr>{summary_table_header}</tr></thead>
  <tbody>{''.join(summary_html_rows)}</tbody>
</table>

<div class="conclusion">
  <h3 style="margin-top:0">🎯 结论</h3>
  {conclusion_text}
</div>

<h2>📈 因子详细分析</h2>
{''.join(detail_blocks)}

<hr style="margin-top:40px">
<p class="muted" style="text-align:center">
  评级标准: 优秀(|IC|≥0.10且|ICIR|≥1.0) | 较强(|IC|≥0.05且|ICIR|≥0.5) | 弱有效(|IC|≥0.02) | 无效<br>
  框架文档: 06_quant_framework.md | 生成器: backtest/report_generator.py
</p>

</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"📄 HTML报告已生成: {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("⚠️ 请通过 main.py 运行完整流程")
