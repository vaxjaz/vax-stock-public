# D线规则效果复核 20260914

- 长期结果: 已触发与合格未触发按同一收益口径对照。
- 盘中演变: 仅使用触发后已验证 quote 计算 15/30 分钟与收盘前路径。
- 边界: 不读取用户成交,不自动修改生产参数。

| 规则版本 | 触发类型 | 周期 | 触发/未触发 | 长期命中 | 增量分离 | 30分钟命中 | 收盘命中 | 时机诊断 | 规则结论 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| d_observe_llm_v2 | breakdown_confirm | T+1 | 68/132 | 50% | +0.53% | 52% (N=46) | 57% (N=51) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+10 | 62/115 | 47% | +4.04% | 54% (N=41) | 58% (N=45) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+30 | 55/55 | 43% | -3.13% | 50% (N=36) | 61% (N=38) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+5 | 68/132 | 44% | +2.43% | 52% (N=46) | 57% (N=51) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakout_confirm | T+1 | 8/18 | 38% | -2.91% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | breakout_confirm | T+10 | 8/18 | 58% | -9.15% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | breakout_confirm | T+30 | 5/8 | 54% | -4.72% | 100% (N=1) | 100% (N=1) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | breakout_confirm | T+5 | 8/18 | 46% | -5.74% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | failed_breakout | T+1 | 7/10 | 35% | -1.83% | 33% (N=6) | 33% (N=6) | preliminary_intraday_conflict | preliminary_conflict |
| d_observe_llm_v2 | failed_breakout | T+10 | 7/10 | 35% | -1.30% | 33% (N=6) | 33% (N=6) | preliminary_intraday_conflict | preliminary_conflict |
| d_observe_llm_v2 | failed_breakout | T+30 | 4/5 | 67% | +6.45% | 33% (N=3) | 33% (N=3) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+5 | 7/10 | 18% | -4.24% | 33% (N=6) | 33% (N=6) | preliminary_intraday_conflict | preliminary_conflict |
| d_observe_llm_v2 | noise_filter | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+30 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+1 | 22/14 | 39% | -0.56% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+10 | 22/14 | 33% | -6.91% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+30 | 22/14 | 28% | -7.74% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+5 | 22/14 | 39% | -1.64% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | reclaim_confirm | T+1 | 37/147 | 52% | -1.50% | 42% (N=24) | 56% (N=25) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+10 | 34/126 | 59% | -3.16% | 43% (N=21) | 59% (N=22) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+30 | 22/79 | 44% | -8.16% | 50% (N=10) | 70% (N=10) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+5 | 37/147 | 57% | -2.59% | 42% (N=24) | 56% (N=25) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | risk_off_confirm | T+1 | 10/13 | 39% | -1.29% | 40% (N=5) | 50% (N=6) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | risk_off_confirm | T+10 | 9/12 | 48% | +1.61% | 25% (N=4) | 40% (N=5) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | risk_off_confirm | T+30 | 8/5 | 62% | +4.71% | 25% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_support |
| d_observe_llm_v2 | risk_off_confirm | T+5 | 10/13 | 43% | +0.50% | 40% (N=5) | 50% (N=6) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | weak_rebound | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+30 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |

> 结论只是可审计证据;生产D线规则不会自动调参。
