# Paper-Style Results Section for Rolling Surveillance Benchmark

Date: 2026-05-07

## Intended Use

This document is a tighter, paper-style rewrite of the combined rolling surveillance results across:

- autoformalization: `result/rolling_eval_autoform/`
- zero-shot raw-table access: `result/rolling_eval_zeroshot/`

It keeps the metric hierarchy used in the detailed report:

- primary: structured-state recovery and patient-level temporal quality
- auxiliary: coarse response-layer summaries (`global_action_accuracy`, `priority_accuracy`)

Reference artifact:

- [rolling_eval_autoform_final_report_2026-05-06.md](/Users/chloe/Documents/New%20project/docs/surveilance/rolling_eval_autoform_final_report_2026-05-06.md)

## Suggested Results Section

### Main Text Draft

We evaluate rolling ICU surveillance under two interfaces. In the autoformalized `session_tools` setting, the agent interacts with a structured function and guideline layer; in the `zeroshot_python` setting, the agent reasons directly over checkpoint-scoped raw MIMIC-IV tables through Python and `query_db`. Because the benchmark target is a structured surveillance state, we treat disease-family recovery metrics as primary: `suspected_conditions_macro_f1`, `alerts_macro_f1`, `alerts_macro_precision`, `alerts_macro_recall`, and exact set match on `suspected_conditions` and `alerts`. We additionally report patient-level temporal quality through first-alert timing error, false-early alert counts, missed-alert trajectories, and a strict longitudinal exact-match rate over the full stay.

On the primary autoformalized `benchmark_2k` benchmark (`2,000` stays, `26,000` checkpoints), the strongest fully completed model is `Qwen3.5-27B`. It achieves the best completed-run `suspected_conditions_macro_f1` (`0.1472`) and misses fewer alerting trajectories (`909`) than the smaller completed Qwen variants. However, all completed models remain weak on the benchmark’s core structured-state outputs: `alerts_macro_f1` remains only `0.2423` to `0.2456`, exact set recovery remains low, and strict patient-level exactness is approximately `1%`. A partial `gpt-oss-120b` run is the strongest provisional long-run result, but because it completed only `1,026/2,000` trajectories, it should be treated as suggestive rather than definitive.

The zero-shot raw-table setting produces a different ranking on the short `benchmark_100` pilot. Here the closed-source models are clearly strongest: `Gemini 3.1 Pro Preview` leads suspect-family recovery (`0.4393` macro F1), while `Claude Sonnet 4.6` leads alert-family recovery (`0.4722` macro F1) and first-alert timing (`3.95h` mean absolute error). `GPT-5.4` is intermediate but still substantially stronger than the open-weight zero-shot models. However, there is no completed zero-shot `benchmark_2k` comparison, and the only saved long-run zero-shot artifact, a partial `Qwen3.5-4B` run, shows severe conservative collapse. Thus, short zero-shot success should not be treated as interchangeable with full-benchmark reliability.

Paired Qwen comparisons on `benchmark_100` show that backend choice changes model behavior in a semantically structured way. Autoformalization substantially improves action calibration and alert-family recovery for the smaller Qwen models, especially on `active_interval` and `recent_measurement + TTL` semantics. By contrast, zero-shot raw-table reasoning preserves more persistent, cumulative, and composite-state recovery for `Qwen3.5-27B`, but does so with weaker alert-family overlap and less stable long-run behavior. Taken together, these results suggest that the benchmark is sensitive not only to model capability, but also to how the model accesses temporal clinical evidence.

### Suggested Shorter Version

On the primary autoformalized `benchmark_2k` rolling surveillance benchmark, the strongest fully completed model is `Qwen3.5-27B`, but all completed models remain weak on the benchmark’s core structured-state outputs and near-zero on strict patient-level exactness. On the short zero-shot raw-table `benchmark_100` pilot, closed-source models substantially outperform open-weight models, with `Gemini 3.1 Pro Preview` and `Claude Sonnet 4.6` dominating suspect- and alert-family recovery respectively. Paired Qwen comparisons show that autoformalization helps acute support-state and alert recovery, while raw-table zero-shot preserves some persistent and cumulative semantics for the largest Qwen model. The benchmark’s main challenge is therefore longitudinal state maintenance under mixed temporal semantics, not coarse escalation detection alone.

## Main Table

### Table 1 Caption

Table 1. Primary autoformalized `benchmark_2k` results. These are the main benchmark results because they evaluate the full `2,000`-stay rolling surveillance setting and directly score structured disease-family recovery plus patient-level alert timing.

### Table 1

| Model | Completed stays | `suspected_conditions_macro_f1` | `alerts_macro_f1` | `alerts_macro_precision` | `alerts_macro_recall` | `suspected_conditions_exact_match` | `alerts_exact_match` | `first_alert_mean_abs_error_hours` | `false_early_alert_trajectories` | `missed_alert_trajectories` | `strict_all4_trajectory_rate` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | `2000/2000` | `0.1472` | `0.2423` | `0.2643` | `0.2355` | `0.1239` | `0.2195` | `10.6119` | `37` | `909` | `0.0110` |
| `Qwen3.5-4B` | `2000/2000` | `0.1396` | `0.2453` | `0.2647` | `0.2390` | `0.1171` | `0.2232` | `9.5982` | `34` | `982` | `0.0090` |
| `Qwen3.5-9B` | `2000/2000` | `0.1366` | `0.2456` | `0.2707` | `0.2380` | `0.1266` | `0.2213` | `12.1627` | `17` | `998` | `0.0115` |
| `gpt-oss-120b` | `1026/2000` | `0.2054` | `0.2533` | `0.2759` | `0.2476` | `0.1276` | `0.2123` | `6.8496` | `58` | `209` | `0.0049` |
| `gemma-4-31B-it` | `1714/2000` | `0.1344` | `0.2277` | `0.2304` | `0.2269` | `0.1309` | `0.2253` | `22.9554` | `2` | `1455` | `0.0117` |

## Zero-Shot Table

### Table 2 Caption

Table 2. Completed zero-shot raw-table `benchmark_100` comparison. The agent reasons directly over checkpoint-scoped raw MIMIC-IV evidence through `zeroshot_python`. These results are useful for cross-model comparison, but they should be interpreted as a short-pilot backend comparison rather than as a substitute for the full `benchmark_2k` benchmark.

### Table 2

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

## Paired Backend Table

### Table 3 Caption

Table 3. Paired `benchmark_100` comparison for the Qwen family across zero-shot raw-table access and autoformalization. We include both overall and positive-only structured-state metrics because overall exact and F1 scores are partly anchored by negative-set checkpoints.

### Table 3

| Model | Mode | `suspected_conditions_macro_f1` | `alerts_macro_f1` | positive-only `suspected_conditions_macro_f1` | positive-only `alerts_macro_f1` | `global_action_accuracy` | `priority_accuracy` | `first_alert_mean_abs_error_hours` | `missed_alert_trajectories` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | autoformalization | `0.1942` | `0.2425` | `0.0165` | `0.0165` | `0.3869` | `0.3777` | `12.6829` | `53` |
| `Qwen3.5-27B` | zero-shot | `0.2063` | `0.2195` | `0.0510` | `0.0176` | `0.3177` | `0.3108` | `12.0606` | `28` |
| `Qwen3.5-9B` | autoformalization | `0.1856` | `0.2549` | `0.0050` | `0.0278` | `0.3531` | `0.3231` | `18.8148` | `67` |
| `Qwen3.5-9B` | zero-shot | `0.1847` | `0.2408` | `0.0019` | `0.0010` | `0.2492` | `0.2408` | `20.0000` | `83` |
| `Qwen3.5-4B` | autoformalization | `0.1854` | `0.2643` | `0.0236` | `0.0534` | `0.3646` | `0.3454` | `11.2632` | `56` |
| `Qwen3.5-4B` | zero-shot | `0.1830` | `0.2401` | `0.0037` | `0.0021` | `0.2700` | `0.2469` | `11.5200` | `69` |

## Auxiliary Table

### Table 4 Caption

Table 4. Auxiliary coarse response-layer summary metrics on the primary autoformalized `benchmark_2k` benchmark. These metrics evaluate the compressed checkpoint output fields `global_action` and `priority`, which are derived from the richer structured checkpoint state rather than representing the full clinical target space.

### Table 4

| Model | Completed stays | `global_action_accuracy` | `priority_accuracy` |
|---|---:|---:|---:|
| `Qwen3.5-27B` | `2000/2000` | `0.4577` | `0.4332` |
| `Qwen3.5-4B` | `2000/2000` | `0.4153` | `0.3993` |
| `Qwen3.5-9B` | `2000/2000` | `0.4083` | `0.3726` |
| `gpt-oss-120b` | `1026/2000` | `0.6317` | `0.5206` |
| `gemma-4-31B-it` | `1714/2000` | `0.2674` | `0.2409` |

## Qwen Figures

### Figure 1

![Qwen benchmark_2k core vs auxiliary](/Users/chloe/Documents/New project/docs/surveilance/figures/qwen_benchmark2k_core_vs_auxiliary.png)

Figure 1. Finished autoformalized Qwen models on the primary `benchmark_2k` benchmark. Left: core structured-state metrics. Right: auxiliary coarse response-layer summary metrics. Coarse summary performance is consistently higher than structured family-state recovery, showing that simplified action/priority labels overstate apparent capability.

### Figure 2

![Qwen benchmark_2k temporal quality](/Users/chloe/Documents/New project/docs/surveilance/figures/qwen_benchmark2k_temporal_quality.png)

Figure 2. Patient-level temporal quality for the finished autoformalized Qwen models. The dominant failure mode is missing true alerting trajectories rather than over-alerting, while strict longitudinal exactness remains near zero for all three models.

### Figure 3

![Qwen benchmark_2k semantic heatmap](/Users/chloe/Documents/New project/docs/surveilance/figures/qwen_benchmark2k_semantic_heatmap.png)

Figure 3. Temporal-semantic analysis for the finished autoformalized Qwen models. The models perform best on `active_interval` states, less well on `recent_measurement + TTL`, and extremely poorly on `persistent_episode`, `cumulative_max_stage`, and `composite_current_state`, indicating weak longitudinal carry-forward and recomposition behavior.

## Suggested Table Callouts in Main Text

- “Table 1 should be treated as the main benchmark table because it evaluates the full `benchmark_2k` task and directly scores structured state plus patient-level temporal quality.”
- “Table 2 shows that short raw-table zero-shot performance can be much stronger for frontier closed-source models, but this is not yet a substitute for completed long-run benchmark evidence.”
- “Table 3 reveals that backend choice changes the Qwen models in a semantically structured way: autoformalization helps acute support and alert recovery, while zero-shot preserves some persistent and cumulative reasoning for the largest Qwen model.”
- “Table 4 is intentionally auxiliary: `global_action` and `priority` are compressed response-layer summaries rather than the full clinical target.”

## Notes for Final Paper Framing

- Lead with autoformalized `benchmark_2k`, not `benchmark_100`.
- Treat the zero-shot raw-table comparison as an important secondary experiment, not the main benchmark.
- Use the completed Qwen `benchmark_2k` runs as the clean primary comparison.
- Treat `gpt-oss-120b` as the strongest provisional long-run open-weight model, but keep its incompleteness explicit.
- Make the open versus closed-source claim backend-specific:
  - on zero-shot `benchmark_100`, closed-source is clearly stronger
  - on autoformalized `benchmark_2k`, there is not yet a fair completed closed-source comparison
- Explain that overall exact-match metrics are partly driven by negative-set checkpoints and should be read alongside positive-only slices.
