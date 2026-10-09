"""Pure environmental mail lines; CAPEX does not change AI track scores."""


def render_capex_lines(snapshot):
    lines = ["AI 资本投入监测（四家云厂商）", f"快照截至：{snapshot.get('as_of', '待验证')}（随财报更新，非实时投资额）",
             "口径：现金 CAPEX；公司整体支出≠纯 AI 支出；不含非现金融资租赁新增。"]
    def amount(value):
        return "待验证" if value is None else f"{value/1e9:.2f} 十亿美元"
    def percent(value):
        return "待验证" if value is None else f"{value:.1f}%"
    for row in snapshot.get("companies", []):
        name = row["name"]
        if not row.get("available"):
            lines.append(f"{name}：待验证（{row.get('reason', '数据缺失')}）")
            continue
        lines.append(f"{name} | {row['period_start']}～{row['period_end']} | CAPEX {amount(row['capex_usd'])} | 同比 {percent(row['yoy_pct'])} | 近四季 {amount(row['ttm_capex_usd'])}")
        lines.append(f"  经营现金流 {amount(row['operating_cashflow_usd'])} | CAPEX/经营现金流 {percent(row['capex_to_ocf_pct'])} | 经营现金流减 CAPEX {amount(row['cashflow_less_capex_usd'])} | 披露 {row['filed']} | 季末距取数日 {row['period_age_days']} 天")
        lines.append(f"  来源：{row['source_url']}")
    lines.extend(["Amazon 口径包含 productive assets、软件等；不将四家相加作为纯 AI 投资额。",
                  "融资租赁口径与未来支出指引：待验证，未混入现金 CAPEX。CAPEX 单项不自动判定泡沫。"])
    return lines
