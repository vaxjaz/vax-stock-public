# 云厂商现金 CAPEX 环境指标

四家公司 SEC Company Facts 官方接口已于 2026-10-08 在 VPS 验证。
文档：https://www.sec.gov/search-filings/edgar-application-programming-interfaces
访问约定：https://www.sec.gov/about/developer-resources

Microsoft / Alphabet / Meta 使用 `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`。
Amazon 使用 `us-gaap:PaymentsToAcquireProductiveAssets`，包含软件等生产性资产；
Amazon 的 PPE-only 字段停止于 2017 年，不作为当前数据 fallback。
经营现金流使用 `us-gaap:NetCashProvidedByUsedInOperatingActivities`。
只取 USD 原始美元值；邮件转为十亿美元。

季度值优先取真实单季披露；否则同财年起点 YTD 相减（Q4 = 全年 - 前三季）。
保留每个操作数的金额、区间、标签、filed、accn；优先同份申报中的操作数。
跨申报相减时操作数仍明确保留，不能将其解释为未经重述影响的独立披露。
按采集日限制已公开申报，非针对过去交易日的 point-in-time 回测。
近四季必须连续且四季齐全；同比须匹配去年同一季度起止日。
经营现金流覆盖比须同期且经营现金流大于零；缺失或不适用展示待验证。
经营现金流减 CAPEX 是现金口径差额，不宣称等同各公司官方 FCF 定义。

公司全部资本支出不是纯 AI 支出；四家口径不完全一致，不汇总为 AI 投资总额。
融资租赁新增、租赁本金偿还、未来 CAPEX 指引不混入；首版均明确待验证。
不根据单项 CAPEX 自动判泡沫，不改 AI 评分、SOX 刹车或仓位档位，不调用 LLM。

服务入口 `services.capex_refresh.refresh_capex`，采集器显式调用。
仅覆盖 `var/eod/current_capex.json`，完整快照缓存 12 小时，失败不伪装为新数据。
邮件通过现有 AI track summary_lines 输出；各家公司单独披露季度/申报日期。
不会恢复日研究累计、历史归档、Markdown 或 Git 自动提交。
SEC 请求用应用标识，不读取邮箱/密钥；可显式设置 `SEC_USER_AGENT`。
串行四次请求且间隔 0.2 秒，每次 daemon 线程墙钟超时 20 秒。
