# 回测框架 - 部署与缓存运维指南

> 配套文档: README.md（框架功能介绍）/ 06_quant_framework.md（量化策略文档）

---

## 一、缓存机制设计

### 数据分类

| 数据类型 | 更新频率 | 数据量 | 缓存策略 |
|---|---|---|---|
| 日K线 | 每个交易日 | 大（每股每年~250行） | **增量**：从本地最新日期+1拉到today |
| 估值（PE/PB/换手） | 每个交易日 | 中 | **增量** |
| 资金流向 | 每个交易日（T+1） | 中 | **增量** |
| 财务指标 | 季度 | 小（每股5-20条） | **条件刷新**：最新ann_date超30天才重拉 |
| 股东户数 | 季度 | 小（每股5-15条） | **条件刷新**：同上 |
| 沪深300成分股 | 半年一次 | 极小（300条） | **自动刷新**：超90天自动重拉 |

### 为什么不"有缓存就跳过"

旧版本是粗暴的"有数据就跳"，问题：
- 6月10日下载了恒瑞医药600276
- 6月17日再跑，恒瑞**完全不更新**（缺6月10-17的K线）
- 7月15日发了Q2财报，股东户数也不刷新

新版本按数据类型分别处理，保证数据始终新鲜。

---

## 二、五种更新模式

| 模式 | 命令 | 行为 | 适用场景 |
|---|---|---|---|
| 增量（默认） | `python main.py` | 日频增量 + 财务30天阈值 | **每日盘后**首选 |
| 智能 | `python main.py --update smart` | 同增量 | 同上 |
| 全量 | `python main.py --update full` | 清空重拉所有 | **首次部署**或大规模数据修复 |
| 财报刷新 | `python main.py --update fundamentals --skip-backtest` | 强制重拉财务+股东户数 | **财报季后**（4/8/10月） |
| 跳过 | `python main.py --update none` | 不动数据，只回测 | 调试因子算法时 |

---

## 三、推荐的Cron部署

### 方案A：每日盘后增量更新（推荐）

```bash
# /etc/cron.d/stock_backtest
# 每个交易日17:30增量更新+完整回测
30 17 * * 1-5  root  cd /opt/stock-report/backtest && /usr/bin/python3 main.py --update incremental >> /var/log/backtest.log 2>&1

# 财报季后强制刷新基本面（4/5月年报季末、8/9月中报季末、10/11月三季报季末、2/3月年报季前）
0 9 5,9,11,3 1 root  cd /opt/stock-report/backtest && /usr/bin/python3 main.py --update fundamentals --skip-backtest >> /var/log/backtest.log 2>&1

# 每周日凌晨全量校验（可选，安全网）
0 3 * * 0  root  cd /opt/stock-report/backtest && /usr/bin/python3 main.py --update full >> /var/log/backtest.log 2>&1
```

### 方案B：轻量版（节省Tushare积分）

```bash
# 仅每周更新一次回测，平时手动跑
0 18 * * 0  root  cd /opt/stock-report/backtest && /usr/bin/python3 main.py >> /var/log/backtest.log 2>&1
```

---

## 四、典型操作场景

### 场景1：首次部署

```bash
cd /opt/stock-report/backtest
python main.py --update full
# 耗时约15-30分钟，下载300只×3年数据
```

### 场景2：每日例行更新

```bash
python main.py
# 约1-2分钟：拉增量K线+重算因子+生成新报告
```

### 场景3：财报季后刷新基本面

A股财报披露规律：
- 1月底-4月底：年报+一季报
- 7月-8月：中报
- 10月：三季报

财报季结束后（如5月初/9月初/11月初）跑一次：

```bash
python main.py --update fundamentals --skip-backtest
# 只刷新所有公司的财务+股东户数，约3-5分钟
# --skip-backtest 跳过回测，因为基本面因子3年回测意义不大，专注更新数据即可
```

### 场景4：调试因子算法

修改了`factor_calculator.py`里的因子计算逻辑后：

```bash
python main.py --update none --recalc
# 不动数据，重算因子+重跑回测，约1分钟
```

### 场景5：检查数据健康度

```bash
python main.py --status
```

输出示例：
```
======================================================================
📦 本地数据状态
======================================================================
股票池: hs300 (300只)
池更新日: 20260520
池更新距今: 21天 ✅

各表最新日期(抽样7只):
代码       K线           估值           资金流         财务公告       股东公告
----------------------------------------------------------------------
000001     20260609      20260609      20260609      20260424      20260424
000002     20260609      20260609      20260609      20260423      20260424
600000     20260609      20260609      20260609      20260420      20260423
...

总记录: K线217,500 | 估值217,500 | 资金流217,500 | 财务4,200 | 股东2,850
数据库大小: 142.8 MB
因子矩阵: 38.2 MB, 最后生成: 2026-06-09 17:35
======================================================================
```

如果某只股票的最新日期明显落后于今天，说明该股可能数据下载失败，可以手动重拉。

### 场景6：自定义回测时间窗口

```bash
# 只回测2024年（验证某段时间的因子有效性）
python main.py --update none --start 20240101 --end 20241231
```

---

## 五、故障排查

### Q1：数据下载到一半失败怎么办

回测框架已自动跳过已下载的股票，直接重跑即可：

```bash
python main.py --update incremental
# 已下载的股票会自动跳过，只拉缺失的
```

### Q2：发现某只股票数据明显异常

```bash
# 单独刷新这只股票
python3 -c "
import sys
sys.path.insert(0, '/opt/stock-report/backtest')
from data_loader import init_loader
store, loader = init_loader()
code = '600276'  # 恒瑞医药
loader.load_daily_kline(code, '20230601', '20260609')
loader.load_daily_basic(code, '20230601', '20260609')
loader.load_moneyflow(code, '20230601', '20260609')
loader.load_fina_indicator(code)
loader.load_holder_number(code)
store.close()
print('done')
"
```

### Q3：Tushare积分超限怎么办

Tushare 2000积分限速：每分钟180次调用。

如果日志频繁出现"限流，等待..."，说明：
- 全量模式（full）短期内跑了多次
- 或者多个进程同时在跑

解决：
1. 配置文件 `config.py` 中调小 `RATE_LIMIT_PER_MIN`（如改到120）
2. 错峰运行
3. 升级Tushare积分（5000分能解锁同花顺概念资金流等额外接口）

### Q4：数据库文件越来越大

正常现象。沪深300×3年完整数据约150-300MB。

如果想清理过期数据（如超过3年的K线）：

```sql
-- 在 backtest/data/hs300_3y.db 里执行
DELETE FROM daily_kline WHERE trade_date < '20230101';
DELETE FROM daily_basic WHERE trade_date < '20230101';
DELETE FROM moneyflow WHERE trade_date < '20230101';
VACUUM;
```

### Q5：HTML报告中文字体乱码（matplotlib图表）

VPS缺中文字体：

```bash
apt install fonts-noto-cjk -y
rm -rf ~/.cache/matplotlib
```

然后重跑：
```bash
python main.py --update none --recalc
```

---

## 六、日志规范

所有运行日志默认输出到stdout。建议生产环境用cron时重定向：

```bash
python main.py --update incremental >> /var/log/backtest.log 2>&1
```

定期清理（保留最近30天）：

```bash
# 加到cron
0 0 1 * * find /var/log -name "backtest.log*" -mtime +30 -delete
```

---

## 七、版本演进规划

| 版本 | 状态 | 内容 |
|---|---|---|
| v1.0 | ✅ 当前 | IC回测 + 分位回测 + HTML报告 |
| v1.1 | 待开发 | 因子正交化（去除相关因子的重复信息） |
| v1.2 | 待开发 | 市场环境分类器（regime filter） |
| v2.0 | 远期 | 完整策略回测（含资金曲线、ATR动态止损、Kelly仓位） |
