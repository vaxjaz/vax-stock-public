# 09 变更日志

> 格式: 顶部最新,append-only。每条带分类 tag: 【架构】【策略】【脚本】【持仓】【数据】【bug修复】【文档】【安全】
> 任何变更必须在此追加一行(包括但不限于:策略升级 / 脚本改动 / 持仓买卖 / 文档更新 / bug 发现与修复)。

## 2026-06-24

- 【架构】盘中盯盘升级为「触发 → lite快照 → codex研判 → 推送」闭环(在原纯价位告警之上)。全链路实测打通并上线,api 与盘中脚本均 systemd 托管。详见 14_intraday_protocol.md 第8节。
- 【脚本】api.py 新增 `GET /analyze/{code}?lite=1` 盘中极速快照: 仅实时价量(MA/位置/振幅/量比5d/RSI/MACD,来自实时+历史K线),严格剔除 right_side_score 三件套 + T-1滞后主力资金流(14_intraday 铁规);不计 analyze 配额。
  - 【关键】lite 分支必须前置于 `refresh_regime()` 直接返回。否则 regime 冷缓存时 refresh_regime 扫全市场,实测把 lite 拖到 **2分43秒**;前置后稳定 3–10s(冷)/ <1s(热)。
- 【脚本】intraday_rules.md = codex 的 system prompt(与 intraday_watch.py 同放 /opt/stock-report/),从 Ch10 + 14_intraday 抽取盘中研判规则。铁律: 不出评分 / 不出买卖价格 / 标"盘中未定论" / 不臆测资金(快照无资金) / ≤3行 / 按模板。每次调用重读当 system 消息(无状态,改规则即时生效)。脚本有 fallback 极简规则防文件丢失。
- 【脚本】intraday_watch.py: notify() 命中触发 → fetch_lite(超时45s 容冷缓存)→ call_codex 喂研判 → 并入微信/邮件推送。codex/lite 失败不影响原始价位告警。codex 配置(token/url/model)从 secrets.json 读。
- 【架构】codex 部署 = CLIProxyAPI(router-for-me/CLIProxyAPI),OpenAI 兼容,VPS 本机 8317 端口,/v1/chat/completions + Bearer api-key。model 用 gpt-5.4(/v1/models 确认可用: codex-auto-review / gpt-5.3-codex-spark / gpt-5.4 / gpt-5.4-mini / gpt-5.5)。
- 【bug修复】tushare_source.py `_safe_call` 超时实现错误并修正。旧版用 `with ThreadPoolExecutor(...) as ex: fut.result(timeout=12)`,但 with 退出时 `shutdown(wait=True)` 会反过来等那个卡死线程跑完,令超时形同虚设 → lite 端点曾卡 75–90s。改为 daemon 线程 + `join(timeout)`,超时直接放弃(孤儿线程随 socket 自结),真生效。
- 【脚本】tushare_source.py / stock_report_enhanced.py 性能优化部署: build_stock_item 8个独立接口串行→ThreadPoolExecutor并行(冷缓存 90s→~10-15s)、去掉 fina 重复拉(periods=1+periods=4 → 只 periods=4)、_rate_limit 加锁。
- 【运维】关键踩坑: VPS 上 FastAPI 服务的 systemd 单元名是 **stock-api.service**(不是 stock-report)。改 api.py/tushare_source.py/stock_report_enhanced.py 任一,须 `systemctl restart stock-api.service` 才生效;此前误用 stock-report 重启导致新代码屡次"没生效"。盘中脚本由 intraday-watch.service 托管,各管各的。
- 【持仓】工业富联 601138 今日清仓(100股,实现 +142.12);新建仓前已于 06-23 建立。holdings.json 同步为 3 只: 恒瑞600276(700@46.844)/ 长江600900(1100@26.962)/ 立讯002475(300@70.227)。
- 【待办】[P1] refresh_regime() 冷缓存约 2分43秒过慢,拖累全量 /analyze 与 EOD 报告(盘中 lite 已绕开)。疑某指数或 EM 接口无超时,提速套路同 _safe_call(加 daemon 线程超时)。
## 2026-06-23

- 【脚本】新增 intraday_watch.py — 盘中实时盯盘+触发推送(独立常驻进程)
  - 数据源仅用 /quote(Sina实时,秒级,不耗Tushare配额、不进analyze慢路径),遵守14_intraday_protocol铁规:盘中不计算/不发布right_side_score评分
  - 触发类型4种: price_above/price_below/pct_above/pct_below;触发后该规则当日静默(fired)不刷屏,重启重置
  - 仅交易时段(09:25-11:32/13:00-15:02)轮询,默认300s;支持 --once(测一次) / --force(无视时段)
  - 推送可插拔: 控制台始终打印; PushPlus微信 + QQ邮箱SMTP 二者可同时/单开/全关。邮箱配置优先从VPS secrets.json读(email_user/email_authcode/email_to/email_enabled/pushplus_token),不进脚本不进对话
  - 实测验证: 中信600030(+7.83%)、东财300059(+12.74%)正确触发券商异动规则;立讯002475(68.4)未达69正确不触发
- 【脚本】监控规则外置 watch_rules.json — 改规则不动代码,脚本每轮热重读(覆盖文件即生效,无需重启);文件缺失回退内置DEFAULT_RULES;热重载保留已触发静默状态(按code+type+level记忆)
- 【架构】intraday api 新增写接口(intraday_api_addon.py,追加到现有FastAPI主文件末尾)
  - GET /watch/list、POST /watch/add(同code+type+level去重覆盖)、POST /watch/replace(整批替换)、POST /watch/clear(?code清单只/无参清空)
  - 写文件用 os.replace 原子替换 + 线程锁,防写一半被盯盘进程读到
  - 目的: 用户口述→Claude调写接口→规则入watch_rules.json→盯盘脚本热重读生效,用户不维护配置文件
- 【架构】api.py 修复(addon粘贴后启动崩溃): 第167行 list[WatchRule]→List[WatchRule];import补 List(typing)和 Body(fastapi)——Body在addon中被用但主文件原未import,是连环崩溃点。三处修复后服务正常起。
- 【部署】写接口闭环已上线实测通过(2026-06-23): /watch/list 200、/watch/add 5→6条写入确认、/watch/replace 整批替换确认、文件落地确认。"用户口述→Claude调接口改规则"模式正式可用。
- 【部署】intraday_watch 做成 systemd 服务 intraday-watch.service(WorkingDirectory=/opt/stock-report,venv python,Restart=always,开机自启)。VPS时区确认 Asia/Shanghai(+0800),交易时段判断无需改。
- 【验证】邮箱推送端到端验证通过: 加"立讯价≥1元"必触发规则→VPS跑--force→用户邮箱实收提醒邮件→证明 规则读取/触发判断/SMTP推送/送达 全链路正确。验证后测试规则已删,恢复纯净5条(立讯站69买/破66止损/跌3%观望 + 中信涨3%真发动信号/跌2%诱多嫌疑)。
- 【安全】⚠️写接口当前【免鉴权】为临时方案(用户决定先上线后收口)。代码已埋鉴权钩子: 设环境变量 WATCH_WRITE_KEY 即启用 X-Watch-Key 校验;或将写接口绑127.0.0.1仅本机。待办[P0]: 上线稳定后一周内收口——本会话Claude无任何密钥即成功写入生产规则文件,证明任何人扫到域名亦可写,勿长期裸奔。

## 2026-06-19

- 【bug修复】tushare_source.py get_moneyflow_summary 主力净流入口径+单位双重错误
  - 根因①字段错: 旧用"(大单+特大单买)−(大单+特大单卖)"分档加总作主力,经60日实测该口径与涨跌相关仅0.147(噪音);net_mf_amount 相关0.871(可信),且与回测IC因子同源
  - 根因②单位错: net_mf_amount 及各档amount官方单位为"万元",应×10000,旧代码误用×1000(注释"千元转元"错误),数值被压成≈0
  - 实测验证: 恒瑞6/18 修复前显示≈0.03亿,修复后+8.09亿(=net_mf_amount 80912.6万×10000,与同花顺+5.13亿同向、与涨跌+3.04%一致)
  - 影响: 此前所有报告资金面信号基本失效(被压成≈0),修复后首次反映真实主力动向。如长江电力暴露10日净流出27.9亿(此前被掩盖)
  - 回测端 factor_calculator.py 本就正确(net_mf_amount×10000),IC=0.0229 不受影响,无需重跑
  - 分档明细字段保留(单位同步修正×10000),仅供资金结构展示,不参与评分
- 【bug修复】macro_indicators.py 融资买入比交易所完整性校验
  - 根因: fetch_margin_to_volume 无条件 groupby.sum(),当某交易所数据当天未发布(盘中早段拉取,深市/北交所融资数据未公布)时,只聚合到部分交易所→分子腰斩→ratio失真
  - 实测: 6/18 margin接口仅返回[SSE],ratio算成5.43%(真实应≈10.6%),落"3年第0%"假信号,把宏观regime从🔴看空误拉成🟡中性
  - 方案: 按交易所pivot,要求SSE+SZSE齐全才计算(口径与分母上证综指+深证成指一致,排除BSE);残缺日丢弃不写缓存;自动回退最近完整日并标注 stale + 报告显示"⚠️采用XXXX(今日数据未就绪)"
  - 修复后: 6/18丢弃→回退6/17(10.69%/第83%/❌),宏观regime纠正为🔴看空(✅2/❌11)
- 【数据】重拉 margin_volume_history 缓存清除历史坏点
  - 因增量逻辑(有缓存只增量不重拉),历史524行混入多个残缺坏点(min=4.61%)
  - 删缓存全量重拉后: 520行(残缺日被正确丢弃),min回到6.81%(=2024年8月真实地量,成交额仅5000亿,分子分母同量级,已验证为真实值非残缺)
- 【安全】watchlist.json 内 tushare_token 明文出现在上传内容中,需去 tushare.pro 后台重置 token 并更新 VPS secrets.json(README Q7 流程)
- 【文档】新增 11_data_integrity_rules.md — 数据严谨性硬规矩(见下),所有指标计算结论必须可追溯、不猜测
- 【待办】stock_report_enhanced.py line 1852 版本头字符串仍显示"框架v1.1/旧IC值",待更新到v1.4(不影响计算)

## 2026-06-17
- 【策略】v1.4 正式落地(取消草案/待9月回测状态)。Signal B 阈值 5亿/60% → 3亿/70% 采纳;依据=用户决策+06-16重跑因子层旁证(20日位置IC微正,放宽不被惩罚)。注:未做Signal B事件回测,胜率为判断值非实测。
- 【回测】06-16重跑(379只/745日,修幸存者偏差+前复权)定为权威IC值:净利同比0.0240、主力净流入0.0229(多空+12.89%/夏普0.90,实战最强)、股东户数-0.0219、右侧合成0.0202(ICIR3.13但多空仅+0.77%→评分作下限过滤非alpha)。
- 【验证】右侧合成评分顶端分位压平(Q3=Q4),为「评分门槛2.0不下调」提供新证据。
- 【文档】06去IC旧值/10去待9月标记/10_known_issues延期划删除线。
## 2026-06-16 (续)
- 【bug修复】East Money板块接口失效(RemoteDisconnected,VPS IP被掐)→ hot_sector_scanner.fetch_sector_overview/find_hot_sectors 迁同花顺 ak.stock_board_industry_summary_ths(),④板块层恢复。5日涨幅暂用今日代理(待补真实历史)
- 【待办】龙头股扫描(成分股取数)+ 机会仓信号B 仍依赖East Money,待迁同花顺;Tushare板块接口(moneyflow_ind_dc/dc_index)均无权限
-
## 2026-06-15

- 【策略】新增框架第十章"分层入场标准"(v1.4 草案):拆为左侧建仓 / 右侧追入 / 机会仓三通道,按标的性质分流
  - 通道A 左侧:深度低估质地(PE历史分位<10% + 52周<15% + 净利>0 + 资金不重度流出)免右侧确认、分批建仓;恐慌市复用优质低位三重豁免。当前案例:恒瑞 600276
  - 通道B 右侧:维持评分≥2.0 + 三选二确认;**高位否决由单维度改两级集群**
  - 通道C 机会仓:信号B阈值放宽(见下)
  - 仓位补至叠加矩阵下沿 40%(执行既有矩阵,非放松)
  - 守住不调:评分门槛2.0 / 右侧三选二 / 派发三件套否决 / 止损线 / 不接刀
  - 所有放宽数值标注 ⚠️待9月回测校准
- 【bug修复】通道B 集群规则两级修订(实盘暴露):初版以"10日资金流出"为否决必要条件,导致生益(位置103%/PE100%但今日微流入)漏放、中际旭创(高位但户数-15.78%强集中+特大单净流入)误杀。改为两级——一级"52周≥95% 且 PE分位≥95%"硬否决(不豁免);二级高位非极端凭"今日特大单方向 / 户数集中<-10%"分流否决 vs 研究层
- 【脚本】opportunity_scanner.py 信号B阈值放宽(**待明日 VPS 执行**,共5处,逻辑2+文字3):
  - 69行 `B_SECTOR_MIN_3D_INFLOW` 5.0 → 3.0
  - 71行 `B_STOCK_MAX_POS_20D` 60 → 70
  - 522 / 578 / 842 行 提示文字 `5亿/60%` → `3亿/70%` 同步(防报告口径矛盾)
- 【数据】确认 macro_indicators.py ERP 走 fallback 国债收益率 2.30%(报告 yield_source=fallback),实际约 1.74%(2026-04-29 CEIC)。但 ERP 信号取百分位/σ,**对全历史减同一常数不改变信号**,改 secrets.json 常数无效;真修需 yc_cb 真实时变序列 + 删 .cache_macro/hs300_erp_history.parquet 重跑。yc_cb 属单独权限接口(非积分门槛),且脚本 curve_type='0001' 参数存疑 —— **待明日 VPS 裸调诊断确认是无权限还是参数错**,本轮不动 secrets.json
- 【文档】10_layered_entry_standards.md(第十章)已含两级集群规则 + 机会仓常量对照(69/71行),**待上传 Claude project**

- 【bug修复】macro_indicators.py ERP 改用 AkShare 真实国债收益率序列(yc_cb无权限确认)
  - 实测:yield 2.30%→1.7446%,erp_pct 4.63%→5.02%(绝对值升)
  - 但 percentile_5y 4.81%→0.82%、sigma -1.59σ→-1.65σ:信号 ❌❌ 不仅未软化,反被坐实
  - 机制:真实历史收益率高于flat假设,重建后历史ERP整体更低,今日ERP反显更极端
  - 修正认知:flat 2.30% 此前是"低估了贵"而非高估;真实数据下沪深300相对债券处5年最贵(第0.82%)
  - 结论:ERP❌❌可信,不再"人工降一档";撤回此前降档建议
- 【脚本】opportunity_scanner.py 信号B阈值放宽5处(3亿/70%)已执行 [v1.4草案,待9月回测校准]
## 2026-06-14

- 【bug修复】macro_indicators.py 修复 4 个 bug:
  - Bug#1: ETF 净申赎单位错误(fd_share 是万份,需 /10000 才是亿元)
  - Bug#2: 维度3 换手率指数代码 `000985.CSI` 不被 Tushare 支持,改为候选列表 `["000985.SH", "000300.SH"]`
  - Bug#3: 维度4 ERP 的 `yc_cb` 接口无权限,加 fallback 到 secrets.json 的 yield_10y_pct
  - Bug#4: summary 函数失败时 errors 字段不上报,补全所有维度的 else 分支
- 【脚本】stock_report_enhanced.py 集成宏观采集时,传 fallback_yield_10y_pct 给 collect_macro_indicators
- 【配置】secrets.json 模板加 yield_10y_pct 字段(默认 2.30%,月度手动维护)
## 2026-06-13

- 【文档】建立 00_README.md / 01_principles.md / 09_changelog.md / 10_known_issues.md 元信息四件套
- 【架构】完成 v2 双源单职责架构: holdings.json(本地) + watchlist.json(VPS) + secrets.json(VPS)
- 【策略】量化框架升级到 v1.3,新增第八章"宏观环境与 Macro Regime"
  - 6 维度宏观指标: ETF净申赎 / 融资比 / 全A换手率 / 沪深300 ERP / 全A宽度 / M1同比
  - 综合 Macro Regime: 🟢看多 / 🟡中性 / 🔴看空
  - 短期 × 宏观 9×3 叠加决策矩阵
  - v1.2 个股评分逻辑零修改,完全向后兼容
- 【脚本】新增 macro_indicators.py (1299行),实现 6 维度采集 + parquet 增量缓存
- 【脚本】stock_report_enhanced.py 集成 [9/10] 宏观采集步骤,新增 "🌐 宏观环境" markdown 章节
- 【脚本】stock_report_enhanced.py 改 v2 双源架构: 读 watchlist.json + secrets.json,HOLDINGS 永远为空字典
- 【模板】Claude 输出从 9 段升级到 10 段(插入 ② 宏观环境)
- 【数据】持仓股 600276 / 600900 同步加入 VPS watchlist
- 【安全】拆 tushare_token 到 secrets.json(chmod 600,不上传 Claude project)
- 【文档】06_quant_framework.md 升级到 v1.3,从 375 行扩展到 597 行
- 【数据】删除 project 中的 portfolio.json(已被 holdings.json 替代)
## 2026-06-12

- 【持仓】收盘后清仓 4 只:科华数据 002335 / 隆基绿能 601012 / 此前已清仓的工业富联 601138 / 中国西电 601179 / 比亚迪 002594
- 【持仓】当前持仓 2 只: 恒瑞医药 600276(500股@46.611) + 长江电力 600900(1100股@26.962)
- 【策略】量化框架升级到 v1.2,三项结构性优化:
  - ①资金流市值归一化分档(ratio=10日净流入/流通市值,≥0.5%+1.5/≥0.1%+1.0/>0+0.5/≤-0.5%-1.0)
  - ②恐慌市优质豁免(业绩>20%+PE历史<20%+20日位置<30%三重确认→惩罚归零)
  - ③regime 平滑(连续2日同向才切换)
- 【脚本】新增 opportunity_scanner.py 机会仓扫描器(信号A涨停板/信号B板块启动)
- 【模板】固定 9 段输出模板写入 memory
## 2026-06-10

- 【策略】量化框架升级到 v1.1,基于沪深300/3年/735日 IC 回测重大修订
- 【回测】发现 10 日主力净流入是最强因子(IC=0.0224, ICIR=2.34)
- 【回测】反转因子在动量市完全失效(20日位置 / RSI / PE百分位 年化收益 -12%~-22%)
- 【回测】资金流斜率因子无效(ICIR=-0.27),删除
## 2026-06-09

- 【架构】项目初版建立。降低大单权重,新增换手 Z-score / 资金斜率 / 综合评分三模块
- 【架构】确立股东户数为最高权重因子(后被 v1.1 回测修订)
---

> 早于 2026-06-09 的历史不在此记录(项目此前未正式归档变更)