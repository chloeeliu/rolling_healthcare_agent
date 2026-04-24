# Autoformalized General ICU Monitoring Benchmark Design

Date: 2026-04-23

## Purpose

This document turns the current benchmark direction into a concrete high-level design for a harder benchmark:

- generalized ICU rolling monitoring
- centered on the autoformalized function library
- with trajectory-level retrieval of guidelines and candidate functions
- with step-level function calling for patient-state evidence
- evaluated on decision quality, timing, and tool efficiency

This design is intentionally benchmark-first, not prompt-engineering-first.

The main question is:

- what is the best way to build a hard, fair benchmark when the agent is supposed to reason over guidelines plus the autoformalized toolbox, but the current autoformalized library has imperfect and uneven support across tasks?

## Related Background

This design builds on:

- [general_icu_surveillance_derived_feasibility_report_2026-04-22.md](/Users/chloe/Documents/New project/docs/general_icu_surveillance_derived_feasibility_report_2026-04-22.md)
- [autoformalized_pipeline_design.md](/Users/chloe/Documents/New project/docs/autoformalized_pipeline_design.md)
- [sepsis_longitudinal_toolbox_design.md](/Users/chloe/Documents/New project/docs/sepsis_longitudinal_toolbox_design.md)
- [src/sepsis_mvp/duckdb_session.py](/Users/chloe/Documents/New project/src/sepsis_mvp/duckdb_session.py)
- [src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)
- [autoformalized_library/functions](/Users/chloe/Documents/New project/autoformalized_library/functions)
- [autoformalized_library/memories](/Users/chloe/Documents/New project/autoformalized_library/memories)

## Design Goal

The goal is not just to score whether a model can call one preselected concept tool.

The goal is to test whether a model can:

1. understand a disease monitoring target from generic instructions
2. retrieve relevant guideline text for that target
3. retrieve likely useful autoformalized functions from the library
4. decide which evidence tools to call at each rolling checkpoint
5. produce clinically meaningful monitoring decisions
6. do all of this efficiently

The benchmark should therefore evaluate three layers at once:

- retrieval quality
- evidence-acquisition quality
- monitoring decision quality

## Core Design Decisions

### 1. Use an autoformalized-native benchmark, not an official-derived-first benchmark

Your concern about the gap is correct.

If we build the benchmark gold labels purely from official derived tables, then we risk penalizing the model for behavior that is actually consistent with the autoformalized toolbox it is allowed to use.

That creates a benchmark mismatch:

- tools operate under one semantic contract
- labels come from another semantic contract

For this benchmark family, the better principle is:

- gold labels should be defined in the same concept space that the agent is allowed to act in

That means the benchmark should be autoformalized-native.

### 2. But do not build gold labels by literally reusing the exact same online tools

A pure "online tool output equals gold label" design is too circular.

That would make the benchmark vulnerable to:

- trivial tool matching
- leakage between inference and evaluation semantics
- poor robustness if a function is buggy

Recommended compromise:

- build labels from frozen, audited, offline label builders that are explicitly aligned to the autoformalized task contract
- keep the agent-facing tools separate runtime interfaces

This is the right middle ground:

- closer to autoformalized semantics than official derived labels
- less circular than evaluating directly on the same live tool outputs

### 3. Use monitoring heads rather than classic billing diagnoses

The best autoformalized candidates are not necessarily "diseases" in the ICD sense.

They are ICU monitoring heads:

- infection
- sepsis
- AKI
- oliguria
- respiratory support escalation
- vasoactive support
- neurologic deterioration
- hyperlactatemia
- severe acidemia
- coagulopathy

This is the right unit for ICU rolling monitoring because:

- it matches how the library is actually organized
- it matches what is timestampable
- it matches how agents will decide whether to monitor, suspect, or alert

## Recommended Task Set

### Recommendation

For the first serious benchmark version, I recommend a `9 + 1` design:

#### Core tasks that are best supported today

1. `infection`
2. `sepsis`
3. `aki`
4. `oliguria`
5. `respiratory_support`
6. `vasoactive_support`
7. `neurologic_deterioration`
8. `hyperlactatemia`
9. `severe_acidemia`

#### Add with one small extension

10. `coagulopathy`

#### Optional task 11

11. `crrt`

### Why this is the right v1 set

These tasks satisfy most of the following:

- feasible in the local database
- plausible using autoformalized evidence
- clinically meaningful in rolling monitoring
- already exposed or almost exposed in the current runtime
- can be expressed in a near-universal action space

### Why not force all available concepts into v1

I would not make the first version larger just because the library is larger.

Examples of concepts that should stay out of v1 as top-level heads:

- severity scores like `apsiii`, `oasis`, `lods`, `sapsii`
- contextual measurements like `invasive_line`
- broader phenotype helpers like `chemistry`, `blood_differential`, `inflammation`
- dedicated `sepsis3.py` as a direct gold or benchmark-facing tool

These are useful as support functions or hidden metadata, but not the cleanest first benchmark heads.

## Per-Task Recommendation

### Tier 1: strongest candidates now

These are the best candidates for an autoformalized-native benchmark today:

- `infection`
- `aki`
- `oliguria`
- `respiratory_support`
- `vasoactive_support`
- `neurologic_deterioration`
- `hyperlactatemia`
- `severe_acidemia`

Reason:

- all have meaningful autoformalized evidence functions
- all have workable timing semantics
- all can be converted into rolling state/action labels without much ambiguity

### Tier 2: keep, but define carefully

- `sepsis`

Reason:

- sepsis should be a composed task built from:
  - infection evidence
  - SOFA evidence
- this is better than treating `autoformalized_library/functions/sepsis3.py` as benchmark-ready

### Tier 3: add after a small extension

- `coagulopathy`
- `crrt`

Reason:

- both functions exist in the library
- neither is exposed as a benchmark-facing tool today

## Task Support Matrix

This table translates the recommended heads into the actual benchmark contract we can support with the current codebase.

| Task head | Trajectory-level library target | Step-level evidence tool | Gold builder basis | Runtime status | Main concern |
|---|---|---|---|---|---|
| `infection` | `suspicion_of_infection` | `query_suspicion_of_infection` | frozen suspicion-of-infection builder | ready | broad syndrome head rather than a single diagnosis |
| `sepsis` | `suspicion_of_infection`, `sofa` | `query_suspicion_of_infection`, `query_sofa` | composed offline contract using infection plus dysfunction | ready with careful spec | direct `sepsis3.py` is not benchmark-safe |
| `aki` | `kdigo_stages` | `query_kdigo_stage` | frozen KDIGO-stage builder | ready | generated semantics are close to, but not identical with, official semantics |
| `oliguria` | `urine_output_rate` | `query_urine_output_rate` | frozen urine-output builder | ready | duration threshold must be frozen explicitly |
| `respiratory_support` | `ventilation` | `query_ventilation_status` | frozen support-level builder | ready | intervention head, not disease etiology |
| `vasoactive_support` | `vasoactive_agent` | `query_vasoactive_agent` | frozen pressor/inotrope builder | ready | escalation semantics should live in task spec, not prompt |
| `neurologic_deterioration` | `gcs` | `query_gcs` | frozen GCS-threshold builder | ready | sedation and intubation can blur meaning |
| `hyperlactatemia` | `bg` | `query_bg` | frozen lactate-threshold builder | ready | `hadm_id`-linked rather than `stay_id`-linked |
| `severe_acidemia` | `bg` | `query_bg` | frozen pH-threshold builder | ready | same `hadm_id` caveat as lactate |
| `coagulopathy` | `coagulation` | `query_coagulation` | frozen INR-threshold builder | adapter needed | not exposed in runtime yet |
| `crrt` | `crrt` | `query_crrt` | frozen CRRT-initiation builder | optional adapter needed | low prevalence and not exposed in runtime yet |

## Best Candidate Diseases For The Autoformalized Way

If the benchmark is explicitly autoformalized-first, the best candidates are the heads that satisfy all four conditions:

- the function exists in `autoformalized_library/functions`
- the output is clinically interpretable over time
- the runtime already exposes it, or the missing adapter is trivial
- the cohort is large enough for rolling evaluation

Under that criterion, the best candidates are:

1. `infection`
2. `sepsis`
3. `aki`
4. `oliguria`
5. `respiratory_support`
6. `vasoactive_support`
7. `neurologic_deterioration`
8. `hyperlactatemia`
9. `severe_acidemia`
10. `coagulopathy`

Why these are the best fit:

- they line up with functions that already exist in the library
- they are clinically actionable monitoring heads rather than billing diagnoses
- they are visible in MIMIC without reconstructing too much bedside workflow logic from scratch
- they can be frozen into stable `keep_monitoring` / `suspect` / `alert` contracts

Why some concepts should stay secondary:

- `sepsis3.py` exists, but it is weaker than a composed infection-plus-SOFA contract
- severity scores like `apsiii` or `oasis` are useful context, but not natural monitor/alert heads
- generic helpers like `vitalsign` or `chemistry` are support tools, not clean top-level labels

## Feasibility Check

### Cohort recommendation

Use the `LOS >= 48h` cohort for the harder benchmark.

Why:

- more true monitoring transitions
- more room for delayed worsening
- more room for efficiency decisions
- still large enough for strong train/dev/test splits

Feasibility summary from the prior cohort audit on the `48h` cohort:

- eligible ICU stays: `46,337`
- infection by `24h`: `29,890`
- sepsis by `24h`: `23,739`
- AKI stage 2/3 by `24h`: `22,437`
- oliguria by `24h`: `24,674`
- respiratory support medium+ by `24h`: `23,417`
- vasoactive support by `24h`: `15,781`
- GCS `<= 8` by `24h`: `4,046`
- lactate `>= 4` by `24h`: `6,519`
- pH `< 7.20` by `24h`: `4,362`
- INR `>= 2` by `24h`: `7,924`

These counts are strong enough for a rebalanced benchmark.

### Split feasibility

On the `48h` cohort, deterministic subject-level split sizes are:

- `train`: `32,654`
- `dev`: `6,934`
- `test`: `6,749`

Even the rarer recommended heads remain workable:

- `gcs_le_8`: train `2,830`, dev `621`, test `595`
- `ph_lt_7_20`: train `3,098`, dev `638`, test `626`
- `inr_ge_2`: train `5,642`, dev `1,177`, test `1,105`

### Autoformalized feasibility check

Current autoformalized runtime exposure is already enough for most of the v1 set:

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_urine_output_rate`
- `query_ventilation_status`
- `query_vasoactive_agent`
- `query_bg`
- `query_gcs`

Missing adapters for the recommended v1 set:

- `query_coagulation`

Optional future adapter:

- `query_crrt`

This is a manageable gap.

## Gold Label Design

## Recommendation

Gold labels should be built from frozen autoformalized-aligned label builders.

Not:

- pure official derived labels
- pure live online tool outputs

### Why not pure official labels

Problem:

- official labels are cleaner for some concepts
- but they do not always match what the autoformalized evidence tools show

Result:

- the agent can be punished for following the toolbox it was given

### Why not pure live tool outputs

Problem:

- too circular
- too easy to game
- too brittle if a function changes

### Recommended compromise

For each task, define a frozen task contract:

- what evidence fields matter
- what threshold defines `suspect`
- what threshold defines `alert`

Then build offline checkpoint labels from those frozen contracts.

This creates:

- tool-native gold semantics
- stable reproducibility
- less circularity

## Recommended Ground-Truth Strategy

Your concern about label gap is well-founded. For this benchmark family, the safest ground-truth strategy is:

1. define a frozen offline task contract for each head
2. implement an offline label builder per head using the same concept family as the autoformalized function
3. expose a separate runtime tool wrapper for agent interaction

That gives us three distinct layers:

- concept layer
  - the clinical meaning we want to evaluate
- offline label layer
  - the versioned gold builder used to construct the dataset
- online tool layer
  - the agent-facing evidence interface used at inference time

This avoids the two bad extremes:

- pure official-derived labels, which create toolbox-to-label mismatch
- pure live-tool labels, which make evaluation circular

### Ground-truth recommendation by task

Use autoformalized-aligned offline builders for:

- `infection`
- `aki`
- `oliguria`
- `respiratory_support`
- `vasoactive_support`
- `neurologic_deterioration`
- `hyperlactatemia`
- `severe_acidemia`
- `coagulopathy`

Use a composed builder for:

- `sepsis`

Recommended sepsis contract:

- `infection` builder determines whether infection evidence is established
- `sofa` builder determines whether organ dysfunction threshold is crossed
- the benchmark label is composed from these two frozen builders

That is much safer than using direct `sepsis3.py` execution as gold.

## Suggested Task Contracts

The benchmark can use a universal 3-state action contract:

- `keep_monitoring`
- `suspect_disease(d)`
- `trigger_alert(d)`

This should be interpreted per disease head.

### Example task contracts

#### Infection

- `keep_monitoring`: no infection evidence yet
- `suspect_disease(infection)`: partial or weak infection evidence
- `trigger_alert(infection)`: autoformalized infection criteria clearly met

#### Sepsis

- `keep_monitoring`: no infection or no clinically meaningful dysfunction
- `suspect_disease(sepsis)`: infection established but alert-level dysfunction not yet established
- `trigger_alert(sepsis)`: infection established and autoformalized sepsis alert criteria met

#### AKI

- `keep_monitoring`: stage 0
- `suspect_disease(aki)`: stage 1
- `trigger_alert(aki)`: stage 2 or 3

#### Oliguria

- `keep_monitoring`: no oliguria
- `suspect_disease(oliguria)`: oliguria threshold crossed
- `trigger_alert(oliguria)`: severe or sustained oliguria threshold crossed

#### Respiratory support

- `keep_monitoring`: low support / supplemental oxygen only
- `suspect_disease(respiratory_support)`: HFNC or NIV
- `trigger_alert(respiratory_support)`: invasive ventilation

#### Vasoactive support

- `keep_monitoring`: no vasoactive support
- `suspect_disease(vasoactive_support)`: any vasoactive or inotrope exposure visible
- `trigger_alert(vasoactive_support)`: active vasoactive requirement or multi-agent / escalating support

#### Neurologic deterioration

- `keep_monitoring`: no concerning impairment
- `suspect_disease(neurologic_deterioration)`: moderate impairment
- `trigger_alert(neurologic_deterioration)`: severe impairment such as `GCS <= 8`

#### Hyperlactatemia

- `keep_monitoring`: lactate below abnormal range
- `suspect_disease(hyperlactatemia)`: elevated but below severe threshold
- `trigger_alert(hyperlactatemia)`: severe lactate threshold reached, e.g. `>= 4`

#### Severe acidemia

- `keep_monitoring`: no acidemia
- `suspect_disease(severe_acidemia)`: mild acidemia
- `trigger_alert(severe_acidemia)`: severe acidemia, e.g. `pH <= 7.20`

#### Coagulopathy

- `keep_monitoring`: normal or near-normal INR
- `suspect_disease(coagulopathy)`: elevated INR / coagulopathy concern
- `trigger_alert(coagulopathy)`: severe INR threshold reached, e.g. `>= 2`

### Important note

The exact thresholds should be frozen in a task spec file, not embedded only in prompts.

## Retrieval Design

The benchmark should have two retrieval layers.

### 1. Trajectory-level retrieval

This happens once per ICU stay before rolling checkpoint decisions begin.

The purpose is to let the model orient itself to:

- disease-specific guideline material
- likely relevant functions in the autoformalized library

The best reuse path is the existing DuckDB session helpers:

- `search_guidelines(keyword)`
- `get_guideline(name)`
- `search_functions(keyword)`
- `get_function_info(name)`
- `load_function(name)`

These already exist in [src/sepsis_mvp/duckdb_session.py](/Users/chloe/Documents/New project/src/sepsis_mvp/duckdb_session.py).

### 2. Step-level evidence retrieval

This happens at each checkpoint and should use benchmark-facing structured tools.

Important design rule:

- trajectory-level retrieval may search broadly across the library
- step-level evidence retrieval should use a curated stable tool interface

This keeps evaluation tractable and output schemas stable.

## Guideline Corpus Design

The guideline layer should be deliberately lightweight.

The benchmark does not need a giant clinical corpus. It needs a compact retrieval corpus that helps the agent:

- orient to the head being monitored
- recover clinically meaningful thresholds and escalation cues
- map disease names onto likely evidence functions

### Recommended folder layout

- [guidelines/general_icu_autoformalized](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized)
- [guidelines/general_icu_autoformalized/txt](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/txt)
- [guidelines/general_icu_autoformalized/seed_sources.md](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/seed_sources.md)

The current `search_guidelines()` helper expects a flat `.txt` directory, so the benchmark should point `guidelines_dir` to:

- `/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/txt`

### Recommended guideline file format

Each file should be short and benchmark-facing:

- one head per file
- one-line title
- short task description
- key thresholds or escalation cues
- likely candidate functions
- provenance links

Suggested filenames:

- `infection.txt`
- `sepsis.txt`
- `aki.txt`
- `oliguria.txt`
- `respiratory_support.txt`
- `vasoactive_support.txt`
- `neurologic_deterioration.txt`
- `hyperlactatemia.txt`
- `severe_acidemia.txt`
- `coagulopathy.txt`

### Recommended source policy

Use NIH-family or NCBI-hosted material when possible for seed curation, then rewrite each source into a compact benchmark summary.

Initial seed links have been tracked in:

- [guidelines/general_icu_autoformalized/seed_sources.md](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/seed_sources.md)

This is better than storing raw page dumps because:

- retrieval stays stable
- irrelevant long passages do not dominate ranking
- benchmark behavior is easier to debug

## Recommended Retrieval Contract

### Trajectory-level retrieval stage

Input:

- disease set
- ICU stay metadata
- benchmark instructions

Allowed operations:

- search guideline names
- fetch selected guideline text
- search candidate function names
- inspect function signatures/docstrings
- optionally inspect memory summaries

Output:

- selected guideline bundle per disease
- selected candidate function set per disease
- concise trajectory plan

### Step-level evidence stage

Input:

- current checkpoint
- rolling history
- retrieved guideline/function context from trajectory-level stage

Allowed operations:

- call benchmark-facing evidence tools

Output:

- disease action(s)

## Recommended Benchmark-Facing Tool Design

Do not expose the entire raw autoformalized library directly at step time.

Instead expose:

- a curated benchmark-facing tool layer
- with stable schemas
- adapted from the autoformalized library

### V1 benchmark-facing tools

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_urine_output_rate`
- `query_ventilation_status`
- `query_vasoactive_agent`
- `query_bg`
- `query_gcs`
- `query_coagulation` after extension

Optional:

- `query_crrt`

### Why this split is important

If step-level execution is allowed to run arbitrary library functions:

- schemas become heterogeneous
- evaluation gets much harder
- debugging gets much harder
- models may overfit function names rather than clinically useful evidence use

The benchmark should reward:

- discovering useful functions at trajectory level
- choosing useful evidence tools at step level

not:

- arbitrary code spelunking at every checkpoint

## Task-To-Tool Decision Flow

At trajectory start, the model should be allowed to discover the space.

At checkpoint time, it should work through a small stable action loop.

Recommended checkpoint-time logic:

1. choose a disease head or small set of heads to prioritize
2. call the minimal evidence tools needed for those heads
3. update the head state
4. emit one of:
   - `keep_monitoring`
   - `suspect_disease(d)`
   - `trigger_alert(d)`

Recommended disease-to-tool mapping:

- `infection`
  - first-line tools: `query_suspicion_of_infection`
- `sepsis`
  - first-line tools: `query_suspicion_of_infection`, `query_sofa`
- `aki`
  - first-line tools: `query_kdigo_stage`
- `oliguria`
  - first-line tools: `query_urine_output_rate`
- `respiratory_support`
  - first-line tools: `query_ventilation_status`
- `vasoactive_support`
  - first-line tools: `query_vasoactive_agent`
- `neurologic_deterioration`
  - first-line tools: `query_gcs`
- `hyperlactatemia`
  - first-line tools: `query_bg`
- `severe_acidemia`
  - first-line tools: `query_bg`
- `coagulopathy`
  - first-line tools: `query_coagulation`

Support tools that may remain useful but should not be core heads:

- `query_vitalsign`
- `query_antibiotic`
- `query_invasive_line`

## Prompt Design

### Recommendation

Use a universal prompt template with:

- disease set
- rolling monitoring framing
- trajectory-level retrieval budget
- step-level tool budget
- explicit output contract

This is the right choice.

It avoids over-curating disease-specific prompts and lets retrieval do more of the work.

### Suggested universal framing

High-level intent:

- "Check the following diseases in a rolling monitoring way."
- "You may first retrieve relevant clinical documents and candidate functions."
- "At each checkpoint, decide whether to continue monitoring, suspect disease, or trigger alert."

### Prompt layers

#### System layer

- universal monitoring instructions
- JSON-only output contract
- retrieval/tool-use contract

#### Trajectory layer

- disease set
- patient stay metadata
- retrieval helpers

#### Step layer

- current checkpoint time
- rolling history
- available evidence tools
- remaining tool budget

### Recommended high-level prompt shape

1. identify the diseases to monitor
2. retrieve relevant guideline snippets
3. retrieve candidate autoformalized functions
4. at each 4-hour checkpoint, call only the patient-state evidence tools you need
5. for each disease head, decide whether to:
   - keep monitoring
   - suspect disease
   - trigger alert

This keeps the prompt universal while still giving the benchmark a stable evaluation contract.

## Recommended Pipeline

### Phase 0: Asset preparation

Build or freeze:

- guideline text directory
- disease-to-keyword mapping
- function registry metadata
- task spec files
- benchmark-facing tool adapters

### Phase 1: Task specification

For each disease head:

- define gold state/action contract
- define primary evidence tools
- define alert threshold
- define timing metric
- define acceptable retrieval keywords

### Phase 2: Offline gold-label building

For each stay and checkpoint:

1. create checkpoint-scoped views
2. run frozen autoformalized-aligned label builders
3. compute disease state
4. materialize:
   - state label
   - first suspicion time
   - first alert time
   - optional auxiliary metadata

### Phase 3: Dataset packaging

Store:

- stay metadata
- checkpoints every 4 hours
- disease set
- gold transitions
- optional benchmark hints

### Phase 4: Trajectory-level retrieval stage

Before checkpoint loop:

1. search guidelines for each disease
2. fetch top guideline texts
3. search functions for each disease
4. fetch top function signatures or memory snippets
5. let the model produce a compact disease-to-function plan

### Phase 5: Step-level monitoring loop

Every 4 hours:

1. pass rolling history plus retrieved context
2. let the agent decide whether to call evidence tools
3. record tool calls and outputs
4. return disease-level action(s)

### Phase 6: Evaluation

Score:

- correctness
- timing
- efficiency

### Why this pipeline is the right fit

It cleanly separates:

- knowledge retrieval
- evidence gathering
- decision making
- evaluation

That separation is what will make the benchmark hard without making it opaque.

## Recommended Checkpoint Grid

Because your draft explicitly says "rolling in every 4 hrs", I recommend:

- `0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48`

This keeps:

- simple temporal semantics
- alignment with existing benchmark style
- enough room for delayed worsening

## Evaluation Design

Evaluation should have three families of metrics.

### 1. Decision quality

Per disease:

- step accuracy
- macro F1
- balanced accuracy
- confusion matrix

Also:

- joint trajectory-level disease-state accuracy

### 2. Timing quality

Per disease:

- suspicion timing error
- alert timing error
- false early suspicion rate
- false early alert rate
- missed alert rate

The timing metric should reward:

- early but not absurdly early detection
- correct escalation order

### 3. Tool efficiency

Per trajectory and per step:

- total evidence tool calls
- calls per checkpoint
- redundant call rate
- repeated same-tool call rate when rolling history already established the state
- tool calls made before positive decision
- trajectory-level retrieval cost

### Recommended composite score

The benchmark leaderboard should not be accuracy-only.

Suggested reporting:

- primary: disease macro F1 + timing score
- secondary: tool efficiency profile
- tertiary: retrieval profile

## Risks and Concerns

### 1. Gold-label circularity

Risk:

- if gold is literally the same tool output the model sees, the benchmark is weak

Mitigation:

- use frozen offline label builders
- version and audit them separately

### 2. Sepsis semantics

Risk:

- `sepsis3.py` in the autoformalized library is not currently trustworthy as a benchmark-facing function

Mitigation:

- define sepsis as a composed task from infection + SOFA
- do not expose `query_sepsis3` in v1

### 3. Coagulopathy and CRRT gaps

Risk:

- not benchmark-exposed today

Mitigation:

- add adapters only after finalizing task contracts

### 4. Too much retrieval variance

Risk:

- unrestricted retrieval may dominate benchmark variance

Mitigation:

- separate trajectory-level retrieval budget from step-level evidence budget
- keep retrieval outputs compact and structured

### 5. Neurologic-label noisiness

Risk:

- a pure `gcs` interpretation can be confounded by sedation, intubation, or procedure context

Mitigation:

- document this as a benchmark caveat in v1
- consider adding auxiliary context fields later rather than blocking the first release

### 6. Hadm-linked evidence caveat

Risk:

- `bg` and `coagulation` heads are admission-linked rather than purely stay-linked

Mitigation:

- document them as time-bounded admission-visible evidence
- keep the cohort caveat explicit in the benchmark README and task specs

## Guideline Corpus Design

### Recommendation

Use a flat guideline text directory compatible with `search_guidelines`.

That helper expects:

- one `.txt` file per guideline
- flat directory, no recursion

So the benchmark should maintain a dedicated folder of curated guideline `.txt` files.

### Initial seed strategy

Start with:

- local generated guideline texts already used in the autoformalization workflow
- then add a small curated external seed set for the benchmark

Example external seed sources:

- [Early Recognition and Initial Management of Sepsis in Adult Patients](https://www.ncbi.nlm.nih.gov/books/NBK598311/)
- [Respiratory Failure - What Is Respiratory Failure? | NHLBI, NIH](https://www.nhlbi.nih.gov/health/respiratory-failure)
- [Acute Respiratory Distress Syndrome | NHLBI, NIH](https://www.nhlbi.nih.gov/health/ards)
- [Acute Kidney Injury - NIDDK](https://www.niddk.nih.gov/research-funding/research-programs/acute-kidney-injury)

Important note:

- some tasks, especially AKI, may ultimately need society guidelines such as KDIGO in addition to NIH-family sources
- that is not a blocker for the benchmark design, but it is worth acknowledging early

## Final Recommendation

The best high-level design is:

1. build an autoformalized-native rolling benchmark on the `48h` ICU cohort
2. use every-4-hour checkpoints
3. define a `9 + 1` task set:
   - 9 core tasks now
   - coagulopathy as the 10th after adding one adapter
4. build gold labels from frozen autoformalized-aligned label builders
5. use trajectory-level retrieval for guidelines and candidate functions
6. use step-level benchmark-facing evidence tools with stable schemas
7. evaluate on:
   - decision quality
   - timing quality
   - tool efficiency

This gives you the right balance of:

- difficulty
- fairness to the toolbox
- reproducibility
- manageable implementation scope

## Next Implementation Step

The next concrete deliverable should be a benchmark spec package with:

1. task spec files for each disease head
2. frozen gold-label contracts
3. benchmark-facing autoformalized tool adapter list
4. dataset schema for multitask rolling checkpoints
5. evaluation schema for accuracy, timing, and efficiency
