# General ICU Surveillance Pipeline Runbook

Date: 2026-04-27

## Purpose

This runbook describes the concrete runnable pipeline for the general ICU surveillance benchmark.

The goal is to stay faithful to the benchmark design:

- ground truth comes from MIMIC-derived SQL
- the agent discovers guideline files and autoformalized functions at runtime
- the benchmark does not add disease-specific helper scripts to improve agent performance

## Current Pipeline Shape

The runnable surveillance benchmark now supports two interfaces over the same checkpoint-scoped session substrate.

### Shared pipeline backbone

1. load the finalized surveillance benchmark CSV
2. convert each ICU stay into a rolling trajectory
3. open a fresh checkpoint-scoped session for each checkpoint
4. expose retrieval and function-discovery capabilities
5. let the agent gather evidence only when needed
6. collect one final structured surveillance decision at each checkpoint
7. call a separate summarizer LLM to write one short checkpoint summary
8. append that summary into a dictionary keyed by `step_index`
9. score predictions against the checkpoint ground truth

### Mode A: `zeroshot_python`

- the model writes short Python snippets when it needs extra evidence
- the session provides native helpers such as `search_guidelines`, `search_functions`, `load_function`, and `query_db`

### Mode B: `session_tools`

- the model does not need to write Python for retrieval or function calling
- the outer tools are `search_guidelines`, `get_guideline`, `search_functions`, `get_function_info`, `load_function`, and `call_function`
- `call_function` auto-loads the owner file if the requested function is not already loaded

## Inputs

### Benchmark dataset

The main runnable dataset input is:

- [benchmark_2k_checkpoint_truth.csv](/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth.csv)

This file already contains:

- the finalized `2,000`-stay benchmark subset
- split assignment
- all rolling checkpoints
- family-level `suspected_conditions`
- family-level `alerts`
- `global_action`
- `priority`

### DuckDB database

The runtime DuckDB database is:

- `/Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db`

### Guideline retrieval corpus

The lightweight filename-based guideline corpus is:

- [guidelines/general_icu_autoformalized/txt](/Users/chloe/Documents/New project/guidelines/general_icu_autoformalized/txt)

It now includes:

- `general_icu_surveillance.txt`
- `infection.txt`
- `sepsis.txt`
- `aki.txt`
- `oliguria.txt`
- `respiratory_support.txt`
- `hemodynamic_shock.txt`
- `neurologic_deterioration.txt`
- `hyperlactatemia.txt`
- `acidemia.txt`
- `coagulopathy.txt`

### Autoformalized function library

The runtime function-discovery directory is:

- [autoformalized_library/functions](/Users/chloe/Documents/New project/autoformalized_library/functions)

The agent is expected to use runtime discovery rather than receiving a benchmark-curated shortlist.

In Python-session mode, discovery happens through session helpers.

In tool-first mode, discovery happens through outer tools:

- `search_functions(keyword)`
- `get_function_info(name)`
- `load_function(name)`
- `call_function(function_name, arguments)`

## Runtime Contract

The surveillance path now has two runnable backends:

- `zeroshot_python`
- `session_tools`

Important clarification:

- the runnable surveillance benchmark still does **not** use the older structured `autoformalized` backend as the primary agent interface
- both runnable modes still discover files from [autoformalized_library/functions](/Users/chloe/Documents/New project/autoformalized_library/functions) at runtime
- the difference is only the interaction surface:
  - `zeroshot_python` exposes discovery helpers inside Python
  - `session_tools` exposes discovery helpers as outer tools

Both modes use the same checkpoint-scoped visibility rules and the same rolling-summary memory contract.

The decision-model output contract per checkpoint is:

```json
{
  "global_action": "continue_monitoring | escalate",
  "suspected_conditions": ["..."],
  "alerts": ["..."],
  "priority": "low | medium | high",
  "recommended_next_tools": ["..."],
  "rationale": "..."
}
```

Then the separate summarizer call writes:

```json
{
  "checkpoint_summary": "..."
}
```

The decision prompt should only briefly define the semantics of `suspected_conditions` and `alerts`; detailed disease criteria should come from retrieved guideline text and discovered functions.

## Key Prompt Shape

### Decision step

The decision model sees:

- current `stay_id`
- current `t_hour`
- the most recent rolling summaries only
- cross-step summary memory as a simple dictionary:
  - `{"0": "...", "1": "...", ...}`
- within-checkpoint tool history for the current checkpoint only

Mode-specific access:

- in `zeroshot_python`, the model gets a checkpoint-scoped Python session with:
  - `search_guidelines`
  - `get_guideline`
  - `search_functions`
  - `get_function_info`
  - `load_function`
  - `query_db`
- in `session_tools`, the model gets outer tools:
  - `search_guidelines`
  - `get_guideline`
  - `search_functions`
  - `get_function_info`
  - `load_function`
  - `call_function`

The key system instructions are:

- this is rolling monitoring, not forecasting
- use only data visible by the current checkpoint
- monitor these families explicitly:
  - infection and sepsis
  - renal injury and urine-output failure, including CRRT when relevant
  - respiratory support escalation and hypoxemia
  - hemodynamic instability, vasoactive support, and shock
  - neurologic deterioration
  - metabolic failure, including lactate elevation and acidemia
  - coagulation abnormality
- discover guideline text and functions yourself
- default to direct decision when the current summaries and evidence are already sufficient
- prefer this tool order:
  - search guideline files for definitions
  - search function files for reusable logic
  - inspect function info to find the right entrypoint
  - in `session_tools`, prefer `call_function` and let it auto-load when possible
  - use `load_function` explicitly when you want to pin a specific file first or resolve ambiguity
  - in `zeroshot_python`, use `query_db` when direct checkpoint evidence inspection is needed
- in `zeroshot_python`, treat Python execution as fallback evidence gathering rather than the default first move
- return either one short Python snippet or one final surveillance decision in `zeroshot_python`
- return either one outer-tool call or one final surveillance decision in `session_tools`
- do not write the memory summary in the decision response

### Detailed prompt: `zeroshot_python`

The implemented Python-session decision prompt has two messages.

System message:

- tells the model it is a `general ICU rolling surveillance agent operating in a checkpoint-scoped DuckDB Python session`
- states this is `rolling monitoring, not forecasting`
- states visible tables already contain only checkpoint-available data
- tells the model to default to a direct final decision when summaries and current evidence are enough
- allows one short Python snippet only when more guideline, function, or patient-state evidence is needed
- says the Python session persists only within the current checkpoint
- explicitly names the monitored surveillance families
- briefly defines:
  - `suspected_conditions`
  - `alerts`
  - `global_action`
  - `priority`
- states that memory summary generation is handled by a separate summarizer call
- marks Python execution as fallback evidence gathering rather than the default first move
- states the preferred search order:
  - guideline files
  - autoformalized functions
  - inspect and load functions
  - `query_db` for direct evidence inspection
- lists the session helpers available inside Python:
  - `search_guidelines`
  - `get_guideline`
  - `search_functions`
  - `get_function_info`
  - `load_function`
  - `query_db`
- gives the Python execution contract:
  - use `query_db(sql, params=None)` for database access
  - use the retrieval helpers directly inside the session
  - preloaded variables are `stay_id`, `subject_id`, `hadm_id`, `visible_until`, `pd`, `np`, `datetime`, `timedelta`
  - set `RESULT` and/or print concise findings
  - keep snippets short
  - do not open database connections directly
- ends with the final decision JSON contract
- appends the current `remaining_python_executions` budget

User message payload:

```json
{
  "step_input": {
    "trajectory_id": "...",
    "stay_id": 30004144,
    "step_index": 3,
    "t_hour": 24,
    "task_name": "general_icu_surveillance"
  },
  "tool_backend": "zeroshot_python",
  "session_helpers": [
    "search_guidelines(keyword='')",
    "get_guideline(name)",
    "search_functions(keyword='')",
    "get_function_info(name)",
    "load_function(name)",
    "query_db(sql, params=None)"
  ],
  "remaining_python_executions": 4,
  "rolling_history": {
    "0": "summary ...",
    "1": "summary ..."
  },
  "history": {
    "python_executions": [],
    "sql_executions": [],
    "tool_outputs": []
  }
}
```

Allowed response shapes:

1. one Python snippet
```python
RESULT = search_functions("sofa")
```

2. one final decision JSON
```json
{
  "global_action": "continue_monitoring",
  "suspected_conditions": [],
  "alerts": [],
  "priority": "low",
  "recommended_next_tools": ["search_functions('sofa')"],
  "rationale": "..."
}
```

### Detailed prompt: `session_tools`

The implemented tool-first decision prompt also has two messages.

System message:

- tells the model it is a `general ICU rolling surveillance agent operating in a checkpoint-scoped session-tools mode`
- states this is `rolling monitoring, not forecasting`
- states visible data already contain only checkpoint-available information
- tells the model to default to a direct final decision when current summaries and evidence are enough
- asks for one tool call only when more evidence is needed
- explicitly names the same monitored surveillance families
- briefly defines:
  - `suspected_conditions`
  - `alerts`
  - `global_action`
  - `priority`
- says the memory summary is written by a separate summarizer call
- states the preferred tool order:
  - search guideline files
  - search autoformalized function files
  - inspect function info
  - call the function directly
- explicitly says:
  - `call_function` auto-loads the owning file if needed
  - `load_function` is optional
  - if a function name could come from more than one file, explicitly load the file you want before calling it
- lists the currently available outer tools with short descriptions
- gives concrete tool-call JSON examples
- ends with the same final decision JSON contract

User message payload:

```json
{
  "step_input": {
    "trajectory_id": "...",
    "stay_id": 30004144,
    "step_index": 3,
    "t_hour": 24,
    "task_name": "general_icu_surveillance"
  },
  "tool_backend": "session_tools",
  "available_tools": [
    "search_guidelines",
    "get_guideline",
    "search_functions",
    "get_function_info",
    "load_function",
    "call_function"
  ],
  "already_called_tools": ["search_functions"],
  "tool_results_by_name": {
    "search_functions": {
      "ok": true,
      "matches": ["sofa"]
    }
  },
  "rolling_history": {
    "0": "summary ...",
    "1": "summary ..."
  }
}
```

Allowed response shapes:

1. one outer-tool call
```json
{
  "tool_name": "call_function",
  "arguments": {
    "function_name": "compute_sofa_score",
    "arguments": {
      "stay_id": 30004144
    }
  }
}
```

2. one final decision JSON
```json
{
  "global_action": "escalate",
  "suspected_conditions": ["infection", "sepsis"],
  "alerts": ["sepsis_alert"],
  "priority": "high",
  "recommended_next_tools": ["search_functions('vasoactive_agent')"],
  "rationale": "..."
}
```

### Repair behavior

Both decision modes have a repair pass.

- if the model output is not valid JSON or does not match the expected shape
- the runtime appends the invalid assistant output
- then adds a short user repair instruction
- the repair instruction requires:
  - JSON only
  - no extra text
  - either one allowed tool call or one final surveillance decision

For `zeroshot_python`, a separate repair path is also used when the model exceeds its remaining Python-execution budget and must commit to a final decision.

### Summary step

The summarizer sees:

- the current checkpoint metadata
- the final surveillance decision
- a compact digest of the current checkpoint tool/code history

The key system instructions are:

- write one very short checkpoint summary
- under 20 words when possible
- mention only the key active state or change
- return exactly `{"checkpoint_summary":"..."}` and nothing else

Detailed summary prompt shape:

System message:

- says this is the rolling memory summary writer for the general ICU surveillance benchmark
- says this is a separate summarizer step after the surveillance decision is already final
- asks for one very short summary for the next checkpoint
- requires:
  - under 20 words when possible
  - only the key active state or change
  - no full rationale restatement
  - no markdown
  - exact JSON object `{"checkpoint_summary":"..."}`

User message payload:

```json
{
  "step_input": {
    "trajectory_id": "...",
    "stay_id": 30004144,
    "step_index": 3,
    "t_hour": 24,
    "task_name": "general_icu_surveillance"
  },
  "final_decision": {
    "global_action": "escalate",
    "suspected_conditions": ["infection", "sepsis"],
    "alerts": ["sepsis_alert"],
    "priority": "high",
    "recommended_next_tools": ["search_functions('vasoactive_agent')"],
    "rationale": "..."
  },
  "current_checkpoint_tool_history": [
    {
      "tool_name": "search_functions",
      "output_preview": "..."
    }
  ]
}
```

Expected summary output:

```json
{
  "checkpoint_summary": "Sepsis alert at 24h; escalate."
}
```

## End-to-End Example

### Round 1: checkpoint input

Example checkpoint:

- `stay_id = 30004144`
- `t_hour = 24`
- rolling history:
  - `{"0": "t=0 stable; no active alerts", "1": "t=4 monitor infection; action=continue_monitoring", "2": "t=8 renal concern emerging"}`

The decision model receives only:

- this checkpoint context
- the retrieval helpers
- the last few summaries

It does not receive the full prior trajectory transcript.

### Round 1A: Python-session exploration

Possible decision-step actions:

1. `search_guidelines("sepsis")`
2. `get_guideline("sepsis")`
3. `search_functions("sofa")`
4. `get_function_info("sofa")`
5. `search_functions("infection")`
6. `load_function("sofa")`
7. `load_function("suspicion_of_infection")`
8. `query_db(...)` or call loaded functions to inspect current evidence

### Round 1B: tool-first exploration

Possible `session_tools` actions:

1. `search_guidelines("sepsis")`
2. `get_guideline("sepsis")`
3. `search_functions("sofa")`
4. `get_function_info("sofa")`
5. `call_function("compute_sofa_score", {"stay_id": 30004144})`
6. `search_functions("infection")`
7. `get_function_info("suspicion_of_infection")`
8. `call_function("get_suspicion_of_infection", {"stay_id": 30004144})`

Notes:

- in `session_tools`, `call_function(...)` auto-loads the owner file if the function is not already loaded
- if multiple files export the same function name, the model can explicitly call `load_function(name)` first to pin the intended file

### Round 1: decision output

Example final decision:

```json
{
  "global_action": "escalate",
  "suspected_conditions": ["infection", "sepsis"],
  "alerts": ["sepsis_alert"],
  "priority": "high",
  "recommended_next_tools": ["search_functions('vasoactive')", "search_functions('bg')"],
  "rationale": "Current evidence supports infection plus organ dysfunction consistent with sepsis."
}
```

### Round 1: separate summary output

Then the summarizer gets the final decision and writes:

```json
{
  "checkpoint_summary": "Sepsis alert at 24h; escalate for infection plus organ dysfunction."
}
```

That summary, and not the full checkpoint trace, is what gets appended to rolling memory.

### Round 2: next checkpoint

At `t_hour = 28`, the decision model sees:

- the same patient stay
- the new checkpoint visibility window
- the same retrieval helpers
- the recent summaries, now including:
  - `{"0": "...", "1": "...", "2": "...", "3": "Sepsis alert at 24h; escalate for infection plus organ dysfunction."}`

The session is fresh for `t=28`, but the memory state carries forward through summaries.

## Minimal Run Commands

Python-session mode:

```bash
python -m src.sepsis_mvp.cli run \
  --dataset dataset/surveilance/benchmark_2k_checkpoint_truth.csv \
  --db-path "/Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db" \
  --tool-backend zeroshot_python \
  --task-mode surveillance \
  --protocol rolling_with_history \
  --agent qwen \
  --guidelines-dir guidelines/general_icu_autoformalized/txt \
  --functions-dir autoformalized_library/functions \
  --zeroshot-session-profile surveillance \
  --sample-size 10 \
  --trajectory-output outputs/surveilance/trajectory_rollouts.jsonl \
  --events-output outputs/surveilance/events.jsonl \
  --evaluation-output outputs/surveilance/eval.json
```

Notes:

- `rolling_with_history` is the intended protocol because the benchmark uses short checkpoint summaries as memory.
- `sample-size 10` is a good smoke-test setting before larger runs.
- the `qwen` agent requirement comes from the current zero-shot Python backend path.

Tool-first mode:

```bash
python -m src.sepsis_mvp.cli run \
  --dataset dataset/surveilance/benchmark_2k_checkpoint_truth.csv \
  --db-path "/Users/chloe/Desktop/healthcare/mimic-iv-3.1/buildmimic/duckdb/mimic4_dk.db" \
  --tool-backend session_tools \
  --task-mode surveillance \
  --protocol rolling_with_history \
  --agent qwen \
  --guidelines-dir guidelines/general_icu_autoformalized/txt \
  --functions-dir autoformalized_library/functions \
  --zeroshot-session-profile surveillance \
  --sample-size 10 \
  --trajectory-output outputs/surveilance/session_tools_trajectory_rollouts.jsonl \
  --events-output outputs/surveilance/session_tools_events.jsonl \
  --evaluation-output outputs/surveilance/session_tools_eval.json
```

## Implemented Evaluation

The current surveillance evaluator measures:

- `global_action_accuracy`
- `priority_accuracy`
- exact match on `suspected_conditions`
- exact match on `alerts`
- set-based macro F1 for suspected conditions
- set-based macro precision, recall, and F1 for alerts
- first-alert timing error
- false-early-alert trajectories
- missed-alert trajectories

## Known Limitations

The pipeline is runnable, but a few benchmark-realistic limitations remain:

- function retrieval is filename-based, not semantic
- guideline retrieval is filename-based, not content search
- some autoformalized files are safer to use compositionally than directly
  - `sepsis3.py` remains the clearest example
- `CRRT` is included in the latent decision layer, but its current reconstruction is weaker than the strongest core heads
- `session_tools` uses stable outer tools rather than dynamically creating one tool per exported function
- if multiple files export the same function name, `call_function` needs either a prior explicit `load_function` or a non-ambiguous target

## Recommended Next Execution Order

1. run a small smoke test on `10` trajectories
2. inspect `events.jsonl` and `trajectory_rollouts.jsonl`
3. check whether the agent is actually using guideline and function discovery
4. then scale to the full dev set
5. keep the test split untouched for final benchmark runs
