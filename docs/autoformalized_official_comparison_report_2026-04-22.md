# Benchmark Comparison Report

Date: 2026-04-22

This report compares four result folders:

- `/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2`
- `/Users/chloe/Documents/New project/result/multi_toolbox_history_autoformalized_v2`
- `/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b`
- `/Users/chloe/Documents/New project/result/sepsis_toolbox_history_official_qwen3_30b`

## Caveats

- The two `v2` runs include `resource_usage` in `eval.json` and `rollouts.json`.
- The older sepsis runs do not include saved token/runtime metrics, so prompt-sensitivity and official-vs-autoformalized runtime comparisons cannot be made directly from these artifacts.
- Sample sizes differ:
  - single-sepsis autoformalized v2: 50 trajectories, 350 steps
  - multitask autoformalized v2: 20 trajectories, 140 steps
- Because of that, comparisons in Section 1 focus on normalized per-step and per-trajectory values, not raw totals.

## 1. Single-Sepsis Autoformalized v2 vs Multitask Autoformalized v2

### Headline

The multitask run is cheaper and more selective, but it is not solving the full multitask problem. It only used sepsis tools in practice and collapsed AKI and respiratory support to default negative states. As a result, its joint accuracy is very low despite decent-looking sepsis subtask numbers.

### Accuracy and task performance

| Metric | Single Sepsis Auto v2 | Multitask Auto v2 |
|---|---:|---:|
| Primary metric | step accuracy `0.5657` | joint step accuracy `0.1714` |
| Sepsis accuracy | `0.5657` | `0.6071` |
| Sepsis macro F1 | `0.4897` | `0.5512` |
| AKI accuracy | n/a | `0.6286` |
| AKI macro F1 | n/a | `0.2573` |
| Respiratory accuracy | n/a | `0.5214` |
| Respiratory macro F1 | n/a | `0.2285` |

### Sepsis class behavior

| Sepsis metric | Single Sepsis Auto v2 | Multitask Auto v2 |
|---|---:|---:|
| `keep_monitoring` F1 | `0.6775` | `0.6560` |
| `infection_suspect` F1 | `0.1846` | `0.2500` |
| `trigger_sepsis_alert` F1 | `0.6070` | `0.7475` |
| `trigger_sepsis_alert` precision | `0.6854` | `1.0000` |
| `trigger_sepsis_alert` recall | `0.5446` | `0.5968` |
| Sepsis grounded rate | infection `1.0`, alert `1.0` | sepsis grounded rate `0.5714` |

### Tool behavior and efficiency

| Metric | Single Sepsis Auto v2 | Multitask Auto v2 |
|---|---:|---:|
| Avg tool calls / step | `0.9743` | `0.4429` |
| Steps without tool calls | `0.0257` | `0.5571` |
| Repeated tool call rate | `0.7537` | `0.4839` |
| Marginal utility of call rate | `0.3930` | `0.5968` |
| Tool counts | infection `226`, sofa `115` | infection `42`, sofa `20` |

### Resource usage

| Metric | Single Sepsis Auto v2 | Multitask Auto v2 |
|---|---:|---:|
| Avg prompt tokens / step | `3980.6343` | `3214.2000` |
| Avg completion tokens / step | `40.7914` | `44.8143` |
| Avg total tokens / step | `4021.4257` | `3259.0143` |
| Avg model runtime / step | `4.2711s` | `4.4462s` |
| Avg tool runtime / step | `1.6715s` | `0.6784s` |
| Avg total step runtime | `5.9626s` | `5.1383s` |
| Avg total tokens / trajectory | `28149.98` | `22813.10` |
| Avg total runtime / trajectory | `41.7385s` | `35.9682s` |

### Rollout-level diagnosis

The multitask run never actually used AKI or respiratory tools. From `rollouts.json`, the tool counts were:

- `query_suspicion_of_infection`: `42`
- `query_sofa`: `20`
- `query_kdigo_stage`: `0`
- `query_ventilation_status`: `0`
- other contextual multitask tools: `0`

Predicted task-action distributions make the failure mode very clear:

- Sepsis predictions:
  - `keep_monitoring`: `84`
  - `infection_suspect`: `19`
  - `trigger_sepsis_alert`: `37`
- AKI predictions:
  - `keep_monitoring`: `140`
- Respiratory predictions:
  - `room_air_or_low_support`: `140`

Ground truth in the same run was much richer:

- AKI ground truth:
  - `keep_monitoring`: `88`
  - `suspect_aki`: `32`
  - `trigger_aki_alert`: `20`
- Respiratory ground truth:
  - `room_air_or_low_support`: `73`
  - `invasive_vent_required`: `67`

### Valuable conclusions

1. The multitask prompt currently buys efficiency by under-engaging with the non-sepsis tasks.
2. Multitask sepsis numbers look superficially strong, especially for `trigger_sepsis_alert`, but they are not accompanied by equally strong grounding and they come inside a joint system that fails badly on AKI and respiratory support.
3. The efficiency gain is real:
   - `-55%` tool calls per step relative to single-sepsis autoformalized v2
   - `-19%` total tokens per step
   - `-14%` total runtime per trajectory
4. But that cheaper behavior is not a clean Pareto improvement. It is largely a task-starvation pattern.
5. The most important benchmark story here is not just that multitask is harder. It is that multitask encourages the model to allocate attention unevenly, and the resulting efficiency can be misleading unless it is read together with per-task recall and actual tool coverage.

## 2. Prompt Sensitivity: Sepsis Autoformalized v2 vs Sepsis Autoformalized

### Headline

The `v2` prompt improves overall sepsis accuracy, alert detection, grounding, and evidence coverage, but it does so by spending substantially more tools. It is a better-performing prompt, but not a cheaper one.

### Accuracy

| Metric | Autoformalized | Autoformalized v2 | Delta |
|---|---:|---:|---:|
| Step accuracy | `0.5200` | `0.5657` | `+0.0457` |
| Macro F1 | `0.4589` | `0.4897` | `+0.0308` |
| `keep_monitoring` F1 | `0.6667` | `0.6775` | `+0.0108` |
| `infection_suspect` F1 | `0.1728` | `0.1846` | `+0.0118` |
| `trigger_sepsis_alert` F1 | `0.5371` | `0.6070` | `+0.0699` |
| `trigger_sepsis_alert` recall | `0.4196` | `0.5446` | `+0.1250` |

### Timing

| Metric | Autoformalized | Autoformalized v2 | Delta |
|---|---:|---:|---:|
| Infection exact match | `0.3800` | `0.3600` | `-0.0200` |
| Infection MAE (h) | `9.1667` | `9.5652` | `+0.3985` |
| Infection missed rate | `0.0400` | `0.0800` | `+0.0400` |
| Alert exact match | `0.4800` | `0.4200` | `-0.0600` |
| Alert MAE (h) | `4.8372` | `4.1702` | `-0.6670` |
| Alert missed rate | `0.1400` | `0.0600` | `-0.0800` |

Interpretation:

- Infection timing got slightly worse in `v2`.
- Alert timing is mixed:
  - worse exact match
  - better mean error
  - much lower missed-alert rate

That suggests `v2` is more willing to fire the alert pathway and therefore misses fewer true alerts, even if it does not always hit the exact transition hour.

### Grounding and evidence discipline

| Metric | Autoformalized | Autoformalized v2 | Delta |
|---|---:|---:|---:|
| Infection grounded rate | `0.9528` | `1.0000` | `+0.0472` |
| Alert grounded rate | `0.9365` | `1.0000` | `+0.0635` |
| Positive action without sufficient evidence | `0.0526` | `0.0000` | `-0.0526` |
| Necessary infection call coverage | `0.8837` | `1.0000` | `+0.1163` |
| Necessary sofa-for-alert coverage | `1.0000` | `1.0000` | `0.0000` |

### Tool efficiency

| Metric | Autoformalized | Autoformalized v2 | Delta |
|---|---:|---:|---:|
| Avg tool calls / step | `0.7171` | `0.9743` | `+0.2572` |
| Steps without tool calls | `0.2829` | `0.0257` | `-0.2572` |
| Repeated tool call rate | `0.6972` | `0.7537` | `+0.0565` |
| Repeated infection call after positive | `0.0101` | `0.1195` | `+0.1094` |
| Marginal utility of call rate | `0.4502` | `0.3930` | `-0.0572` |
| Infection tool calls | `198` | `226` | `+28` |
| SOFA tool calls | `53` | `115` | `+62` |

### Valuable conclusions

1. `v2` is better on benchmark accuracy, especially on the alert class.
2. `v2` is stricter and cleaner in evidence grounding.
3. `v2` pays for that improvement with much heavier tool use:
   - about `+36%` more tool calls per step
   - more repeated calls
   - especially many more `SOFA` calls
4. The biggest efficiency regression in `v2` is not just “more tools.” It is specifically repeated infection checking after infection is already known.
5. If the benchmark priority is raw sepsis accuracy and groundedness, `v2` is preferable. If the priority is selective, high-yield tool use, the older prompt was more efficient even though it was less reliable.

### Missing comparison

Token and runtime comparisons cannot be made for this section because the older autoformalized run does not save `resource_usage` in its result files.

## 3. Official vs Autoformalized on Single Sepsis

Comparison folders:

- `/Users/chloe/Documents/New project/result/sepsis_toolbox_history_official_qwen3_30b`
- `/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b`

### Headline

The official toolbox clearly outperforms the older autoformalized toolbox on single-sepsis accuracy, timing, grounding, and overall tool economy. Autoformalized uses more tools but does not convert that extra work into better sepsis performance.

### Accuracy

| Metric | Official | Autoformalized | Delta |
|---|---:|---:|---:|
| Step accuracy | `0.6743` | `0.5200` | `+0.1543` |
| Macro F1 | `0.6188` | `0.4589` | `+0.1599` |
| `keep_monitoring` F1 | `0.8333` | `0.6667` | `+0.1666` |
| `infection_suspect` F1 | `0.4242` | `0.1728` | `+0.2514` |
| `trigger_sepsis_alert` F1 | `0.5989` | `0.5371` | `+0.0618` |

### Timing

| Metric | Official | Autoformalized | Delta |
|---|---:|---:|---:|
| Infection exact match | `0.7200` | `0.3800` | `+0.3400` |
| Infection MAE (h) | `5.2800` | `9.1667` | `-3.8867` |
| Infection missed rate | `0.0000` | `0.0400` | `-0.0400` |
| Alert exact match | `0.6000` | `0.4800` | `+0.1200` |
| Alert MAE (h) | `1.9000` | `4.8372` | `-2.9372` |
| Alert missed rate | `0.2000` | `0.1400` | `+0.0600` |

Interpretation:

- Official is much better aligned on infection timing and substantially better on alert timing when it does fire.
- Autoformalized misses fewer alert transitions, but the alerts it makes are less temporally precise overall.

### Grounding and evidence

| Metric | Official | Autoformalized |
|---|---:|---:|
| Infection grounded rate | `1.0000` | `0.9528` |
| Alert grounded rate | `1.0000` | `0.9365` |
| Positive action without sufficient evidence | `0.0000` | `0.0526` |
| Necessary infection call coverage | `1.0000` | `0.8837` |
| Necessary sofa-for-alert coverage | `1.0000` | `1.0000` |

### Tool efficiency

| Metric | Official | Autoformalized | Delta |
|---|---:|---:|---:|
| Avg tool calls / step | `0.5714` | `0.7171` | `-0.1457` |
| Steps without tool calls | `0.4286` | `0.2829` | `+0.1457` |
| Repeated tool call rate | `0.6600` | `0.6972` | `-0.0372` |
| Repeated infection call after positive | `0.0000` | `0.0101` | `-0.0101` |
| Marginal utility of call rate | `0.3900` | `0.4502` | `-0.0602` |
| Infection tool calls | `176` | `198` | `-22` |
| SOFA tool calls | `24` | `53` | `-29` |
| SOFA marginal utility | `0.7917` | `0.5660` | `+0.2257` |

Interpretation:

- Official is more selective overall.
- Autoformalized has slightly higher overall marginal-utility rate, but that comes with many more calls.
- The sharper result is tool-level selectivity:
  - official uses less than half as many `SOFA` calls
  - those `SOFA` calls are much higher-yield

### Valuable conclusions

1. Official is the stronger baseline on single-sepsis under these artifacts.
2. The biggest official advantage is not only raw accuracy. It is cleaner timing and much more selective use of `SOFA`.
3. Autoformalized’s extra tool activity does not buy enough accuracy to justify its cost in this comparison.
4. The one area where autoformalized looks somewhat more favorable is alert missed rate, suggesting it may be more willing to probe or fire on borderline cases. But that willingness comes with weaker timing precision and weaker grounding.

### Missing comparison

Token and runtime comparisons cannot be made for this section because neither older result folder stores `resource_usage`.

## Overall Takeaways

1. Multitask is not just harder because there are more labels. It is harder because the agent appears to allocate its evidence budget unevenly across tasks.
2. Prompt changes matter a lot. The `v2` autoformalized prompt improved sepsis accuracy and groundedness, but it also made tool use markedly more expensive.
3. On older single-sepsis runs, official is the stronger and more efficient baseline than autoformalized.
4. The most useful benchmark lens is not accuracy alone. The combination of:
   - class-level F1
   - transition timing
   - grounding
   - necessary-call coverage
   - marginal utility of calls
   tells a much richer story about how the agent is reasoning.
5. For future multitask prompt work, the main target should be evidence allocation:
   - retain the efficiency gains of the multitask run
   - but force better coverage of AKI and respiratory reasoning through prompt design, not runtime intervention
