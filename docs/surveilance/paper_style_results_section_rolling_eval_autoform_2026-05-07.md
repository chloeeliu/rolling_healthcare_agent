# NeurIPS-Style Results Section for Rolling Surveillance Benchmark

Date: 2026-05-07

## Intended Use

This document is a tighter Results-section rewrite for the paper draft. It integrates:

- autoformalization results from `result/rolling_eval_autoform/`
- zero-shot raw-table results from `result/rolling_eval_zeroshot/`

It follows the requested structure:

1. results summary / introduction
2. longitudinal state tracking is the core bottleneck
3. backend matters: zero-shot vs autoformalization
4. open-weight vs closed-source models
5. failure modes

Primary reference:

- [rolling_eval_autoform_final_report_2026-05-06.md](/Users/chloe/Documents/New%20project/docs/surveilance/rolling_eval_autoform_final_report_2026-05-06.md)

## 1. Results Summary / Introduction

We evaluate rolling ICU surveillance under two interfaces. In the autoformalized `session_tools` setting, the agent interacts with a structured function and guideline layer. In the `zeroshot_python` setting, the agent reasons directly over checkpoint-scoped raw MIMIC-IV tables through Python and `query_db`. Across both settings, the model must output a structured surveillance state, including `suspected_conditions` and `alerts`, while `global_action` and `priority` serve only as compressed response-layer summaries.

Our primary benchmark is the autoformalized `benchmark_2k` evaluation, which contains `2,000` ICU stays and `26,000` checkpoint decisions. On this benchmark, the strongest fully completed model is `Qwen3.5-27B`, which achieves the best completed-run `suspected_conditions_macro_f1` (`0.1472`) and misses fewer alerting trajectories (`909`) than the smaller completed Qwen variants. However, even the best completed model remains far from reliable longitudinal surveillance: `alerts_macro_f1` remains near `0.24`, exact set recovery remains low, and strict patient-level exactness is only `1.10%`. A partial `gpt-oss-120b` run is stronger on several metrics, but because it completed only `1,026/2,000` trajectories, it should be treated as provisional.

The zero-shot raw-table setting produces a different short-pilot ranking on `benchmark_100`. Here the closed-source models are substantially stronger than the open-weight models. `Gemini 3.1 Pro Preview` achieves the best suspect-family recovery (`0.4393` macro F1), while `Claude Sonnet 4.6` achieves the best alert-family recovery (`0.4722` macro F1) and first-alert timing (`3.95h` mean absolute error). However, there is no completed zero-shot `benchmark_2k` comparison, so these results should be interpreted as backend-specific pilot evidence rather than as a replacement for the main benchmark.

### Table 1 Caption

Table 1. Primary autoformalized `benchmark_2k` results. This is the main benchmark table because it evaluates the full `2,000`-stay rolling surveillance task and directly scores structured disease-family recovery plus patient-level temporal quality.

### Table 1

| Model | Completed stays | `suspected_conditions_macro_f1` | `alerts_macro_f1` | `alerts_macro_precision` | `alerts_macro_recall` | `suspected_conditions_exact_match` | `alerts_exact_match` | `first_alert_mean_abs_error_hours` | `false_early_alert_trajectories` | `missed_alert_trajectories` | `strict_all4_trajectory_rate` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | `2000/2000` | `0.1472` | `0.2423` | `0.2643` | `0.2355` | `0.1239` | `0.2195` | `10.6119` | `37` | `909` | `0.0110` |
| `Qwen3.5-4B` | `2000/2000` | `0.1396` | `0.2453` | `0.2647` | `0.2390` | `0.1171` | `0.2232` | `9.5982` | `34` | `982` | `0.0090` |
| `Qwen3.5-9B` | `2000/2000` | `0.1366` | `0.2456` | `0.2707` | `0.2380` | `0.1266` | `0.2213` | `12.1627` | `17` | `998` | `0.0115` |
| `gpt-oss-120b` | `1026/2000` | `0.2054` | `0.2533` | `0.2759` | `0.2476` | `0.1276` | `0.2123` | `6.8496` | `58` | `209` | `0.0049` |
| `gemma-4-31B-it` | `1714/2000` | `0.1344` | `0.2277` | `0.2304` | `0.2269` | `0.1309` | `0.2253` | `22.9554` | `2` | `1455` | `0.0117` |

### Suggested Main-Text Callout

- “Table 1 shows that the strongest completed model is still far from robust longitudinal surveillance-state tracking: checkpoint-level family recovery remains weak, missed-alert trajectories remain common, and strict patient-level exactness remains near zero.”

## 2. Longitudinal State Tracking Is the Core Bottleneck

The central empirical result is that coarse checkpoint plausibility does not translate into correct longitudinal state tracking. Models often recover enough local evidence to choose a reasonable top-level surveillance posture, but they fail to maintain the correct evolving disease-family state over time. This is visible in three ways.

First, family-level structured-state metrics remain much lower than coarse summary metrics. For example, on autoformalized `benchmark_2k`, `Qwen3.5-27B` reaches `0.4577` `global_action_accuracy`, yet only `0.1472` `suspected_conditions_macro_f1`. Similar gaps appear for the other completed Qwen models. The benchmark therefore cannot be characterized as a simple escalation-versus-monitoring task; the harder problem is reconstructing the correct family-state configuration behind the action.

Second, patient-level alerting remains brittle. Even when a model eventually emits some correct signals, it frequently misses entire alerting trajectories. On `benchmark_2k`, the completed Qwen runs miss `909`, `998`, and `982` alerting stays respectively. This indicates that the dominant failure is not minor timing noise, but failure to carry the appropriate surveillance state forward across the stay.

Third, strict longitudinal exactness remains near zero. Requiring exact agreement on `global_action`, `priority`, `suspected_conditions`, and `alerts` at every checkpoint yields only `0.90%` to `1.15%` accuracy for the completed autoformalized Qwen runs. This harsh metric is nonetheless appropriate for a rolling surveillance benchmark: the clinical burden lies in sustaining coherent state over time, not merely in producing isolated locally plausible answers.

The same conclusion becomes sharper when suspect and alert metrics are decomposed into overall, negative-set, and positive-set checkpoints. Overall `alerts_exact_match` clusters near `0.22`, but this is largely driven by negative-set checkpoints where the gold alert set is empty. On the completed Qwen `benchmark_2k` runs, negative-only `alert_exact` is `0.9477` to `0.9647`, whereas positive-only `alert_exact` is only `0.0038` to `0.0112`. Positive-only `alert_macro_f1` remains only `0.0343`, `0.0352`, and `0.0398`. Thus, the benchmark’s real difficulty lies in recovering active structured state, not in preserving emptiness.

### Table 2 Caption

Table 2. Decomposition of the completed Qwen `benchmark_2k` runs into overall, negative-set, and positive-set checkpoints. The clustering of overall exact-match metrics is largely a negative-set effect; positive-set recovery remains extremely weak.

### Table 2

| Model | Slice | `suspected_conditions_exact` | `suspected_conditions_macro_f1` | `alerts_exact` | `alerts_macro_f1` | `alerts_macro_precision` | `alerts_macro_recall` |
|---|---|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | overall | `0.1239` | `0.1472` | `0.2195` | `0.2423` | `0.2643` | `0.2355` |
| `Qwen3.5-27B` | negative only | `0.9189` | `0.9189` | `0.9529` | `0.9529` | `0.9529` | `0.9529` |
| `Qwen3.5-27B` | positive only | `0.0071` | `0.0338` | `0.0049` | `0.0343` | `0.0628` | `0.0255` |
| `Qwen3.5-9B` | overall | `0.1266` | `0.1366` | `0.2213` | `0.2456` | `0.2707` | `0.2380` |
| `Qwen3.5-9B` | negative only | `0.9601` | `0.9601` | `0.9647` | `0.9647` | `0.9647` | `0.9647` |
| `Qwen3.5-9B` | positive only | `0.0041` | `0.0156` | `0.0038` | `0.0352` | `0.0676` | `0.0253` |
| `Qwen3.5-4B` | overall | `0.1171` | `0.1396` | `0.2232` | `0.2453` | `0.2647` | `0.2390` |
| `Qwen3.5-4B` | negative only | `0.8766` | `0.8766` | `0.9477` | `0.9477` | `0.9477` | `0.9477` |
| `Qwen3.5-4B` | positive only | `0.0055` | `0.0313` | `0.0112` | `0.0398` | `0.0648` | `0.0317` |

### Semantic Interpretation

The temporal-semantic analysis points to the same bottleneck. In the completed Qwen `benchmark_2k` runs, performance is consistently strongest on `active_interval` states, weaker on `recent_measurement + TTL`, and extremely poor on `persistent_episode`, `cumulative_max_stage`, and `composite_current_state`. This means the models can partially identify currently visible support states, but rarely maintain persistent sepsis-related state, preserve cumulative AKI stage, or recompute composite shock states correctly.

![Qwen benchmark_2k bottleneck decomposition](/Users/chloe/Documents/New project/docs/surveilance/figures/qwen_benchmark2k_bottleneck_decomposition.png)

Figure 1. Overall versus positive-only structured-state metrics for the completed Qwen `benchmark_2k` runs. The apparent moderate overall scores collapse once evaluation is restricted to positive suspect and alert checkpoints.

![Qwen benchmark_2k semantic heatmap](/Users/chloe/Documents/New project/docs/surveilance/figures/qwen_benchmark2k_semantic_heatmap.png)

Figure 2. Temporal-semantic analysis for the completed Qwen `benchmark_2k` runs. The models are strongest on `active_interval` states and weakest on `persistent_episode`, `cumulative_max_stage`, and `composite_current_state`.

### Suggested Main-Text Callout

- “The main bottleneck is not coarse escalation detection but longitudinal structured-state maintenance: once we restrict evaluation to positive checkpoints, exact alert recovery is near zero for all completed Qwen models.”

## 3. Backend Matters: Zero-Shot vs Autoformalization

The paired Qwen comparison on `benchmark_100` shows that backend choice changes behavior in a structured, non-monotonic way. Autoformalization is not simply an easier version of the task, nor is zero-shot simply more faithful to the data. Instead, the two interfaces emphasize different temporal reasoning capabilities.

For the smaller Qwen models, autoformalization substantially improves coarse action calibration and alert-family recovery. Relative to zero-shot, the Qwen-family average on `benchmark_100` rises from `0.2790` to `0.3682` in `global_action_accuracy`, from `0.2662` to `0.3487` in `priority_accuracy`, and from `0.2335` to `0.2539` in `alerts_macro_f1`. Positive-only alert recovery improves even more sharply, from `0.0069` to `0.0326` macro F1 on average. This suggests that the structured function layer is especially helpful for acute support-state lookup and explicit thresholded alert logic.

However, autoformalization does not uniformly improve suspect-family reasoning. `Qwen3.5-27B` performs better in zero-shot on suspect-family recovery (`0.2063` versus `0.1942`) and substantially better on positive-only suspect recovery (`0.0510` versus `0.0165`). It also misses fewer alerting trajectories in zero-shot (`28` versus `53`). Semantic analysis explains why: zero-shot `Qwen3.5-27B` preserves more `persistent_episode`, `cumulative_max_stage`, and `composite_current_state` structure, whereas autoformalization helps mainly on `active_interval` and, more modestly, `recent_measurement + TTL`.

This is an important scientific finding in its own right. The benchmark is sensitive not only to model size and family, but also to how the model accesses temporal clinical evidence. The formalized tool layer appears to regularize smaller models and improve local support-state recovery, but it can also suppress some persistent and cumulative state tracking for larger models if the model relies too heavily on local retrieval instead of maintaining internal longitudinal structure.

![Qwen benchmark_100 backend comparison](/Users/chloe/Documents/New project/docs/surveilance/figures/qwen_benchmark100_backend_comparison.png)

Figure 3. Paired Qwen comparison on `benchmark_100`. Autoformalization generally improves action calibration and alert-family recovery for the smaller models, while zero-shot preserves stronger positive-only suspect recovery for `Qwen3.5-27B`.

### Table 3 Caption

Table 3. Paired `benchmark_100` comparison for the Qwen family across zero-shot raw-table access and autoformalization. Backend choice changes both accuracy and failure mode.

### Table 3

| Model | Mode | `suspected_conditions_macro_f1` | `alerts_macro_f1` | positive-only `suspected_conditions_macro_f1` | positive-only `alerts_macro_f1` | `global_action_accuracy` | `priority_accuracy` | `first_alert_mean_abs_error_hours` | `missed_alert_trajectories` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen3.5-27B` | autoformalization | `0.1942` | `0.2425` | `0.0165` | `0.0165` | `0.3869` | `0.3777` | `12.6829` | `53` |
| `Qwen3.5-27B` | zero-shot | `0.2063` | `0.2195` | `0.0510` | `0.0176` | `0.3177` | `0.3108` | `12.0606` | `28` |
| `Qwen3.5-9B` | autoformalization | `0.1856` | `0.2549` | `0.0050` | `0.0278` | `0.3531` | `0.3231` | `18.8148` | `67` |
| `Qwen3.5-9B` | zero-shot | `0.1847` | `0.2408` | `0.0019` | `0.0010` | `0.2492` | `0.2408` | `20.0000` | `83` |
| `Qwen3.5-4B` | autoformalization | `0.1854` | `0.2643` | `0.0236` | `0.0534` | `0.3646` | `0.3454` | `11.2632` | `56` |
| `Qwen3.5-4B` | zero-shot | `0.1830` | `0.2401` | `0.0037` | `0.0021` | `0.2700` | `0.2469` | `11.5200` | `69` |

### Suggested Main-Text Callout

- “Backend choice is not a superficial implementation detail: autoformalization helps smaller Qwen models recover acute support and alert structure, while raw-table zero-shot preserves some persistent and cumulative semantics for `Qwen3.5-27B`.”

## 4. Open-Weight vs Closed-Source Models

The open-weight versus closed-source conclusion depends on which backend is being evaluated.

In zero-shot raw-table `benchmark_100`, the closed-source models are clearly stronger. Averaged across `GPT-5.4`, `Claude Sonnet 4.6`, and `Gemini 3.1 Pro Preview`, the closed-source group achieves `0.3595` `suspected_conditions_macro_f1`, `0.4190` `alerts_macro_f1`, `5.22h` first-alert mean absolute error, and `14.3` missed-alert trajectories. The corresponding open-weight averages are `0.2057`, `0.2361`, `12.84h`, and `41.2`. This is a large and consistent gap.

Within the closed-source zero-shot group, the ranking is itself meaningful. `Gemini` is best on suspect-family recovery and exact suspect-set matching, while `Claude` is best on alert-family recovery and timing, albeit with the most false-early alerts. `GPT-5.4` is clearly weaker than Claude and Gemini on the core structured-state metrics, but still stronger than the open-weight zero-shot models.

By contrast, the autoformalized setting does not yet permit a fair open-weight versus closed-source leaderboard claim. The only reliable completed `benchmark_2k` evidence comes from open-weight models, because the autoformalized closed-source runs are incomplete and tool-error-heavy. Thus, the correct claim is backend-specific: closed-source models dominate the short raw-table pilot, while open-weight models currently provide the only completed evidence on the full autoformalized benchmark.

The cost profile of the open-weight zero-shot runs also helps explain some of this spread. After reconstructing the prompt stack from the saved zero-shot prompt template and per-step tool traces, the dominant cost source is not the tool outputs themselves but the repeated instruction scaffold plus checkpoint payload that must be re-sent on every model turn. Tool-output context is still substantial, especially for the larger open-weight models, accounting for roughly `13%` to `18%` of prompt-side cost. `Qwen3.5-27B` is the most expensive overall because it combines a large fixed prompt burden with high completion cost, while `gemma-4-31B-it` spends heavily on prompt-side interaction context but produces very few completion tokens. This suggests that some open-weight zero-shot failures are not simply low-effort shortcuts; several models incur heavy retrieval and control-flow cost without converting that interaction into stronger structured-state recovery.

![Zero-shot benchmark_100 open vs closed](/Users/chloe/Documents/New project/docs/surveilance/figures/zeroshot_benchmark100_open_vs_closed.png)

Figure 4. Completed zero-shot raw-table `benchmark_100` comparison. Closed-source models cluster in the upper-right, indicating stronger joint suspect- and alert-family recovery than the open-weight zero-shot models.

![Zero-shot benchmark_100 open-weight cost breakdown](/Users/chloe/Documents/New project/docs/surveilance/figures/zeroshot_benchmark100_open_weight_cost_breakdown.png)

Figure 5. Open-weight zero-shot cost decomposition on `benchmark_100`. Each stacked bar reconstructs average tokens per trajectory into fixed instruction scaffold, checkpoint payload plus rolling memory, accumulated Python code history, accumulated tool-output context, summary-writer overhead, estimated repair/retry overhead, and measured completion tokens. The prompt-side split is reconstructed from the saved backend prompt template and per-step tool traces, while the completion segment is directly measured.

### Table 4 Caption

Table 4. Completed zero-shot raw-table `benchmark_100` comparison across open-weight and closed-source models. These results show a clear short-pilot advantage for closed-source systems, but do not replace the need for completed long-run evaluation.

### Table 4

| Model | Family | `suspected_conditions_macro_f1` | `alerts_macro_f1` | `suspected_conditions_exact_match` | `alerts_exact_match` | `first_alert_mean_abs_error_hours` | `missed_alert_trajectories` |
|---|---|---:|---:|---:|---:|---:|---:|
| `Gemini/gemini-3.1-pro-preview` | closed-source | `0.4393` | `0.4636` | `0.2531` | `0.2423` | `4.6047` | `8` |
| `Claude/claude-sonnet-4-6` | closed-source | `0.3830` | `0.4722` | `0.1808` | `0.2338` | `3.9535` | `8` |
| `GPT/gpt-5.4` | closed-source | `0.2561` | `0.3212` | `0.1862` | `0.2192` | `7.1045` | `27` |
| `gpt-oss-120b` | open-weight | `0.2564` | `0.2167` | `0.1715` | `0.1831` | `11.3333` | `4` |
| `Qwen3.5-27B` | open-weight | `0.2063` | `0.2195` | `0.1800` | `0.2062` | `12.0606` | `28` |
| `gemma-4-31B-it` | open-weight | `0.1982` | `0.2632` | `0.1646` | `0.2046` | `9.2778` | `22` |
| `Qwen3.5-9B` | open-weight | `0.1847` | `0.2408` | `0.1831` | `0.2408` | `20.0000` | `83` |
| `Qwen3.5-4B` | open-weight | `0.1830` | `0.2401` | `0.1815` | `0.2385` | `11.5200` | `69` |

### Suggested Main-Text Callout

- “Open-weight versus closed-source should be treated as a backend-specific claim: closed-source models dominate the short zero-shot raw-table pilot, but only open-weight models currently provide completed evidence on the full autoformalized benchmark.”

## 5. Failure Modes

The combined results expose two broad failure classes: conceptual longitudinal reasoning failures and interface-mediated infrastructure failures.

The most important conceptual failure is conservative collapse. Many open-weight models, especially in zero-shot, drift toward near-always `continue_monitoring` behavior. On raw-table `benchmark_100`, `Qwen3.5-9B` predicts `continue_monitoring` on `98.92%` of steps and `Qwen3.5-4B` on `96.54%`. The partial zero-shot `benchmark_2k` `Qwen3.5-4B` run is even more extreme at `98.15%`. This collapse explains why overall exact-match can still look superficially moderate while positive-only alert recovery is near zero.

The second conceptual failure is semantic selectivity. Even when models avoid complete conservative collapse, they tend to recover only the easiest temporal semantics. The completed Qwen `benchmark_2k` runs are strongest on `active_interval`, weaker on `recent_measurement + TTL`, and extremely weak on `persistent_episode`, `cumulative_max_stage`, and `composite_current_state`. This indicates that maintaining persistent and cumulative state across checkpoints is harder than detecting currently visible support or measurement states.

The main interface-mediated failure lies in tool reliability and callable discoverability. In the autoformalized `session_tools` setting, repeated failures cluster around a small set of helpers, including blood-gas, vasoactive, KDIGO, and GCS-related functions. These issues are especially severe in the autoformalized closed-source pilots, which makes those runs unsuitable for definitive comparison. At the same time, the backend contrast suggests that interface design genuinely changes the reasoning profile, so the observed differences cannot be dismissed as pure infrastructure noise.

### Practical Interpretation

The paper should therefore separate:

- longitudinal state-tracking failures, which are central to the benchmark claim
- interface and tool failures, which affect some backends more than others

Both matter. The first establishes that rolling current-state ICU surveillance is intrinsically hard. The second shows that agent interface design can either expose or mask parts of that difficulty.

### Suggested Closing Paragraph

Overall, the results support three main conclusions. First, longitudinal structured-state tracking, rather than coarse escalation detection, is the core bottleneck of the benchmark. Second, backend choice materially changes which temporal semantics models can recover, so zero-shot raw-table reasoning and autoformalization should be treated as substantively different evaluation conditions. Third, while frontier closed-source models are strongest in the short raw-table pilot, the only reliable completed evidence on the full `benchmark_2k` benchmark currently comes from open-weight models, and even the best completed run remains far from robust patient-level surveillance-state tracking.
