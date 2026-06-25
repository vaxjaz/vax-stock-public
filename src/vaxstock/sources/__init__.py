# -*- coding: utf-8 -*-
"""数据源层: 行情 / 资金 / 估值 / 美股参考。

子模块:
    eastmoney   东方财富: 板块排行 / 大盘涨跌统计 / 个股资金流向
    sina        新浪财经: 实时行情 / 大盘指数
    tushare_src 历史K线+估值 (基于 TushareSource, 需调用方传入已初始化实例)
    us_market   美股参考数据 (yfinance 懒导入, import 无网络副作用)

依赖方向: sources → config, util  (不依赖 indicators / analysis 等上层)
"""
