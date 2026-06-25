# -*- coding: utf-8 -*-
"""vaxstock —— A股量化分析引擎 (重构版)

本包是对单体脚本 script/stock_report_enhanced.py 的渐进式重构,
目标是拆分为标准 Python 包并消除 import 副作用。生产单体脚本保持原样。

【分层架构】
    config      统一配置层: 路径 / 密钥 / 全局常量 (import 不连网、不初始化 client)
    util        无状态工具函数: safe_float / fmt_* / to_float 等
    sources     数据源层: 新浪 / 东方财富 / Tushare 行情与基本面拉取
    indicators  指标计算层: technical(均线/MACD/RSI) / valuation(估值百分位/换手z/资金斜率) / regime(市场环境)
    analysis    分析层: 派生指标、右侧打分、个股组装
    report      呈现层: HTML / Markdown 渲染与附件
    services    服务层: 邮件推送、文件清理、采集编排等副作用入口
    research    离线研究层: 回测、因子评估等非生产路径

【依赖方向】 (上层依赖下层, 反向禁止)
    services -> report -> analysis -> indicators -> sources -> config
                                          util  ----------------^

【重构原则】
    - 逻辑零改动, 只搬位置
    - 消除 import 副作用 (import 任何模块不得连网 / 不得初始化外部 client)
    - 密钥环境变量优先于 secrets.json
    - 生产单体脚本 stock_report_enhanced.py 保持原样, VPS 零影响
"""

__version__ = "2.0.0-refactor"
