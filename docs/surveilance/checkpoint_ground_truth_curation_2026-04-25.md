# General ICU Surveillance Checkpoint Ground-Truth Curation

Date: 2026-04-25

## Purpose

This document defines the next dataset-build step after cohort finalization:

- checkpoint-level ground truth
- the latent decision registry
- generalized `suspect` vs `alert` mapping
- and the recommended `~2,000`-stay benchmark package

It builds on:

- [general_icu_surveillance_dataset_design_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/general_icu_surveillance_dataset_design_2026-04-25.md)
- [surveillance_dataset_cohort_audit_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/surveillance_dataset_cohort_audit_2026-04-25.md)

The first concrete build based on this design is documented in:

- [checkpoint_ground_truth_build_report_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/checkpoint_ground_truth_build_report_2026-04-25.md)

## Core Recommendation

Build ground truth in two layers:

1. a latent checkpoint decision layer with `25` canonical ICU surveillance decisions
2. a benchmark response layer that maps those decisions into:
   - `suspected_conditions`
   - `alerts`
   - `global_action`
   - `priority`

This gives us:

- enough granularity for a hard ICU benchmark
- a generalized and stable scoring interface
- and a way to keep the model output simple even when the internal label space is larger

## Recommended Benchmark Size

Use a benchmark package of about `2,000` ICU stays.

Because the cohort already requires `LOS >= 48h`, this corresponds to roughly:

- `13` checkpoints per stay (`0, 4, ..., 48`)
- about `26,000` checkpoint rows

That is large enough for:

- meaningful trajectory evaluation
- many-task coverage
- unit and onset heterogeneity

but still small enough to:

- run agent evaluation at reasonable cost
- inspect failure modes
- and avoid an excessively prevalence-skewed benchmark

## Which Splits to Use

Keep the full `46,337`-stay cohort as the label-build universe, but create the public benchmark package from the held-out side only:

- benchmark `dev`: `400` stays
- benchmark `test`: `1,600` stays

Recommendation:

- do not use the original training split for the benchmark package
- keep it available only for ablations, prompt iteration, or internal experiments

This preserves a clean evaluation story.

## Latent Decision Registry

The latent decision registry is stored at:

- [checkpoint_decision_registry.csv](/Users/chloe/Documents/New project/dataset/surveilance/checkpoint_decision_registry.csv)

It contains `25` canonical decisions across `8` families:

1. infection
2. sepsis
3. renal
4. respiratory
5. hemodynamic
6. neurologic
7. metabolic
8. coagulation

### Why keep a latent registry

The benchmark prompt should stay simple.
The labels should not.

The latent registry gives us:

- finer task coverage than a small disease-only label set
- exact SQL-level semantics for checkpoint truth
- and a clean way to evaluate both family-level decisions and specific ICU states

## Generalized `suspect` vs `alert`

Use a generalized family-level method.

### `suspect`

A family is in `suspected_conditions` at checkpoint `t` if the highest active decision in that family is a `suspect` decision.

Examples:

- `aki_stage1`
- `oliguria_6h`
- `resp_support_hfnc_or_niv`
- `hyperlactatemia_ge_2`
- `coagulopathy_inr_ge_1_5`

### `alert`

A family is in `alerts` at checkpoint `t` if the highest active decision in that family is an `alert` decision.

Examples:

- `sepsis_alert`
- `septic_shock_alert`
- `aki_stage2`
- `aki_stage3`
- `resp_support_invasive_vent`
- `vasoactive_multi_agent_or_high_intensity`
- `gcs_severe_impairment_le_8`

### Precedence rule

Within each family, only the highest-precedence active decision should define the exposed output state.

Examples:

- if both `aki_stage1` and `aki_stage3` are active, expose renal as alert-level, not both
- if both `resp_support_hfnc_or_niv` and `resp_support_invasive_vent` are active, expose only the invasive state for scoring
- if both `coagulopathy_inr_ge_1_5` and `coagulopathy_inr_ge_2` are active, expose only the alert-level coagulation state

This gives a generalized and deterministic suspect/alert mapping without hand-writing per-disease output rules.

## Four Checkpoint State Types

The most important design choice is that not all ICU states should persist the same way.

We should use four checkpoint state types.

### 1. Persistent episode

Use for diagnoses or syndrome onsets that should remain true for the episode once detected in the `0-48h` benchmark window.

Applies to:

- `infection_suspected`
- `infection_confirmed_or_strongly_supported`
- `sepsis_alert`

Checkpoint rule:

- active at checkpoint `t` if first qualifying onset time is `<= t`

### 2. Cumulative max stage

Use for injury-stage concepts where the benchmark should reflect the worst stage attained so far, not only the current row value.

Applies to:

- `aki_stage1`
- `aki_stage2`
- `aki_stage3`

Checkpoint rule:

- compute the maximum KDIGO stage observed up to checkpoint `t`
- activate the highest attained stage only

This is better than instantaneous staging because the agent should remember that injury has occurred.

### 3. Active interval

Use for support therapies that are active only while the support overlaps the checkpoint.

Applies to:

- `resp_support_hfnc_or_niv`
- `resp_support_invasive_vent`
- `vasoactive_support_any`
- `vasoactive_multi_agent_or_high_intensity`
- `crrt_active`

Checkpoint rule:

- active if support start time is `<= t` and end time is `NULL` or `> t`

### 4. Recent-measurement / rolling-window state

Use for lab/vital-derived states where the decision should reflect the latest available evidence within a limited trailing window.

Applies to:

- `oliguria_6h`
- `severe_oliguria_or_anuria`
- `hypoxemia_pf_lt_200`
- `hypoxemia_pf_lt_100`
- `gcs_moderate_impairment_9_12`
- `gcs_severe_impairment_le_8`
- `hyperlactatemia_ge_2`
- `severe_hyperlactatemia_ge_4`
- `acidemia_ph_lt_7_30`
- `severe_acidemia_ph_le_7_20`
- `coagulopathy_inr_ge_1_5`
- `coagulopathy_inr_ge_2`

Checkpoint rule:

- select the most recent qualifying source row `<= t`
- require it to fall within the task-specific recency TTL
- deactivate if TTL expires and no newer abnormal row appears

Recommended TTLs:

- `6h` for `oliguria_6h`
- `24h` for `severe_oliguria_or_anuria`
- `8h` for GCS
- `12h` for blood-gas-based states
- `24h` for INR-based states

### How to read the paper temporal-semantics figure

The paper version of this section uses a schematic figure to explain that the benchmark does **not** apply one single temporal rule to every label.

Important note:

- this figure is illustrative rather than cohort-averaged
- it is not showing one real patient trajectory
- it is showing the intended checkpoint semantics for each state type

Read the figure from top to bottom.

#### Panel 1: persistent episode

- example shown: `sepsis_alert`
- y-axis states are `off` and `on`
- once the state turns on, it stays on for the rest of the benchmark window

How to interpret it:

- if Sepsis-3 first becomes visible at hour `12`, then checkpoints `12, 16, 20, ..., 48` all remain positive
- later checkpoints do not “forget” that sepsis occurred

This panel represents:

- `infection_suspected`
- `infection_confirmed_or_strongly_supported`
- `sepsis_alert`

#### Panel 2: cumulative max stage

- example shown: AKI stage moving from `0` to `1` to `2` to `3`
- y-axis is ordinal stage, not binary on/off
- once a worse stage is reached, the benchmark keeps the highest stage attained so far

How to interpret it:

- if AKI reaches stage `2` at hour `16`, then checkpoint `20` still exposes stage `2` even if the latest row later looks less severe
- if stage `3` is reached at hour `24`, then all later checkpoints expose stage `3`

This panel represents:

- `aki_stage1`
- `aki_stage2`
- `aki_stage3`

The key idea is:

- AKI is not treated as “current latest creatinine only”
- it is treated as a remembered worst-so-far injury state

#### Panel 3: active interval

- example shown: support turns on, later turns off, and can turn on again
- y-axis states are `off` and `on`
- positivity depends on whether the support interval overlaps the current checkpoint

How to interpret it:

- if invasive ventilation or vasoactive support is active from `12h` to `24h`, then checkpoints inside that interval are positive
- once the support ends, later checkpoints become negative again unless a new support interval begins

This panel represents:

- `resp_support_hfnc_or_niv`
- `resp_support_invasive_vent`
- `vasoactive_support_any`
- `vasoactive_multi_agent_or_high_intensity`
- `crrt_active`

The key idea is:

- support therapies are current treatment states, not permanent once-on labels

#### Panel 4: recent measurement + TTL

- example shown: an abnormal lab or physiologic value turns the state on, but it later expires if no newer supporting evidence arrives
- y-axis states are `off` and `on`
- positivity is based on the most recent relevant measurement within a task-specific trailing window

How to interpret it:

- a lactate abnormality can be active at hour `12`
- if no newer abnormal lactate is seen and the `12h` TTL expires, the state turns off again
- later, a new abnormal measurement can turn it back on

This panel represents:

- `oliguria_6h`
- `severe_oliguria_or_anuria`
- `hypoxemia_pf_lt_200`
- `hypoxemia_pf_lt_100`
- `gcs_moderate_impairment_9_12`
- `gcs_severe_impairment_le_8`
- `hyperlactatemia_ge_2`
- `severe_hyperlactatemia_ge_4`
- `acidemia_ph_lt_7_30`
- `severe_acidemia_ph_le_7_20`
- `coagulopathy_inr_ge_1_5`
- `coagulopathy_inr_ge_2`

The key idea is:

- these are recent physiologic states, not episode-level states
- the benchmark intentionally allows them to appear, expire, and reappear

#### Panel 5: composite current state

- example shown: septic shock becomes positive only when multiple component states are simultaneously active
- y-axis states are `off` and `on`
- the label is recomputed independently at every checkpoint from its components

How to interpret it:

- even if `sepsis_alert` persists, `septic_shock_alert` only stays positive when the support and metabolic components are also active
- if vasoactive support stops or the recent lactate evidence expires, the composite shock label turns off

This panel represents:

- `septic_shock_alert`
- `shock_hypoperfusion_alert`

The key idea is:

- composite heads depend on conjunction across families
- they are neither permanent episode states nor simple single-measurement states

### What this figure is trying to prove

The figure is meant to make three benchmark properties visually obvious:

1. this is a real longitudinal benchmark, not a repeated static QA task
2. different disease families require different temporal reasoning operations
3. the agent must jointly reason about:
   - remembered past events
   - worst-so-far injury
   - current support exposure
   - recent physiologic evidence
   - and cross-family recomputation

That mixed temporal structure is one of the main sources of difficulty in the surveillance benchmark.

## This Is Not A Uniform One-Time-Trigger Benchmark

An important clarification for dataset users is that the surveillance benchmark does **not** use one single step-level ground-truth rule for every disease or ICU state.

It is **not** a simple benchmark where:

- a condition turns positive once
- then stays positive forever
- and the same persistence rule is reused for every head

Instead, the step-level ground truth is intentionally **disease-dependent**.

The reason is clinical rather than purely technical:

- some ICU concepts are episode-level syndromes
- some are cumulative injury stages
- some are current support states
- some are recent physiologic abnormalities
- and some are composite high-acuity states that should be recomputed at every checkpoint

So the benchmark uses different checkpoint semantics for different disease families because the underlying clinical states behave differently.

### Family-by-family interpretation

#### Infection family

Decisions:

- `infection_suspected`
- `infection_confirmed_or_strongly_supported`

Recommended step-level semantics:

- treat these as **persistent episode** states
- once the first qualifying infection evidence is visible, the state remains active for the rest of the `0-48h` benchmark window

Why:

- suspicion of infection is an episode-level state rather than a short-lived vital-sign state
- once infection evidence has appeared, the benchmark should preserve that fact longitudinally

#### Sepsis family

Decision:

- `sepsis_alert`

Recommended step-level semantics:

- treat this as a **persistent episode** state
- once Sepsis-3 onset is visible, it remains active for the rest of the benchmark window

Why:

- this benchmark is testing whether the agent detects that sepsis has occurred during the ICU course
- a later checkpoint should still remember that alert-level sepsis was already reached

Important distinction:

- `sepsis_alert` is persistent
- but shock-like derivatives of sepsis are **not** necessarily persistent

#### Renal family

Decisions:

- `aki_stage1`
- `aki_stage2`
- `aki_stage3`
- `oliguria_6h`
- `severe_oliguria_or_anuria`
- `crrt_active`

Recommended step-level semantics:

- `aki_stage1/2/3` use **cumulative max stage**
- `oliguria_6h` and `severe_oliguria_or_anuria` use **rolling-window current state**
- `crrt_active` uses **active interval**

Why:

- AKI stage should reflect the worst injury attained so far, not just the latest row
- oliguria is a short-horizon dynamic physiologic state and should expire when the rolling window no longer supports it
- CRRT is an active therapy and should only count while it overlaps the checkpoint

So the renal family intentionally mixes three different persistence styles.

#### Respiratory family

Decisions:

- `resp_support_hfnc_or_niv`
- `resp_support_invasive_vent`
- `hypoxemia_pf_lt_200`
- `hypoxemia_pf_lt_100`

Recommended step-level semantics:

- support decisions use **active interval**
- PF-ratio decisions use **recent measurement with TTL**

Why:

- mechanical or non-invasive support is only clinically active while the support is actually on
- hypoxemia is a recent physiologic state, not an episode-level once-positive label

So the respiratory family is explicitly **not** modeled as one-time-trigger.

#### Hemodynamic family

Decisions:

- `vasoactive_support_any`
- `vasoactive_multi_agent_or_high_intensity`
- `septic_shock_alert`
- `shock_hypoperfusion_alert`

Recommended step-level semantics:

- vasoactive-support decisions use **active interval**
- shock-alert decisions use **composite current state**

Why:

- vasopressor exposure should only count while the therapy is active
- shock states are best represented as current high-acuity combinations of sepsis, support, and metabolic evidence
- these states should be recomputed each checkpoint rather than turned on forever after a single early event

This is one of the clearest examples of why a naive one-time-trigger rule would be clinically misleading.

#### Neurologic family

Decisions:

- `gcs_moderate_impairment_9_12`
- `gcs_severe_impairment_le_8`

Recommended step-level semantics:

- use **recent measurement with TTL**

Why:

- neurologic status can change quickly over time
- the benchmark should reflect the most recent observed impairment, not a permanent flag from an earlier low GCS

#### Metabolic family

Decisions:

- `hyperlactatemia_ge_2`
- `severe_hyperlactatemia_ge_4`
- `acidemia_ph_lt_7_30`
- `severe_acidemia_ph_le_7_20`

Recommended step-level semantics:

- use **recent measurement with TTL**

Why:

- lactate and pH are classic dynamic physiologic measurements
- they should remain active only while recent evidence supports them

#### Coagulation family

Decisions:

- `coagulopathy_inr_ge_1_5`
- `coagulopathy_inr_ge_2`

Recommended step-level semantics:

- use **recent measurement with TTL**

Why:

- INR abnormalities are lab-based current states, although less volatile than blood-gas heads
- they should not be treated as permanent once-onset diagnoses in this benchmark

### Practical summary

At the step level, the benchmark uses different semantics because different ICU conditions have different clinical meanings.

The intended interpretation is:

- infection and sepsis: **once-onset, then persist**
- AKI stage: **worst stage attained so far**
- support therapies: **active only while currently on**
- labs and physiologic abnormalities: **active only while recently supported by evidence**
- shock-like composite states: **recomputed at every checkpoint**

This is deliberate.

It makes the benchmark closer to real ICU surveillance, where the agent must reason over:

- event memory
- cumulative injury
- current treatment state
- and recent physiologic state

rather than over a single uniform trigger rule.

## Composite Current States

Some alert heads should be recomputed from component states at every checkpoint rather than treated as once-on episode flags.

This is the right pattern for shock-like states.

### `septic_shock_alert`

Active if all are true at checkpoint `t`:

- `sepsis_alert` is active
- `vasoactive_support_any` is active
- `hyperlactatemia_ge_2` is active in its recency window

### `shock_hypoperfusion_alert`

Active if all are true at checkpoint `t`:

- `sepsis_alert` is active
- `vasoactive_support_any` is active
- `severe_hyperlactatemia_ge_4` is active in its recency window

This makes these states more clinically faithful than a simple “once positive, always positive” rule.

## Why This Labeling Scheme Is Better

This checkpoint scheme is better than pure ever-positive labels because it preserves the difference between:

- a diagnosis that persists through the episode
- a support therapy that turns on and off
- a recent lab derangement that should expire if not refreshed
- and a cumulative injury stage that should not be forgotten once reached

That is the right level of realism for ICU surveillance.

## Task-by-Task Rationale and Label Criteria

This section explains, one by one, why each selected surveillance head is included in the benchmark and how it is labeled at the checkpoint level.

The selection principles are consistent across the registry:

- the head should represent a clinically meaningful ICU monitoring state
- the head should matter for escalation or focused follow-up
- the head should be definable from `mimiciv_derived` tables or a very small transparent extension
- the head should add coverage, overlap, or temporal complexity rather than duplicate another label exactly

### Infection family

#### `infection_suspected`

Why we selected it:

- infection suspicion is one of the most common and important early ICU monitoring problems
- it is the natural precursor state for sepsis reasoning
- it gives the benchmark an episode-level state that should be remembered longitudinally after onset

Checkpoint label criterion:

- source: `mimiciv_derived.suspicion_of_infection`
- active at checkpoint `t` if `first suspected_infection_time <= t`
- persistence style: persistent episode

#### `infection_confirmed_or_strongly_supported`

Why we selected it:

- this distinguishes weaker infection suspicion from stronger microbiology-supported infection evidence
- it makes the infection family more clinically granular without requiring diagnosis codes
- it is useful for cases where infection evidence strengthens over time

Checkpoint label criterion:

- source: `suspicion_of_infection.positive_culture`
- active at checkpoint `t` if `first positive culture_time <= t`
- persistence style: persistent episode

### Sepsis family

#### `sepsis_alert`

Why we selected it:

- sepsis is one of the central ICU surveillance syndromes and a core benchmark target
- it naturally composes multiple upstream clinical signals rather than a single raw measurement
- it creates a strong longitudinal memory requirement because later checkpoints should preserve that sepsis onset already occurred

Checkpoint label criterion:

- source: `mimiciv_derived.sepsis3`
- active at checkpoint `t` if `first Sepsis-3 onset <= t`
- persistence style: persistent episode

### Renal family

#### `aki_stage1`

Why we selected it:

- stage 1 AKI is a common early renal warning state
- it gives the benchmark a suspect-level renal state rather than only severe kidney injury
- it is useful for testing whether the agent can maintain worst-so-far injury memory across checkpoints

Checkpoint label criterion:

- source: `mimiciv_derived.kdigo_stages`
- active at checkpoint `t` if `max aki_stage_smoothed up to checkpoint >= 1`
- persistence style: cumulative max stage

#### `aki_stage2`

Why we selected it:

- stage 2 AKI is a clear alert-level renal deterioration state
- it is common enough to support robust evaluation
- it is clinically distinct from mild AKI and often changes management urgency

Checkpoint label criterion:

- source: `mimiciv_derived.kdigo_stages`
- active at checkpoint `t` if `max aki_stage_smoothed up to checkpoint >= 2`
- persistence style: cumulative max stage

#### `aki_stage3`

Why we selected it:

- stage 3 AKI is one of the key severe alert heads in the benchmark
- it helps ensure the released subset contains meaningful high-acuity renal cases
- it is also a strong test of delayed deterioration, because many cases become stage 3 later in the 48-hour window

Checkpoint label criterion:

- source: `mimiciv_derived.kdigo_stages`
- active at checkpoint `t` if `max aki_stage_smoothed up to checkpoint >= 3`
- persistence style: cumulative max stage

#### `oliguria_6h`

Why we selected it:

- urine-output decline is a classic ICU surveillance signal that often precedes or complements creatinine-based AKI
- it adds short-horizon rolling-window difficulty to the renal family
- it captures a dynamic physiologic state rather than a cumulative diagnosis

Checkpoint label criterion:

- source: `mimiciv_derived.urine_output_rate`
- active if the most recent urine-output row `<= t` has `uo_tm_6hr >= 6` and `uo_mlkghr_6hr < 0.5`
- persistence style: rolling-window current state
- recency window: `6h`

#### `severe_oliguria_or_anuria`

Why we selected it:

- this provides an alert-level urine-output failure state beyond mild oliguria
- it increases renal severity resolution without relying only on KDIGO stage
- it contributes delayed and fluctuating patterns that are different from persistent AKI labels

Checkpoint label criterion:

- source: small extension over `urine_output_rate`
- active if the most recent urine-output row `<= t` satisfies the severe 12-hour or 24-hour oliguria / anuria threshold
- persistence style: rolling-window current state
- recency window: `24h`

#### `crrt_active`

Why we selected it:

- CRRT is a high-acuity renal support state that is clinically meaningful even when numerically rare
- it helps distinguish severe renal injury from active organ support
- it adds intervention-based interval semantics to the renal family

Checkpoint label criterion:

- source: `mimiciv_derived.crrt`
- active if CRRT mode is active at checkpoint `t`
- persistence style: active interval

### Respiratory family

#### `resp_support_hfnc_or_niv`

Why we selected it:

- this captures intermediate respiratory support escalation before intubation
- it adds a suspect-level respiratory state that is treatment-based rather than diagnosis-based
- it helps represent non-trivial respiratory monitoring trajectories that are less severe than invasive ventilation

Checkpoint label criterion:

- source: `mimiciv_derived.ventilation`
- active if `ventilation_status` in `HFNC` or `NonInvasiveVent` overlaps checkpoint `t`
- persistence style: active interval

#### `resp_support_invasive_vent`

Why we selected it:

- invasive ventilation is one of the most important ICU alert-level support states
- it is common, high-acuity, and strongly associated with multi-family overlap
- it is a natural respiratory alert for benchmark scoring

Checkpoint label criterion:

- source: `mimiciv_derived.ventilation`
- active if `ventilation_status` in `InvasiveVent` or `Tracheostomy` overlaps checkpoint `t`
- persistence style: active interval

#### `hypoxemia_pf_lt_200`

Why we selected it:

- PF ratio under 200 is a clinically meaningful oxygenation abnormality that often coexists with respiratory support escalation
- it introduces recent-measurement semantics rather than pure intervention semantics
- it allows respiratory surveillance to include physiology, not only support devices

Checkpoint label criterion:

- source: `mimiciv_derived.bg`
- active if the most recent PF-ratio measurement within the trailing window is `< 200`
- persistence style: recent measurement with TTL
- recency window: `12h`

#### `hypoxemia_pf_lt_100`

Why we selected it:

- PF ratio under 100 represents a severe alert-level oxygenation failure state
- it is thinner than invasive ventilation and therefore useful for rare-alert enrichment
- it helps separate very severe hypoxemia from more general respiratory support exposure

Checkpoint label criterion:

- source: `mimiciv_derived.bg`
- active if the most recent PF-ratio measurement within the trailing window is `< 100`
- persistence style: recent measurement with TTL
- recency window: `12h`

### Hemodynamic family

#### `vasoactive_support_any`

Why we selected it:

- any vasoactive support is a strong signal of hemodynamic instability even before more severe shock criteria are met
- it gives the benchmark a suspect-level support state that is highly actionable
- it also serves as a key component for septic-shock-like composite heads

Checkpoint label criterion:

- source: `mimiciv_derived.vasoactive_agent`
- active if any vasoactive or inotrope interval overlaps checkpoint `t`
- persistence style: active interval

#### `vasoactive_multi_agent_or_high_intensity`

Why we selected it:

- this is an alert-level escalation beyond single-agent support
- it captures a more severe hemodynamic support pattern than `vasoactive_support_any`
- it improves the benchmark's ability to represent severe circulatory failure

Checkpoint label criterion:

- source: small extension over `vasoactive_agent`
- current implementation activates when two or more vasoactive agents are active at checkpoint `t`
- persistence style: active interval

#### `septic_shock_alert`

Why we selected it:

- septic shock is a canonical ICU high-acuity syndrome that should be represented separately from sepsis alone
- it forces the benchmark to evaluate cross-family composition: infection/sepsis, hemodynamic support, and metabolic evidence
- it is a core alert head for the enriched benchmark subset

Checkpoint label criterion:

- source: small extension over `sepsis3 + vasoactive_agent + bg`
- active if:
  - `sepsis_alert` is active
  - `vasoactive_support_any` is active
  - recent lactate is `>= 2`
- persistence style: composite current state
- recency window for lactate: `12h`

#### `shock_hypoperfusion_alert`

Why we selected it:

- this represents a more severe shock-with-hypoperfusion state than `septic_shock_alert`
- it is clinically valuable because it sharpens high-acuity hemodynamic failure beyond sepsis plus pressor exposure alone
- it is an intentionally thinner alert head that stresses difficult benchmark cases

Checkpoint label criterion:

- source: small extension over `sepsis3 + vasoactive_agent + bg`
- active if:
  - `sepsis_alert` is active
  - `vasoactive_support_any` is active
  - recent lactate is `>= 4`
- persistence style: composite current state
- recency window for lactate: `12h`

### Neurologic family

#### `gcs_moderate_impairment_9_12`

Why we selected it:

- moderate GCS impairment is a common neurologic surveillance state that is less severe than coma-level deterioration
- it gives the benchmark a suspect-level neurologic head with rapid temporal turnover
- it broadens the benchmark beyond infection, renal, and respiratory-heavy cases

Checkpoint label criterion:

- source: `mimiciv_derived.gcs`
- active if the most recent GCS within the trailing window is `9-12`
- persistence style: recent measurement with TTL
- recency window: `8h`

#### `gcs_severe_impairment_le_8`

Why we selected it:

- GCS `<= 8` is a clinically meaningful alert-level neurologic deterioration state
- it is one of the key thinner severe heads in the 2k subset
- it adds a non-lab, non-pressor, non-renal severe phenotype to the benchmark

Checkpoint label criterion:

- source: `mimiciv_derived.gcs`
- active if the most recent GCS within the trailing window is `<= 8`
- persistence style: recent measurement with TTL
- recency window: `8h`

### Metabolic family

#### `hyperlactatemia_ge_2`

Why we selected it:

- lactate elevation is a common ICU metabolic warning signal and an important component of shock reasoning
- it gives the benchmark a suspect-level metabolic state with short recency semantics
- it is also useful as a compositional building block for hemodynamic alert heads

Checkpoint label criterion:

- source: `mimiciv_derived.bg`
- active if the most recent lactate within the trailing window is `>= 2`
- persistence style: recent measurement with TTL
- recency window: `12h`

#### `severe_hyperlactatemia_ge_4`

Why we selected it:

- lactate `>= 4` is a clinically important severe metabolic derangement
- it increases severity resolution within the metabolic family
- it also supports the more severe hypoperfusion composite state

Checkpoint label criterion:

- source: `mimiciv_derived.bg`
- active if the most recent lactate within the trailing window is `>= 4`
- persistence style: recent measurement with TTL
- recency window: `12h`

#### `acidemia_ph_lt_7_30`

Why we selected it:

- mild-to-moderate acidemia is a broad ICU metabolic warning state
- it complements lactate by capturing acid-base failure more directly
- it adds another recent-measurement head with potentially reversible dynamics

Checkpoint label criterion:

- source: `mimiciv_derived.bg`
- active if the most recent pH within the trailing window is `< 7.30`
- persistence style: recent measurement with TTL
- recency window: `12h`

#### `severe_acidemia_ph_le_7_20`

Why we selected it:

- severe acidemia is one of the key high-acuity alert heads in the benchmark
- it is clinically meaningful across multiple etiologies, not only infection
- it increases coverage of severe metabolic failure cases that may be relatively uncommon but important

Checkpoint label criterion:

- source: `mimiciv_derived.bg`
- active if the most recent pH within the trailing window is `<= 7.20`
- persistence style: recent measurement with TTL
- recency window: `12h`

### Coagulation family

#### `coagulopathy_inr_ge_1_5`

Why we selected it:

- INR elevation gives the benchmark a hematologic/coagulation surveillance axis that is otherwise absent from the major organ-failure heads
- it contributes meaningful breadth beyond sepsis, renal, respiratory, and hemodynamic states
- it works well as a suspect-level coagulation abnormality

Checkpoint label criterion:

- source: `mimiciv_derived.coagulation`
- active if the most recent INR within the trailing window is `>= 1.5`
- persistence style: recent measurement with TTL
- recency window: `24h`

#### `coagulopathy_inr_ge_2`

Why we selected it:

- INR `>= 2` is a cleaner alert-level coagulopathy state
- it is severe enough to matter clinically but common enough to support evaluation
- it ensures the benchmark covers major coagulation abnormality rather than only mild lab drift

Checkpoint label criterion:

- source: `mimiciv_derived.coagulation`
- active if the most recent INR within the trailing window is `>= 2.0`
- persistence style: recent measurement with TTL
- recency window: `24h`

## Onset Timing Evidence

The onset-timing audit is:

- [decision_onset_timing.csv](/Users/chloe/Documents/New project/dataset/surveilance/decision_onset_timing.csv)

This matters because a useful rolling benchmark should contain both:

- early positives
- delayed deterioration

Key patterns:

- very early-heavy states:
  - `infection_suspected`: `90.30%` of positive stays start by `4h`
  - `hyperlactatemia_ge_2`: `76.55%`
  - `resp_support_invasive_vent`: `70.77%`
  - `sepsis_alert`: `63.76%`
- delayed-progression states:
  - `aki_stage3`: `56.21%` start in `24-48h`
  - `severe_oliguria_or_anuria`: `32.42%` in `24-48h` and `65.89%` in `12-24h`
  - `crrt_active`: `35.96%` in `24-48h`
- mixed-timing states:
  - `septic_shock_alert`
  - `shock_hypoperfusion_alert`
  - `gcs` impairment states
  - `PF ratio` states

This is exactly why the benchmark subset should not be sampled only by stay-level positivity.
It should also be sampled by onset timing.

## Recommended 2,000-Stay Sampling Strategy

Do not try to make every decision exactly balanced.
That would destroy ICU realism.

Instead, use a soft-balanced sampling plan with three layers.

### Layer 1: Realistic core diversity (`1,200` stays)

Sample across:

- first care unit family
- overall checkpoint complexity
- onset profile

Recommended stratification axes:

- unit group: `MICU/CVICU`, `mixed med-surg/surgical/trauma`, `CCU`, `neuro-facing`
- core-family count by `24h`: `0-1`, `2-3`, `4+`
- onset profile:
  - mostly early (`>=60%` of first positive families by `12h`)
  - mixed
  - delayed (`at least one alert family first turns on in 24-48h`)

This layer preserves realism.

### Layer 2: alert enrichment (`600` stays)

Oversample stays positive by `48h` for at least one of the rarer but benchmark-important alert heads:

- `aki_stage3`
- `septic_shock_alert`
- `shock_hypoperfusion_alert`
- `hypoxemia_pf_lt_100`
- `gcs_severe_impairment_le_8`
- `severe_acidemia_ph_le_7_20`
- `coagulopathy_inr_ge_2`
- `vasoactive_multi_agent_or_high_intensity`

These heads are all common enough in the full cohort to support enrichment without duplicating odd edge cases.

### Layer 3: low-signal / mostly-negative stays (`200` stays)

Reserve a smaller slice for harder low-evidence monitoring:

- zero or one core family by `24h`
- fewer intervention-heavy supports
- neuro-intermediate and other lower-density contexts included

This prevents the benchmark from becoming only a “severely positive ICU” dataset.

## Soft Floors for the 2,000-Stay Package

After sampling, enforce soft stay-level minimums for the following heads by `48h`:

- `aki_stage3`: at least `180`
- `septic_shock_alert`: at least `180`
- `shock_hypoperfusion_alert`: at least `120`
- `hypoxemia_pf_lt_100`: at least `180`
- `gcs_severe_impairment_le_8`: at least `120`
- `severe_acidemia_ph_le_7_20`: at least `120`
- `coagulopathy_inr_ge_2`: at least `180`
- `vasoactive_multi_agent_or_high_intensity`: at least `150`

Optional extended floors:

- `resp_support_hfnc_or_niv`: at least `120`
- `crrt_active`: at least `60`

These are soft floors, not exact prevalence targets.

The purpose is:

- not to equalize every head
- but to avoid a benchmark where high-acuity decisions are too sparse to evaluate well

## What Should Be Scored

The benchmark should score three layers.

### 1. Family-level structured outputs

Primary benchmark score:

- `suspected_conditions`
- `alerts`
- `global_action`
- `priority`

This is the main user-facing score.

### 2. Latent decision recovery

Secondary score:

- evaluate whether the latent `25` checkpoint decisions are recoverable from the agent output and rationale
- use these mainly for slice analysis and error taxonomy

### 3. Timing

Track:

- first correct suspicion time
- first correct alert time
- false early alert rate
- delayed alert rate

This is critical for a rolling benchmark.

## Global Action and Priority Derivation

Use generalized rules from the active checkpoint states.

### `global_action`

- `escalate` if any alert-level family is active
- `continue_monitoring` otherwise

### `priority`

- `high` if any of:
  - hemodynamic alert active
  - respiratory alert active
  - `aki_stage3`
  - `gcs_severe_impairment_le_8`
  - `severe_acidemia_ph_le_7_20`
  - `shock_hypoperfusion_alert`
- `medium` if any alert is active but none of the high-priority rules fire, or if `>=3` suspect families are active
- `low` otherwise

This can be revised later, but it is a clean starting rule set.

## Implementation Plan

The build should happen in this order.

1. Materialize the `LOS >= 48h` checkpoint grid.
2. Build per-decision checkpoint states for all `25` latent decisions using the registry rules.
3. Apply family precedence at each checkpoint.
4. Derive `suspected_conditions`, `alerts`, `global_action`, and `priority`.
5. Summarize each stay into sampling features:
   - family counts
   - alert-head positives
   - onset timing profile
   - unit group
6. Sample the `2,000`-stay benchmark package using the three-layer strategy.
7. Export:
   - full checkpoint truth for the selected stays
   - stay-level manifest
   - per-decision benchmark prevalence summary
   - onset/timing summary

## Main Recommendation

The safest and strongest design is:

- label all `46,337` cohort stays first
- sample the final benchmark package second
- use a `25`-decision latent registry
- expose generalized `suspect` and `alert` outputs at the family level
- and target a soft-balanced `2,000`-stay benchmark rather than artificial exact balancing

That preserves both:

- ICU realism
- and enough head coverage for meaningful evaluation
