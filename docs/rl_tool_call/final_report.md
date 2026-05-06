# Final RL Tool-Calling Report

Date: 2026-05-05

## Executive Summary

The completed evidence supports the central claim that direct prompting is not enough for reliable clinical tool use in the rolling sepsis task. The Qwen prompt-tool baseline completed all 98 trajectories but used tools sparsely, never called SOFA, and often made positive sepsis-state decisions without sufficient evidence. The reward-policy proxy shows the target behavior that RL is intended to learn: establish suspected infection, then query SOFA before triggering sepsis alert.

The true verl GRPO checkpoint was not completed because the A100 smoke run reached SGLang/Ray/Torch compatibility errors during rollout weight sync. Therefore, no trained RL result should be reported as measured. The best current estimate is that successful GRPO would land between the prompt baseline and the reward-policy proxy, with the largest gains expected in tool grounding, SOFA-call coverage, unsupported-positive reduction, and timing error.

## Baseline vs. RL Tool-Call Performance

| Metric | Prompt-tool baseline, measured | Reward-policy proxy, measured | Expected trained GRPO range |
|---|---:|---:|---:|
| Trajectories | 98 | 98 | 98 test trajectories |
| Step accuracy | 0.4446 | 0.7988 | 0.60-0.72 |
| Step macro F1 | 0.3391 | 0.7234 | 0.50-0.65 |
| Infection exact timing | 0.1837 | 0.4388 | 0.30-0.40 |
| Infection MAE hours | 8.6022 | 2.0351 | 3.0-5.0 |
| Sepsis alert exact timing | 0.3878 | 0.6122 | 0.48-0.58 |
| Sepsis alert MAE hours | 6.9048 | 1.8367 | 2.5-4.0 |
| Infection grounding rate | 0.5479 | 1.0000 | 0.80-0.95 |
| Alert grounding rate | 0.0000 | 1.0000 | 0.60-0.85 |
| Avg tool calls per step | 0.2391 | 1.6195 | 0.80-1.30 |
| Steps without tool calls | 0.7609 | 0.0000 | 0.10-0.30 |
| Necessary infection-call coverage | 0.2892 | 1.0000 | 0.75-0.95 |
| Necessary SOFA-call coverage | 0.0000 | 1.0000 | 0.55-0.85 |
| Unsupported positive-action rate | 0.5372 | 0.0000 | 0.10-0.25 |
| Mean trajectory reward | 0.2008 | 1.1468 | 0.65-0.95 |
| Mean step reward | 0.3046 | 1.0508 | 0.70-0.95 |

Interpretation:

- The measured prompt baseline is weak primarily because it does not learn the staged evidence policy. It called `query_suspicion_of_infection` 164 times and `query_sofa` 0 times across 686 steps.
- The measured reward-policy proxy is an upper/reference behavior, not an RL checkpoint. It called `query_suspicion_of_infection` 686 times and `query_sofa` 425 times, producing perfect grounding but more tool use than an efficient learned policy should need.
- The expected trained GRPO policy should not be assumed to match the proxy. A realistic first successful run should improve evidence-seeking behavior substantially while still making some timing and schema mistakes because the dataset is small and the task is multi-turn.

## Further Supporting Evidence

Measured artifacts:

- Baseline evaluation: `data/rl_tool_call/full_prompt_tool_qwen4b_eval.json`
- Baseline rewards: `data/rl_tool_call/full_prompt_tool_qwen4b_rewards.json`
- Reward-policy proxy evaluation: `data/rl_tool_call/full_rl_policy_proxy_eval.json`
- Reward-policy proxy rewards: `data/rl_tool_call/full_rl_policy_proxy_rewards.json`
- Full metric summary: `data/rl_tool_call/full_run_summary.md`

Key measured failure modes:

- The prompt baseline skipped tool calls on 76.09% of steps.
- It had 0.00 SOFA-call coverage for alert decisions.
- It had 53.72% positive-action-without-sufficient-evidence rate.
- Infection timing MAE was 8.60 hours and alert timing MAE was 6.90 hours.

Key measured proxy strengths:

- Necessary infection-call coverage reached 1.00.
- Necessary SOFA-call coverage reached 1.00.
- Unsupported positive-action rate dropped to 0.00.
- Infection timing MAE fell to 2.04 hours and alert timing MAE fell to 1.84 hours.

Paper support:

- Search-R1 supports the training premise: prompting a model to use an external information tool is often suboptimal, while RL over multi-turn tool interactions can teach the model when and how to use tools. The paper reports large retrieval-reasoning gains for Qwen-scale models using outcome-based RL with multi-turn search interactions.
- EHR-R1 supports the clinical premise: EHR tasks benefit from domain-specific reasoning enhancement and multi-stage training, including RL, rather than relying on generic prompting alone. It also uses MIMIC-IV-derived evaluation to motivate EHR-specific reasoning benchmarks.

## Conclusion

The current project should be reported as having completed the benchmark, prompt-tool baseline, reward function, reward-policy proxy, and verl GRPO integration attempt. It should not claim a completed RL-trained checkpoint. The most defensible conclusion is:

RL-style optimization is likely to improve this task because the measured baseline failure is exactly the kind of behavior the reward targets: missing necessary tools, skipping SOFA, unsupported positive decisions, and poor transition timing. Based on the proxy ceiling and related RL tool-use/EHR reasoning literature, a successful first GRPO run is expected to move macro F1 from 0.3391 into roughly the 0.50-0.65 range, reduce alert timing MAE from 6.90 hours to roughly 2.5-4.0 hours, and raise SOFA-call coverage from 0.00 into roughly the 0.55-0.85 range.

## References

- Jin et al., "Search-R1: Training LLMs to Reason and Leverage Search Engines with Reinforcement Learning", arXiv:2503.09516.
- Liao et al., "EHR-R1: A Reasoning-Enhanced Foundational Language Model for Electronic Health Record Analysis", arXiv:2510.25628.
