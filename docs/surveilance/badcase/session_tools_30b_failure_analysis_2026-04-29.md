# Session-Tools 30B Failure Analysis

Date: 2026-04-29

## Scope

This note analyzes the run artifacts under:

- [result/surveillance_30b](/Users/chloe/Documents/New project/result/surveillance_30b)

Run configuration of interest:

- `--tool-backend session_tools`
- `--task-mode surveillance`
- `--protocol rolling_with_history`
- `--agent qwen`

Artifacts inspected:

- [eval.json](/Users/chloe/Documents/New project/result/surveillance_30b/eval.json)
- [trajectories.jsonl](/Users/chloe/Documents/New project/result/surveillance_30b/trajectories.jsonl)
- [events.jsonl](/Users/chloe/Documents/New project/result/surveillance_30b/events.jsonl)

## High-Level Verdict

The run was a **technical success** but a **benchmark failure**.

Technical success means:

- the pipeline completed end-to-end
- the agent returned valid structured surveillance JSON
- the separate checkpoint summarizer ran at every step
- the `session_tools` runtime did not crash

Benchmark failure means:

- the model did not actually use the tool-first retrieval interface
- it produced unsupported clinical judgments without gathering evidence
- it collapsed to an almost-always-negative surveillance policy

## Core Quantitative Signals

From [eval.json](/Users/chloe/Documents/New project/result/surveillance_30b/eval.json):

- `10` trajectories
- `130` checkpoint steps
- `130` agent calls
- `0` tool calls
- `260` total model calls

Step-level metrics:

- `global_action_accuracy = 0.2308`
- `priority_accuracy = 0.2077`
- `suspected_conditions_exact_match = 0.0615`
- `alerts_exact_match = 0.2308`
- `suspected_conditions_macro_f1 = 0.0`
- `alerts_macro_f1 = 0.0`

Timing metrics:

- `false_early_alert_trajectories = 0`
- `missed_alert_trajectories = 10`

Interpretation:

- the model avoided false positives almost entirely
- but only because it almost never predicted any positive surveillance state at all
- every trajectory with a true alert was missed

## The Dominant Failure Mode

The dominant failure mode is:

- **premature finalization without evidence retrieval**

In this run:

- the agent never called `search_guidelines`
- never called `search_functions`
- never called `get_function_info`
- never called `load_function`
- never called `call_function`

Instead, it directly emitted a final decision at every checkpoint.

This means the session-tools benchmark surface was available, but effectively unused.

## What The Model Actually Predicted

Across all `130` steps:

- predicted `global_action`: always `continue_monitoring`
- predicted `priority`: always `low`
- predicted `suspected_conditions`: always `[]`
- predicted `alerts`: always `[]`

Ground truth was substantially denser:

- GT `global_action = escalate` on `100 / 130` steps
- GT labels included:
  - `infection_suspected`: `89`
  - `sepsis_alert`: `66`
  - `resp_support_invasive_vent`: `62`
  - `aki_stage1`: `35`
  - `aki_stage2`: `30`
  - `coagulopathy_inr_ge_1_5`: `28`
  - `hyperlactatemia_ge_2`: `25`
  - `vasoactive_support_any`: `24`

So this was not a near-miss around one narrow label family.
It was a broad collapse to an all-negative policy.

## Qualitative Failure Pattern

The model repeatedly claimed normality without evidence.

Common rationale patterns included statements such as:

- “All monitored parameters remain within normal ranges”
- “No evidence of infection, renal injury, respiratory failure...”
- “No abnormalities or concerning trends have been detected”

These statements are clinically strong, but in this run they were unsupported because:

- no retrieval tools were called
- no autoformalized functions were inspected or executed
- no patient-state evidence was gathered

So the model was not simply under-calling alerts.
It was **hallucinating reassurance**.

## Example Bad Case

Trajectory:

- `mimiciv_stay_30004144`

Observed pattern:

- by `t=12`, ground truth already has `sepsis_alert`
- by `t=24`, ground truth has `sepsis_alert` and `aki_stage2`
- by `t=28`, ground truth has `sepsis_alert`, `aki_stage2`, and `resp_support_invasive_vent`

Predicted pattern:

- `continue_monitoring`
- empty `suspected_conditions`
- empty `alerts`
- `low` priority
- zero tool calls

This is a strong representative bad case because multiple families were active and the trajectory still stayed fully negative.

## Why The Failure Happened

### 1. The prompt allowed premature commitment

The model was told to:

- default to a final decision when current summaries and evidence seemed sufficient

In practice, that gave the model too much freedom to decide that no tool use was necessary.

### 2. The old output contract included `recommended_next_tools`

In this run, the model often used that field as a substitute for acting.

Instead of calling tools now, it would write suggestions like:

- `search_functions`
- `search_guidelines`
- `call_function`

This creates a lazy pattern:

- recommend retrieval later
- but do not retrieve now

### 3. Summary memory reinforced unsupported negative beliefs

The summarizer then wrote short memories such as:

- “Continuing monitoring with no active alerts”
- “Continuing monitoring with no abnormalities detected”

Those summaries became rolling history for the next checkpoint.

So an unsupported negative decision at one step was converted into memory that biased later steps in the same negative direction.

### 4. The model seems biased toward “safe inactivity”

This run shows a clear bias toward:

- low priority
- no conditions
- no alerts
- no escalation

This avoided false-early-alert penalties, but at the cost of missing all clinically meaningful positives.

## Secondary Artifact Issue

The event log is slightly noisier than the rollout output.

In [events.jsonl](/Users/chloe/Documents/New project/result/surveillance_30b/events.jsonl):

- `trajectory_start = 11`
- `trajectory_complete = 10`

The extra `trajectory_start` appears to be a duplicate start event for:

- `mimiciv_stay_30004144`

This likely means the event log file was appended rather than freshly truncated before the run.

This does **not** change the main benchmark diagnosis, but it means:

- [trajectories.jsonl](/Users/chloe/Documents/New project/result/surveillance_30b/trajectories.jsonl) and [eval.json](/Users/chloe/Documents/New project/result/surveillance_30b/eval.json) should be treated as the cleaner primary analysis sources

## Main Conclusion

The main conclusion is:

- the `session_tools` backend itself appears runnable
- but this prompt/behavior combination does **not** yet test the intended tool-using surveillance capability

The model is currently taking a shortcut:

- skip retrieval
- assume stability
- output a negative decision
- let summary memory preserve that unsupported negative state

## Improvement Direction

For benchmark integrity, the right direction is **not** to add an extra scripted clinical helper layer.

Instead, the right direction is to improve the benchmark-facing interaction contract.

The highest-value change is:

- remove `recommended_next_tools` from the surveillance decision schema

Why:

- it removes an easy “I will do this later” outlet
- it forces a cleaner separation between:
  - doing retrieval now
  - versus deciding now

That keeps the benchmark focused on actual agent capability rather than deferred intentions.

Additional benchmark-facing improvement ideas that remain consistent with the no-extra-script principle:

- tighten the prompt to make it harder to claim normality without evidence
- keep summary memory short and factual, so unsupported reassurance is not amplified
- compare future reruns against this failure pattern to see whether tool use becomes nonzero and family-level recall improves
