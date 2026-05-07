# Rolling Surveillance Evaluation Final Report

Date: 2026-05-06

## Scope

This report synthesizes the final rolling-surveillance evaluation artifacts under:

- `result/rolling_eval_autoform/`

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

- The benchmark remains difficult even for the strongest available runs. On the primary `benchmark_2k` setting, no fully completed model exceeded `45.77%` global-action accuracy or `43.32%` priority accuracy, and exact stay-level longitudinal correctness remained near zero.
- Among the fully completed `2,000`-stay open-weight runs, `Qwen3.5-27B` is the strongest overall model. It is best on `global_action_accuracy`, `priority_accuracy`, and `suspected_conditions_macro_f1`, while also missing fewer alert trajectories than the smaller Qwen variants.
- `gpt-oss-120b` is the most promising partially completed open-weight run. On the first `1,026` completed trajectories of `benchmark_2k`, it substantially outperforms the finished Qwen runs on global-action and priority accuracy, and it misses far fewer alert trajectories. However, it is still incomplete and should be reported as provisional rather than as the primary headline.
- The closed-source pilots are not yet publication-grade comparisons. `Claude Sonnet 4.6` and `Gemini 3.1 Pro Preview` only completed `28/100` and `24/100` trajectories respectively before interruption, and both were heavily affected by repeated tool-runtime failures.
- Across nearly all models, the same pattern appears: models are better at deciding that some monitoring or escalation action is needed than they are at reconstructing the correct full disease-family state over time. This is exactly the difficulty predicted by the benchmark design.

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

## Evaluation Status Audit

Not all runs finished cleanly. This matters for fair reporting.

| Model | Family | `benchmark_100` | `benchmark_2k` | Status note |
|---|---|---:|---:|---|
| `Qwen3.5-27B` | open-weight | `100/100` | `2000/2000` | fully completed |
| `Qwen3.5-9B` | open-weight | `65/100` recovered | `2000/2000` | `benchmark_100` artifact incomplete, `benchmark_2k` completed |
| `Qwen3.5-4B` | open-weight | `100/100` | `2000/2000` | fully completed |
| `gemma-4-31B-it` | open-weight | `100/100` | `1714/2000` recovered | `benchmark_2k` incomplete |
| `gpt-oss-120b` | open-weight | `100/100` | `1026/2000` recovered | `benchmark_2k` interrupted by backend error |
| `Claude/claude-sonnet-4-6` | closed-source | `28/100` recovered | not run | interrupted |
| `Gemini/gemini-3.1-pro-preview` | closed-source | `24/100` recovered | not run | interrupted |

Important implication:

- the only clean, apples-to-apples primary comparison on the full `2,000`-stay benchmark is among the completed Qwen runs
- `gpt-oss-120b` and `gemma-4-31B-it` are informative but provisional on `benchmark_2k`
- the closed-source results are pilot evidence only and should not be presented as definitive leaderboard entries

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

This is not the official benchmark metric, but it is a useful indicator of true longitudinal consistency.

## Primary Results: `benchmark_2k`

`benchmark_2k` is the main benchmark and should be the primary table in the paper.

| Model | Completed stays | Global action | Priority | Suspected cond. macro F1 | Alerts macro F1 | Alerts exact match | First-alert MAE (h) | Missed alert trajectories | Strict all-4 trajectory rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | `2000/2000` | `0.4577` | `0.4332` | `0.1472` | `0.2423` | `0.2195` | `10.6119` | `909 / 1883` | `0.0110` |
| `Qwen3.5-4B` | `2000/2000` | `0.4153` | `0.3993` | `0.1396` | `0.2453` | `0.2232` | `9.5982` | `982 / 1883` | `0.0090` |
| `Qwen3.5-9B` | `2000/2000` | `0.4083` | `0.3726` | `0.1366` | `0.2456` | `0.2213` | `12.1627` | `998 / 1883` | `0.0115` |
| `gpt-oss-120b` | `1026/2000` | `0.6317` | `0.5206` | `0.2054` | `0.2533` | `0.2123` | `6.8496` | `209 / 967` | `0.0049` |
| `gemma-4-31B-it` | `1714/2000` | `0.2674` | `0.2409` | `0.1344` | `0.2277` | `0.2253` | `22.9554` | `1455 / 1612` | `0.0117` |

### Main interpretation of `benchmark_2k`

`Qwen3.5-27B` is the best fully completed model.

Why that conclusion is the safest:

- it has the best top-level action control: `0.4577` global action, `0.4332` priority
- it has the best completed-run disease-state reconstruction on `suspected_conditions_macro_f1`
- it misses fewer alert trajectories than the smaller completed Qwen variants
- it is based on the full intended `2,000`-stay benchmark rather than a partial sample

At the same time, the full table shows that the benchmark remains hard in a deeper sense:

- all models remain clustered around `0.22` to `0.25` on alert-family macro F1
- exact alert-family match per checkpoint stays around `0.21` to `0.23`
- strict all-output stay-level success is only `0.49%` to `1.17%`

So even when a model is often directionally correct, it still rarely maintains a fully correct longitudinal surveillance state over the whole stay.

### What the provisional `gpt-oss-120b` result means

The partial `gpt-oss-120b` run is the most interesting incomplete result.

On the `1,026` completed stays, it is substantially stronger than the finished Qwen runs on:

- `global_action_accuracy`: `0.6317`
- `priority_accuracy`: `0.5206`
- `suspected_conditions_macro_f1`: `0.2054`
- first-alert timing error: `6.85h`
- missed alert trajectories: `209 / 967`

However, two cautions matter:

- the run only covers about half of the intended benchmark
- its exact alert-match rate is not higher than the completed Qwen runs, and its strict longitudinal exactness is actually lower

This suggests a specific behavioral profile:

- `gpt-oss-120b` is much more willing to surface non-empty surveillance states and escalate earlier
- that improves sensitivity and top-level action performance
- but it does not yet translate into robust checkpoint-by-checkpoint full-state correctness

This is promising, but it is not yet a fully comparable final result.

### Qwen scaling is not monotonic on every metric

Within the completed Qwen family:

- `27B` is clearly best on top-level decision quality
- `4B` and `9B` slightly edge `27B` on alert macro F1
- `27B` still has better overall balance because it misses fewer alert trajectories and is stronger on the higher-level decisions that control surveillance behavior

This is an important nuance for the paper:

- model scale seems to help most on maintaining the correct monitoring/escalation policy
- it does not automatically solve the harder disease-family reconstruction problem

## Auxiliary Results: `benchmark_100`

`benchmark_100` is useful for pilot comparison and sanity checking, but it should not replace the `benchmark_2k` story.

| Model | Family | Completed stays | Global action | Priority | Suspected cond. macro F1 | Alerts macro F1 | Alerts exact match | First-alert MAE (h) | Strict all-4 trajectory rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `gpt-oss-120b` | open-weight | `100/100` | `0.6454` | `0.4792` | `0.2157` | `0.2469` | `0.2031` | `5.15` | `0.0000` |
| `Qwen3.5-27B` | open-weight | `100/100` | `0.3869` | `0.3777` | `0.1942` | `0.2425` | `0.2300` | `12.68` | `0.0200` |
| `Qwen3.5-4B` | open-weight | `100/100` | `0.3646` | `0.3454` | `0.1854` | `0.2643` | `0.2408` | `11.26` | `0.0200` |
| `Qwen3.5-9B` | open-weight | `65/100` recovered | `0.3302` | `0.3136` | `0.2039` | `0.2382` | `0.2107` | `19.11` | `0.0308` |
| `gemma-4-31B-it` | open-weight | `100/100` | `0.3069` | `0.2838` | `0.1821` | `0.2434` | `0.2415` | `16.00` | `0.0200` |
| `Gemini/gemini-3.1-pro-preview` | closed-source | `24/100` recovered | `0.2564` | `0.2564` | `0.2671` | `0.1959` | `0.1891` | `5.00` | `0.0417` |
| `Claude/claude-sonnet-4-6` | closed-source | `28/100` recovered | `0.2060` | `0.2088` | `0.2225` | `0.1758` | `0.1758` | `0.00` on only `3` matched alert cases | `0.0357` |

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

## Open-Weight Versus Closed-Source Interpretation

The user requested explicit attention to the difference between open-source/open-weight models and closed-source models. The safest reading is:

### What we can say confidently

- The best completed full-benchmark results currently come from open-weight models, because only open-weight models finished the entire `benchmark_2k` evaluation.
- The strongest provisional result in the entire folder also comes from an open-weight model, `gpt-oss-120b`, though that run is incomplete.
- The closed-source pilots in this artifact set do not currently support a fair leaderboard comparison because they were interrupted early and were strongly affected by tool failures.

### What we should not say yet

- We should not claim that open-weight models are inherently better than closed-source models on this benchmark.
- We should not claim that Claude or Gemini fail the benchmark in a definitive sense, because the saved runs are too partial and too tool-error-heavy.
- We should not build a main paper figure that directly ranks closed-source and open-weight models together unless the closed-source runs are rerun cleanly to completion.

### Best paper-ready phrasing

A defensible summary sentence is:

- in the current artifact set, the most reliable completed evidence comes from open-weight models, while the closed-source pilots remain incomplete and should be treated as preliminary

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

Open-weight models can achieve moderate checkpoint-level surveillance control, but full longitudinal state tracking remains unsolved.

Support:

- completed Qwen runs reach about `0.41` to `0.46` global-action accuracy on the full benchmark
- but exact longitudinal correctness remains around `1%`

### Claim 3

Different models fail in systematically different ways.

Support:

- Qwen family: more conservative, better calibrated top-level control, but many missed alerts
- `gpt-oss-120b`: much higher sensitivity and stronger action-level performance, but weaker exact structured-state calibration
- closed-source pilots: severe conservatism plus heavy tool-runtime fragility in the current saved runs

## What Should Be Headline Results in the Paper

Recommended primary headline table:

- the completed `benchmark_2k` runs for `Qwen3.5-27B`, `Qwen3.5-9B`, and `Qwen3.5-4B`

Recommended secondary or appendix table:

- provisional partial `benchmark_2k` runs for `gpt-oss-120b` and `gemma-4-31B-it`

Recommended appendix or pilot note only:

- `benchmark_100` closed-source runs for `Claude` and `Gemini`

Recommended headline sentence:

- the best fully completed model on the primary `2,000`-stay rolling surveillance benchmark is `Qwen3.5-27B`, but even this model remains far from reliable full-trajectory surveillance-state tracking

Recommended secondary sentence:

- a partial `gpt-oss-120b` run suggests that stronger action-level surveillance performance may be possible, but the current saved artifact is incomplete and should be treated as provisional

## Recommended Next Steps

If you want the strongest final paper package from these artifacts, the highest-value next steps are:

1. rerun the closed-source pilots to clean completion before making any open versus closed-source claim
2. rerun `gpt-oss-120b` `benchmark_2k` to completion, because it is the most likely challenger to `Qwen3.5-27B`
3. fix the repeated callable failures around blood-gas, KDIGO, vasoactive, and GCS helpers, then rerun at least one representative model to quantify how much of the failure is infrastructure versus reasoning
4. include a strict stay-level longitudinal metric in the analysis appendix, because it communicates the benchmark difficulty much better than step-only metrics

## Final Takeaway

The final artifact set already supports a strong and publishable story.

That story is not merely:

- some models do better than others

The stronger story is:

- rolling ICU surveillance with mixed temporal semantics is genuinely hard
- current models can often choose a plausible monitoring or escalation action
- but they still struggle to maintain the correct structured clinical state over time
- open-weight models currently provide the strongest completed evidence in this artifact set
- and the most promising incomplete run, `gpt-oss-120b`, suggests there is still room to improve sensitivity without solving the deeper longitudinal consistency problem
