# Benchmark Experiment Audit

## Scope

This note audits the current longitudinal benchmark artifacts in:

- `/Users/chloe/Documents/New project/result`
- `/Users/chloe/Documents/New project/data`
- `/Users/chloe/Documents/New project/docs`

The goal is to answer two questions:

1. What benchmark evidence is already complete enough to trust?
2. Which experiments in the intended method x protocol grid still need to be run or built?

## Headline Conclusions

- The only protocol that is actually implemented end to end today is `rolling, no history`.
- The strongest completed single-task benchmark is full sepsis with `official` vs `autoformalized`.
- The multitask comparison is useful but still incomplete because the saved cohorts are not matched in coverage.
- The current zero-shot raw run is not an evaluated baseline yet. It is only a partial debug trace with code-generation failures.
- Your proposed scope change makes sense: zero-shot should be scaled back to `infection-only` rather than full sepsis.

## What Is Already Completed

### 1. Single-task sepsis, rolling without history

Saved artifacts:

- `/Users/chloe/Documents/New project/result/single_sepsis_Qwen3-30B-A3B-Instruct-2507/qwen_eval.json`
- `/Users/chloe/Documents/New project/result/auto_sepsis_Qwen3-30B-A3B-Instruct-2507/auto_qwen_sepsis_qwen_eval.json`
- `/Users/chloe/Documents/New project/docs/official_vs_auto_single_sepsis_report.md`

Current read:

- `official`: step accuracy `0.8003`, macro F1 `0.6152`
- `autoformalized`: step accuracy `0.6589`, macro F1 `0.5463`
- This is the cleanest completed head-to-head result in the repo right now.

### 2. Multitask rolling without history

Saved artifacts:

- `/Users/chloe/Documents/New project/result/official_multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_eval.json`
- `/Users/chloe/Documents/New project/result/auto_multi_Qwen3-30B-A3B-Instruct-2507/auto_qwen_multitask_eval.json`
- `/Users/chloe/Documents/New project/result/multitask_official_vs_auto_comparison.json`
- `/Users/chloe/Documents/New project/docs/official_vs_auto_multitask_report.md`

Current read:

- `official`: 94 completed trajectories out of intended 96
- `autoformalized`: 59 completed trajectories out of intended 96
- The result is directionally useful, but not yet a clean final benchmark table.

### 3. AKI non-monotonic smoke checks

Saved artifacts:

- `/Users/chloe/Documents/New project/data/aki_non_monotonic_eval.json`
- `/Users/chloe/Documents/New project/data/aki_non_monotonic_auto_eval.json`

Current read:

- These are smoke runs, not benchmark runs.
- They use the `heuristic` agent on tiny samples, not the main Qwen benchmark setup.
- They should not be treated as final rows in the benchmark report.

### 4. Zero-shot raw sepsis debug trace

Saved artifact:

- `/Users/chloe/Documents/New project/result/zeroshot_sepsis_Qwen3-30B-A3B-Instruct-2507/zeroshot_sepsis_events.jsonl`

Current read:

- Only `3` trajectories started and only `4` checkpoint steps appear in the event log.
- There is no rollout JSON and no eval JSON.
- The trace shows repeated `SyntaxError` failures from long generated raw-MIMIC scripts.

## Protocol Status

The runner currently behaves like `rolling, no history`.

Why:

- The benchmark loop recreates `history` inside each checkpoint loop in `/Users/chloe/Documents/New project/src/sepsis_mvp/environment.py`.
- `history` is initialized fresh at each step, then only used within that checkpoint.
- There is no separate protocol switch for `single-step` or `rolling with history`.

Relevant code evidence:

- `/Users/chloe/Documents/New project/src/sepsis_mvp/environment.py:67`
- `/Users/chloe/Documents/New project/src/sepsis_mvp/environment.py:83`
- `/Users/chloe/Documents/New project/src/sepsis_mvp/environment.py:108`

Implication:

- Any row labeled `rolling with history` is still missing.
- Any row labeled `single-step` is also still missing as a first-class protocol.

## Method Status

### Official

- Strong evidence exists for single-task sepsis and partial multitask.
- No completed infection-only benchmark row yet.
- No completed protocol-ablation rows beyond rolling without history.

### Autoformalization

- Strong evidence exists for single-task sepsis and partial multitask.
- No completed infection-only benchmark row yet.
- No completed protocol-ablation rows beyond rolling without history.
- AKI non-monotonic still needs a real Qwen benchmark run.

### Zero-shot

- The current implementation is restricted to single-task sepsis in `/Users/chloe/Documents/New project/src/sepsis_mvp/cli.py:114`.
- There is no completed eval artifact yet.
- Based on the current bad-case trace, full sepsis is too hard for this baseline in its present form.

## Recommended Scope Revision

For zero-shot, move from full sepsis to `infection-only`.

Why this is the right tradeoff:

- The bad-case trace shows the model trying to rebuild the entire infection-plus-SOFA ladder in raw SQL/Python.
- That combines program synthesis, schema recall, temporal visibility logic, and SOFA reconstruction in one loop.
- Infection-only gives you a meaningful baseline comparison without forcing zero-shot to solve the hardest organ-dysfunction logic.

What to compare on that slice:

- `official`
- `autoformalized`
- `zero-shot`

What to simplify:

- Use a simplified YAML and decision rule focused only on infection visibility and evidence.

## Experiments Still Missing

### P0: Missing but directly aligned with your revised benchmark story

- Infection-only, `official`, `rolling no-history`
- Infection-only, `autoformalized`, `rolling no-history`
- Infection-only, `zero-shot`, `rolling no-history`
- Full sepsis, `zero-shot`, any protocol

Interpretation:

- The infection-only table does not exist yet for any method.
- Full-sepsis zero-shot should probably be treated as blocked or deprioritized rather than required.

### P0: Missing because current multitask evidence is not yet final

- Multitask `official` rerun or backfill to full `96/96`
- Multitask `autoformalized` rerun or backfill to full `96/96`
- Matched final official-vs-auto comparison on the same completed cohort

### P1: Missing because protocol support is not built yet

- `single-step` protocol implementation
- `rolling with history` protocol implementation
- Sepsis protocol ablation once those two are implemented
- AKI protocol ablation once those two are implemented

### P1: Missing benchmark slice you explicitly want next

- A new single-sepsis task framed as:
  `Within 24 hours of ICU admission, when is SOFA onset?`

This likely needs:

- a dedicated dataset definition
- a clear target label contract
- a matching visible-concept tool contract
- protocol comparison on the same cohort

### P2: Missing because only smoke evidence exists

- AKI non-monotonic, `official`, real Qwen benchmark run
- AKI non-monotonic, `autoformalized`, real Qwen benchmark run

## Practical Run Order

Recommended order:

1. Build the infection-only slice and run `official`, `autoformalized`, and `zero-shot` on `rolling no-history`.
2. Finish the incomplete multitask official and auto runs so the comparison table is cohort-matched.
3. Add `rolling with history` by carrying forward a concise state summary per checkpoint.
4. Add `single-step` as a separate runner protocol.
5. Build the dedicated single-sepsis SOFA-onset benchmark and use it for the protocol comparison.

## Suggested History Payload For Rolling-With-History

Your proposed sepsis history design is reasonable and easy to implement:

- `step_index`
- `sofa_score`
- `infection`
- `evidence`

Append one concise summary per previous checkpoint and keep it sepsis-specific for now.

That is a good benchmark-first choice. It does not need to be generalized before it is useful.

## Bottom Line

The current repo already supports a solid `official` vs `autoformalized` story for full sepsis under `rolling, no history`.

What is still missing for the benchmark paper-quality table is:

- the infection-only zero-shot comparison
- true protocol ablations
- a completed matched multitask rerun
- the new single-sepsis SOFA-onset benchmark you described
