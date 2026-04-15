# Longitudinal Agent Baseline Trajectory Analysis

## Scope

This report analyzes the saved baseline trajectories under `/Users/chloe/Documents/New project/result`:

- single-task sepsis agent:
  `/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507`
- multitask agent:
  `/Users/chloe/Documents/New project/result/multi_Qwen3-30B-A3B-Instruct-2507`

The focus is not just headline accuracy. The goal is to understand how these longitudinal agents actually behave over checkpoints:

- how often they call tools
- whether they maintain intermediate states
- whether they alert early or late
- which tasks are solved by direct tool reading versus true multi-step reasoning

## Result Files

Single-task sepsis:

- [/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507/qwen_rollouts.json](/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507/qwen_rollouts.json)
- [/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507/qwen_trajectories.jsonl](/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507/qwen_trajectories.jsonl)
- [/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507/qwen_events.jsonl](/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507/qwen_events.jsonl)

Multitask:

- [/Users/chloe/Documents/New project/result/multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_rollouts.json](/Users/chloe/Documents/New project/result/multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_rollouts.json)
- [/Users/chloe/Documents/New project/result/multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_trajectories.jsonl](/Users/chloe/Documents/New project/result/multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_trajectories.jsonl)
- [/Users/chloe/Documents/New project/result/multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_events.jsonl](/Users/chloe/Documents/New project/result/multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_events.jsonl)

## Important Comparison Caveat

These two runs are useful together, but they are not a pure multitask ablation:

- both runs use `Qwen3-30B-A3B-Instruct-2507`
- the single-task and multitask datasets are not matched by stay identity

So the comparison is still informative, but it should be interpreted as:

- a single-task sepsis baseline
- a multitask longitudinal-monitoring baseline

not as a clean matched-cohort multitask ablation.

## Executive Summary

The strongest baseline insights are:

1. Both agents are fully grounded in the sense that they call concept tools before deciding, but neither agent is selective.
   The single-task agent always queries both tools.
   The multitask agent always queries all four tools.

2. The main failure mode is not tool refusal anymore. It is longitudinal state collapse.
   The agents often skip or blur the intermediate escalation state, especially for sepsis.

3. Sepsis is clearly the hardest task.
   In both the single-task and multitask settings, the model struggles to hold `infection_suspect` as a stable intermediate state.

4. AKI is much easier than sepsis in multitask mode.
   Most AKI mistakes are conservative undercalls, not wild failures.

5. Respiratory support is almost solved in multitask mode.
   That appears to come from the task being close to direct tool reading rather than deep longitudinal reasoning.

## Single-Task Sepsis Baseline

### Top-line behavior

Cohort size:

- 98 rollouts
- 686 checkpoint steps

Step-level accuracy:

- `0.8003`

Class distribution:

- ground truth:
  - `keep_monitoring`: 367
  - `infection_suspect`: 69
  - `trigger_sepsis_alert`: 250
- predictions:
  - `keep_monitoring`: 343
  - `infection_suspect`: 18
  - `trigger_sepsis_alert`: 325

Interpretation:

- The single-task sepsis agent is strongly biased toward the terminal alert state.
- It predicts `trigger_sepsis_alert` more often than the ground truth.
- It almost never uses the intermediate `infection_suspect` label.

### Per-class performance

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| `keep_monitoring` | 0.8834 | 0.8256 | 0.8535 |
| `infection_suspect` | 0.3889 | 0.1014 | 0.1609 |
| `trigger_sepsis_alert` | 0.7354 | 0.9560 | 0.8313 |

Interpretation:

- `infection_suspect` is the core weakness.
- The model is good at deciding when a stay is no longer normal.
- But once it leaves `keep_monitoring`, it usually jumps too quickly to `trigger_sepsis_alert`.

### Timing behavior

Infection transition timing:

- exact match rate: `0.7143`
- mean absolute error: `2.57` hours
- early rate: `0.1327`
- late rate: `0.1531`
- missed rate: `0.0`

Sepsis alert timing:

- exact match rate: `0.5714`
- mean absolute error: `2.65` hours
- early rate: `0.3673`
- late rate: `0.0612`
- missed rate: `0.0`

Interpretation:

- The single-task sepsis agent almost never misses an alert entirely.
- The cost of that recall is early alerting.
- Alert timing is much more early-biased than late-biased.

Stay-level detection summary:

- true positive trajectories: 48
- missed positive trajectories: 0
- false positive trajectories: 13
- true negative trajectories: 37

This is a high-recall, over-alerting baseline.

### Tool-use pattern

From the event trace:

- 686 steps
- 1372 tool calls
- exactly 2 tool calls per step
- fixed tool pattern on every step:
  - `query_suspicion_of_infection`
  - `query_sofa`

Interpretation:

- This is a fully grounded but non-adaptive tool policy.
- The model is not using tools strategically.
- It behaves more like a fixed extraction pass than a selective monitoring agent.

### Policy-level insight

When tool outputs show:

- suspected infection = `true`
- SOFA `>= 2`

the single-task agent predicts:

- `trigger_sepsis_alert`: 323 times
- `infection_suspect`: 18 times
- `keep_monitoring`: 5 times

When tool outputs show:

- suspected infection = `true`
- SOFA `< 2`

the single-task agent predicts:

- `keep_monitoring`: 79 times
- `infection_suspect`: 0 times
- `trigger_sepsis_alert`: 0 times

This is one of the most important findings in the whole analysis.

It suggests the baseline is effectively using an implicit rule like:

- infection visible + SOFA high -> alert
- infection visible + SOFA low -> keep monitoring

That means it is not truly representing the intermediate surveillance state well.
It treats `infection_suspect` as a rare exception rather than as a stable part of longitudinal reasoning.

### Error archetypes

Common single-task mistakes:

1. Early alert on `infection_suspect` trajectories with pre-ICU infection and elevated SOFA.
   Example: stay `30135840` at `t=0` is ground-truth `infection_suspect`, but the model triggers immediately because infection is already visible and SOFA is 4.

2. Suppressing `infection_suspect` when infection is visible but SOFA is low.
   Example: stay `30246991` remains `keep_monitoring` across multiple checkpoints even though suspected infection is already visible and SOFA is 1.

3. Occasional false alert on non-sepsis trajectories with high SOFA but no infection.
   There are 13 false-positive trajectories at the stay level.

Overall interpretation:

- the agent can detect “normal vs abnormal”
- it can detect “late severe sepsis”
- it does not maintain the clinically useful intermediate suspicion state

## Multitask Baseline

### Top-line behavior

Cohort size:

- 96 rollouts
- 672 checkpoint steps

Joint step accuracy:

- `0.5818`

Per-task accuracy:

- sepsis: `0.6741`
- AKI: `0.8423`
- respiratory support: `0.9702`

Interpretation:

- Joint correctness is much lower than per-task correctness because all three decisions must be right simultaneously.
- The multitask agent is strong on AKI and respiratory support, but sepsis remains the bottleneck.

### Multitask tool-use pattern

From the event trace:

- 672 steps
- 3360 `model_output_raw` events
- 2688 tool calls
- exactly 4 tool calls per step
- exactly 5 raw model outputs per step

The standard per-step sequence is:

1. tool call for infection
2. tool call for SOFA
3. tool call for KDIGO
4. tool call for ventilation
5. final `task_actions`

Observed notable property:

- no repair events
- no forced-tool correction events

Interpretation:

- the multitask prompt/controller contract is now stable
- the model is following the tool protocol cleanly
- current errors come from decision quality, not formatting or tool-call failure

### Sepsis head in multitask mode

Ground truth rows:

- `keep_monitoring`: 279
- `infection_suspect`: 142
- `trigger_sepsis_alert`: 251

Predicted rows:

- `keep_monitoring`: 393
- `infection_suspect`: 81
- `trigger_sepsis_alert`: 198

Per-class metrics:

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| `keep_monitoring` | 0.6870 | 0.9677 | 0.8036 |
| `infection_suspect` | 0.4074 | 0.2324 | 0.2960 |
| `trigger_sepsis_alert` | 0.7576 | 0.5976 | 0.6682 |

Timing:

- `infection_suspect` exact timing: `0.6562`
- `trigger_sepsis_alert` exact timing: `0.6042`
- missed infection transition rate: `0.2292`
- missed alert rate: `0.1250`

Interpretation:

- Multitask sepsis is still weak, but in a different way from the single-task baseline.
- The model is more conservative overall.
- It undercalls both `infection_suspect` and `trigger_sepsis_alert`, especially the intermediate state.

Policy-level insight:

When infection is visible and SOFA is high in multitask mode, the sepsis head predicts:

- `trigger_sepsis_alert`: 189
- `infection_suspect`: 71
- `keep_monitoring`: 60

When infection is visible and SOFA is low, it predicts:

- `keep_monitoring`: 62
- `infection_suspect`: 10

So the same underlying pattern appears again:

- the model has trouble sustaining `infection_suspect`
- it uses SOFA to decide between baseline and alert more than between suspicion and alert

This is a key benchmark insight.
Even in multitask mode with a much larger model, sepsis is still not behaving like a clean three-state monitor.

### AKI head

Ground truth rows:

- `keep_monitoring`: 373
- `suspect_aki`: 163
- `trigger_aki_alert`: 136

Predicted rows:

- `keep_monitoring`: 443
- `suspect_aki`: 135
- `trigger_aki_alert`: 94

Per-class metrics:

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| `keep_monitoring` | 0.8420 | 1.0000 | 0.9142 |
| `suspect_aki` | 0.7333 | 0.6074 | 0.6644 |
| `trigger_aki_alert` | 1.0000 | 0.6912 | 0.8174 |

Timing:

- `suspect_aki` exact timing: `0.8542`
- `trigger_aki_alert` exact timing: `0.8958`

Interpretation:

- AKI is the cleanest solved task in multitask mode.
- Errors are mostly conservative:
  - `suspect_aki -> keep_monitoring`
  - `trigger_aki_alert -> suspect_aki`
- Very few catastrophic false positives appear.

Policy-level insight:

When the latest smoothed KDIGO stage is:

- `< 1`: the agent predicts `keep_monitoring` almost always
- `= 1`: the agent predicts `suspect_aki` most of the time
- `>= 2`: the agent predicts `trigger_aki_alert` most of the time

This is close to the intended task logic.

So AKI behaves like a good concept-thresholding task for this baseline.

### Respiratory support head

Ground truth rows:

- `room_air_or_low_support`: 361
- `high_flow_or_noninvasive_support`: 30
- `invasive_vent_required`: 281

Predicted rows:

- `room_air_or_low_support`: 380
- `high_flow_or_noninvasive_support`: 27
- `invasive_vent_required`: 265

Per-class metrics:

| Class | Precision | Recall | F1 |
|---|---:|---:|---:|
| `room_air_or_low_support` | 0.9500 | 1.0000 | 0.9744 |
| `high_flow_or_noninvasive_support` | 0.9630 | 0.8667 | 0.9123 |
| `invasive_vent_required` | 1.0000 | 0.9431 | 0.9707 |

Timing:

- `high_flow_or_noninvasive_support` exact timing: `0.9896`
- `invasive_vent_required` exact timing: `1.0000`

Stay-level detection summary:

- respiratory true positives: 53
- respiratory misses: 0
- respiratory false positives: 0
- respiratory true negatives: 43

Interpretation:

- Respiratory support is nearly solved.
- This is not just a model victory. It also reflects task structure.
- The respiratory tool returns a near-direct concept summary of support level, so the decision boundary is very close to the tool output.

That makes respiratory support a useful control task:

- it shows the agent can follow the longitudinal tool protocol
- it is less informative about multi-step medical reasoning than sepsis

## Cross-Agent Comparison

### 1. Tool orchestration is no longer the main bottleneck

Single-task:

- exactly 2 tools every step

Multitask:

- exactly 4 tools every step
- clean 5-turn tool loop
- no repair/forced-tool interventions

Interpretation:

- the current prompt/controller stack is working
- the baseline has moved past “can the model call tools?”
- the current frontier is “can the model reason over longitudinal concept evidence?”

### 2. Intermediate states are the real difficulty

Single-task sepsis:

- `infection_suspect` recall: `0.1014`

Multitask sepsis:

- `infection_suspect` recall: `0.2324`

Multitask AKI:

- `suspect_aki` recall: `0.6074`

Multitask respiratory:

- `high_flow_or_noninvasive_support` recall: `0.8667`

Interpretation:

- The harder the task depends on a meaningful intermediate surveillance state, the worse the baseline performs.
- Sepsis is hardest because the intermediate state is not a direct thresholded readout from one tool.
- AKI is better because the intermediate state tracks one concept signal directly.
- Respiratory support is easiest because the label is almost explicit in the tool output.

### 3. Single-task sepsis is high-recall and over-alerting

Single-task sepsis:

- false-positive trajectories: 13
- missed positive trajectories: 0
- early alert rate: `0.3673`

Interpretation:

- the agent behaves like a safety-first detector
- it would be clinically noisy
- it is useful as a high-recall baseline, but not as a calibration baseline

### 4. Multitask sepsis becomes more conservative, not more precise

Compared with the single-task sepsis baseline, the multitask sepsis head:

- predicts `keep_monitoring` much more often
- misses more infection and alert transitions
- still does not model `infection_suspect` well

Interpretation:

- multitasking does not just reduce sepsis performance by adding noise
- it appears to push the agent toward conservative under-escalation on the hardest task

### 5. The task family has three different reasoning burdens

From easiest to hardest for this baseline:

1. respiratory support
2. AKI
3. sepsis

Why:

- respiratory support: near-direct tool-to-label mapping
- AKI: one-tool thresholding with a meaningful but manageable intermediate stage
- sepsis: cross-tool integration plus a fragile intermediate state that is not well captured by simple thresholding

## Error Archetypes

### Sepsis archetype A: early alert because infection is visible and SOFA is already high

Example:

- stay `30135840` in the single-task run
- `t=0`
- infection already visible before ICU
- SOFA already elevated
- ground truth: `infection_suspect`
- prediction: `trigger_sepsis_alert`

This is a clinically understandable mistake, but it collapses the intended surveillance staging.

### Sepsis archetype B: suppressing infection suspicion when SOFA is low

Example:

- stay `30246991` in the single-task run
- suspected infection visible from early checkpoints
- SOFA remains 1
- ground truth stays in `infection_suspect`
- prediction stays `keep_monitoring`

This suggests the baseline is using organ dysfunction as a gate for infection suspicion rather than as a gate for sepsis alert only.

### AKI archetype: conservative under-escalation

Typical pattern:

- stage 1 seen -> model sometimes remains `keep_monitoring`
- stage 2/3 seen -> model sometimes stays at `suspect_aki`

This is a mild timing calibration issue, not a breakdown of task understanding.

### Respiratory archetype: occasional undercall from invasive to lower support

Typical pattern:

- `invasive_vent_required -> room_air_or_low_support` or
- `invasive_vent_required -> high_flow_or_noninvasive_support`

These are rare.
The main story for respiratory is strong alignment between tool output and decision.

## Practical Insights For The Baseline

1. The current benchmark is successfully distinguishing “tool use” from “longitudinal reasoning.”
   The agents can use tools.
   The residual challenge is reasoning over staged escalation.

2. Sepsis is the highest-value task for future prompt and policy work.
   It is the clearest place where the intermediate state matters and the baseline fails.

3. AKI is a good calibration task.
   Improvements here should mostly reflect better threshold/timing behavior rather than major tool-use issues.

4. Respiratory support is a good protocol sanity-check, but not the strongest reasoning stress test.

5. A stronger future baseline may need explicit state-machine prompting.
   Right now the sepsis behavior looks closer to:
   “normal vs alert”
   than to a true:
   “normal -> suspicion -> alert”
   surveillance policy.

## Recommendations

### Prompting and policy

1. Add explicit state-transition guidance for sepsis.
   The agent should be told that infection suspicion is a valid final state even when SOFA is still low.

2. Add targeted few-shot examples for:
   - infection visible + low SOFA -> `infection_suspect`
   - infection visible + high SOFA but GT not yet alert -> still `infection_suspect` when appropriate

3. Consider task-specific decision heads after tool gathering instead of one shared free-form reasoning pass.
   The current tool protocol is stable enough that post-tool decision logic is now the main frontier.

### Evaluation

4. Track intermediate-state recall as a first-class metric.
   Overall step accuracy hides the most important weakness.

5. For sepsis, report both:
   - alert recall
   - infection-suspicion recall

Those two numbers capture the baseline’s real calibration tradeoff much better than accuracy alone.

## Bottom Line

The baseline agents are now real longitudinal tool users, not formatting failures.

That is a meaningful milestone.

The next challenge is not getting the model to call tools.
It is getting the model to behave like a staged monitor instead of a coarse abnormality detector.

The strongest baseline pattern is:

- respiratory support is almost solved
- AKI is mostly solved with conservative timing errors
- sepsis still needs genuine stateful longitudinal reasoning

That makes sepsis the most valuable task for future agent improvement, and makes the current benchmark family useful because the three tasks expose different layers of capability rather than all testing the same thing.
