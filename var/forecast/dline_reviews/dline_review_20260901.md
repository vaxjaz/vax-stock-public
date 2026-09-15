# D线规则效果复核 20260901

- 长期结果: 已触发与合格未触发按同一收益口径对照。
- 盘中演变: 仅使用触发后已验证 quote 计算 15/30 分钟与收盘前路径。
- 边界: 不读取用户成交,不自动修改生产参数。

| 规则版本 | 触发类型 | 周期 | 触发/未触发 | 长期命中 | 增量分离 | 30分钟命中 | 收盘命中 | 时机诊断 | 规则结论 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| d_observe_llm_v2 | breakdown_confirm | T+1 | 62/115 | 49% | +0.51% | 54% (N=41) | 58% (N=45) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+10 | 59/90 | 50% | +4.13% | 51% (N=39) | 60% (N=42) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+30 | 49/31 | 54% | +0.52% | 50% (N=30) | 59% (N=32) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakdown_confirm | T+5 | 59/100 | 45% | +2.69% | 51% (N=39) | 60% (N=42) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | breakout_confirm | T+1 | 8/18 | 38% | -2.91% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | breakout_confirm | T+10 | 7/16 | 57% | -10.21% | 67% (N=3) | 67% (N=3) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | breakout_confirm | T+30 | 5/4 | 33% | -1.52% | 100% (N=1) | 100% (N=1) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | breakout_confirm | T+5 | 7/18 | 48% | -6.72% | 67% (N=3) | 67% (N=3) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | failed_breakout | T+1 | 7/10 | 35% | -1.83% | 33% (N=6) | 33% (N=6) | preliminary_intraday_conflict | preliminary_conflict |
| d_observe_llm_v2 | failed_breakout | T+10 | 5/9 | 36% | -0.09% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | failed_breakout | T+30 | 3/4 | 57% | +4.89% | 50% (N=2) | 50% (N=2) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | failed_breakout | T+5 | 5/10 | 13% | -2.77% | 50% (N=4) | 50% (N=4) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | noise_filter | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+30 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | noise_filter | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | panic_rebound_probe | T+1 | 22/14 | 39% | -0.56% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+10 | 22/14 | 33% | -6.91% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+30 | 18/12 | 27% | -8.03% | 43% (N=7) | 57% (N=7) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | panic_rebound_probe | T+5 | 22/14 | 39% | -1.64% | 55% (N=11) | 64% (N=11) | mixed_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | reclaim_confirm | T+1 | 34/126 | 52% | -1.54% | 43% (N=21) | 59% (N=22) | mixed_intraday_path | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+10 | 30/104 | 56% | -3.57% | 39% (N=18) | 61% (N=18) | preliminary_trigger_early | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+30 | 15/58 | 42% | -9.49% | 100% (N=3) | 67% (N=3) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | reclaim_confirm | T+5 | 30/112 | 54% | -3.27% | 39% (N=18) | 61% (N=18) | preliminary_trigger_early | mixed |
| d_observe_llm_v2 | risk_off_confirm | T+1 | 9/12 | 33% | -1.76% | 25% (N=4) | 40% (N=5) | insufficient_intraday_path | preliminary_conflict |
| d_observe_llm_v2 | risk_off_confirm | T+10 | 9/9 | 50% | +2.41% | 25% (N=4) | 40% (N=5) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | risk_off_confirm | T+30 | 7/2 | 67% | -1.27% | 33% (N=3) | 67% (N=3) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | risk_off_confirm | T+5 | 9/9 | 50% | +1.23% | 25% (N=4) | 40% (N=5) | insufficient_intraday_path | mixed |
| d_observe_llm_v2 | weak_rebound | T+1 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+10 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+30 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |
| d_observe_llm_v2 | weak_rebound | T+5 | 0/0 | 待验证 | 待验证 | 待验证 (N=0) | 待验证 (N=0) | insufficient_intraday_path | insufficient_counterfactual |

> 结论只是可审计证据;生产D线规则不会自动调参。
