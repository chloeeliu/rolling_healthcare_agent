# Zero-Shot Raw Sepsis Bad-Case Analysis

## Scope

This note analyzes the latest observed failure trace from the new `zeroshot_raw` backend for single-task sepsis monitoring.

The goal is not to score the run. The goal is to understand:

- what the model appears to be trying to do
- what information it is asking from raw MIMIC
- why the run looks "stuck"
- which parts are model behavior versus pipeline behavior
- what the next guardrails should be

The analysis is based on:

- the current zero-shot controller in [src/sepsis_mvp/agent.py](/Users/chloe/Documents/New project/src/sepsis_mvp/agent.py)
- the raw execution runtime in [src/sepsis_mvp/zeroshot_raw.py](/Users/chloe/Documents/New project/src/sepsis_mvp/zeroshot_raw.py)
- the benchmark loop in [src/sepsis_mvp/environment.py](/Users/chloe/Documents/New project/src/sepsis_mvp/environment.py)
- the user-provided event trace excerpt for `trajectory_id = mimiciv_stay_30058012`, `t_hour = 0`

## Executive Summary

The latest bad case is no longer a JSON parser failure. The model is now successfully returning fenced Python, and the agent is successfully extracting it. The run fails one layer later: the generated Python itself is truncated and therefore syntactically incomplete.

The important distinction is:

- old failure mode: model output could not be parsed as JSON
- new failure mode: model output can be parsed as code, but the code is incomplete

That is why the logs show:

- `model_output_raw` containing a Python block
- `tool_call` to `run_python`
- `tool_output` with `SyntaxError`
- another `model_output_raw` that tries to patch the previous code
- another `SyntaxError`

So the system is not stuck in the JSON repair loop. It is stuck in a code-generation retry loop.

## What The Model Is Trying To Do

From the trace, the model is attempting to reconstruct the full sepsis ladder from raw tables in one large script at `t_hour = 0`.

It is trying to answer two questions at once:

1. Is suspected infection already visible?
2. Is there already enough organ dysfunction evidence to justify `trigger_sepsis_alert`?

To do that, it asks for:

- hospital prescriptions as a proxy for systemic antibiotics
- microbiology events as a proxy for cultures
- positive cultures as supporting evidence
- ICU charted variables and hospital labs as proxies for SOFA components
- ICU inputevents as a proxy for vasopressor use
- ICU outputevents as a proxy for urine output

In other words, the model is not choosing a minimal next query. It is trying to write a full raw-MIMIC sepsis workup script in a single turn.

## What The Model Asked For In This Trace

The first generated block tries to inspect:

- `mimiciv_hosp.prescriptions`
  - counts of antibiotics before `visible_until`
  - manual route filters like `IV`, `PO`, `IM`, `SC`
- `mimiciv_hosp.microbiologyevents`
  - counts of cultures before `visible_until`
  - counts of positive cultures
- `mimiciv_icu.chartevents`
  - PaO2
  - FiO2
  - MAP
  - GCS components
- `mimiciv_hosp.labevents`
  - platelets
  - bilirubin
  - creatinine
- `mimiciv_icu.inputevents`
  - vasopressor itemids
- `mimiciv_icu.outputevents`
  - urine output

That means the model is implicitly trying to rebuild:

- suspected infection
- a SOFA-like organ dysfunction summary
- a final 3-way benchmark label

## What The Model Is Not Doing

The trace is equally informative for what the model is *not* doing.

It is not:

- starting with schema discovery such as `DESCRIBE` or `information_schema`
- checking one table at a time
- first asking only whether infection suspicion is visible
- first asking only whether a prior tool error was caused by truncation
- restarting with a small fresh snippet after syntax failure

Instead, it assumes:

- route filters from memory
- itemids from memory
- approximate SOFA logic from memory
- that the whole decision can be reconstructed in one shot

This is exactly the kind of behavior that makes zero-shot raw generation brittle.

## Why The First Block Failed

The first `run_python` call failed with:

- `SyntaxError`
- `unterminated triple-quoted string literal`

This happened because the model output was cut off inside a triple-quoted SQL string.

That means:

- the output parser accepted the code block
- the runtime executed it
- Python failed before any SQL could meaningfully run

This is not a schema error. It is a code truncation error.

## Why The Second Block Failed

The second block is a "repair" attempt from the model, but it does not truly recover.

It fails with:

- `SyntaxError`
- `'[' was never closed`

This second error is again consistent with truncation. The code ends in the middle of:

- `gcs_motor.iloc[`

So the model is still producing incomplete code. The retry did not switch strategies. It simply continued trying to write a long multi-query script.

## Why The Run Looks Stuck

The environment allows repeated tool interactions per checkpoint in [src/sepsis_mvp/environment.py](/Users/chloe/Documents/New project/src/sepsis_mvp/environment.py), and the zero-shot prompt allows multiple Python executions per checkpoint in [src/sepsis_mvp/agent.py](/Users/chloe/Documents/New project/src/sepsis_mvp/agent.py).

So once the model falls into this pattern:

- write a large script
- get syntax error
- try to patch the large script
- get another syntax error

it can spend the whole checkpoint budget retrying code instead of making progress.

This is a coordination failure between:

- the model's tendency to overbuild
- the permissive code extractor
- the absence of a syntax pre-check before `run_python`

## What The Trace Suggests About The Model's Internal Strategy

At a high level, the model seems to be using this latent policy:

1. Reconstruct all relevant sepsis evidence directly from raw MIMIC.
2. Try to derive both infection and organ dysfunction in one script.
3. Use counts and threshold-like checks as rough proxies for benchmark labels.
4. If execution fails, continue the previous script rather than restarting smaller.

That is an understandable strategy, but it is poorly matched to this pipeline.

The benchmark would work much better if the model behaved like:

1. Ask one short question.
2. Read the result.
3. Ask the next short question.
4. Commit to an action once the minimum needed evidence is visible.

The current trace shows the opposite.

## Additional Quality Issues Visible In The Generated Code

Even ignoring truncation, the generated code already shows several likely reasoning or implementation issues:

1. It tries to recreate suspected infection using simple counts rather than the official asymmetric antibiotic-culture window logic.
2. It hardcodes medication routes and itemids from memory instead of verifying them.
3. It uses broad "presence of abnormality" checks rather than true SOFA scoring logic.
4. Some SQL conditions appear under-parenthesized around `AND` and `OR`, which could change semantics even if the code were complete.
5. It uses a monolithic script structure instead of preserving checkpoint budget for iterative discovery.

So the trace is useful even beyond truncation: it shows how much hidden burden the raw zero-shot baseline puts on the model.

## Root Cause Breakdown

The bad case is best understood as three stacked issues.

### 1. Task difficulty

The model is being asked to do:

- program synthesis
- raw database querying
- temporal visibility reasoning
- clinical mapping to benchmark labels

all at once.

### 2. Output-shape fragility

Even after moving from JSON-escaped code to fenced Python, the model can still produce code that is too long for a clean complete generation.

### 3. Controller guardrail gap

The controller currently accepts a code block and sends it straight to `run_python`. It does not yet:

- require a closed fence only
- compile the code before execution
- detect truncation-like syntax errors and request a short fresh restart

## What This Bad Case Does *Not* Mean

This trace does not mean:

- the raw runtime cannot access the right tables
- `query_db` is broken
- the benchmark dataset is malformed
- the model is refusing to reason

It means the current zero-shot execution contract still gives the model enough freedom to produce oversized, fragile code.

## Recommended Next Fixes

The most important next changes are controller-side, not dataset-side.

### 1. Reject open or obviously incomplete code blocks

The zero-shot extractor in [src/sepsis_mvp/agent.py](/Users/chloe/Documents/New project/src/sepsis_mvp/agent.py) should only accept:

- a closed fenced Python block
- or a final action JSON object

An open-ended block should be treated as invalid output, not executable code.

### 2. Compile code before calling `run_python`

Before issuing the tool call, the agent should run:

- `compile(code, "<model>", "exec")`

If compilation fails with truncation-like syntax errors, the controller should ask for a fresh short snippet instead of sending the code to the runtime.

### 3. Add a truncation-specific repair prompt

The current retry behavior is too generic. After a truncation-like syntax error, the repair prompt should say:

- start over
- do not continue the prior script
- use one short complete snippet
- do only one query or one check
- avoid triple-quoted SQL

### 4. Prefer small-step execution

The prompt should keep pushing the model toward:

- infection first
- then organ dysfunction
- then final action

rather than "rebuild all of sepsis in one pass."

### 5. Consider lightweight code-size limits

If a code snippet is excessively long, the controller can reject it before execution and ask for:

- fewer lines
- fewer queries
- one focused subproblem

## Why This Failure Is Still Valuable

This bad case is actually a useful baseline result.

It demonstrates that in the raw zero-shot setting, a strong model does not naturally behave like a careful monitoring agent. It tends to behave like an overconfident code generator trying to reconstruct an entire clinical concept stack from memory.

That is precisely the experimental point of this baseline:

- official backend shows what happens when concept abstractions are provided
- autoformalized backend shows what happens when raw logic is compiled into reusable functions
- zero-shot raw shows what happens when the model must invent the concept extraction process itself

This trace is therefore not just a bug report. It is evidence that the raw zero-shot setting meaningfully exposes the value of derived abstractions and controller guardrails.
