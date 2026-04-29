# General ICU Surveillance Dataset Design

Date: 2026-04-25

## Purpose

This document updates the surveillance benchmark design for the dataset-curation phase.

The benchmark goal is now:

- test the original general capability of the agent
- not improve the agent with extra helper scripts or heavily curated tool wrappers
- evaluate whether the agent can discover relevant guideline text and autoformalized functions on its own
- use official MIMIC-derived SQL as the ground truth, even when the autoformalized library does not perfectly support the task

This is a benchmark-first design, not an agent-optimization design.

## Core Benchmark Contract

The benchmark should intentionally preserve difficulty.

That means:

- do not expose the full autoformalized function library directly as a preselected toolbox
- do not add disease-specific wrapper tools just to improve performance
- do not build gold labels from autoformalized outputs
- do not tune special prompts per disease

Instead:

- let the agent search for guidelines
- let the agent search for functions
- let the agent inspect and load functions
- let the agent decide what to call
- score against official MIMIC-derived ground truth

## Available Tools

The benchmark now supports two runnable interfaces over the same checkpoint-scoped DuckDB session substrate.

### Mode A: Python-session mode

This is the original `zeroshot_python` path.

The model can execute short Python snippets inside a checkpoint-scoped DuckDB session and use native session helpers:

- `search_guidelines(keyword)`
- `get_guideline(name)`
- `search_functions(keyword)`
- `get_function_info(name)`
- `load_function(name)`
- `query_db(sql)`

### Mode B: Tool-first session mode

This is the new `session_tools` path.

The model does not need to write Python just to do retrieval or call a discovered function. The outer tools are:

- `search_guidelines(keyword)`
- `get_guideline(name)`
- `search_functions(keyword)`
- `get_function_info(name)`
- `load_function(name)`
- `call_function(function_name, arguments)`

Important design rules:

- the agent may discover additional functions through `search_functions`
- the full library should not be pre-exposed as a ready-made benchmark toolbox
- `call_function(...)` should auto-load the owner file when the requested function is not yet loaded
- if a function name is ambiguous across files, the model can disambiguate by explicitly using `load_function(name)` first

This keeps the benchmark faithful to the original discovery problem while allowing both a Python-first and a tool-first interface.

## Retrieval Logic

The retrieval logic should stay lightweight and original.

### Guideline retrieval

Guidelines are retrieved through the DuckDB session helpers:

- search by filename keyword
- open the selected `.txt` guideline file

There is no embedding-based retrieval and no benchmark-specific re-ranking layer.

### Function retrieval

Functions are retrieved through lightweight helpers:

- search by filename keyword
- inspect signature/docstring via `get_function_info`
- either load selected files explicitly with `load_function`
- or call the desired exported function directly with `call_function`, which auto-loads its owner file if needed

There is no benchmark-side shortlist of “good functions” passed to the agent up front.

## Agent Memory Design

The benchmark memory should also stay minimal.

At each checkpoint:

1. the agent works on the current `t_hour`
2. the decision model returns the final surveillance decision
3. a separate summarizer LLM call writes a very short checkpoint summary
4. that summary is appended to a dictionary keyed by `step_index`

At the next checkpoint, the agent should receive only:

- current `t_hour`
- currently available tools
- the summary dictionary from earlier steps

Example:

- `{0: "infection considered; no clear alert yet", 1: "respiratory support escalated; continue monitoring for sepsis and shock"}`

Important design rule:

- do not replay the full prior trajectory context
- do not replay all prior tool outputs verbatim
- do not build a hand-engineered long-memory scaffold

This makes the benchmark much closer to real constrained longitudinal reasoning.

## Ground Truth Design

Ground truth should use official MIMIC-derived SQL.

That is now a deliberate choice.

### Why use MIMIC-derived SQL

- it gives cleaner and more stable benchmark semantics
- it avoids circularity between the autoformalized tools and the labels
- it lets us measure the original performance gap of the autoformalized library honestly

### What this means

Task inclusion should no longer depend on whether the autoformalized library supports the task well.

Instead:

- include clinically important ICU surveillance states if they can be defined from MIMIC-derived SQL or simple extensions
- then evaluate how well the agent’s discovered autoformalized functions recover those states

### Acceptable ground-truth extensions

The benchmark may extend the standard derived tables with small transparent SQL definitions where needed.

Examples:

- septic shock from `sepsis3` + vasoactive support + lactate
- support-escalation subtypes from `ventilation`
- multi-agent vasoactive support from `vasoactive_agent`

The key is:

- official/derived-first labels
- transparent SQL definitions
- versioned and documented

### Selected surveillance families

The benchmark intentionally covers the major ICU monitoring axes rather than only one disease family:

- infection: suspicion and stronger microbiology-supported infection evidence
- sepsis: Sepsis-3 onset
- renal: AKI staging, oliguria, severe oliguria/anuria, and CRRT
- respiratory: HFNC/NIV, invasive ventilation, and PF-ratio hypoxemia
- hemodynamic: any vasoactive support, multi-agent support, septic shock, and shock with hypoperfusion
- neurologic: moderate and severe GCS impairment
- metabolic: lactate elevation and acidemia
- coagulation: INR-based coagulopathy

The detailed disease-by-disease rationale and checkpoint label criteria are documented in:

- [checkpoint_ground_truth_curation_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/checkpoint_ground_truth_curation_2026-04-25.md)

## Cohort Design

Use the existing surveillance cohort foundation:

- ICU stays with `LOS >= 48h`
- subject-level deterministic train/dev/test split
- checkpoint grid every `4` hours from `0` to `48`

Why this cohort still makes sense:

- enough room for rolling deterioration and delayed transitions
- large enough for many-task supervision
- already audited across ICU unit types and LOS ranges

Detailed cohort-finalization evidence is now in:

- [surveillance_dataset_cohort_audit_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/surveillance_dataset_cohort_audit_2026-04-25.md)
- [checkpoint_ground_truth_curation_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/checkpoint_ground_truth_curation_2026-04-25.md)
- [checkpoint_ground_truth_build_report_2026-04-25.md](/Users/chloe/Documents/New project/docs/surveilance/checkpoint_ground_truth_build_report_2026-04-25.md)

Reference cohort artifacts:

- [surveillance_stay_manifest.csv](/Users/chloe/Documents/New project/dataset/surveilance/surveillance_stay_manifest.csv)
- [surveillance_checkpoint_grid.csv](/Users/chloe/Documents/New project/dataset/surveilance/surveillance_checkpoint_grid.csv)
- [phase1_autoformalized_surveillance_dataset_report_2026-04-23.md](/Users/chloe/Documents/New project/docs/surveilance/phase1_autoformalized_surveillance_dataset_report_2026-04-23.md)

## Prompt Note

The runtime prompt should briefly define the decision semantics, rather than trying to teach full clinical criteria inside the prompt.

Recommended minimal wording:

- `suspected_conditions` means clinically meaningful concern that should keep monitoring focused on that condition family
- `alerts` means high-acuity or high-confidence states that justify escalation now
- the prompt should explicitly name the monitored surveillance families so the task scope is clear
- the prompt should present a simple workflow:
  - first use rolling memory
  - if memory is not enough for a disease family, search guideline criteria for that family
  - if that is still not enough, search the function library for useful functions for that family
  - use functions, and in Python-session mode also `query_db`, to inspect current patient evidence
  - then decide monitor vs suspect vs alert
- the prompt should state a preferred tool-use order:
  - search guidelines first for definitions
  - search functions next for reusable logic
  - inspect function info before calling or loading
  - in tool-first mode, call functions directly and let `call_function` auto-load when possible
  - use `load_function` explicitly when you want to pin a particular file or resolve ambiguity
  - in Python-session mode, use `query_db` when direct checkpoint evidence inspection is needed
- the prompt should include one general evidence principle:
  - do not claim that a disease family is normal, absent, or unchanged unless supported by current checkpoint evidence or explicit rolling memory
  - absence of retrieved evidence is not evidence of patient normality
  - if memory does not settle a family and current-step evidence is empty, the next move should usually be retrieval rather than a final negative decision

That is enough to anchor the decision interface while still requiring the agent to search guidelines for condition-specific detail.

## Prompt Modes

The benchmark now has two prompt-facing runtime modes.

### `zeroshot_python`

This mode uses a checkpoint-scoped DuckDB Python session.

The decision prompt should:

- describe the task as rolling surveillance rather than forecasting
- explicitly name the monitored surveillance families
- define the structured decision fields briefly
- carry only summary-memory from prior checkpoints
- expose the session helpers in the prompt payload:
  - `search_guidelines`
  - `get_guideline`
  - `search_functions`
  - `get_function_info`
  - `load_function`
  - `query_db`
- frame Python execution as fallback evidence gathering
- enforce a remaining-execution budget

The model may respond with either:

- one short Python snippet
- or one final surveillance decision JSON

### `session_tools`

This mode uses outer tools over the same hidden checkpoint-scoped session substrate.

The decision prompt should:

- describe the task as rolling surveillance rather than forecasting
- explicitly name the monitored surveillance families
- define the structured decision fields briefly
- carry only summary-memory from prior checkpoints
- expose the currently available tools in the prompt payload:
  - `search_guidelines`
  - `get_guideline`
  - `search_functions`
  - `get_function_info`
  - `load_function`
  - `call_function`
- prefer direct tool use over Python
- explain that `call_function` auto-loads the owner file when possible
- explain that `load_function` is optional and useful for explicit file pinning or ambiguity resolution

The model may respond with either:

- one tool-call JSON object
- or one final surveillance decision JSON

### Shared summary prompt

Both modes use the same separate summarizer step after each checkpoint decision.

That summarizer prompt should:

- see only the current checkpoint metadata, final decision, and compact current-step history
- write one very short summary
- return exactly `{"checkpoint_summary":"..."}` for the next checkpoint memory

The exact implemented prompt contracts for both modes are documented in:

- [general_icu_surveillance_pipeline_runbook_2026-04-27.md](/Users/chloe/Documents/New project/docs/surveilance/general_icu_surveillance_pipeline_runbook_2026-04-27.md)

## Decision Space Design

The benchmark should not use a tiny three-task label space.

It should use a larger ICU surveillance decision catalog, but still keep the output structured enough to score reliably.

## Recommended output shape

The final decision output at each checkpoint should remain structured, for example:

```json
{
  "global_action": "continue_monitoring | escalate",
  "suspected_conditions": ["infection", "aki_stage1", "resp_support_hfnc_niv"],
  "alerts": ["sepsis_alert", "aki_stage3_alert"],
  "priority": "low | medium | high",
  "rationale": "..."
}
```

Then a second summarizer call writes:

```json
{
  "checkpoint_summary": "short rolling memory summary"
}
```

The benchmark should score the structured decision fields, not just the free-text rationale.

## Recommended decision catalog

I recommend a catalog of `24` canonical surveillance decisions.

That is large enough to feel like real ICU monitoring, but still manageable for labeling and evaluation.

### Infection / sepsis family

1. `infection_suspected`
2. `infection_confirmed_or_strongly_supported`
3. `sepsis_alert`
4. `septic_shock_alert`

### Renal family

5. `aki_stage1`
6. `aki_stage2`
7. `aki_stage3`
8. `oliguria_6h`
9. `severe_oliguria_or_anuria`
10. `crrt_active`

### Respiratory family

11. `resp_support_hfnc_or_niv`
12. `resp_support_invasive_vent`
13. `hypoxemia_pf_lt_200`
14. `hypoxemia_pf_lt_100`

### Hemodynamic family

15. `vasoactive_support_any`
16. `vasoactive_multi_agent_or_high_intensity`
17. `shock_hypoperfusion_alert`

### Neurologic family

18. `gcs_moderate_impairment_9_12`
19. `gcs_severe_impairment_le_8`

### Metabolic / acid-base family

20. `hyperlactatemia_ge_2`
21. `severe_hyperlactatemia_ge_4`
22. `acidemia_ph_lt_7_30`
23. `severe_acidemia_ph_le_7_20`

### Hematologic / coagulation family

24. `coagulopathy_inr_ge_2`

## Runnable Pipeline Status

The design is now implemented in a minimally curated runnable form.

What is already wired:

- the finalized `2,000`-stay benchmark subset
- direct CSV loading for surveillance trajectories from:
  - [benchmark_2k_checkpoint_truth.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth.csv)
- the checkpoint-scoped DuckDB Python session backend
- lightweight guideline retrieval through `.txt` files in:
  - [guidelines/general_icu_autoformalized/txt](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/txt)
- function discovery and loading from:
  - [autoformalized_library/functions](/Users/chloe/Documents/New project/autoformalized_library/functions)
- rolling short-summary memory between checkpoints
- a separate post-decision summarizer call for memory writing
- surveillance-specific evaluation for action, condition-set, alert-set, and timing metrics

What remains intentionally minimal:

- no benchmark-side disease-specific helper wrappers
- no preselected function shortlist shown to the agent
- no benchmark-side retrieval reranking
- no condition-specific prompt tuning

The runnable operator notes now live in:

- [general_icu_surveillance_pipeline_runbook_2026-04-27.md](/Users/chloe/Documents/New project/docs/surveilance/general_icu_surveillance_pipeline_runbook_2026-04-27.md)

## Why this decision space is the right size

This design is better than a tiny disease list because:

- it includes both prevalent syndromes and clinically meaningful ICU states
- it includes stage-like severity when stage matters
- it allows several families to be positive at once
- it captures real escalation patterns instead of forcing one diagnosis per step

It is also better than trying to enumerate “hundreds of ICU diseases,” because:

- most ICU surveillance behavior is driven by organ dysfunction and support states
- many diagnoses collapse onto the same monitoring decisions
- a well-designed 20 to 50 decision catalog can cover most ICU surveillance situations even if it does not cover every named diagnosis

## Labeling Strategy

The dataset should be multi-label at each checkpoint.

That means:

- one checkpoint can have zero, one, or many positive decisions
- labels should be stored as a sparse or wide multi-hot structure
- hierarchical conflicts should be documented explicitly

Examples:

- `aki_stage3` implies the renal family is severe, but the benchmark can decide whether to:
  - mark only the highest stage, or
  - mark cumulative stages

Recommended rule:

- within stage families, use the highest active stage only
- across different families, allow full multi-label activation

So:

- `aki_stage3` should not also require `aki_stage1` and `aki_stage2` as separate positives
- but `aki_stage3` can co-exist with `sepsis_alert`, `resp_support_invasive_vent`, and `coagulopathy_inr_ge_2`

## Dataset Curation Plan

The dataset curation process should proceed in layers.

### Layer 1: cohort foundation

Already built:

- eligible stays
- split assignment
- checkpoint grid
- cohort distribution summaries

### Layer 2: ground-truth decision builders

For each decision in the catalog:

- define the SQL source
- define the first visible event rule
- define the checkpoint activation rule
- define family-specific precedence logic

Examples:

- `sepsis_alert`
  - based on `mimiciv_derived.sepsis3`
- `septic_shock_alert`
  - based on `sepsis3` plus vasoactive support plus lactate threshold
- `aki_stage2`
  - based on `mimiciv_derived.kdigo_stages`
- `resp_support_invasive_vent`
  - based on `mimiciv_derived.ventilation`

### Layer 3: task registry

Build a registry table containing:

- decision name
- family
- SQL source table(s)
- onset definition
- checkpoint activation definition
- precedence rule
- whether it is scored in `suspected_conditions`, `alerts`, or both

### Layer 4: labeled checkpoint dataset

Each row should correspond to one stay and one checkpoint.

It should include:

- stay metadata
- split
- `t_hour`
- checkpoint time
- multi-label decision columns
- global-priority label
- optional family summary columns

## Evaluation Design

Because the benchmark is multi-label and rolling, evaluation should also be multi-part.

### 1. Decision-set quality

Per checkpoint:

- exact-match rate on predicted decision set
- micro F1
- macro F1
- family-level F1

### 2. Timing quality

For alertable decisions:

- first-detection timing error
- false early alert rate
- missed alert rate

### 3. Retrieval quality

Because the benchmark explicitly includes discovery:

- how often the agent searched guidelines
- how often it searched functions
- whether it inspected useful functions before loading
- retrieval efficiency per trajectory

### 4. Tool economy

Do not optimize the benchmark for very large tool budgets.

Track:

- searches per checkpoint
- loads per checkpoint
- total loaded functions per trajectory

## What We Should Not Add

To keep the benchmark honest, do not add:

- a curated shortlist of recommended functions per task
- task-specific wrappers that directly answer the benchmark decisions
- extra benchmark scripts that precompute tool suggestions for the agent
- disease-specific memory templates
- custom prompt scaffolds per condition family

Those may improve agent performance, but they reduce the value of the benchmark.

## Main Risks

### 1. Search is filename-based, not semantic

The DuckDB session retrieval is based on simple filename matching.

That means:

- retrieval difficulty is real
- naming conventions matter
- search failure is part of the benchmark, not just noise

### 2. Mismatch between labels and discovered functions

This is intentional in the new benchmark contract.

But it means some tasks will be genuinely hard because:

- the ground truth is derived-first
- the discovered function support may be partial or weak

### 3. Decision-space sparsity

A 24-decision catalog is much richer than a small benchmark, but some labels will still be rare.

This will require:

- prevalence reporting
- careful train/dev/test checks
- possibly family-aware sampling for evaluation subsets

### 4. Memory compression tradeoff

Providing only the last `N` summaries is the right stress test, but it may cause:

- loss of long-range temporal detail
- accumulation of summary mistakes
- dependence on summary quality

That is acceptable, but it should be documented as a benchmark feature.

## Final Recommendation

For dataset curation, the best design is:

1. keep the `LOS >= 48h` surveillance cohort
2. keep the `4h` checkpoint grid
3. use DuckDB session search helpers as the primary agent-facing discovery interface
4. use official MIMIC-derived SQL as the ground truth
5. use a structured multi-label decision catalog of about `24` ICU surveillance decisions
6. use short rolling memory summaries instead of full history replay

This gives you a benchmark that is:

- hard
- realistic
- agent-discovery-centric
- not over-curated
- and still labelable at scale

## Next Design Step

Before building labels, the next artifact should be a decision registry spec:

- one row per decision
- source table(s)
- SQL onset rule
- checkpoint activation rule
- alert/suspect family
- precedence logic

That registry will be the bridge from this design document to the actual labeled dataset build.
