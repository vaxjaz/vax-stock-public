# vaxstock v2 部署(systemd, 基础设施即代码)

v2 一刀切顶替 v1(不并存)。本目录是三服务的 systemd 模板,env 统一收口到
`/etc/vaxstock/vaxstock.env`(已建,600)。**切换是运维动作(C3b),不在代码 PR 内。**

| 服务 | unit | 入口 | 说明 |
|---|---|---|---|
| API | `stock-api.service` | `python -m vaxstock.services.api` | FastAPI/Uvicorn,端口读 `API_PORT`(缺省80) |
| 盘中盯盘 | `intraday-watch.service` | `python -m vaxstock.services.intraday` | 长驻,触发推送 |
| EOD | `vaxstock-eod.service` + `.timer` | `python -m vaxstock.services.eod` | oneshot,次日凌晨05:00 由 timer 拉起 |
| D线观察任务 | `vaxstock-dline-plan.service` | `python -m vaxstock.services.dline_plan` | EOD 成功后 `--no-block` 异步启动,消费 `var/forecast/current_job.json` |

> v2 入口已验:api(内部 uvicorn,`API_PORT` 缺省80)/ intraday(`[--once][--force]`)/ eod(oneshot,退出码 0/1)。

---

## v2 顶替上线步骤(一刀切,有数秒 api 停服窗口)

前置:`/etc/vaxstock/vaxstock.env` 已建(600),venv 已 `pip install -e ".[tracks,dev]"`。

1. 备份旧 unit:`cp /etc/systemd/system/{stock-api,intraday-watch}.service /root/v1-unit-backup/`
2. 禁旧 EOD cron:`crontab -e` 注释掉 `0 16 * * 1-5 ... stock_report_enhanced.py` 那行(避免 v1/v2 双 EOD)。**v1 backtest 那几条不动。**
3. 装 v2 unit:`cp deploy/*.service deploy/*.timer /etc/systemd/system/` ; `systemctl daemon-reload`
4. 切 api+intraday(配套):`systemctl restart stock-api.service intraday-watch.service`
5. 验证:`curl -s -m10 http://127.0.0.1/health` ; `systemctl status stock-api intraday-watch --no-pager | head`
6. 启 EOD timer:`systemctl enable --now vaxstock-eod.timer` ; `systemctl list-timers | grep vaxstock`
7. 手验一次 EOD:`systemctl start vaxstock-eod.service` ; `journalctl -u vaxstock-eod -n 30 --no-pager`

## 回滚(任一步失败)

- api/intraday:`cp /root/v1-unit-backup/*.service /etc/systemd/system/` ; `systemctl daemon-reload` ; `systemctl restart stock-api intraday-watch`
- EOD:`systemctl disable --now vaxstock-eod.timer` ; `crontab -e` 恢复 16:00 那行
- 说明:仅 unit 指向变化,v1 代码 `/opt/stock-report` 原样保留,回滚即恢复。

---

## Auto GitHub commit after EOD / D-line / intraday triggers

`vaxstock-eod.service` and `vaxstock-dline-plan.service` call `python -m vaxstock.services.git_autocommit` in `ExecStartPost`. `intraday-watch.service` is long-running, so `services.intraday` calls `git_autocommit --stage intraday` immediately after a trigger forecast row is written.

Enable it explicitly in `/etc/vaxstock/vaxstock.env`:

```bash
GIT_AUTOCOMMIT_ENABLED=1
GIT_AUTOCOMMIT_PUSH=1
# optional
GIT_AUTOCOMMIT_REMOTE=origin
GIT_AUTOCOMMIT_BRANCH=main
```

Safety rules:

- EOD stage only stages generated A/B/C data and the D-line job envelope: `var/reports`, `var/eval`, `var/prediction`, `var/forecast/current_job.json`, `var/forecast/observation_jobs.jsonl`.
- D-line stage only stages generated D-line task files: `var/forecast/current_job.json`, `var/forecast/current_tasks.json`, `var/forecast/current_tasks.md`, `var/forecast/observation_tasks.jsonl`.
- Intraday stage only stages live D-line/forecast trigger artifacts: `var/forecast/forecasts.jsonl` plus the current D-line task context files needed to read the alert.
- If any non-whitelisted file is dirty, the autocommit step skips and prints the blocking paths.
- Push requires non-interactive GitHub credentials for root/systemd, such as SSH deploy key or a stored credential helper. The code never stores tokens.
- Git prompts are disabled (`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`); missing credentials fail fast in journal logs.
## Private daily action artifact

After `vaxstock-dline-plan.service` reaches a terminal status, it refreshes `var/strategy/daily_action_latest.md` and sends the idempotent `[每日操作]` pre-market plan. After 15:02, the long-running intraday service reads same-day D-line v2 facts from `forecasts.jsonl`, writes separate `var/strategy/close_review_<target>.md` / `close_review_latest.md` artifacts without overwriting the pre-market plan, and sends a separately idempotent `[收盘复盘]` email. A D-line trigger is never treated as an executed order; execution remains pending until confirmed holdings are updated. `status=done` sends the normal plan; `partial_done` / `partial_failed` / `missing_payload` sends an explicit degraded plan with all conditional adds disabled. These files contain private account amounts, are gitignored, and are never committed. Missing account data degrades to pending rather than fabricated amounts. The EOD process still writes A/B/C reports and queues D, but no longer sends the legacy digest email itself.
