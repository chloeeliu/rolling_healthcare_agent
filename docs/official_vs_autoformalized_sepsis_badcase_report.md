# Official vs Autoformalized Sepsis Bad-Case Report

## Scope

This report compares bad cases from two saved single-sepsis runs:

- official: [/Users/chloe/Documents/New project/result/sepsis_toolbox_history_official_qwen3_30b](/Users/chloe/Documents/New%20project/result/sepsis_toolbox_history_official_qwen3_30b)
- autoformalized v2: [/Users/chloe/Documents/New project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2](/Users/chloe/Documents/New%20project/result/sepsis_toolbox_history_autoformalized_qwen3_30b_v2)

It is intended as a companion to:

- [/Users/chloe/Documents/New project/docs/sepsis_autoformalized_qwen3_30b_v2_badcase_report.md](/Users/chloe/Documents/New%20project/docs/sepsis_autoformalized_qwen3_30b_v2_badcase_report.md)

The goal is to compare failure structure, not just aggregate accuracy. The key question is:

- when these two systems fail, do they fail for the same reason?

The answer is clearly no.

## Executive Summary

The official backend is better not only because it has higher accuracy. It fails in a fundamentally different way.

### Official bad cases

Official is mostly a **sticky continuation** system:

- it often makes an early state commitment
- then carries that state forward with few or no further tool calls
- so many of its errors are persistence errors rather than tool-interpretation errors

### Autoformalized bad cases

Autoformalized v2 is mostly a **high-activity but unstable interpretation** system:

- it uses tools on almost every step
- most wrong steps still contain a tool call
- some tool outputs are internally inconsistent
- and the model sometimes fails even after seeing clearly positive SOFA evidence

So the benchmark-relevant conclusion is:

- official is quieter and more stable, but can become stale
- autoformalized is more active, but the extra activity is not reliably converted into better step decisions

## 1. High-Level Comparison

| Metric | Official | Autoformalized v2 |
|---|---:|---:|
| Step accuracy | `0.6743` | `0.5657` |
| Perfect trajectories | `25 / 50` | `13 / 50` |
| Wrong steps | `114 / 350` | `152 / 350` |
| Avg errors / trajectory | `2.28` | `3.04` |
| Avg tools / trajectory | `4.00` | `6.82` |

### Trajectory-level prevalence

| Failure Type | Official | Autoformalized v2 |
|---|---:|---:|
| Any missed-alert trajectory | `16 / 50` | `20 / 50` |
| Any false-alert trajectory | `4 / 50` | `9 / 50` |
| Any false-infection trajectory | `9 / 50` | `15 / 50` |
| Any missed-infection trajectory | `0 / 50` | `18 / 50` |
| Infection-tool inconsistency trajectory | `0 / 50` | `21 / 50` |

The missing line in official is especially important:

- official has no infection-tool inconsistency pattern at all
- autoformalized v2 has it in `42%` of trajectories

## 2. The Biggest Structural Difference: What Happens Around Errors

### Official: errors mostly happen without a tool call

From the saved official rollouts:

- wrong steps with tool call: `20`
- wrong steps without tool call: `94`

That means `82.5%` of official wrong steps happen when the model is simply continuing a previous state.

Error breakdown:

| Error Type | Errors | With Tool | Without Tool |
|---|---:|---:|---:|
| `keep_monitoring -> infection_suspect` | `39` | `12` | `27` |
| `keep_monitoring -> trigger_sepsis_alert` | `19` | `4` | `15` |
| `trigger_sepsis_alert -> infection_suspect` | `56` | `4` | `52` |

### Autoformalized v2: errors mostly happen after a tool call

From the saved autoformalized v2 rollouts:

- wrong steps with tool call: `150`
- wrong steps without tool call: `2`

That means `98.7%` of autoformalized wrong steps happen after a tool interaction on the same step.

### Why this matters

This is the cleanest bad-case distinction between the two backends:

- official’s main weakness is stale or overly conservative state persistence
- autoformalized’s main weakness is unstable decision-making despite active evidence collection

So they do not need the same fix.

## 3. Official Failure Archetype A: Sticky Missed Alert

### Pattern

Official’s most common bad case is:

- ground truth has transitioned to `trigger_sepsis_alert`
- the model stays at `infection_suspect`
- and it often does so without calling `query_sofa` again

This is the largest official confusion bucket:

- `trigger_sepsis_alert -> infection_suspect`: `56` steps

### Representative case

Trajectory:

- `trajectory_id = mimiciv_stay_33979090`
- `stay_id = 33979090`

Observed behavior:

| `t_hour` | GT | Pred | Tools |
|---:|---|---|---|
| `0` | `infection_suspect` | `infection_suspect` | `query_suspicion_of_infection` |
| `4` | `trigger_sepsis_alert` | `infection_suspect` | none |
| `8` | `trigger_sepsis_alert` | `infection_suspect` | none |
| `12` | `trigger_sepsis_alert` | `infection_suspect` | none |
| `16` | `trigger_sepsis_alert` | `infection_suspect` | none |
| `20` | `trigger_sepsis_alert` | `infection_suspect` | none |
| `24` | `trigger_sepsis_alert` | `infection_suspect` | none |

### Interpretation

This is not a backend inconsistency. It is a selective-underquerying failure:

- infection was established
- the model never revisited the unresolved alert question
- so it stayed in the intermediate state far too long

Compared with autoformalized:

- autoformalized often misses alert **after** seeing strong SOFA
- official often misses alert because it **never asks again**

## 4. Official Failure Archetype B: Sticky False Infection

### Pattern

Official also has persistent false `infection_suspect` trajectories:

- `keep_monitoring -> infection_suspect`: `39` steps
- spread across `9` trajectories

The pattern is again sticky rather than noisy:

- infection is established early
- the model keeps `infection_suspect`
- it often makes few or no further tool calls

### Representative case

Trajectory:

- `trajectory_id = mimiciv_stay_33601567`
- `stay_id = 33601567`

Observed behavior:

| `t_hour` | GT | Pred | Tools |
|---:|---|---|---|
| `0` | `keep_monitoring` | `infection_suspect` | `query_suspicion_of_infection` |
| `4` | `keep_monitoring` | `infection_suspect` | none |
| `8` | `keep_monitoring` | `infection_suspect` | none |
| `12` | `keep_monitoring` | `infection_suspect` | none |
| `16` | `keep_monitoring` | `infection_suspect` | none |
| `20` | `keep_monitoring` | `infection_suspect` | none |
| `24` | `keep_monitoring` | `infection_suspect` | none |

### Interpretation

This looks like concept mismatch plus inertia:

- the official suspicion-of-infection concept is positive
- the benchmark still wants `keep_monitoring`
- the model then continues the intermediate state without reassessment

Compared with autoformalized:

- autoformalized has more false-infection trajectories (`15` vs `9`)
- but official’s false-infection bad cases are often **longer and quieter**

## 5. Official Failure Archetype C: Early False Alert Then Persistence

### Pattern

Official has fewer false-alert trajectories than autoformalized:

- official: `4 / 50`
- autoformalized v2: `9 / 50`

But when official does false-alert, it often commits early and then persists.

### Representative case

Trajectory:

- `trajectory_id = mimiciv_stay_31054046`
- `stay_id = 31054046`

Observed behavior:

| `t_hour` | GT | Pred | Tools / Evidence |
|---:|---|---|---|
| `0` | `keep_monitoring` | `infection_suspect` | infection positive |
| `4` | `keep_monitoring` | `trigger_sepsis_alert` | `query_sofa`, `latest_sofa_24hours = 6` |
| `8` | `keep_monitoring` | `trigger_sepsis_alert` | none |
| `12` | `keep_monitoring` | `trigger_sepsis_alert` | none |
| `16` | `keep_monitoring` | `trigger_sepsis_alert` | none |
| `20` | `keep_monitoring` | `trigger_sepsis_alert` | none |
| `24` | `keep_monitoring` | `trigger_sepsis_alert` | none |

### Interpretation

Again, the official pattern is commitment plus carry-forward:

- one early SOFA query
- one early alert decision
- then no reconsideration

Compared with autoformalized:

- autoformalized false alerts usually involve repeated tool use and repeated positive SOFA-like outputs
- official false alerts often involve a single early strong signal and then persistence

## 6. Autoformalized Failure Types That Official Mostly Avoids

There are two major bad-case families in autoformalized v2 that are largely absent in official.

### A. Infection-tool internal inconsistency

Autoformalized v2:

- `54` inconsistent infection outputs
- `21 / 50` trajectories affected

Official:

- no corresponding pattern found

This is a major difference in backend trustworthiness.

### B. Wrong after active tool use

Official:

- only `20 / 114` wrong steps have a tool call

Autoformalized v2:

- `150 / 152` wrong steps have a tool call

This means official is failing mostly by not updating often enough, while autoformalized is failing despite updating frequently.

## 7. Autoformalized Failure Types That Official Still Shares

Not everything is unique to autoformalized. There are shared benchmark-hardness patterns.

### Shared pattern 1: sticky intermediate state

Both backends can overuse `infection_suspect` as a resting state:

- official: `trigger_sepsis_alert -> infection_suspect` is the largest error bucket
- autoformalized: `trigger_sepsis_alert -> infection_suspect` is also large

But the mechanisms differ:

- official usually gets stuck there without new evidence
- autoformalized can stay there even after strong positive SOFA

### Shared pattern 2: false infection suspicion under benchmark semantics

Both backends produce trajectories where infection evidence is clinically plausible but benchmark labels still want `keep_monitoring`.

That suggests some error budget comes from:

- label-concept mismatch
- not just backend quality

## 8. What This Means For Benchmark Interpretation

This comparison sharpens the benchmark story considerably.

### Official errors mean

- the benchmark is hard because the agent must know when to re-query
- history can become stale
- tool efficiency pressure can create under-updating

### Autoformalized errors mean

- the benchmark is also hard because active evidence collection is not enough
- backend outputs must be internally coherent
- the model must correctly integrate evidence once it has it

So the same benchmark is exposing two different stress points:

1. **decision persistence under sparse querying** for official
2. **decision instability under dense querying** for autoformalized

That is a valuable benchmark property, not a bug in the evaluation.

## 9. Most Valuable Conclusions

1. Official is more accurate partly because it is more stable and internally coherent.
2. Official’s main weakness is stale continuation, not contradictory tool outputs.
3. Autoformalized’s extra tool usage does not reliably buy better decisions.
4. The infection-tool inconsistency in autoformalized is a backend defect that does not appear in official.
5. The shared `infection_suspect` stickiness across both backends suggests a genuine benchmark difficulty around the intermediate sepsis state.
6. If the goal is to improve autoformalized fairly, the first target should not be "make it call more tools." It already does. The first targets should be:
   - infection-tool coherence
   - clearer alert escalation after positive SOFA
   - better alignment between backend concepts and benchmark labels
