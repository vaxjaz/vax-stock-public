# D线规则效果复核 20260727

- 长期结果: 已触发与合格未触发按同一收益口径对照。
- 盘中演变: 仅使用触发后已验证 quote 计算 15/30 分钟与收盘前路径。
- 边界: 不读取用户成交,不自动修改生产参数。

| 规则版本 | 触发类型 | 周期 | 触发/未触发 | 长期命中 | 增量分离 | 30分钟命中 | 收盘命中 | 时机诊断 | 规则结论 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| d_observe_llm_v2 | breakdown_confirm | T+1 | 54/44 | 49% | +0.02% | 51% (N=35) | 59% (N=37) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+10 | 9/0 | 67% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakdown_confirm | T+5 | 43/22 | 65% | +4.97% | 46% (N=24) | 73% (N=26) | mixed_intraday_path | stable_support |
| d_observe_llm_v2 | breakout_confirm | T+1 | 5/6 | 36% | -3.17% | 100% (N=1) | 100% (N=1) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | breakout_confirm | T+10 | 4/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakout_confirm | T+5 | 5/4 | 22% | -7.21% | 100% (N=1) | 100% (N=1) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+1 | 3/5 | 25% | -2.47% | 50% (N=2) | 50% (N=2) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+10 | 1/0 | 100% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+5 | 3/4 | 14% | -1.65% | 50% (N=2) | 50% (N=2) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+1 | 19/12 | 42% | -0.43% | 50% (N=8) | 50% (N=8) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | panic_rebound_probe | T+10 | 3/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+5 | 15/6 | 29% | -2.85% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | reclaim_confirm | T+1 | 19/70 | 58% | -1.02% | 57% (N=7) | 57% (N=7) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+10 | 5/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | reclaim_confirm | T+5 | 13/45 | 48% | -6.56% | 100% (N=1) | 100% (N=1) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | risk_off_confirm | T+1 | 8/2 | 40% | -1.54% | 25% (N=4) | 50% (N=4) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | risk_off_confirm | T+10 | 1/0 | 100% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | risk_off_confirm | T+5 | 6/1 | 71% | +2.47% | 50% (N=2) | 100% (N=2) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |

> 结论只是可审计证据;生产D线规则不会自动调参。
