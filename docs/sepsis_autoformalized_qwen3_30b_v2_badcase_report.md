# Sepsis Autoformalized Qwen3-30B v2 Bad-Case Report

## Scope

This report analyzes bad cases from:

- result folder: [/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2](/Users/chloe/Documents/New%20project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2)
- evaluation summary: [/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2/eval.json](/Users/chloe/Documents/New%20project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2/eval.json)
- rollout traces: [/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2/rollouts.json](/Users/chloe/Documents/New%20project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2/rollouts.json)

The goal is not just to list failures. The goal is to separate:

- benchmark difficulty
- model decision failures
- autoformalized tool-layer inconsistencies
- concept mismatch between the autoformalized backend and the benchmark labels

## Executive Summary

This run is not primarily failing because the agent skipped tools. It is failing after tool use.

The strongest high-level findings are:

- step accuracy is only `0.5657`, which means `152 / 350` step decisions are wrong
- only `13 / 50` trajectories are perfect
- the agent uses almost one tool per step on average: `6.82` tools per trajectory over `7` steps
- `150 / 152` wrong steps still had a tool call on that same step

So the dominant issue is not lack of evidence collection. It is what happens after evidence is collected.

The bad cases cluster into four recurring archetypes:

1. infection tool internal inconsistency
2. missed alert despite strong SOFA evidence
3. persistent false `infection_suspect`
4. false alert from high SOFA plus autoformalized infection evidence, even when the benchmark label remains `keep_monitoring`

The most important structural finding is that the infection tool itself is sometimes internally inconsistent:

- `54` step-level tool outputs contain evidence and/or a non-null `first_visible_suspected_infection_hour`
- but still report `has_suspected_infection = false`
- this affects `21 / 50` trajectories

That means some of the worst missed-alert cases are not purely prompt problems. The backend is giving the model contradictory signals.

## 1. Global Error Structure

### Overall performance context

From `eval.json`:

- step accuracy: `0.5657`
- macro F1: `0.4897`
- alert missed rate: `0.06`
- infection missed rate: `0.08`
- avg tool calls per step: `0.9743`
- repeated tool call rate: `0.7537`
- repeated infection call after positive: `0.1195`

From `rollouts.json`:

- total trajectories: `50`
- total steps: `350`
- average errors per trajectory: `3.04`
- average tools per trajectory: `6.82`
- perfect trajectories: `13 / 50`

### Step-level confusion breakdown

These are the dominant wrong transitions in the saved rollouts:

| Ground Truth | Prediction | Count |
|---|---:|---:|
| `keep_monitoring` | `infection_suspect` | `52` |
| `trigger_sepsis_alert` | `infection_suspect` | `31` |
| `keep_monitoring` | `trigger_sepsis_alert` | `26` |
| `infection_suspect` | `keep_monitoring` | `21` |
| `trigger_sepsis_alert` | `keep_monitoring` | `20` |
| `infection_suspect` | `trigger_sepsis_alert` | `2` |

This is a very informative pattern:

- the biggest single problem is false early infection suspicion
- the second biggest problem is failure to escalate from infection to alert
- the third biggest problem is false alerting from a positive SOFA-like state

### Almost all errors happen after tool use

For each wrong transition type, the step almost always includes a tool call:

| Error Type | Errors | With Tool | Without Tool |
|---|---:|---:|---:|
| `keep_monitoring -> infection_suspect` | `52` | `52` | `0` |
| `trigger_sepsis_alert -> infection_suspect` | `31` | `31` | `0` |
| `keep_monitoring -> trigger_sepsis_alert` | `26` | `24` | `2` |
| `infection_suspect -> keep_monitoring` | `21` | `21` | `0` |
| `trigger_sepsis_alert -> keep_monitoring` | `20` | `20` | `0` |
| `infection_suspect -> trigger_sepsis_alert` | `2` | `2` | `0` |

This is why the bad-case story should not be told as "the model needed more tool use." The run already uses tools heavily. The hard part is interpreting their outputs consistently.

## 2. Trajectory-Level Prevalence Of Failure Archetypes

Across the 50 trajectories:

- trajectories with any missed alert behavior: `20`
- trajectories with any false alert behavior: `9`
- trajectories with any false infection-suspect behavior: `15`
- trajectories with any missed infection behavior: `18`
- trajectories where SOFA `>= 2` was observed but the model still did not alert: `11`
- trajectories with infection-tool internal inconsistency: `21`

This means the largest trajectory-level buckets are:

1. missed alert
2. infection-tool inconsistency
3. missed infection
4. false infection

Only `13 / 50` trajectories are fully clean.

## 3. Failure Archetype A: Infection Tool Internal Inconsistency

### What it looks like

The infection tool sometimes returns:

- evidence present
- `first_visible_suspected_infection_hour` present
- but `has_suspected_infection = false`

This happened in `54` step-level tool outputs across `21` trajectories.

That is a backend-level coherence problem, not just a model reasoning problem.

### Representative case

Trajectory:

- `trajectory_id = mimiciv_stay_34428643`
- `stay_id = 34428643`

Observed steps:

| `t_hour` | GT | Pred | Tool signal |
|---:|---|---|---|
| `4` | `trigger_sepsis_alert` | `keep_monitoring` | `has_suspected_infection = false`, `first_visible_suspected_infection_hour = 2.32`, `evidence_n = 2` |
| `8` | `trigger_sepsis_alert` | `keep_monitoring` | `has_suspected_infection = false`, `first_visible_suspected_infection_hour = 2.32`, `evidence_n = 2` |
| `12` | `trigger_sepsis_alert` | `keep_monitoring` | `has_suspected_infection = false`, `first_visible_suspected_infection_hour = 2.32`, `evidence_n = 3` |

This is not a subtle case. The tool exposes positive-looking infection evidence but still denies infection at the boolean level. A model that follows the boolean will miss the alert. A model that follows the reconstructed evidence may contradict the tool contract.

### Why it matters

This failure pattern directly explains part of:

- `trigger_sepsis_alert -> keep_monitoring`
- `infection_suspect -> keep_monitoring`

Error-condition breakdown supports that:

- for `trigger_sepsis_alert -> keep_monitoring`, `19 / 20` wrong steps had infection-tool inconsistency
- for `infection_suspect -> keep_monitoring`, `6 / 21` wrong steps had infection-tool inconsistency, and `20 / 21` had infection reported negative

### Likely interpretation

This looks like an adapter-level mismatch in the autoformalized infection tool:

- evidence and first-visible time are reconstructed from one path
- boolean infection state comes from another path

The result is an output object that is not self-consistent.

## 4. Failure Archetype B: Missed Alert Despite Strong SOFA Evidence

### What it looks like

The model sometimes observes clearly positive SOFA output and still stays at `infection_suspect`.

This happened on:

- `17` step-level tool outputs where `latest_sofa_24hours >= 2`
- but the prediction was not `trigger_sepsis_alert`
- across `11` trajectories

### Representative case

Trajectory:

- `trajectory_id = mimiciv_stay_33979090`
- `stay_id = 33979090`

Observed steps:

| `t_hour` | GT | Pred | SOFA signal |
|---:|---|---|---|
| `16` | `trigger_sepsis_alert` | `infection_suspect` | `latest_sofa_24hours = 12` |
| `20` | `trigger_sepsis_alert` | `infection_suspect` | `latest_sofa_24hours = 15` |

Component detail at `t = 20`:

- respiration `4`
- coagulation `2`
- liver `3`
- cardiovascular `1`
- CNS `4`
- renal `1`

This is not a borderline SOFA case. The model saw a massively positive organ-dysfunction signal and still did not stay in `trigger_sepsis_alert`.

### Why it matters

This is a clean decision-policy failure. The tool output is already strongly positive. The model is not missing the alert because evidence was absent.

Error-condition breakdown supports that:

- `trigger_sepsis_alert -> infection_suspect` has `24` steps where infection was positive
- and `7` steps where SOFA `>= 2` was explicitly visible

### Likely interpretation

The model appears overly sticky on the intermediate state `infection_suspect`, even after receiving decisive SOFA evidence. This is a prompt/policy problem, not just a backend problem.

## 5. Failure Archetype C: Persistent False `infection_suspect`

### What it looks like

Once the model sees infection evidence, it sometimes remains in `infection_suspect` for many checkpoints, even when the benchmark ground truth stays at `keep_monitoring`.

This is the largest single confusion bucket:

- `52` wrong steps of `keep_monitoring -> infection_suspect`
- spread across `15` trajectories

### Representative case

Trajectory:

- `trajectory_id = mimiciv_stay_33601567`
- `stay_id = 33601567`

Observed steps:

| `t_hour` | GT | Pred | Tool signal |
|---:|---|---|---|
| `4` | `keep_monitoring` | `infection_suspect` | infection tool says `has_suspected_infection = true`, `first_visible_suspected_infection_hour = 1.5` |
| `8` | `keep_monitoring` | `infection_suspect` | `latest_sofa_24hours = 0` |
| `16` | `keep_monitoring` | `infection_suspect` | `latest_sofa_24hours = 1` |
| `24` | `keep_monitoring` | `infection_suspect` | `latest_sofa_24hours = 1` |

This is a good example of a "sticky intermediate state." The model is not escalating, but it also is not returning to `keep_monitoring`.

### Why it matters

This pattern likely reflects a concept mismatch between:

- the benchmark label semantics
- and the broader infection suspicion heuristic used by the autoformalized backend

Error-condition breakdown supports that:

- for `keep_monitoring -> infection_suspect`, `25 / 52` wrong steps had infection explicitly positive
- and `20 / 52` had SOFA `< 2`

So in many of these steps, the model is behaving coherently relative to its tools:

- infection positive
- no alert-level organ dysfunction
- therefore `infection_suspect`

But the benchmark still wants `keep_monitoring`.

### Likely interpretation

This is not pure hallucination. It is a mismatch between:

- what the autoformalized infection concept thinks is visible infection suspicion
- and what the benchmark labels count as the intermediate positive state

## 6. Failure Archetype D: False Alert From High SOFA

### What it looks like

The model sometimes predicts `trigger_sepsis_alert` while the benchmark still says `keep_monitoring`, usually after seeing clearly positive SOFA output.

This occurred in:

- `26` wrong steps of `keep_monitoring -> trigger_sepsis_alert`
- across `9` trajectories

### Representative case

Trajectory:

- `trajectory_id = mimiciv_stay_31054046`
- `stay_id = 31054046`

Observed steps:

| `t_hour` | GT | Pred | SOFA signal |
|---:|---|---|---|
| `8` | `keep_monitoring` | `trigger_sepsis_alert` | `latest_sofa_24hours = 5` |
| `16` | `keep_monitoring` | `trigger_sepsis_alert` | `latest_sofa_24hours = 5` |
| `24` | `keep_monitoring` | `trigger_sepsis_alert` | `latest_sofa_24hours = 6` |

### Why it matters

This is not evidence-free overcalling. For `keep_monitoring -> trigger_sepsis_alert`:

- `22 / 26` wrong steps had SOFA `>= 2`
- only `2 / 26` wrong steps had infection explicitly positive in the tool outputs captured on that step

So these false alerts mostly happen when the model sees strong organ dysfunction and over-completes the Sepsis-3 rule.

### Likely interpretation

There are two plausible contributors:

1. the model is too eager to combine organ dysfunction with earlier infection evidence
2. the autoformalized SOFA concept may be broader or harsher than the benchmark's intended alert semantics at those checkpoints

This is likely a benchmark-alignment issue, not a random reasoning mistake.

## 7. Root Cause Split

The bad cases are best understood as a mixture of three different problems.

### A. Backend coherence problems

Most important:

- infection tool internal inconsistency

Evidence:

- `54` step-level inconsistent infection outputs
- `21 / 50` trajectories affected

These cases are unfair to interpret as pure model failure.

### B. Model decision-policy problems

Most important:

- the model sometimes sees very high SOFA and still remains at `infection_suspect`

Evidence:

- `17` steps with SOFA `>= 2` but no alert
- example trajectory `mimiciv_stay_33979090` with SOFA `12` and `15`

These cases look like genuine decision failures.

### C. Concept mismatch between backend and benchmark

Most important:

- infection-suspect false positives that are plausible relative to autoformalized evidence
- false alerts driven by strongly positive SOFA-like signals

These are not best framed as "the model is irrational." They are better framed as:

- the autoformalized concept layer is not identical to the benchmark semantics

## 8. Most Valuable Conclusions

1. This run is already tool-heavy. The main weakness is not insufficient tool use.
2. The single most important backend problem is infection-tool internal inconsistency.
3. The single clearest model problem is failure to stay in `trigger_sepsis_alert` after observing strongly positive SOFA.
4. The single most important benchmark-alignment problem is persistent `infection_suspect` where the autoformalized backend seems to believe infection is visible but the benchmark still wants `keep_monitoring`.
5. Because these three failure sources are mixed together, raw step accuracy alone hides the real story. The saved rollouts show that some bad cases are backend defects, some are policy defects, and some are concept mismatches.

## 9. Suggested Follow-Up

If the next goal is to improve this benchmark path without controller curation, the highest-value next checks are:

1. audit the autoformalized infection adapter for boolean/evidence consistency
2. inspect whether the prompt makes `infection_suspect` too sticky after infection becomes visible
3. compare the autoformalized infection and SOFA semantics against the benchmark label construction for the representative bad-case stays above

Those three steps would tell us which portion of the current error budget is actually prompt-fixable, versus backend-fixable, versus label-definition mismatch.
