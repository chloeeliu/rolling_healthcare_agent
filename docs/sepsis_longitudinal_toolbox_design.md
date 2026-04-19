# Sepsis Longitudinal Toolbox Design

## Scope

This note proposes the next-stage longitudinal benchmark design for **single-task sepsis**.

The goal is to move beyond the current step-local policy, where the agent effectively:

- sees the current checkpoint
- calls a fixed small set of tools
- predicts the current sepsis label

Even with rolling history enabled, the current setup still behaves like a repeated single-step policy because:

- the required tool set is small and mostly fixed
- the agent is forced into the same tool order at every checkpoint
- the evaluation mostly scores label accuracy and coarse grounding, not real longitudinal efficiency

The next design should instead behave like a **real longitudinal monitoring task**:

- each checkpoint provides compact summaries of all previous checkpoints
- the model chooses whether to call tools at the current checkpoint
- the model can call multiple tools, with no hard-coded required order
- the benchmark evaluates both decision quality and tool-use quality

Relevant current implementation:

- runner and CLI: [src/sepsis_mvp/cli.py](/Users/chloe/Documents/New project/src/sepsis_mvp/cli.py)
- environment loop: [src/sepsis_mvp/environment.py](/Users/chloe/Documents/New project/src/sepsis_mvp/environment.py)
- agent/controller: [src/sepsis_mvp/agent.py](/Users/chloe/Documents/New project/src/sepsis_mvp/agent.py)
- official runtime: [src/sepsis_mvp/tools.py](/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py)
- autoformalized runtime: [src/sepsis_mvp/autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)
- current zero-shot/raw design note: [docs/zeroshot_raw_pipeline_design.md](/Users/chloe/Documents/New project/docs/zeroshot_raw_pipeline_design.md)

## Recommendation

### Short answer

This should be built as a **new protocol within the same pipeline**, not as a silent rewrite of the current `rolling_with_history`.

### Why

`rolling_with_history` currently means:

- same dataset
- same task labels
- same fixed tool semantics
- same per-step tool requirement logic
- plus historical context

The new design changes much more than that:

- tool selection becomes free-form instead of fixed-order
- the tool surface expands from 2 sepsis tools to a toolbox
- the evaluation target expands from label accuracy to efficiency and longitudinal evidence management

So overloading `rolling_with_history` would make comparisons ambiguous.

### Recommended protocol naming

Keep:

- `rolling_no_history`
- `rolling_with_history`

Add a new protocol:

- `rolling_toolbox_with_history`

This keeps the current protocols stable and lets us compare:

1. fixed-tool repeated-step baseline
2. fixed-tool plus longitudinal summaries
3. agentic toolbox plus longitudinal summaries

That makes ablations much cleaner.

## Design Goal

The design goal is to benchmark whether a model can do **efficient longitudinal sepsis monitoring**, not just whether it can classify a checkpoint.

That means the agent should learn policies like:

- if infection is already clearly established, do not keep re-checking infection every step
- if infection is absent and nothing meaningful changed, maybe do not call anything
- if infection is positive but SOFA evidence is weak, focus on organ-dysfunction tools
- if the history already shows stable infection positivity and stable high SOFA, additional repeated calls have low utility

This is the core behavior that the current fixed-order setup cannot reveal.

## Proposed Protocol

### Name

`rolling_toolbox_with_history`

### Scope for first implementation

Only single-task `sepsis`.

That narrower scope is the right starting point because:

- the label space is already defined
- the current task is clinically coherent
- the history summary format is already partially in place
- the efficiency logic is easiest to define for sepsis first

## Per-Step Interaction Contract

At each checkpoint:

1. The model receives:
   - current checkpoint metadata
   - full prior rolling history for this stay
   - the available sepsis toolbox
   - an instruction to call only useful tools
2. The model may:
   - call zero tools and decide immediately
   - call one tool
   - call multiple tools
   - stop whenever it is ready to return a final action
3. The final action remains the same:
   - `keep_monitoring`
   - `infection_suspect`
   - `trigger_sepsis_alert`

### Important property

There should be **no hard-coded mandatory tool order** in this protocol.

The benchmark should evaluate whether the model can decide **which** tool is useful at the current checkpoint, not whether it can follow a prescribed sequence.

## History Format

The history should be explicit and flat, covering **all previous checkpoints**.

Example for current step `3`:

```json
{
  "protocol": "rolling_toolbox_with_history",
  "rolling_history": [
    {
      "step_index": 0,
      "t_hour": 0,
      "infection": false,
      "infection_first_visible_hour": null,
      "infection_first_visible_time": null,
      "sofa_score": null,
      "max_sofa_score_so_far": null,
      "evidence": []
    },
    {
      "step_index": 1,
      "t_hour": 4,
      "infection": true,
      "infection_first_visible_hour": 4,
      "infection_first_visible_time": "2150-01-01T04:00:00",
      "sofa_score": 1,
      "max_sofa_score_so_far": 1,
      "evidence": [
        {
          "antibiotic": "cefepime",
          "antibiotic_time": "2150-01-01T04:00:00",
          "culture_time": "2150-01-01T05:00:00",
          "specimen": "blood"
        }
      ]
    },
    {
      "step_index": 2,
      "t_hour": 8,
      "infection": true,
      "infection_first_visible_hour": 4,
      "infection_first_visible_time": "2150-01-01T04:00:00",
      "sofa_score": 2,
      "max_sofa_score_so_far": 2,
      "evidence": [
        {
          "antibiotic": "cefepime",
          "antibiotic_time": "2150-01-01T04:00:00",
          "culture_time": "2150-01-01T05:00:00",
          "specimen": "blood"
        }
      ]
    }
  ]
}
```

### Prompt framing

The prompt should explicitly say:

- this is a real longitudinal task
- rolling history contains all earlier checkpoint summaries
- do not re-query tools with low expected value
- call tools only when they provide new or missing evidence for the current decision

## Toolbox Design

### Principle

The toolbox should expose **decision-relevant evidence slices**, not giant raw dumps and not only one monolithic sepsis tool.

The first version should provide a shared high-level tool interface across:

- `official`
- `autoformalized`

The exact implementation can differ under the hood, but the visible tool names and return schemas should match as closely as possible.

### Verified shared candidate set

Using the current codebase exactly as it exists today, the strict shared toolbox across `official` and `autoformalized` is:

1. `query_suspicion_of_infection`
2. `query_sofa`
3. `query_ventilation_status`
4. `query_kdigo_stage`

These are all already exposed in both runtimes:

- official runtime in [tools.py](/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py)
- autoformalized runtime in [autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)

### Requested additional candidate: `query_sirs`

`query_sirs` is **not** currently a strict shared benchmark-facing tool.

Current status:

- an autoformalized function exists at [functions/sirs.py](/Users/chloe/Documents/New project/autoformalized_library/functions/sirs.py)
- but there is no benchmark-facing `query_sirs` adapter in [autoformalized.py](/Users/chloe/Documents/New project/src/sepsis_mvp/autoformalized.py)
- and there is no official runtime `query_sirs` in [tools.py](/Users/chloe/Documents/New project/src/sepsis_mvp/tools.py)

So if we want to stay within the user preference of **existing candidates only**, the first protocol version should use the shared 4-tool set above and treat `query_sirs` as a later optional extension.

### Why this 4-tool shape is still useful

Even without `query_sirs`, this toolbox already allows the agent to:

- inspect infection evidence
- inspect organ dysfunction via SOFA
- inspect respiratory support trajectory
- inspect AKI trajectory as a possible distractor or alternative severity cue

This is not a pure sepsis-minimal toolbox, but it is a realistic shared candidate set that can reveal longitudinal tool-choice behavior.

## How To Build The Toolbox From Existing Libraries

### Official backend

Already benchmark-exposed:

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_ventilation_status`

Not currently benchmark-exposed:

- `query_sirs`

### Autoformalized backend

Already benchmark-exposed:

- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage` backed by `kdigo_stages`
- `query_ventilation_status`

Exists in the library but not currently benchmark-exposed:

- `sirs`

So the clean first implementation should use the shared benchmark-exposed 4-tool set.

## Agent Behavior

### Current behavior

The current agent logic for sepsis effectively does:

1. infection tool
2. if infection positive, SOFA tool
3. decide

That is reasonable for a fixed-tool baseline, but it is not a true toolbox policy.

### New toolbox behavior

For `rolling_toolbox_with_history`, the controller should instead:

- present the full toolbox
- allow repeated tool interactions until the model returns a final action
- avoid any required-tool ordering logic
- still keep a maximum safety cap to prevent infinite loops

### First implementation status

The first implementation should stay deliberately narrow:

- scope: single-task `sepsis` only
- visible toolbox: `query_suspicion_of_infection`, `query_sofa`, `query_kdigo_stage`, `query_ventilation_status`
- history: keep the compact rolling sepsis summaries already used in `rolling_with_history`
- controller: remove required-tool forcing and let the model decide whether to call a tool or act

This keeps the benchmark comparison clean while still making the task genuinely longitudinal and tool-selective.

### Practical recommendation

Use a generous but finite cap such as:

- `max_tool_calls_per_step = 8` or `10`

This is still “freely choose” in benchmark terms, while keeping runs bounded.

### Prompt guidance

The prompt should strongly encourage:

- call a tool only if it is likely to change the current decision
- do not repeat a tool if history already provides stable sufficient evidence
- if infection has already been clearly established, focus on organ dysfunction rather than re-checking infection
- if both infection and SOFA status are already sufficiently established in history, consider deciding without new calls

## Evaluation Design

The new protocol should report both **decision quality** and **tool-use quality**.

### A. Existing metrics to keep

- step accuracy
- macro F1
- infection timing
- sepsis alert timing
- standard grounding

These preserve continuity with the current benchmark.

### B. New tool-efficiency metrics

I recommend adding the following.

#### 1. Repeated-call rate

Definition:

- fraction of tool calls that repeat the same tool after that tool’s relevant evidence was already stably established earlier in the same trajectory

Examples:

- repeated infection calls after infection is already positive and unchanged
- repeated total SOFA calls when the recent history already shows stable high SOFA and no new evidence-gathering need

This metric should be reported overall and by tool.

#### 2. Action-without-sufficient-evidence rate

Definition:

- fraction of non-baseline final actions returned without enough evidence in either:
  - current-step calls
  - rolling history

Suggested minimum evidence rules:

- `infection_suspect` requires infection evidence
- `trigger_sepsis_alert` requires:
  - infection evidence
  - alert-level organ dysfunction evidence

This is stricter and more longitudinal than the current grounding metric.

#### 3. Necessary-call coverage

Definition:

- for checkpoints where new evidence was needed to support the correct decision, how often did the model call at least one necessary tool

Examples:

- infection-negative to infection-positive transition should usually be accompanied by infection-relevant evidence acquisition unless already present in history
- infection-positive to sepsis-alert transition should usually be accompanied by SOFA-relevant evidence acquisition unless already present in history

#### 4. Marginal utility of call

Definition:

- fraction of tool calls whose output materially changed the evidence state relative to the immediately preceding history

A call has positive marginal utility if it:

- reveals a new infection state
- updates first visible infection time
- raises max SOFA
- reveals new SOFA components relevant to alerting
- otherwise changes decision-relevant state

Low-utility calls are not necessarily “wrong,” but they are inefficient.

#### 5. History-use efficiency

Definition:

- rate at which the agent refrains from calling tools when rolling history already contains sufficient evidence for the correct current action

This is a direct measure of whether the policy is actually longitudinal.

## Grounding Redesign

The current grounding logic is mostly call-presence based.

For the toolbox protocol, grounding should become more specific:

- infection-grounded if infection-positive action is supported by infection tool or equivalent infection summary already in history
- alert-grounded if trigger action is supported by infection plus organ dysfunction evidence
- unsupported escalation if the agent escalates with neither current nor historical evidence

This should be evaluated per step and aggregated.

## Why This Should Stay In The Same Runner

Even though this is a new protocol, it should still live in the same benchmark pipeline because:

- it uses the same trajectory datasets
- it uses the same checkpoint sequence
- it uses the same final labels
- it uses the same rollout object
- it can reuse most of the environment and evaluation framework

So this is **not** a fully separate pipeline.

It is a **new protocol mode** inside the same benchmark system.

## Implementation Sketch

### Phase 1

Add protocol:

- `rolling_toolbox_with_history`

### Phase 2

Add sepsis toolbox definitions:

- start with the shared benchmark-exposed 4-tool set
- `query_suspicion_of_infection`
- `query_sofa`
- `query_kdigo_stage`
- `query_ventilation_status`

Treat `query_sirs` as a phase-2 option only if we later decide to add a thin shared adapter in both backends.

### Phase 3

Update agent/controller:

- no fixed required-tool order for this protocol
- prompt exposes toolbox and rolling history
- prompt encourages efficient tool use

### Phase 4

Update environment:

- allow multiple tool calls until final action
- maintain same current-step history
- carry forward rolling longitudinal summaries

### Phase 5

Add evaluation:

- repeated-call rate
- action-without-sufficient-evidence rate
- necessary-call coverage
- marginal utility of call
- history-use efficiency

## Recommendation

Build this as:

- **same benchmark pipeline**
- **new protocol**
- **single-task sepsis first**

Concretely:

- do **not** replace `rolling_with_history`
- add `rolling_toolbox_with_history`

That gives the cleanest comparison story:

1. fixed-step no-history
2. fixed-step with-history
3. agentic toolbox with-history

This is the right level of change for the task you want to study.
