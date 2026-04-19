# Single-Sepsis Comparison: Fixed Tool Calling vs Toolbox With History

This note compares four Qwen3-30B result folders for the **single-task sepsis** benchmark:

1. [auto_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New project/result/auto_sepsis_Qwen3-30B-A3B-Instruct-2507)
2. [official_single_sepsis_Qwen3-30B-A3B-Instruct-2507](/Users/chloe/Documents/New project/result/official_single_sepsis_Qwen3-30B-A3B-Instruct-2507)
3. [sepsis_toolbox_history_autoformalized_qwen3_30b](/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b)
4. [sepsis_toolbox_history_official_qwen3_30b](/Users/chloe/Documents/New project/result/sepsis_toolbox_history_official_qwen3_30b)

## Main Takeaways

- The old single-sepsis baseline is **not a real longitudinal task** in practice.
  Every step always calls both `query_suspicion_of_infection` and `query_sofa`, so tool use is fixed and history reuse is irrelevant.
- The new toolbox-with-history protocol **is a real longitudinal task**.
  Tool use becomes sparse, selective, and history-sensitive:
  - many steps have no new tool call
  - repeated-call rate becomes measurable
  - necessary-call coverage becomes meaningful
  - marginal utility of a tool call becomes measurable
- On the matched 50-stay cohort, **official toolbox-with-history** is the strongest longitudinal variant.
  It uses far fewer tools than the old official baseline, improves infection onset timing substantially, and keeps evidence discipline clean.
- The cost of realism is real:
  toolbox-with-history is more efficient, but step accuracy is lower than the fixed-tool baseline.
- Across both protocols, **official > autoformalized**.

## Source Of Truth And Caveats

- The old baseline folders contain **98 trajectories**.
- The toolbox-with-history folders contain **50 trajectories**.
- For fair comparison, the fixed-tool baselines were also evaluated on the **matched first 50 trajectory IDs** used by the toolbox runs.
- For the official toolbox folder, [events.jsonl](/Users/chloe/Documents/New project/result/sepsis_toolbox_history_official_qwen3_30b/events.jsonl) appears stale and contains 60 trajectories, while [rollouts.json](/Users/chloe/Documents/New project/result/sepsis_toolbox_history_official_qwen3_30b/rollouts.json) and [eval.json](/Users/chloe/Documents/New project/result/sepsis_toolbox_history_official_qwen3_30b/eval.json) are internally consistent at 50 trajectories.
  This report treats `rollouts.json` and `eval.json` as the source of truth.
- For toolbox runs, the newer `toolbox_efficiency` metrics are more informative than the old `tool_grounding` metric.

## Protocol Meaning

### Old fixed-tool single sepsis

- visible tools: `query_suspicion_of_infection`, `query_sofa`
- behavior in practice: always call both tools each step
- average calls per step: exactly `2.0`
- zero-call rate: `0.0`

This is a useful benchmark baseline, but it is closer to a fixed repeated checklist than to longitudinal monitoring.

### New toolbox with history

- visible tools:
  - `query_suspicion_of_infection`
  - `query_sofa`
  - `query_kdigo_stage`
  - `query_ventilation_status`
- behavior in practice:
  - variable number of calls per step
  - many steps with no new tool call
  - explicit reuse of prior checkpoint history

This is much closer to a real longitudinal monitoring setting.

## Saved Eval Summary

These are the saved run-level evals as found in each folder.

| Run | Backend | Protocol | N trajectories | Step acc | Macro F1 | Infection exact | Alert exact |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Auto baseline | autoformalized | fixed single sepsis | 98 | 0.6589 | 0.5463 | 0.2959 | 0.5612 |
| Official baseline | official | fixed single sepsis | 98 | 0.8003 | 0.6152 | 0.6875 | 0.3958 |
| Auto toolbox | autoformalized | rolling_toolbox_with_history | 50 | 0.5200 | 0.4589 | 0.3800 | 0.4800 |
| Official toolbox | official | rolling_toolbox_with_history | 50 | 0.6743 | 0.6188 | 0.7200 | 0.6000 |

Interpretation:

- On their native saved evals, the official toolbox run already looks competitive on alert timing and clearly better than the auto toolbox run.
- But because the sample sizes differ, the fairest head-to-head comparison is the matched 50-stay slice below.

## Matched 50-Stay Comparison

This uses the 50 trajectory IDs from the toolbox runs and compares all four conditions on the same cohort.

### Step-Level And Tool-Use Summary

| Run | Step acc | Avg tool calls/step | Zero-call rate | Tool counts |
| --- | ---: | ---: | ---: | --- |
| Auto baseline | 0.6457 | 2.0000 | 0.0000 | infection `350`, sofa `350` |
| Official baseline | 0.7686 | 2.0000 | 0.0000 | infection `350`, sofa `350` |
| Auto toolbox | 0.5200 | 0.7171 | 0.2829 | infection `198`, sofa `53` |
| Official toolbox | 0.6743 | 0.5714 | 0.4286 | infection `176`, sofa `24` |

What this means:

- The fixed baselines are rigid:
  - exactly 2 calls per step
  - no history reuse
  - no tool-efficiency tradeoff
- The toolbox runs are genuinely longitudinal:
  - auto toolbox reduces calls by `64.1%` vs auto baseline
  - official toolbox reduces calls by `71.4%` vs official baseline
  - official toolbox makes no new tool call on `42.86%` of steps

```mermaid
xychart-beta
  title "Matched 50 Stays: Step Accuracy"
  x-axis ["Auto baseline", "Auto toolbox", "Official baseline", "Official toolbox"]
  y-axis "Accuracy" 0 --> 0.85
  bar [0.6457, 0.5200, 0.7686, 0.6743]
```

```mermaid
xychart-beta
  title "Matched 50 Stays: Average Tool Calls Per Step"
  x-axis ["Auto baseline", "Auto toolbox", "Official baseline", "Official toolbox"]
  y-axis "Calls / step" 0 --> 2.1
  bar [2.0, 0.7171, 2.0, 0.5714]
```

### Transition Timing On The Matched 50-Stay Cohort

Ground-truth onset was reconstructed directly from the per-step `gt_action` sequence in `rollouts.json`.

| Run | Infection exact | Infection MAE | Infection early | Infection late | Infection missed | Alert exact | Alert MAE | Alert early | Alert late | Alert missed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Auto baseline | 0.3000 | 4.88 | 0.34 | 0.36 | 0.00 | 0.6200 | 2.96 | 0.26 | 0.12 | 0.00 |
| Official baseline | 0.7200 | 2.64 | 0.16 | 0.12 | 0.00 | 0.5600 | 2.64 | 0.36 | 0.08 | 0.00 |
| Auto toolbox | 0.3200 | 4.3333 | 0.32 | 0.32 | 0.04 | 0.4800 | 4.8372 | 0.12 | 0.26 | 0.14 |
| Official toolbox | 0.8200 | 0.40 | 0.18 | 0.00 | 0.00 | 0.6000 | 1.90 | 0.08 | 0.12 | 0.20 |

Key observations:

- **Official toolbox** is the best infection-onset tracker in this comparison:
  - infection exact match improves from `0.72` to `0.82`
  - infection MAE drops from `2.64h` to `0.40h`
  - late infection calls drop from `0.12` to `0.00`
- For alert timing, **official toolbox** also improves precision:
  - alert exact match improves from `0.56` to `0.60`
  - alert MAE improves from `2.64h` to `1.90h`
  - early alert rate drops from `0.36` to `0.08`
- But official toolbox also becomes more conservative at the alert stage:
  - alert missed rate rises from `0.00` to `0.20`
  - this matches the confusion pattern where many true alerts are downgraded to `infection_suspect`
- Auto toolbox is much less stable:
  - infection timing is only slightly better than auto baseline
  - alert timing is worse than auto baseline

```mermaid
xychart-beta
  title "Matched 50 Stays: Infection Onset Exact Match"
  x-axis ["Auto baseline", "Auto toolbox", "Official baseline", "Official toolbox"]
  y-axis "Exact match rate" 0 --> 0.9
  bar [0.30, 0.32, 0.72, 0.82]
```

## Why Toolbox With History Is A Real Longitudinal Task

The strongest evidence is not just the lower call count. It is the fact that tool use becomes behaviorally meaningful.

### Fixed baseline

- every step calls both tools
- repeated-call rate is not interesting because the protocol forces repetition
- necessary-call coverage is trivially perfect because every call is forced
- marginal utility is not meaningful because the model cannot skip low-value calls

### Toolbox with history

- repeated-call rate becomes meaningful
- zero-call steps indicate actual history reuse
- necessary-call coverage shows whether the model knows when it must check something
- positive-action-without-sufficient-evidence shows whether the model is making unsupported decisions
- marginal utility of call shows whether calls add new evidence

This is the core reason the toolbox-with-history protocol is a more realistic longitudinal benchmark.

## Toolbox Efficiency: Official vs Autoformalized

These metrics only apply to the two toolbox-with-history runs.

| Metric | Auto toolbox | Official toolbox |
| --- | ---: | ---: |
| Avg tool calls / step | 0.7171 | 0.5714 |
| Steps without tool calls | 0.2829 | 0.4286 |
| Repeated tool call rate | 0.6972 | 0.6600 |
| Repeated infection call after positive | 0.0101 | 0.0000 |
| Positive action without sufficient evidence | 0.0526 | 0.0000 |
| Necessary infection-call coverage | 0.8837 | 1.0000 |
| Necessary SOFA-call coverage for alert | 1.0000 | 1.0000 |
| Marginal utility of any call | 0.4502 | 0.3900 |

Tool mix:

| Run | Infection calls | SOFA calls | SOFA share |
| --- | ---: | ---: | ---: |
| Auto toolbox | 198 | 53 | 21.1% |
| Official toolbox | 176 | 24 | 12.0% |

Per-tool marginal utility:

| Run | Infection-call utility | SOFA-call utility |
| --- | ---: | ---: |
| Auto toolbox | 0.4192 | 0.5660 |
| Official toolbox | 0.3352 | 0.7917 |

Interpretation:

- Official toolbox is more disciplined:
  - fewer calls overall
  - more zero-call steps
  - no unsupported positive actions
  - perfect necessary-call coverage on both infection and SOFA
- Official SOFA calls are much more targeted:
  - only `24` SOFA calls total
  - but `79.17%` of them are marginally useful
- Auto toolbox explores more and calls SOFA more often, but still produces more unsupported positives and weaker decision quality

```mermaid
xychart-beta
  title "Toolbox Runs: Tool Mix"
  x-axis ["Auto infection", "Auto SOFA", "Official infection", "Official SOFA"]
  y-axis "Calls" 0 --> 220
  bar [198, 53, 176, 24]
```

## Error Pattern Comparison

### Official baseline

Main pattern on matched 50:

- strong `keep_monitoring -> keep_monitoring`
- strong `trigger_sepsis_alert -> trigger_sepsis_alert`
- but substantial hard over-alerting:
  - `keep_monitoring -> trigger_sepsis_alert`: `39`

This looks like a powerful but blunt fixed-checklist policy.

### Official toolbox

Main pattern on matched 50:

- `keep_monitoring -> keep_monitoring`: `145`
- `trigger_sepsis_alert -> trigger_sepsis_alert`: `56`
- `trigger_sepsis_alert -> infection_suspect`: `56`
- `keep_monitoring -> trigger_sepsis_alert`: `19`

So the toolbox policy reduces hard false alerts, but often stops one level short of the final alert.

### Auto baseline

Main pattern on matched 50:

- `keep_monitoring -> keep_monitoring`: `116`
- `trigger_sepsis_alert -> trigger_sepsis_alert`: `102`
- `keep_monitoring -> trigger_sepsis_alert`: `56`

This version over-alerts aggressively.

### Auto toolbox

Main pattern on matched 50:

- `keep_monitoring -> keep_monitoring`: `121`
- `keep_monitoring -> infection_suspect`: `67`
- `trigger_sepsis_alert -> trigger_sepsis_alert`: `47`
- `trigger_sepsis_alert -> infection_suspect`: `46`

This version shifts many errors into overcalling `infection_suspect`.

## Bottom Line

If the goal is raw step accuracy, the old **official fixed-tool baseline** is still strongest.

If the goal is a **real longitudinal benchmark with meaningful tool-use evaluation**, the most promising condition here is **official toolbox with history**:

- it uses much less tool budget
- it makes explicit history reuse possible
- it keeps evidence use disciplined
- it achieves the best infection-onset timing on the matched cohort
- it improves alert timing precision relative to the fixed official baseline

Its main remaining weakness is clear:

- it under-calls or under-escalates at the alert stage
- practically, that means too many true alerts become `infection_suspect`
- the next prompt/tooling improvement should focus on when SOFA re-checking is necessary for escalation

## Suggested Next Follow-Up

The best next analysis or patch is:

1. keep the official toolbox-with-history protocol as the main longitudinal direction
2. tighten escalation behavior for true alert transitions
3. specifically target the `trigger_sepsis_alert -> infection_suspect` error mode
4. keep using toolbox-efficiency metrics as first-class outputs, not just step accuracy
