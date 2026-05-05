# Longitudinal Surveillance Paper-Writing Notes

Date: 2026-05-02

## Purpose

This note distills the main writing recommendations for describing the longitudinal ICU surveillance benchmark and its results in the paper.

The goal is not to redesign the benchmark.
The goal is to present it clearly, defensibly, and with the right separation between:

- benchmark construction
- task difficulty
- model behavior
- autoformalization gains

## Main Recommendation

The longitudinal task should be framed first and foremost as a **current-state ICU surveillance benchmark with heterogeneous temporal semantics**, not merely as a longer multi-step monitoring task.

The key claim is not just:

- models get worse as the horizon becomes longer

The stronger and more accurate claim is:

- models struggle because different disease families require different memory and update rules across time

This is the most distinctive part of the benchmark and should be the center of the writing.

## What The Longitudinal Benchmark Actually Tests

The benchmark does **not** primarily test future prediction.

It tests whether an agent can repeatedly infer the patient's **current surveillance state** at each checkpoint from:

- partial EHR evidence available up to that time
- compact memory from earlier checkpoints
- its own evidence-gathering strategy

This distinction matters.

Good wording:

- current-state surveillance
- rolling monitoring
- state tracking over evolving partial evidence

Less precise wording to avoid:

- forecasting
- future deterioration prediction
- next-step outcome prediction

The benchmark is hard because the agent must maintain a clinically consistent latent state while the observable evidence changes and decays.

## Core Longitudinal Difficulty

The most important writing point is that this benchmark does **not** use a single temporal rule.

Different disease families follow different checkpoint semantics:

- persistent episode states
  - infection
  - sepsis
- cumulative worst-so-far states
  - AKI stages
- active-interval states
  - ventilation
  - vasoactive support
  - CRRT
- recent-measurement states with TTL
  - oliguria
  - PF ratio
  - GCS
  - lactate
  - pH
  - INR
- recomputed composite states
  - septic shock
  - shock with hypoperfusion

This means the agent cannot use a single cheap heuristic such as:

- remember the latest value only
- remember the running maximum only
- keep all positives permanently active

All three strategies fail on different families.

This is the main reason the benchmark is a real longitudinal reasoning task rather than repeated static classification.

## Benchmark Section vs Results Section

The paper should separate **what the benchmark is** from **what the models do on it**.

### Put in Benchmark / Task Description

- source cohort size
- released benchmark size
- checkpoint cadence
- decision families and latent decision count
- coverage and overlap statistics
- soft-balanced subset construction
- temporal semantics by disease family
- memory and agent interaction contract

### Put in Results

- checkpoint vs trajectory performance gap
- action prediction vs disease-state tracking gap
- frontier vs open-weight differences
- effect of autoformalized functions
- failure interpretation

If the benchmark section already explains temporal heterogeneity clearly, the results section can then say:

- performance remains low because the agent must respect persistent, decaying, active, and recomputed states simultaneously

That is much stronger than restating benchmark construction details in the results section.

## Recommended Longitudinal Narrative

The longitudinal write-up should make the following four claims in order.

### 1. Strong checkpoint performance does not imply strong trajectory performance

This is the cleanest empirical hook.

For example:

- some frontier models reach moderate checkpoint-level action accuracy
- but trajectory accuracy remains much lower

Interpretation:

- many failures are not isolated local mistakes
- they are failures to maintain a consistent evolving clinical state across time

### 2. Disease tracking is harder than global action prediction

The paper should explicitly explain the gap between:

- global-action accuracy
- family-level F1 for `suspected_conditions`
- family-level F1 for `alerts`

Interpretation:

- deciding whether to escalate can be easier than reconstructing the full multi-organ surveillance picture

This is clinically meaningful:

- a model may detect that "something is wrong"
- but still fail to identify the right active families and alert-level states

### 3. Mixed temporal semantics are the defining source of difficulty

This should be the conceptual centerpiece.

Recommended contrast:

- persistent families must stay active after onset
- AKI must expose the worst stage reached so far
- support therapies must disappear when the intervention no longer overlaps the checkpoint
- recent physiologic abnormalities must expire when their evidence becomes stale
- composite states must be recomputed from changing component evidence

The benchmark therefore penalizes both:

- agents that over-persist stale signals
- agents that forget states that should remain active

### 4. Autoformalized functions improve longitudinal consistency, not just local retrieval

The effect of the library should be described carefully.

Safe phrasing:

- the library gives the agent compact clinically aligned abstractions for important surveillance states
- this reduces the need to rediscover evidence pathways from the raw schema at every checkpoint
- the benefit appears primarily in improved longitudinal consistency and lower token cost

Avoid overstating:

- "the functions encode the correct temporal semantics"

That claim is too strong because the benchmark ground truth comes from the derived-SQL layer, not directly from the autoformalized runtime.

## Recommended Metric Framing

The paper should define the surveillance metrics explicitly before interpreting them.

At minimum, define:

- checkpoint-level global-action accuracy
- checkpoint-level priority accuracy
- family-level F1 for `suspected_conditions`
- family-level F1 for `alerts`
- trajectory accuracy

Recommended interpretation:

- `global_action` asks whether the top-level monitoring vs escalation decision is correct
- `priority` asks whether the urgency level is appropriate
- `suspected_conditions` and `alerts` ask whether the agent recovers the correct disease-family picture
- `trajectory accuracy` asks whether the agent remains correct across the full checkpoint sequence of a stay

Important note:

- if `trajectory accuracy` means exact correctness over all checkpoints of a stay, say that explicitly
- if it uses a different aggregation rule, define it precisely

Without this sentence, readers may over- or under-interpret the reported number.

## What To Emphasize In The Figures

### Coverage / overlap figure

The purpose of the coverage figure is:

- to show that the benchmark covers most ICU stays
- and that many stays activate multiple surveillance families by 24h

This figure supports the claim that the task is broad and multi-problem rather than centered on a single disease.

### Temporal-semantics figure

This figure is conceptually central.

Its role is to show that:

- different disease families update differently over time
- the task is not a once-positive-forever benchmark
- the longitudinal challenge comes from multiple incompatible temporal update rules

This figure should be referenced directly in the results discussion, not only in the benchmark section.

### Result figure

The result figure should communicate three ideas:

- checkpoint performance remains far above trajectory performance
- disease-family tracking is harder than top-level action prediction
- autoformalized functions improve longitudinal performance and token efficiency

The figure caption should describe those ideas semantically, not by visual placement alone.

Prefer:

- "Top: trajectory-level comparison ..."
- "Bottom left: checkpoint accuracy over time ..."
- "Bottom right: summary surveillance metrics ..."

over:

- "Bottom Left"
- "Top"
- "Right"

unless the layout is extremely stable and visually obvious.

## Recommended Result Wording

Below is the intended logic for the final longitudinal results subsection.

### Claim A: agents struggle to maintain correct state over time

Suggested content:

- even strong models show a large gap between checkpoint correctness and trajectory correctness
- this indicates that the main difficulty is temporal consistency, not isolated local prediction

### Claim B: the full disease picture is harder than the top-level action

Suggested content:

- global-action accuracy is consistently higher than family-level `suspected_conditions` and `alerts` F1
- this means models often detect that the patient is concerning without recovering the right structured multi-family explanation

### Claim C: the benchmark is hard because of heterogeneous temporal semantics

Suggested content:

- persistent, cumulative, active-interval, TTL, and composite states coexist in the same stay
- therefore both stale-memory and forgetful-memory strategies fail

### Claim D: autoformalization improves consistency and efficiency

Suggested content:

- pre-verified functions reduce repeated schema rediscovery
- they help the agent retrieve more relevant evidence with lower token cost
- gains appear especially in trajectory-level behavior, where compounding step errors matter most

## Phrases To Prefer

- longitudinal ICU surveillance
- current-state monitoring
- heterogeneous temporal semantics
- multi-family surveillance state
- persistent vs decaying vs recomputed states
- trajectory-level consistency
- partial evidence at each checkpoint
- clinically consistent state tracking

## Phrases To Avoid Or Soften

- once-positive-forever benchmark
  - acceptable only when explicitly contrasting against our design
- functions encode the correct temporal semantics
  - too strong; use "clinically aligned abstractions" instead
- the model predicts the patient's future condition
  - inaccurate for this task
- disease classification over time
  - too weak; this is a surveillance-state task

## Suggested Revision Targets In The Current Draft

### 1. Add one sentence defining the metrics

Readers should not need to infer what:

- `Acc.`
- `Prio.`
- `Susp. F1`
- `Alerts F1`
- `Traj. Acc.`

mean from the table alone.

### 2. State explicitly that this is a current-state benchmark

This should appear near the start of the longitudinal results subsection.

### 3. Emphasize that mixed temporal semantics are the distinctive challenge

This point should be stated before discussing the autoformalization gains.

### 4. Soften any causal claim about the library being "correct"

Prefer:

- compact clinically aligned abstractions
- reduced schema rediscovery
- improved consistency under repeated monitoring

### 5. Keep benchmark construction details mostly in the benchmark section

The results section should reference the task design, not re-explain it at full length.

## Recommended One-Paragraph Summary

If a short summary is needed, this is the core message:

The longitudinal surveillance benchmark is difficult not simply because it is long, but because it requires the agent to maintain a clinically consistent multi-family ICU state under heterogeneous temporal rules. Some states persist once triggered, others expose the worst severity reached so far, others are active only while an intervention overlaps the checkpoint, and still others expire when recent evidence becomes stale. This makes trajectory-level correctness substantially harder than per-checkpoint action prediction. Autoformalized functions appear to help primarily by reducing repeated schema rediscovery and improving longitudinal consistency, rather than by solving the task through a single static disease heuristic.
