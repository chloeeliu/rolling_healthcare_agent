# Rolling Surveillance Evaluation Final Report

Date: 2026-05-06

## Scope

This report synthesizes the final rolling-surveillance evaluation artifacts under:

- `result/rolling_eval_autoform/`
- `result/rolling_eval_zeroshot/`

It is written against the benchmark design and writing guidance in:

- `docs/surveilance/general_icu_surveillance_dataset_design_2026-04-25.md`
- `docs/surveilance/checkpoint_ground_truth_curation_2026-04-25.md`
- `docs/surveilance/checkpoint_ground_truth_build_report_2026-04-25.md`
- `docs/surveilance/paper_longitudinal_writing_notes_2026-05-02.md`

The goal is to give a paper-ready, method-aware interpretation of the final results, with explicit attention to the difference between:

- completed versus partial runs
- open-weight/open-source models versus closed-source API models
- top-level surveillance action prediction versus full rolling state tracking

## Executive Summary

- The evaluation now spans two distinct surveillance backends:
  - `session_tools` autoformalization, where the agent queries the autoformalized function and guideline layer
  - `zeroshot_python`, where the agent reasons directly over checkpoint-scoped raw MIMIC-IV tables through Python and `query_db`
- The benchmark output is a structured surveillance decision, not a binary action label alone. The model must return disease/state names through `suspected_conditions` and `alerts`, while `global_action` and `priority` are compressed response-layer summaries derived from that richer state.
- The benchmark remains difficult even for the strongest available runs. On the primary autoformalized `benchmark_2k` setting, no fully completed model exceeded `45.77%` `global_action_accuracy` or `43.32%` `priority_accuracy`, and the family-level core metrics remained substantially lower than those coarse summaries.
- Among the fully completed `2,000`-stay open-weight autoformalized runs, `Qwen3.5-27B` is the strongest overall model. It is best on `global_action_accuracy`, `priority_accuracy`, and `suspected_conditions_macro_f1`, while also missing fewer alert trajectories than the smaller Qwen variants.
- `gpt-oss-120b` is the most promising partially completed open-weight autoformalized run. On the first `1,026` completed trajectories of `benchmark_2k`, it substantially outperforms the finished Qwen runs on several core and temporal metrics. However, it is still incomplete and should be reported as provisional rather than as the primary headline.
- The zero-shot raw-table setting tells a different story. On the short `benchmark_100` evaluation, closed-source models are clearly strongest: `Gemini 3.1 Pro Preview` leads suspect-family recovery (`0.4393` macro F1), while `Claude Sonnet 4.6` leads alert-family recovery (`0.4722` macro F1) and first-alert timing (`3.95h` mean absolute error). `GPT-5.4` is intermediate but still comfortably ahead of the open-weight zero-shot runs.
- For open-weight Qwen models, zero-shot versus autoformalization is not a simple win or loss. Autoformalization generally improves action calibration and alert-family recovery for the smaller Qwen models, especially on active-interval and TTL-style semantics, but `Qwen3.5-27B` retains better raw-table suspect-family recovery and stronger persistent / cumulative semantics under zero-shot. The tradeoff is that the autoformalized `27B` run becomes more conservative and misses many more alerting trajectories.
- The closed-source comparison must be qualified by backend. In zero-shot `benchmark_100`, the closed-source models are complete and clearly stronger. In autoformalization, the saved closed-source runs are incomplete and tool-error-heavy, so they are not fair leaderboard entries. Across nearly all settings, the core difficulty remains the same: models are better at deciding that some monitoring or escalation action is needed than they are at reconstructing the correct full disease-family state over time.

## Benchmark Recap

This benchmark is a rolling current-state ICU surveillance task, not a future-prediction task.

The evaluated agent must repeatedly infer the patient's surveillance state at each checkpoint from:

- checkpoint-scoped EHR evidence
- function and guideline discovery via `session_tools`
- compressed memory from prior checkpoints

The main benchmark configuration is:

- cohort: `2,000` held-out ICU stays
- horizon: `0, 4, ..., 48` hours
- checkpoints per stay: `13`
- total checkpoint rows: about `26,000`
- latent decision space: `25` decisions
- decision families: `8`

The benchmark intentionally mixes several temporal semantics:

- persistent episode states
- cumulative worst-so-far states
- active support intervals
- recent-measurement states with TTL
- recomputed composite states

That mixed temporal structure is central to interpretation. A model can perform reasonably on a top-level action label while still failing to maintain the correct evolving clinical state across families such as infection, sepsis, renal dysfunction, respiratory support, hemodynamics, neurologic impairment, metabolic derangement, and coagulation.

## Experiment Modes

The combined results here come from two surveillance backends that expose very different interfaces to the model.

### `zeroshot_python`

This is the raw-table setting.

Per the runbook, the model receives a checkpoint-scoped Python session with:

- `search_guidelines`
- `get_guideline`
- `search_functions`
- `get_function_info`
- `load_function`
- `query_db`

This means the model can directly inspect raw MIMIC-IV evidence through DuckDB queries inside the checkpoint session.

### `session_tools`

This is the autoformalization setting.

Instead of directly calling `query_db`, the model operates through outer tools:

- `search_guidelines`
- `get_guideline`
- `search_functions`
- `get_function_info`
- `load_function`
- `call_function`

So the comparison is not merely “prompt A versus prompt B.” It is a comparison between:

- direct raw-table reasoning with Python and ad hoc querying
- structured access through the formalized surveillance function layer

## Response-Layer Compression

An important reporting point is that the benchmark does **not** ask the model to output only a binary label.

The runtime output contract is a structured checkpoint decision:

- `global_action`
- `suspected_conditions`
- `alerts`
- `priority`

The clinically richer part of the output is:

- `suspected_conditions`
- `alerts`

Those fields carry the concrete disease-family or surveillance-state names.

By design, `global_action` and `priority` are compressed summaries derived from the richer checkpoint state rather than the benchmark’s full target space:

- `global_action = escalate` if any alert-level family is active, else `continue_monitoring`
- `priority` is derived from high-acuity families and suspect/alert burden

This matters for interpretation:

- `global_action_accuracy` and `priority_accuracy` are useful coarse summary metrics
- but they should not be treated as the main evidence that the benchmark is clinically meaningful
- the main benchmark difficulty lives in the structured family-state outputs and their temporal dynamics

The released `benchmark_2k` label distribution also shows that these coarse summaries are heavily compressed:

- `global_action`: `77.36%` `escalate`, `22.64%` `continue_monitoring`
- `priority`: `40.71%` `medium`, `38.49%` `high`, `20.80%` `low`

So a model can achieve a superficially moderate coarse score without truly recovering the correct disease-family state.

## Evaluation Status Audit

Not all runs finished cleanly, and the two backends have very different coverage. This matters for fair reporting.

| Mode | Model | Family | `benchmark_100` | `benchmark_2k` | Status note |
|---|---|---|---:|---:|---|
| `session_tools` | `Qwen3.5-27B` | open-weight | `100/100` | `2000/2000` | fully completed |
| `session_tools` | `Qwen3.5-9B` | open-weight | `100/100` recovered from `rollouts.json` | `2000/2000` | `benchmark_100` canonical trajectory file was truncated, but saved rollouts cover all `100` stays |
| `session_tools` | `Qwen3.5-4B` | open-weight | `100/100` | `2000/2000` | fully completed |
| `session_tools` | `gpt-oss-120b` | open-weight | `100/100` | `1026/2000` recovered | `benchmark_2k` interrupted by backend error |
| `session_tools` | `gemma-4-31B-it` | open-weight | `100/100` | `1714/2000` recovered | `benchmark_2k` incomplete |
| `session_tools` | `Claude/claude-sonnet-4-6` | closed-source | `28/100` recovered | not run | interrupted |
| `session_tools` | `Gemini/gemini-3.1-pro-preview` | closed-source | `24/100` recovered | not run | interrupted |
| `zeroshot_python` | `GPT/gpt-5.4` | closed-source | `100/100` | not run | completed short raw-table pilot |
| `zeroshot_python` | `Claude/claude-sonnet-4-6` | closed-source | `100/100` | not run | completed short raw-table pilot |
| `zeroshot_python` | `Gemini/gemini-3.1-pro-preview` | closed-source | `100/100` | not run | completed short raw-table pilot |
| `zeroshot_python` | `Qwen3.5-27B` | open-weight | `100/100` | not run | completed short raw-table pilot |
| `zeroshot_python` | `Qwen3.5-9B` | open-weight | `100/100` | not run | completed short raw-table pilot |
| `zeroshot_python` | `Qwen3.5-4B` | open-weight | `100/100` | `394/2000` recovered | only saved partial long raw-table run |
| `zeroshot_python` | `gpt-oss-120b` | open-weight | `100/100` | not run | completed short raw-table pilot |
| `zeroshot_python` | `gemma-4-31B-it` | open-weight | `100/100` | not run | completed short raw-table pilot |

Important implications:

- the only clean, apples-to-apples primary comparison on the full `2,000`-stay benchmark is still among the completed autoformalized Qwen runs
- `gpt-oss-120b` and `gemma-4-31B-it` remain informative but provisional on autoformalized `benchmark_2k`
- the zero-shot raw-table setting currently supports a fair `benchmark_100` comparison across open-weight and closed-source models
- there is no completed zero-shot `benchmark_2k` leaderboard, so short raw-table performance should not be overgeneralized to the full benchmark
- the autoformalized closed-source results remain pilot evidence only and should not be presented as definitive leaderboard entries

Artifact provenance note:

- when `evaluation.json` is available, its metrics are used directly
- when `rollouts.json` is available, it is preferred over `trajectories.jsonl` for completion recovery
- `events.jsonl` is useful for provenance, but not always sufficient to reconstruct missing completed rollouts

## Metric Hierarchy

The report uses the following priority order.

### Core benchmark metrics

- `suspected_conditions_macro_f1`
- `alerts_macro_f1`
- `alerts_macro_precision`
- `alerts_macro_recall`
- `suspected_conditions_exact_match`
- `alerts_exact_match`

These are the main structured-state metrics because they directly evaluate whether the model recovered the correct disease-family surveillance state.

### Temporal and patient-level metrics

- `first_alert_mean_abs_error_hours`
- `false_early_alert_trajectories`
- `missed_alert_trajectories`
- `strict_all4_trajectory_rate`

These matter because this is a longitudinal benchmark. A model that is locally plausible but cannot sustain the correct surveillance picture over the full stay is still failing an important part of the task.

### Auxiliary coarse response-layer summaries

- `global_action_accuracy`
- `priority_accuracy`

These are still useful, but they are secondary because they compress the richer checkpoint state into simplified action and urgency labels.

## Metric Note

For completed runs, this report uses the saved `evaluation.json` metrics directly.

For incomplete runs, metrics were reconstructed from saved `trajectories.jsonl` using the same set-metric convention implied by the saved evaluation summaries:

- empty gold and empty prediction count as `1.0` precision and recall for the set-based family metrics

This keeps the provisional numbers aligned with the completed-run summaries.

In addition to the official metrics, this report also uses one derived strict stay-level metric:

- `strict_all4_trajectory_rate`: a stay counts as correct only if every checkpoint exactly matches all four exposed outputs:
  - `global_action`
  - `priority`
  - `suspected_conditions`
  - `alerts`

This is not a saved official metric, but it is a useful patient-level longitudinal indicator.

## Why Trajectory-Level Metrics Matter

Trajectory-level performance is important in this benchmark because the clinical task is not merely to be locally plausible at isolated checkpoints.

What we want to know is whether a model can:

- maintain the right surveillance state across time
- trigger alerts at the right point in the stay
- avoid silently missing whole alerting trajectories
- stay longitudinally consistent under mixed temporal semantics

So while strict exact trajectory correctness is harsh, it is still meaningful. It should not be the only metric, but it belongs in the core interpretation of a rolling surveillance benchmark rather than being treated as a throwaway appendix-only statistic.

## Metric Definitions

The surveillance metrics are defined in `src/sepsis_mvp/environment.py`.

### Auxiliary coarse summaries

### `global_action_accuracy`

At each checkpoint, the model predicts a top-level surveillance decision.
This metric is the fraction of checkpoints where that top-level action exactly matches the benchmark label.

Interpretation:

- high values mean the model often gets the overall surveillance posture right
- this does **not** mean it has reconstructed the correct detailed disease-family state

### `priority_accuracy`

At each checkpoint, the model predicts the urgency level.
This metric is the fraction of checkpoints where the predicted urgency matches the benchmark label.

Interpretation:

- severity calibration
- stricter than simple action correctness because a model can choose the right action direction but the wrong urgency

### Core structured-state metrics

### `suspected_conditions_exact_match`

At each checkpoint, the benchmark exposes a set of active suspect-level family states.
This metric asks whether the predicted set matches the gold set **exactly**.

Interpretation:

- harsh set-level metric
- a single extra or missing suspect label makes the whole checkpoint wrong

### `alerts_exact_match`

Same idea as above, but for the alert-level family state set.

Interpretation:

- exact structured alert-state recovery
- useful, but harsh

### `suspected_conditions_macro_f1`

At each checkpoint, compare the predicted suspect set to the gold suspect set with set-based F1, then average across checkpoints.

Important detail:

- when both the gold and predicted sets are empty, the saved evaluation convention treats precision and recall as `1.0`

Interpretation:

- better than exact match for measuring partial family-state recovery
- still reflects both misses and spurious extra family labels

### `alerts_macro_precision`

Average set precision for the predicted alert set over checkpoints.

Interpretation:

- of the alert-family labels the model emitted, how many were correct

### `alerts_macro_recall`

Average set recall for the gold alert set over checkpoints.

Interpretation:

- of the alert-family labels that should have been active, how many did the model recover

### `alerts_macro_f1`

The harmonic mean of alert precision and recall at each checkpoint, averaged across checkpoints.

Interpretation:

- best single family-level summary of alert-state reconstruction

### Temporal and patient-level metrics

### `first_alert_mean_error_hours`

For stays where both the benchmark and the model emitted a first alert, compute:

- predicted first-alert hour minus gold first-alert hour

Then average that signed timing error.

Interpretation:

- negative means early alerts on average
- positive means late alerts on average

### `first_alert_mean_abs_error_hours`

Average absolute timing error for the first alert.

Interpretation:

- how far off the model is, regardless of direction

### `false_early_alert_trajectories`

Count of stays where the model’s first alert happened earlier than the benchmark’s first alert.

### `missed_alert_trajectories`

Count of stays where the benchmark had at least one alert but the model never emitted an alert.

Interpretation:

- trajectory-level alert omission
- especially important in this benchmark because many models are conservative

## Autoformalization Primary Results: `benchmark_2k`

`benchmark_2k` is the main benchmark and should be the primary table in the paper.

### Core and Temporal Metrics

| Model | Completed stays | `suspected_conditions_macro_f1` | `alerts_macro_f1` | `alerts_macro_precision` | `alerts_macro_recall` | `suspected_conditions_exact_match` | `alerts_exact_match` | `first_alert_mean_abs_error_hours` | `false_early_alert_trajectories` | `missed_alert_trajectories` | `strict_all4_trajectory_rate` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | `2000/2000` | `0.1472` | `0.2423` | `0.2643` | `0.2355` | `0.1239` | `0.2195` | `10.6119` | `37` | `909` | `0.0110` |
| `Qwen3.5-4B` | `2000/2000` | `0.1396` | `0.2453` | `0.2647` | `0.2390` | `0.1171` | `0.2232` | `9.5982` | `34` | `982` | `0.0090` |
| `Qwen3.5-9B` | `2000/2000` | `0.1366` | `0.2456` | `0.2707` | `0.2380` | `0.1266` | `0.2213` | `12.1627` | `17` | `998` | `0.0115` |
| `gpt-oss-120b` | `1026/2000` | `0.2054` | `0.2533` | `0.2759` | `0.2476` | `0.1276` | `0.2123` | `6.8496` | `58` | `209` | `0.0049` |
| `gemma-4-31B-it` | `1714/2000` | `0.1344` | `0.2277` | `0.2304` | `0.2269` | `0.1309` | `0.2253` | `22.9554` | `2` | `1455` | `0.0117` |

### Auxiliary Coarse Summary Metrics

| Model | Completed stays | `global_action_accuracy` | `priority_accuracy` |
|---|---:|---:|---:|
| `Qwen3.5-27B` | `2000/2000` | `0.4577` | `0.4332` |
| `Qwen3.5-4B` | `2000/2000` | `0.4153` | `0.3993` |
| `Qwen3.5-9B` | `2000/2000` | `0.4083` | `0.3726` |
| `gpt-oss-120b` | `1026/2000` | `0.6317` | `0.5206` |
| `gemma-4-31B-it` | `1714/2000` | `0.2674` | `0.2409` |

## Structured-State Metric Decomposition

The suspect and alert set metrics need to be interpreted carefully because both include a large number of negative-set checkpoints. That makes the overall exact-match metrics deceptively flat across models.

For the primary `benchmark_2k` release:

- gold suspect set empty rate: `0.1281`
- gold alert set empty rate: `0.2264`

This means that a model that frequently predicts empty sets can accumulate a non-trivial exact-match score without truly recovering positive disease-state structure.

All decomposition values below were recomputed directly from `benchmark_2k` `rollouts.json` using the same `_set_f1` scorer implemented in [environment.py](/Users/chloe/Documents/New%20project/src/sepsis_mvp/environment.py:422). This keeps the split tables numerically aligned with the official `evaluation.json` step-level metrics.

### Finished Qwen Models: Overall Set Metrics

| Model | `suspect_overall_exact` | `suspect_overall_macro_f1` | `alert_overall_exact` | `alert_overall_macro_f1` | `alert_overall_macro_precision` | `alert_overall_macro_recall` |
|---|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | `0.1239` | `0.1472` | `0.2195` | `0.2423` | `0.2643` | `0.2355` |
| `Qwen3.5-9B` | `0.1266` | `0.1366` | `0.2213` | `0.2456` | `0.2707` | `0.2380` |
| `Qwen3.5-4B` | `0.1171` | `0.1396` | `0.2232` | `0.2453` | `0.2647` | `0.2390` |

At first glance these values look very close, especially for `alert_overall_exact`, which clusters around `0.22`.

### Finished Qwen Models: Negative-Set Checkpoints

| Model | `suspect_negative_exact` | `suspect_negative_pred_empty_rate` | `alert_negative_exact` | `alert_negative_pred_empty_rate` |
|---|---:|---:|---:|---:|
| `Qwen3.5-27B` | `0.9189` | `0.9189` | `0.9529` | `0.9529` |
| `Qwen3.5-9B` | `0.9601` | `0.9601` | `0.9647` | `0.9647` |
| `Qwen3.5-4B` | `0.8766` | `0.8766` | `0.9477` | `0.9477` |

Under the benchmark scorer, empty-empty pairs receive precision `= 1`, recall `= 1`, and F1 `= 1`. As a result, the negative-only exact-match and negative-only F1 values move together; the simpler exact / predicted-empty presentation is therefore sufficient for the negative slice.

These negative-case results explain the clustering:

- almost all exact matches on alert sets come from checkpoints where the gold alert set is empty
- similarly, a large fraction of suspect-set exactness comes from empty suspect checkpoints

In other words:

- `alert_overall_exact` near `0.22` is largely an empty-alert baseline effect
- `suspect_overall_exact` near `0.12` is similarly anchored by empty-suspect checkpoints

### Finished Qwen Models: Positive-Set Checkpoints

| Model | `suspect_positive_exact` | `suspect_positive_pred_nonempty_rate` | `suspect_positive_macro_f1` | `alert_positive_exact` | `alert_positive_pred_nonempty_rate` | `alert_positive_macro_f1` | `alert_positive_macro_precision` | `alert_positive_macro_recall` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | `0.0071` | `0.1657` | `0.0338` | `0.0049` | `0.3124` | `0.0343` | `0.0628` | `0.0255` |
| `Qwen3.5-9B` | `0.0041` | `0.0758` | `0.0156` | `0.0038` | `0.2449` | `0.0352` | `0.0676` | `0.0253` |
| `Qwen3.5-4B` | `0.0055` | `0.2112` | `0.0313` | `0.0112` | `0.2626` | `0.0398` | `0.0648` | `0.0317` |

These positive-only results tell the real story.

Key takeaways:

- true positive-step exact match is near zero for both suspect and alert sets across all finished Qwen models
- the finished Qwen models remain highly conservative on positive suspect and alert recovery
- `Qwen3.5-27B` is best on suspect-family recovery overall, but not on positive-only alert exactness
- `Qwen3.5-4B` is slightly less conservative on positive alert steps, which explains why some alert metrics look marginally better even though it is not stronger overall
- `Qwen3.5-9B` is the most conservative of the three on positive suspect recovery

### Why Larger Models Do Not Separate Much on `alerts_exact_match`

The lack of separation on `alerts_exact_match` is not evidence that the models are equally strong.

Instead it reflects a structural property of the metric under this benchmark:

1. empty alert sets still make up `22.64%` of checkpoints
2. the Qwen models predict empty alert sets on `74.77%` to `80.26%` of checkpoints
3. many gold alert sets are multi-label rather than singleton
4. exact set match collapses all partial successes to zero

So the larger model does help in broader ways, but `alerts_exact_match` is too dominated by empty-set correctness and multi-label harshness to show that advantage clearly.

### Main interpretation of `benchmark_2k`

`Qwen3.5-27B` is the best fully completed model.

Why that conclusion is the safest:

- it has the best completed-run disease-state reconstruction on `suspected_conditions_macro_f1`
- it misses fewer alert trajectories than the smaller completed Qwen variants
- it keeps the best overall balance between core structured-state quality and patient-level temporal behavior
- it is based on the full intended `2,000`-stay benchmark rather than a partial sample

At the same time, the full table shows that the benchmark remains hard in a deeper sense:

- family-level core metrics remain much lower than the coarse summary metrics
- alert-family macro F1 remains clustered around `0.23` to `0.25`
- suspect-family macro F1 remains only `0.14` to `0.15` for the finished Qwen runs
- exact family-set recovery per checkpoint remains low even when coarse response-layer metrics look moderate
- strict patient-level exactness remains near zero even for the strongest completed runs

So even when a model is often directionally correct, it still rarely maintains a fully correct longitudinal surveillance state over the whole stay.

### What the provisional `gpt-oss-120b` result means

The partial `gpt-oss-120b` run is the most interesting incomplete result.

On the `1,026` completed stays, it is substantially stronger than the finished Qwen runs on several core and temporal metrics:

- `suspected_conditions_macro_f1`: `0.2054`
- `alerts_macro_f1`: `0.2533`
- first-alert timing error: `6.85h`
- missed alert trajectories: `209 / 967`
- and, secondarily, on the coarse summaries `global_action_accuracy` and `priority_accuracy`

However, two cautions matter:

- the run only covers about half of the intended benchmark
- its exact alert-match rate is not higher than the completed Qwen runs, and its strict longitudinal exactness is actually lower

This suggests a specific behavioral profile:

- `gpt-oss-120b` is much more willing to surface non-empty surveillance states and escalate earlier
- that improves sensitivity and core alert recovery
- but it does not yet translate into robust checkpoint-by-checkpoint full-state correctness

This is promising, but it is not yet a fully comparable final result.

### Qwen scaling is not monotonic on every metric

Within the completed Qwen family:

- `27B` is best on `suspected_conditions_macro_f1`
- `4B` and `9B` slightly edge `27B` on `alerts_macro_f1`
- `27B` still has the best overall balance because it misses fewer alert trajectories and is strongest on the richer suspect-family recovery task

This is an important nuance for the paper:

- model scale seems to help most on maintaining the richer surveillance picture
- it does not automatically solve the harder disease-family reconstruction problem

## Deep Dive: Finished Qwen Models by Temporal Semantics

The most useful additional analysis is to ask how the finished Qwen models behave across the benchmark’s five temporal-semantic state types:

- persistent episode
- cumulative max stage
- active interval
- recent measurement + TTL
- composite current state

This matters because the benchmark is hard precisely because these state types require different update rules over time.

### High-level pattern

All three finished Qwen models behave much more like **current local detectors** than robust longitudinal state trackers.

They are clearly strongest on:

- `active_interval`
- then `recent_measurement_ttl`

They are dramatically weaker on:

- `persistent_episode`
- `cumulative_max_stage`
- `composite_current_state`

That pattern is exactly what we would expect if the models struggle to remember or recompute clinically persistent state over long horizons.

### Prevalence-aware Qwen semantic slice on `benchmark_2k`

The table below uses a prevalence-aware view:

- `GT+ step rate`: fraction of checkpoints where that semantic state type is truly active
- `Any pred | GT+`: among positive checkpoints, how often the model predicts any state of that semantic type
- `Exact on GT+`: among positive checkpoints, how often it gets the semantic-type subset exactly right
- `Micro F1`: label-level F1 within that semantic-type subset across the full benchmark

#### `Qwen3.5-27B`

| Semantic type | GT+ step rate | Any pred \| GT+ | Exact on GT+ | Micro F1 |
|---|---:|---:|---:|---:|
| Persistent episode | `0.7686` | `0.0111` | `0.0036` | `0.0116` |
| Cumulative max stage | `0.5433` | `0.0120` | `0.0038` | `0.0074` |
| Active interval | `0.4161` | `0.3135` | `0.0820` | `0.1655` |
| Recent measurement + TTL | `0.4023` | `0.2173` | `0.0310` | `0.0833` |
| Composite current state | `0.0938` | `0.0008` | `0.0004` | `0.0008` |

#### `Qwen3.5-9B`

| Semantic type | GT+ step rate | Any pred \| GT+ | Exact on GT+ | Micro F1 |
|---|---:|---:|---:|---:|
| Persistent episode | `0.7686` | `0.0077` | `0.0004` | `0.0071` |
| Cumulative max stage | `0.5433` | `0.0012` | `0.0001` | `0.0001` |
| Active interval | `0.4161` | `0.2022` | `0.0825` | `0.1638` |
| Recent measurement + TTL | `0.4023` | `0.1583` | `0.0218` | `0.0592` |
| Composite current state | `0.0938` | `0.0074` | `0.0029` | `0.0065` |

#### `Qwen3.5-4B`

| Semantic type | GT+ step rate | Any pred \| GT+ | Exact on GT+ | Micro F1 |
|---|---:|---:|---:|---:|
| Persistent episode | `0.7686` | `0.0100` | `0.0027` | `0.0124` |
| Cumulative max stage | `0.5433` | `0.0133` | `0.0033` | `0.0067` |
| Active interval | `0.4161` | `0.1606` | `0.0666` | `0.1299` |
| Recent measurement + TTL | `0.4023` | `0.3366` | `0.0514` | `0.1187` |
| Composite current state | `0.0938` | `0.0406` | `0.0180` | `0.0364` |

### Semantic interpretation

#### 1. Persistent episode states are the biggest blind spot

These should be comparatively easy conceptually once the model has detected onset:

- infection suspicion
- stronger infection support
- sepsis alert

But all three Qwen models almost never keep them active when they should be active.

Most strikingly:

- the gold persistent-state subset is active on `76.86%` of checkpoints
- yet `Qwen3.5-27B` predicts any persistent state on only `1.11%` of those positive checkpoints
- `Qwen3.5-9B` is even more conservative at `0.77%`
- `Qwen3.5-4B` is similar at `1.00%`

Interpretation:

- the models are not reliably carrying forward episode-style state once it has begun
- they behave more like “re-check from scratch” agents than stateful surveillance trackers

#### 2. Cumulative max-stage semantics are also largely missed

For AKI staging, the benchmark asks for worst stage attained so far, not just the current instantaneous value.

Again the Qwen models mostly fail to preserve that cumulative memory:

- the cumulative-stage subset is positive on `54.33%` of checkpoints
- yet any positive prediction on positive checkpoints is only `1.20%` for `27B`, `0.12%` for `9B`, and `1.33%` for `4B`

Interpretation:

- the Qwen models are not behaving like cumulative-memory trackers for AKI
- this is strong evidence that cumulative temporal semantics are a real source of difficulty

#### 3. Active intervals are where Qwen does best

The Qwens are much better on states that are active only while support overlaps the checkpoint:

- ventilation support
- vasoactive support
- CRRT

Here `Qwen3.5-27B` is the strongest and best balanced:

- `31.35%` any-prediction rate on positive checkpoints
- `0.1655` micro F1

Interpretation:

- active support therapies may be easier because they are often anchored in clearer current-state signals
- this is the strongest evidence that the models can use local checkpoint evidence when the semantics are truly current-state

#### 4. Recent-measurement TTL states are partially recoverable, but noisy

These include:

- oliguria
- PF-ratio hypoxemia
- GCS impairment
- lactate
- acidemia
- INR coagulopathy

`Qwen3.5-4B` is surprisingly the most willing to emit these TTL-style states:

- `33.66%` any-prediction rate on positive checkpoints
- best TTL micro F1 among the finished Qwens at `0.1187`

But that comes with more spurious positives.

Interpretation:

- the smaller model is less conservative on short-horizon recent-measurement abnormalities
- the larger models are more conservative and therefore miss more TTL-positive checkpoints

#### 5. Composite current states are almost never reconstructed

This is the harshest semantic category:

- `septic_shock_alert`
- `shock_hypoperfusion_alert`

These require recomputing multiple component conditions jointly at each checkpoint.

All finished Qwen models are very weak here:

- `Qwen3.5-27B`: `0.08%` any-prediction rate on positive checkpoints
- `Qwen3.5-9B`: `0.74%`
- `Qwen3.5-4B`: `4.06%`

Interpretation:

- recomputed composite states are not being robustly assembled from component evidence
- this is exactly the kind of multi-rule temporal reasoning the benchmark was designed to stress

### Best concise takeaway on Qwen semantics

The cleanest summary sentence is:

- the finished Qwen models are strongest on locally observable current support states, weaker on recent TTL states, and weakest by far on persistent, cumulative, and composite semantics that require explicit longitudinal state maintenance or recomputation

## Autoformalization Pilot Results: `benchmark_100`

`benchmark_100` is useful for pilot comparison and sanity checking, but it should not replace the `benchmark_2k` story.

### Core and Temporal Metrics

| Model | Family | Completed stays | `suspected_conditions_macro_f1` | `alerts_macro_f1` | `alerts_macro_precision` | `alerts_macro_recall` | `suspected_conditions_exact_match` | `alerts_exact_match` | `first_alert_mean_abs_error_hours` | `false_early_alert_trajectories` | `missed_alert_trajectories` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `gpt-oss-120b` | open-weight | `100/100` | `0.2157` | `0.2469` | `0.2694` | `0.2393` | `0.1492` | `0.2031` | `5.15` | `10` | `14` |
| `Qwen3.5-27B` | open-weight | `100/100` | `0.1942` | `0.2425` | `0.2554` | `0.2387` | `0.1831` | `0.2300` | `12.68` | `0` | `53` |
| `Qwen3.5-4B` | open-weight | `100/100` | `0.1854` | `0.2643` | `0.2896` | `0.2571` | `0.1715` | `0.2408` | `11.26` | `1` | `56` |
| `Qwen3.5-9B` | open-weight | `100/100` recovered from `rollouts.json` | `0.1856` | `0.2549` | `0.2777` | `0.2483` | `0.1815` | `0.2338` | `18.81` | `1` | `67` |
| `gemma-4-31B-it` | open-weight | `100/100` | `0.1821` | `0.2434` | `0.2442` | `0.2430` | `0.1762` | `0.2415` | `16.00` | `0` | `81` |
| `Gemini/gemini-3.1-pro-preview` | closed-source | `24/100` recovered | `0.2671` | `0.1959` | `0.1987` | `0.1944` | `0.2564` | `0.1891` | `5.00` | `0` | `19` |
| `Claude/claude-sonnet-4-6` | closed-source | `28/100` recovered | `0.2225` | `0.1758` | `0.1758` | `0.1758` | `0.2170` | `0.1758` | `0.00` on only `3` matched alert cases | `0` | `24` |

### Auxiliary Coarse Summary Metrics

| Model | Family | Completed stays | `global_action_accuracy` | `priority_accuracy` |
|---|---|---:|---:|---:|
| `gpt-oss-120b` | open-weight | `100/100` | `0.6454` | `0.4792` |
| `Qwen3.5-27B` | open-weight | `100/100` | `0.3869` | `0.3777` |
| `Qwen3.5-4B` | open-weight | `100/100` | `0.3646` | `0.3454` |
| `Qwen3.5-9B` | open-weight | `100/100` recovered from `rollouts.json` | `0.3531` | `0.3231` |
| `gemma-4-31B-it` | open-weight | `100/100` | `0.3069` | `0.2838` |
| `Gemini/gemini-3.1-pro-preview` | closed-source | `24/100` recovered | `0.2564` | `0.2564` |
| `Claude/claude-sonnet-4-6` | closed-source | `28/100` recovered | `0.2060` | `0.2088` |

### How to read the `benchmark_100` results

Three points matter most.

First, `gpt-oss-120b` is again the strongest action-level model in the small pilot, which is consistent with its partial `benchmark_2k` behavior.

Second, the small pilot does not give a clean open-source versus closed-source verdict.

Why not:

- the closed-source runs are very incomplete
- both closed-source runs were interrupted manually before completion
- both showed heavy tool-runtime failure rates

Third, even on this smaller benchmark, full stay-level exactness is still poor.

The strongest action-level model in the pilot, `gpt-oss-120b`, has:

- `0.6454` global-action accuracy
- but `0.0000` strict all-4 trajectory rate

So the same gap appears again:

- top-level surveillance action prediction is easier than maintaining the exact full longitudinal surveillance state

## Zero-Shot Raw-Table Results: `benchmark_100`

The zero-shot raw-table setting uses `tool_backend = zeroshot_python`, meaning the model reasons directly over checkpoint-scoped raw MIMIC-IV evidence through Python and `query_db`.

This is a materially different interface from the autoformalized `session_tools` setting, so these results should be interpreted as a comparison across backends rather than a pure prompt ablation.

### Core and Temporal Metrics

| Model | Family | Completed stays | `suspected_conditions_macro_f1` | `alerts_macro_f1` | `alerts_macro_precision` | `alerts_macro_recall` | `suspected_conditions_exact_match` | `alerts_exact_match` | `first_alert_mean_abs_error_hours` | `false_early_alert_trajectories` | `missed_alert_trajectories` | `strict_all4_trajectory_rate` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Gemini/gemini-3.1-pro-preview` | closed-source | `100/100` | `0.4393` | `0.4636` | `0.4788` | `0.4862` | `0.2531` | `0.2423` | `4.6047` | `19` | `8` | `0.0100` |
| `Claude/claude-sonnet-4-6` | closed-source | `100/100` | `0.3830` | `0.4722` | `0.4657` | `0.5201` | `0.1808` | `0.2338` | `3.9535` | `31` | `8` | `0.0000` |
| `GPT/gpt-5.4` | closed-source | `100/100` | `0.2561` | `0.3212` | `0.3789` | `0.3022` | `0.1862` | `0.2192` | `7.1045` | `17` | `27` | `0.0100` |
| `gpt-oss-120b` | open-weight | `100/100` | `0.2564` | `0.2167` | `0.2445` | `0.2084` | `0.1715` | `0.1831` | `11.3333` | `23` | `4` | `0.0000` |
| `Qwen3.5-27B` | open-weight | `100/100` | `0.2063` | `0.2195` | `0.2304` | `0.2175` | `0.1800` | `0.2062` | `12.0606` | `13` | `28` | `0.0100` |
| `gemma-4-31B-it` | open-weight | `100/100` | `0.1982` | `0.2632` | `0.3026` | `0.2497` | `0.1646` | `0.2046` | `9.2778` | `12` | `22` | `0.0100` |
| `Qwen3.5-9B` | open-weight | `100/100` | `0.1847` | `0.2408` | `0.2408` | `0.2408` | `0.1831` | `0.2408` | `20.0000` | `0` | `83` | `0.0200` |
| `Qwen3.5-4B` | open-weight | `100/100` | `0.1830` | `0.2401` | `0.2408` | `0.2401` | `0.1815` | `0.2385` | `11.5200` | `2` | `69` | `0.0200` |

### Auxiliary Coarse Summary Metrics

| Model | Family | Completed stays | `global_action_accuracy` | `priority_accuracy` |
|---|---|---:|---:|---:|
| `Claude/claude-sonnet-4-6` | closed-source | `100/100` | `0.7623` | `0.5677` |
| `Gemini/gemini-3.1-pro-preview` | closed-source | `100/100` | `0.7254` | `0.5938` |
| `GPT/gpt-5.4` | closed-source | `100/100` | `0.6654` | `0.5169` |
| `gemma-4-31B-it` | open-weight | `100/100` | `0.5538` | `0.3792` |
| `gpt-oss-120b` | open-weight | `100/100` | `0.5315` | `0.4169` |
| `Qwen3.5-27B` | open-weight | `100/100` | `0.3177` | `0.3108` |
| `Qwen3.5-4B` | open-weight | `100/100` | `0.2700` | `0.2469` |
| `Qwen3.5-9B` | open-weight | `100/100` | `0.2492` | `0.2408` |

### Zero-Shot Interpretation

The short raw-table setting supports a clean open-weight versus closed-source comparison because all eight `benchmark_100` runs are complete.

The dominant pattern is clear:

- the closed-source models are dramatically stronger than the open-weight models on raw-table `benchmark_100`
- closed-source average `suspected_conditions_macro_f1` is `0.3595` versus `0.2057` for open-weight
- closed-source average `alerts_macro_f1` is `0.4190` versus `0.2361`
- closed-source average first-alert absolute error is `5.22h` versus `12.84h`
- closed-source average missed-alert count is `14.3` versus `41.2`

Within the closed-source group:

- `Gemini 3.1 Pro Preview` is best on suspect-family state recovery and exact suspect-set matching
- `Claude Sonnet 4.6` is best on alert-family macro F1 and first-alert timing, but it is also the most aggressive, with `31` false-early trajectories
- `GPT-5.4` is clearly weaker than Claude and Gemini on the core structured-state metrics, but still stronger than the open-weight zero-shot runs

Within the open-weight group:

- `gpt-oss-120b` is the strongest suspect-family zero-shot model and misses only `4` alerting trajectories, but it pays for that sensitivity with many false-early trajectories and relatively weak alert-family F1
- `gemma-4-31B-it` is the strongest open-weight zero-shot model on alert-family F1, but still remains far behind the closed-source leaders
- the Qwen zero-shot runs are especially unstable: `Qwen3.5-9B` and `Qwen3.5-4B` collapse toward near-always-`continue_monitoring` behavior

### Why Zero-Shot `benchmark_100` Is Not Enough

The zero-shot raw-table setting currently does **not** provide a completed `benchmark_2k` comparison.

The only saved long-run zero-shot artifact is a partial `Qwen3.5-4B` run on `394/2000` stays. That run is a warning sign rather than reassuring evidence:

- `global_action_accuracy = 0.2411`
- `priority_accuracy = 0.2130`
- `alerts_macro_f1 = 0.2278`
- but positive-only `alerts_macro_f1 = 0.0013`
- and the model predicts `continue_monitoring` on `98.15%` of steps

So the raw-table setting can look much better on short pilot runs than it does under sustained long-horizon evaluation. This is why the paper’s primary benchmark claims should still be anchored in the completed autoformalized `benchmark_2k` results.

## Zero-Shot Versus Autoformalization

The fairest paired comparison is on `benchmark_100`, where the Qwen family completed both backends cleanly.

### Qwen `benchmark_100`: Overall and Positive-Only Comparison

| Model | Mode | `suspected_conditions_macro_f1` | `alerts_macro_f1` | positive-only `suspected_conditions_macro_f1` | positive-only `alerts_macro_f1` | `global_action_accuracy` | `priority_accuracy` | `first_alert_mean_abs_error_hours` | `missed_alert_trajectories` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | autoformalization | `0.1942` | `0.2425` | `0.0165` | `0.0165` | `0.3869` | `0.3777` | `12.6829` | `53` |
| `Qwen3.5-27B` | zero-shot | `0.2063` | `0.2195` | `0.0510` | `0.0176` | `0.3177` | `0.3108` | `12.0606` | `28` |
| `Qwen3.5-9B` | autoformalization | `0.1856` | `0.2549` | `0.0050` | `0.0278` | `0.3531` | `0.3231` | `18.8148` | `67` |
| `Qwen3.5-9B` | zero-shot | `0.1847` | `0.2408` | `0.0019` | `0.0010` | `0.2492` | `0.2408` | `20.0000` | `83` |
| `Qwen3.5-4B` | autoformalization | `0.1854` | `0.2643` | `0.0236` | `0.0534` | `0.3646` | `0.3454` | `11.2632` | `56` |
| `Qwen3.5-4B` | zero-shot | `0.1830` | `0.2401` | `0.0037` | `0.0021` | `0.2700` | `0.2469` | `11.5200` | `69` |

### What Autoformalization Changes

For the Qwen family as a whole on `benchmark_100`, autoformalization changes behavior in a structured way rather than simply shifting all metrics up or down.

What it improves on average:

- `global_action_accuracy`: `0.3682` versus `0.2790`
- `priority_accuracy`: `0.3487` versus `0.2662`
- `alerts_macro_f1`: `0.2539` versus `0.2335`
- positive-only `alerts_macro_f1`: `0.0326` versus `0.0069`

What it does **not** uniformly improve:

- average suspect-family macro F1 is essentially flat to slightly lower
- average suspect positive-only F1 is slightly lower: `0.0150` versus `0.0189`
- `Qwen3.5-27B` becomes much more conservative on stay-level alerting, missing `53` trajectories in autoformalization versus `28` in zero-shot

The best interpretation is that autoformalization regularizes smaller Qwen models and helps them recover explicit acute support / alert structure, but can also push the larger Qwen model into a more cautious output regime that under-calls alerts.

### Temporal-Semantic Comparison for Qwen

The semantic split makes that backend tradeoff clearer.

Across the Qwen family on `benchmark_100`:

- autoformalization strongly improves `active_interval` semantics on average: micro F1 `0.1685` versus `0.0125`
- autoformalization also modestly improves `recent_measurement_ttl`: `0.0533` versus `0.0424`
- zero-shot is better on average for `persistent_episode`: `0.0169` versus `0.0041`
- zero-shot is better on average for `cumulative_max_stage`: `0.0242` versus `0.0063`
- zero-shot is better on `composite_current_state`: `0.0164` versus `0.0000`

This suggests that the autoformalized function layer is particularly helpful for:

- active support intervals
- recent-measurement states with explicit TTL-like reasoning

But direct raw-table reasoning still allows `Qwen3.5-27B` to recover some persistent, cumulative, and composite structure that the formalized interface currently suppresses.

## Open-Weight Versus Closed-Source Interpretation

The user requested explicit attention to the difference between open-source/open-weight models and closed-source models. The safest reading now depends on backend.

### What we can say confidently

- In zero-shot raw-table `benchmark_100`, the closed-source models are clearly stronger than the open-weight models.
- In autoformalized `benchmark_2k`, the best completed full-benchmark results currently come from open-weight models, because only open-weight models finished the full evaluation.
- The strongest provisional long-run autoformalized result in the artifact set is still `gpt-oss-120b`, an open-weight model, though that run is incomplete.
- The autoformalized closed-source runs do not currently support a fair leaderboard comparison because they were interrupted early and were strongly affected by tool failures.

### What we should not say yet

- We should not claim that open-weight models are inherently better than closed-source models on this benchmark overall.
- We should not claim that the zero-shot closed-source ordering will automatically carry over to the full `benchmark_2k` setting, because no completed closed-source long-run artifact exists.
- We should not claim that Claude or Gemini fail the autoformalized benchmark in a definitive sense, because the saved `session_tools` runs are too partial and too tool-error-heavy.
- We should not build a single backend-mixed leaderboard that treats zero-shot `benchmark_100` and autoformalized `benchmark_2k` as the same experimental condition.

### Best paper-ready phrasing

A defensible summary sentence is:

- in the current artifact set, closed-source models dominate the short zero-shot raw-table pilot, while open-weight models provide the only reliable completed evidence on the full autoformalized `benchmark_2k` benchmark

## Behavior Patterns That Matter

### 1. Global action is easier than full disease-state tracking

This is the clearest recurring result.

Examples on `benchmark_2k`:

- `Qwen3.5-27B`: `0.4577` global action versus `0.1472` suspected-condition macro F1
- `Qwen3.5-4B`: `0.4153` global action versus `0.1396` suspected-condition macro F1
- `Qwen3.5-9B`: `0.4083` global action versus `0.1366` suspected-condition macro F1

Interpretation:

- models often identify that the patient requires monitoring or escalation
- but they do not reliably reconstruct the correct active family state behind that decision

This is clinically meaningful and fits the intended benchmark story.

### 2. Most models are too conservative about emitting alerts

The ground-truth benchmark is not sparse at the stay level. Many trajectories contain at least one alert family.

Yet several models predict far fewer alert states than the benchmark contains.

Examples on `benchmark_2k`:

- ground truth alert density is about `1.57` alerts per checkpoint
- `Qwen3.5-27B` predicts `0.274` alerts per checkpoint
- `Qwen3.5-4B` predicts `0.251`
- `Qwen3.5-9B` predicts `0.213`
- `gemma-4-31B-it` predicts only `0.049`

This under-calling behavior explains the large missed-alert counts:

- `Qwen3.5-27B`: `909` missed alert trajectories
- `Qwen3.5-4B`: `982`
- `Qwen3.5-9B`: `998`
- `gemma-4-31B-it`: `1455` on its partial run

The same pattern appears even more starkly in zero-shot for the smaller Qwen models:

- on raw-table `benchmark_100`, `Qwen3.5-9B` predicts `continue_monitoring` on `98.92%` of steps
- `Qwen3.5-4B` predicts it on `96.54%`
- the partial zero-shot `benchmark_2k` `Qwen3.5-4B` run predicts it on `98.15%`

So raw-table zero-shot can collapse into an almost-always-negative policy unless the model is either very strong or given a more structured interface.

### 3. `gpt-oss-120b` trades conservatism for higher sensitivity

`gpt-oss-120b` behaves differently.

On the partial `benchmark_2k` run:

- it predicts `0.598` alerts per checkpoint, much closer to the true alert burden than the Qwen or gemma runs
- it misses far fewer alert trajectories: `209 / 967`
- it also reaches the best provisional first-alert timing error

But that more sensitive behavior does not fully solve exact longitudinal correctness:

- alert exact-match stays at `0.2123`
- strict all-4 stay-level accuracy is still only `0.0049`

So the model appears more willing to raise surveillance state, but not yet consistently correct in the full structured label space.

### 4. Longitudinal exactness is the real bottleneck

All models struggle badly when we ask for exact full-trajectory correctness.

On `benchmark_2k`, strict all-4 trajectory accuracy is:

- `1.10%` for `Qwen3.5-27B`
- `0.90%` for `Qwen3.5-4B`
- `1.15%` for `Qwen3.5-9B`
- `0.49%` for partial `gpt-oss-120b`
- `1.17%` for partial `gemma-4-31B-it`

### 5. Backend choice changes *which* temporal semantics survive

This is one of the most important new findings from the combined artifact set.

For the Qwen family on `benchmark_100`:

- autoformalization strongly helps `active_interval` and, to a lesser extent, `recent_measurement_ttl`
- zero-shot helps `Qwen3.5-27B` preserve some `persistent_episode`, `cumulative_max_stage`, and `composite_current_state` structure

This suggests that the formalized tool layer is not merely making the task easier or harder globally. It is reshaping the temporal reasoning burden:

- explicit support-state lookup and TTL-like checks become easier
- persistent and cumulative cross-checkpoint carry-forward can become more brittle if the model relies too heavily on local tool retrieval and not enough on internal state maintenance

This is the strongest evidence that the benchmark is testing more than isolated local decisions.

The models are not simply making a few scattered errors.
They are failing to sustain a clinically coherent evolving surveillance state through the full checkpoint sequence.

## Tool and Runtime Failure Analysis

Tool reliability clearly affected several runs.

The most repeated failures were concentrated in a small set of functions:

- `get_blood_gas_info`
- `get_vasoactive_agent_info`
- `kdigo_stages`
- `get_gcs`
- `get_kdigo_stages`

The closed-source pilots were especially exposed to these issues:

- `Claude` logged `686` tool errors in `28` recovered trajectories, dominated by `get_blood_gas_info`
- `Gemini` logged `473` tool errors in `24` recovered trajectories, again dominated by `get_blood_gas_info`

Some open-weight runs were also affected:

- `Qwen3.5-27B` `benchmark_100` showed thousands of repeated `NameError` events around blood-gas and vasoactive retrieval
- `Qwen3.5-4B` and `Qwen3.5-9B` `benchmark_2k` showed many `UnknownFunction` failures around GCS and KDIGO helper names

This matters for interpretation:

- part of the benchmark difficulty is true clinical-temporal reasoning difficulty
- but part of the observed failure surface is still tool discoverability and tool reliability

That is not necessarily a flaw in the benchmark story.
In fact, because the design intentionally requires search and function discovery rather than a perfect pre-wrapped toolbox, these failures are part of the real agent-evaluation burden.

Still, for paper reporting, it is worth separating:

- conceptual longitudinal reasoning failures
- infrastructure or callable-library failures

## What the Results Support as Main Claims

The current results support the following claims strongly.

### Claim 1

The benchmark is hard because it requires mixed-temporal current-state tracking rather than simple next-step prediction or static classification.

Support:

- low strict trajectory exactness across all models
- moderate action accuracy but weak family-state reconstruction
- large missed-alert counts for most models

### Claim 2

Backend choice changes model behavior in systematic and semantically meaningful ways.

Support:

- for the Qwen family, autoformalization strongly improves active-interval and alert-family recovery, especially for the smaller models
- zero-shot preserves more persistent / cumulative reasoning in `Qwen3.5-27B`, but smaller zero-shot Qwens collapse toward near-always-negative behavior
- the raw-table and autoformalized interfaces are therefore not interchangeable abstractions of the same task

### Claim 3

Different models fail in systematically different ways.

Support:

- Qwen family: more conservative, better calibrated top-level control, but many missed alerts
- `gpt-oss-120b`: much higher sensitivity and stronger action-level performance, but weaker exact structured-state calibration
- zero-shot closed-source models: much stronger short-horizon structured-state recovery than zero-shot open-weight models
- autoformalized closed-source pilots: severe runtime fragility in the current saved artifacts

### Claim 4

Short zero-shot success should not be confused with full-benchmark reliability.

Support:

- all eight zero-shot `benchmark_100` runs complete cleanly, but there is no completed zero-shot `benchmark_2k` comparison
- the only saved long-run zero-shot artifact, `Qwen3.5-4B`, shows extreme conservative collapse despite superficially moderate overall alert metrics
- the full `benchmark_2k` story therefore still has to be told primarily through the completed autoformalized runs

## What Should Be Headline Results in the Paper

Recommended primary headline table:

- the completed `benchmark_2k` runs for `Qwen3.5-27B`, `Qwen3.5-9B`, and `Qwen3.5-4B`

Recommended second main-text table:

- the zero-shot raw-table `benchmark_100` comparison across all completed open-weight and closed-source models

Recommended secondary or appendix table:

- provisional partial `benchmark_2k` runs for `gpt-oss-120b` and `gemma-4-31B-it`

Recommended appendix or pilot note only:

- the interrupted autoformalized `benchmark_100` closed-source pilots for `Claude` and `Gemini`
- the partial zero-shot `benchmark_2k` `Qwen3.5-4B` run

Recommended headline sentence:

- the best fully completed model on the primary `2,000`-stay rolling surveillance benchmark is `Qwen3.5-27B`, but even this model remains far from reliable full-trajectory surveillance-state tracking

Recommended secondary sentence:

- on the short raw-table `benchmark_100` pilot, closed-source models substantially outperform open-weight models, but that advantage has not yet been validated on the full `benchmark_2k` benchmark

Recommended third sentence:

- paired Qwen comparisons show that autoformalization changes the task in a structured way: it helps acute support-state and alert-family recovery, but can suppress some persistent and cumulative state tracking

## Recommended Next Steps

If you want the strongest final paper package from these artifacts, the highest-value next steps are:

1. rerun at least one closed-source model on the full autoformalized `benchmark_2k`, because this is the biggest remaining gap in the evidence
2. rerun `gpt-oss-120b` `benchmark_2k` to completion, because it is the most likely challenger to `Qwen3.5-27B`
3. run at least one additional zero-shot `benchmark_2k` model to clean completion, so the raw-table setting can be judged on the primary benchmark rather than only on `benchmark_100`
4. fix the repeated callable failures around blood-gas, KDIGO, vasoactive, and GCS helpers, then rerun at least one representative autoformalized closed-source model to quantify how much of the failure is infrastructure versus reasoning
5. include strict stay-level and positive-only structured-state metrics in the analysis appendix, because they communicate the benchmark difficulty much better than step-only overall exact-match scores

## Final Takeaway

The final artifact set already supports a strong and publishable story.

That story is not merely that some models do better than others.

The stronger story is this:

- rolling ICU surveillance with mixed temporal semantics is genuinely hard
- the full `benchmark_2k` autoformalized results show that even the best completed models remain far from reliable patient-level longitudinal state tracking
- short raw-table zero-shot pilots can make strong closed-source models look very good, but that success does not yet replace the need for long-run benchmark evidence
- zero-shot and autoformalization expose different temporal reasoning strengths and weaknesses, which is itself an important scientific finding about how tool interface design shapes longitudinal clinical-state tracking
- current models can often choose a plausible monitoring or escalation action
- but they still struggle to maintain the correct structured clinical state over time
- open-weight models currently provide the strongest completed evidence in this artifact set
- and the most promising incomplete run, `gpt-oss-120b`, suggests there is still room to improve sensitivity without solving the deeper longitudinal consistency problem
