# Eval results

Mode: LLM off (rule based agents). Trips: 50 from `evals/trips.jsonl`. Hard checks: `app/tools/checks.py`.

| metric | multi-agent | single pass (no negotiation, no critic) |
|---|---|---|
| trips | 50 | 50 |
| complete plans | 100% | 100% |
| within budget | 96% | 96% |
| avg overspend when over | Rs 380 | Rs 380 |
| plans with zero violations | 100% | 58% |
| avg violations per plan | 0.00 | 0.48 |
| avg places per plan | 4.2 | 4.2 |
| avg negotiation rounds | 0.00 | 0.00 |
| avg latency | 7 ms | 1 ms |
| avg tokens | 0 | 0 |
| avg cost | $0.0000 | $0.0000 |

## Within budget by budget level

Budget level is the trip budget divided by a fair cost estimate (0.6 very tight, 1.6 generous).

| budget level | multi-agent | single pass (no negotiation, no critic) |
|---|---|---|
| 0.6 | 8/10 | 8/10 |
| 0.75 | 10/10 | 10/10 |
| 0.9 | 10/10 | 10/10 |
| 1.2 | 10/10 | 10/10 |
| 1.6 | 10/10 | 10/10 |

## Violations by type

| type | multi-agent | single pass (no negotiation, no critic) |
|---|---|---|
| late_arrival | 0 | 4 |
| too_much_travel | 0 | 20 |
