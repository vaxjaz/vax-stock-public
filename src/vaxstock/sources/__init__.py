# -*- coding: utf-8 -*-
"""数据源层: 行情 / 资金 / 估值 / 美股参考。

子模块:
    market      大盘数据(Tushare): 指数行情 + 涨跌家数/涨跌停 (替代东财, MR3)
    sina        新浪财经: 个股实时行情
    tushare_src 历史K线+估值 + 全市场单日 + 个股资金流 (基于 TushareSource, 调用方传入已初始化实例)
    us_market   美股参考数据 (yfinance 懒导入, import 无网络副作用)

MR3 减法: 已移除 eastmoney(东财)子模块——VPS 连不上东财, 大盘指数/涨跌家数改走 Tushare,
          个股资金流删除东财兜底仅留 Tushare, 板块排行(get_em_sector_ranking)按减法方向不再迁移。

依赖方向: sources → config, util  (不依赖 indicators / analysis 等上层)
"""
