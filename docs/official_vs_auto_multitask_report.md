# Official vs Autoformalized Multitask Report

## Scope

This report compares the saved multitask Qwen runs under:

- official visible concepts: `/Users/chloe/Documents/New project/result/official_multi_Qwen3-30B-A3B-Instruct-2507`
- autoformalized visible concepts: `/Users/chloe/Documents/New project/result/auto_multi_Qwen3-30B-A3B-Instruct-2507`

Reference multitask dataset: `/Users/chloe/Documents/New project/rolling_monitor_dataset/multitask/rolling_multitask.csv`

## Important Caveat

This is not a clean full-cohort comparison from the saved artifacts alone.

- intended multitask cohort size: `96` stays
- official saved trajectories: `94`
- auto saved trajectories: `59`
- overlap on exact trajectory id: `57`
- official-only saved trajectories: `37`
- auto-only saved trajectories: `2`

So there are two fair views:

- saved-run view: each backend scored on everything that was actually saved
- matched-overlap view: both backends scored only on the shared saved trajectories

The matched-overlap view is the right one for backend comparison. The saved-run view is still useful for completeness and provenance.

## Executive Summary

The official backend is the stronger multitask system overall, and that conclusion survives the matched-overlap check.

Why:

- much better joint multitask accuracy on the matched overlap: `0.5113` vs `0.3233`
- decisive AKI advantage on the matched overlap: `0.8471` vs `0.6291`
- better respiratory support accuracy on the matched overlap: `0.9649` vs `0.9173`
- both backends are fully grounded in the narrow benchmark sense, so the gap is not caused by tool refusal

The sepsis head is more nuanced than the joint result:

- auto is slightly higher on matched sepsis step accuracy: `0.6291` vs `0.5915`
- but official preserves the intermediate `infection_suspect` state better: recall `0.2283` vs `0.1087`
- in practice, auto is more terminal-alert-oriented on sepsis, while official is materially cleaner on AKI and somewhat cleaner on respiratory support

The root cause is concept-layer instability, not missing tool use:

- infection flag disagreement on overlap steps: `112/399`
- auto infection internal contradictions (`evidence` present while flag is false): `101` steps
- AKI stage disagreement: `145/399` steps
- respiratory support disagreement: `105/399` steps

## 1. Saved-Run Results

These numbers use every completed trajectory found in each folder, even though the folders are not equally complete.

### Official

- joint step accuracy: `0.5775`
- sepsis accuracy / macro F1: `0.6702` / `0.5848`
- AKI accuracy / macro F1: `0.8419` / `0.7973`
- respiratory accuracy / macro F1: `0.9696` / `0.9519`

### Autoformalized

- joint step accuracy: `0.3269`
- sepsis accuracy / macro F1: `0.6368` / `0.5349`
- AKI accuracy / macro F1: `0.6247` / `0.4711`
- respiratory accuracy / macro F1: `0.9201` / `0.8400`

Interpretation:

- official is stronger on all three tasks in the saved-run view
- but this view is still confounded by the missing saved trajectories, especially the smaller auto run

## 2. Matched-Overlap Results

The rest of the report uses the `57` shared trajectories.

### Headline Metrics

- joint step accuracy: official `0.5113` vs auto `0.3233`
- sepsis accuracy: official `0.5915` vs auto `0.6291`
- AKI accuracy: official `0.8471` vs auto `0.6291`
- respiratory accuracy: official `0.9649` vs auto `0.9173`

### Paired Correctness

- joint steps where both are correct: `99`
- joint steps where only official is correct: `105`
- joint steps where only auto is correct: `30`
- trajectories solved perfectly only by official: `9`
- trajectories solved perfectly only by auto: `2`

Task-specific paired view:

- sepsis steps only-official-correct / only-auto-correct: `35` / `50`
- AKI steps only-official-correct / only-auto-correct: `96` / `9`
- respiratory steps only-official-correct / only-auto-correct: `32` / `13`

Interpretation:

- the multitask gap is driven mostly by AKI, with respiratory support a clear secondary contributor
- sepsis is closer: auto gets some extra terminal alerts right, while official better retains the intermediate surveillance state

## 3. Transition Timing

### Sepsis

- infection_suspect exact match: official `0.4194` vs auto `0.0000`
- infection_suspect missed rate: official `0.4516` vs auto `0.6774`
- trigger_sepsis_alert exact match: official `0.2667` vs auto `0.4333`
- trigger_sepsis_alert missed rate: official `0.4000` vs auto `0.1333`

Sepsis takeaway:

- official is much better at surfacing the intermediate infection stage at the right checkpoint
- auto is more willing to jump to the terminal alert state, which helps some late-sepsis labels but harms the surveillance ladder

### AKI

- suspect_aki exact match: official `0.8286` vs auto `0.1143`
- suspect_aki missed rate: official `0.0286` vs auto `0.5429`
- trigger_aki_alert exact match: official `0.6957` vs auto `0.1304`
- trigger_aki_alert missed rate: official `0.2609` vs auto `0.6522`

AKI takeaway:

- official is dramatically better at both stage-1 suspicion timing and stage-2-or-3 alert timing
- auto misses over half of the intermediate AKI transitions and roughly two thirds of the severe AKI alerts on the overlap

### Respiratory Support

- invasive support exact match: official `1.0000` vs auto `0.8000`
- invasive support missed rate: official `0.0000` vs auto `0.0333`

Respiratory takeaway:

- official is effectively perfect on the matched overlap
- auto is still strong, but it introduces avoidable support-level drift

## 4. Tool-Output Divergence

Both agents always call the same tools, so the real question is what those tools expose.

### Infection Tool

- infection flag disagreement: `112/399` steps
- infection hour present in only one backend: `109/399` steps
- auto evidence-present / flag-false contradictions: `101`

This is the clearest autoformalized failure mode. The backend often exposes infection evidence or a reconstructed first-visible hour, but still keeps `has_suspected_infection = false`. That breaks the benchmark contract at the concept level before the policy even acts.

### SOFA Tool

- auto SOFA at least 2 points higher than official: `119` steps
- auto SOFA at least 2 points lower than official: `50` steps
- auto minus official SOFA delta: mean `0.2757`, range `-11.0000` to `5.0000`

The issue is not a simple monotone bias. Auto SOFA is unstable in both directions, which is consistent with it being a visible-prefix recomputation rather than a faithful wrapper over the official hourly rolling concept.

### AKI Tool

- AKI stage disagreement: `145/399` steps

The overlap examples show both early auto stage-1 overcalls and missed official-positive stages. That lines up with the large AKI timing and accuracy gap.

### Respiratory Tool

- respiratory support disagreement: `105/399` steps

The dominant pattern is auto overcalling invasive support when raw strings such as `Endotracheal tube` remain visible, even when the official concept has already normalized the support state back down.

## 5. Bottom Line

The official backend should remain the reference multitask visible-concept layer.

The strongest reasons are:

- it wins clearly on the only fair summary metric here: matched-overlap joint accuracy
- it is far more reliable on AKI, which is where multitask performance diverges most
- it avoids the auto backend's infection inconsistency and respiratory support overcalls

The autoformalized backend is not uniformly worse. On the matched overlap it is roughly competitive on sepsis macro F1 and slightly higher on sepsis step accuracy. But that comes with a more alert-heavy policy, much weaker intermediate infection recall, and large concept-level instability in AKI and respiratory support.

So the right conclusion is:

- autoformalized is promising as a concept-generation experiment
- but in its current form it is not yet a drop-in replacement for the official multitask concept layer

## Generated Files

- `/Users/chloe/Documents/New project/result/official_multi_Qwen3-30B-A3B-Instruct-2507/qwen_multitask_eval.json`
- `/Users/chloe/Documents/New project/result/auto_multi_Qwen3-30B-A3B-Instruct-2507/auto_qwen_multitask_eval.json`
- `/Users/chloe/Documents/New project/result/multitask_official_vs_auto_comparison.json`
