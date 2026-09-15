# D线规则效果复核 20260824

- 长期结果: 已触发与合格未触发按同一收益口径对照。
- 盘中演变: 仅使用触发后已验证 quote 计算 15/30 分钟与收盘前路径。
- 边界: 不读取用户成交,不自动修改生产参数。

| 规则版本 | 触发类型 | 周期 | 触发/未触发 | 长期命中 | 增量分离 | 30分钟命中 | 收盘命中 | 时机诊断 | 规则结论 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| d_observe_llm_v2 | breakdown_confirm | T+1 | 59/95 | 47% | +0.32% | 51% (N=39) | 60% (N=42) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+10 | 56/67 | 58% | +5.73% | 49% (N=37) | 59% (N=39) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+30 | 9/0 | 78% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakdown_confirm | T+5 | 58/87 | 47% | +2.53% | 50% (N=38) | 59% (N=41) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakout_confirm | T+1 | 7/18 | 40% | -3.31% | 67% (N=3) | 67% (N=3) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | breakout_confirm | T+10 | 6/12 | 50% | -11.47% | 100% (N=2) | 100% (N=2) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | breakout_confirm | T+30 | 4/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakout_confirm | T+5 | 6/15 | 43% | -7.33% | 100% (N=2) | 100% (N=2) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | failed_breakout | T+1 | 5/9 | 29% | -2.09% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | failed_breakout | T+10 | 4/5 | 44% | -2.49% | 33% (N=3) | 33% (N=3) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+30 | 1/0 | 100% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+5 | 5/7 | 17% | -3.72% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | noise_filter | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+30 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+1 | 22/14 | 39% | -0.56% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+10 | 22/14 | 33% | -6.91% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+30 | 3/0 | 0% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+5 | 22/14 | 39% | -1.64% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | reclaim_confirm | T+1 | 30/107 | 53% | -1.58% | 39% (N=18) | 61% (N=18) | preliminary_trigger_early | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+10 | 24/85 | 53% | -5.09% | 50% (N=12) | 75% (N=12) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+30 | 5/0 | 20% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | reclaim_confirm | T+5 | 28/103 | 54% | -3.17% | 44% (N=16) | 69% (N=16) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | risk_off_confirm | T+1 | 9/9 | 33% | -2.17% | 25% (N=4) | 40% (N=5) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | risk_off_confirm | T+10 | 9/5 | 64% | +4.68% | 25% (N=4) | 40% (N=5) | insufficient_intraday_path | preliminary_support |
| d_observe_llm_v2 | risk_off_confirm | T+30 | 1/0 | 100% | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | risk_off_confirm | T+5 | 9/8 | 53% | +1.89% | 25% (N=4) | 40% (N=5) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | weak_rebound | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+30 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |

> 结论只是可审计证据;生产D线规则不会自动调参。
