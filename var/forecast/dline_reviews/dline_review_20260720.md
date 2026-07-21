# D线规则效果复核 20260720

- 长期结果: 已触发与合格未触发按同一收益口径对照。
- 盘中演变: 仅使用触发后已验证 quote 计算 15/30 分钟与收盘前路径。
- 边界: 不读取用户成交,不自动修改生产参数。

| 规则版本 | 触发类型 | 周期 | 触发/未触发 | 长期命中 | 增量分离 | 30分钟命中 | 收盘命中 | 时机诊断 | 规则结论 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| d_observe_llm_v2 | breakdown_confirm | T+1 | 34/16 | 58% | -0.26% | 38% (N=16) | 76% (N=17) | preliminary_trigger_early | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+10 | 2/0 | 100% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakdown_confirm | T+5 | 9/0 | 100% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakout_confirm | T+1 | 5/4 | 22% | -2.93% | 100% (N=1) | 100% (N=1) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakout_confirm | T+10 | 3/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakout_confirm | T+5 | 4/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+1 | 3/4 | 14% | -4.41% | 50% (N=2) | 50% (N=2) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+5 | 1/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+1 | 11/2 | 46% | +5.08% | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+5 | 3/0 | 33% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | reclaim_confirm | T+1 | 12/29 | 76% | +1.18% | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | preliminary_support |
| d_observe_llm_v2 | reclaim_confirm | T+10 | 1/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | reclaim_confirm | T+5 | 5/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | risk_off_confirm | T+1 | 5/0 | 80% | 待验证 | 0% (N=1) | 100% (N=1) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | risk_off_confirm | T+5 | 1/0 | 100% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |

> 结论只是可审计证据;生产D线规则不会自动调参。
