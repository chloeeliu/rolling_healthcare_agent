# AKI Overall Analysis in MIMIC-IV

## Purpose

This note summarizes why AKI is a good candidate for a non-monotonic longitudinal monitoring benchmark and which MIMIC concept table is the best hidden state source.

## Recommended Concept Table

Use `mimiciv_derived.kdigo_stages`.

Why this table is the right base layer:

- It is already the derived AKI concept table in the MIMIC concept stack.
- It exposes both a raw stage (`aki_stage`) and a smoothed stage (`aki_stage_smoothed`).
- It preserves clinically useful contributors:
  - `aki_stage_creat`
  - `aki_stage_uo`
  - `aki_stage_crrt`
- It is naturally compatible with checkpoint-based longitudinal labeling.

For non-monotonic AKI state labels, `aki_stage_smoothed` is the best default source because it reduces oscillation caused by alternating creatinine and urine-output measurements while still preserving meaningful worsening and recovery.

## Table Size and Coverage

From `mimiciv_derived.kdigo_stages`:

- rows: `5,099,899`
- ICU stays: `94,458`

Row-level distribution for `aki_stage`:

- stage 0: `3,826,559`
- stage 1: `335,519`
- stage 2: `502,820`
- stage 3: `435,001`

Row-level distribution for `aki_stage_smoothed`:

- stage 0: `2,796,005`
- stage 1: `677,283`
- stage 2: `893,754`
- stage 3: `732,857`

Stay-level max smoothed stage:

- max stage 0: `25,248`
- max stage 1: `17,314`
- max stage 2: `30,918`
- max stage 3: `20,978`

This means `69,210 / 94,458` stays ever reach smoothed stage `> 0`, so AKI is common enough for a state-tracking benchmark without aggressive resampling.

## What Drives AKI in the Concept Table

Row-level positive contributor counts:

- creatinine-driven rows (`aki_stage_creat > 0`): `173,652`
- urine-output-driven rows (`aki_stage_uo > 0`): `915,576`
- CRRT-driven rows (`aki_stage_crrt > 0`): `203,035`

Stay-level contributor presence:

- any creatinine component: `31,462` stays
- any urine-output component: `52,522` stays
- any CRRT component: `2,897` stays

The main implication is that urine output matters a lot. A future visible AKI tool should expose contributor detail rather than only a single stage label.

## Why AKI Should Not Be Treated as Monotonic

### Across the Full ICU Stay

Using row-to-row changes in `aki_stage_smoothed`:

- stays with any upward stage change: `68,688`
- stays with any downward stage change: `53,211`
- stays with both upward and downward changes: `52,971`
- average number of stage changes per stay: `4.69`
- median number of stage changes per stay: `2`

### Within the First 24 ICU Hours

Using all visible KDIGO rows up to `intime + 24h`:

- stays with any upward change: `57,315`
- stays with any downward change: `24,684`
- stays with both upward and downward changes: `24,279`
- average number of changes: `1.49`
- median number of changes: `1`

### On 4-Hour Checkpoints

Using latest visible `aki_stage_smoothed` at `t = 0, 4, 8, 12, 16, 20, 24`:

- stays with any upward checkpoint change: `59,564`
- stays with any downward checkpoint change: `18,773`
- stays with both upward and downward checkpoint changes: `16,753`
- average checkpoint-stage changes: `1.22`
- median checkpoint-stage changes: `1`

This is the key result: even after discretizing to 4-hour checkpoints, AKI remains meaningfully non-monotonic.

## Early Visibility and Why It Matters

Checkpoint distribution of latest visible `aki_stage_smoothed`:

At `t=0`:

- no visible KDIGO row yet: `13,621`
- stage 0: `69,000`
- stage 1: `7,090`
- stage 2: `2,177`
- stage 3: `2,570`

At `t=24`:

- no visible KDIGO row yet: `66`
- stage 0: `46,526`
- stage 1: `15,155`
- stage 2: `27,265`
- stage 3: `5,446`

So early missingness is real. If the benchmark must use exactly four labels (`no_aki`, `aki_stage_1`, `aki_stage_2`, `aki_stage_3`), the cleanest design is to filter to stays with a visible KDIGO stage already available at `t=0`.

Among ICU stays with LOS `>= 24h` and a visible KDIGO row at every checkpoint from `0` to `24h`, there are `63,728` eligible stays.

Within that fully observed cohort:

- `t=0`: stage 0 `54,024`, stage 1 `5,782`, stage 2 `1,802`, stage 3 `2,120`
- `t=24`: stage 0 `28,526`, stage 1 `9,735`, stage 2 `21,203`, stage 3 `4,264`

## Common 0–24h Checkpoint Paths

Examples of common paths using the latest visible smoothed stage:

- `0>0>0>0>0>0>0`: `30,718`
- `0>0>0>1>2>2>2`: `3,111`
- `0>0>1>1>2>2>2`: `3,008`
- `0>0>0>0>0>1>1`: `2,462`
- `0>0>0>0>0>0>1`: `2,240`
- `0>0>0>0>1>1>0`: `996`
- `0>0>0>1>1>0>0`: `867`
- `3>3>3>3>3>3>3`: `940`

Two patterns matter for benchmark design:

- persistent or progressive AKI is common enough to support escalation tasks
- downgrade and recovery paths are also common enough that a non-monotonic benchmark is justified

## Recommendation for the Next Benchmark

If we move beyond monotonic escalation, the most natural AKI state-tracking label space is:

- `no_aki`
- `aki_stage_1`
- `aki_stage_2`
- `aki_stage_3`

Recommended hidden state source:

- `latest visible aki_stage_smoothed` at each checkpoint

Recommended visible support fields for a future AKI tool:

- `latest_aki_stage_smoothed`
- `aki_stage_creat`
- `aki_stage_uo`
- `aki_stage_crrt`
- optional recent trend over the last few checkpoints

## Bottom Line

AKI in MIMIC is a strong non-monotonic monitoring task candidate:

- it is common
- it often worsens and improves within the same ICU stay
- its concept table already exists
- the derived concept provides both a stable stage label and clinically meaningful contributors

That makes `mimiciv_derived.kdigo_stages`, especially `aki_stage_smoothed`, a strong foundation for the next longitudinal benchmark stage.
