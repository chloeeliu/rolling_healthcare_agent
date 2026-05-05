WITH features AS (
  SELECT *
  FROM read_csv_auto('/Users/chloe/Documents/New project/dataset/surveilance/benchmark_stay_sampling_features.csv', header = true)
),
layer_targets AS (
  SELECT 'dev' AS split, 'core_diversity' AS sampling_layer, 240 AS target_n
  UNION ALL SELECT 'dev', 'alert_enrichment', 120
  UNION ALL SELECT 'dev', 'low_signal', 40
  UNION ALL SELECT 'test', 'core_diversity', 960
  UNION ALL SELECT 'test', 'alert_enrichment', 480
  UNION ALL SELECT 'test', 'low_signal', 160
),
pool AS (
  SELECT
    f.*,
    CASE
      WHEN f.sampling_layer = 'core_diversity' THEN concat_ws('|', f.unit_group, f.complexity_bucket, f.onset_profile)
      WHEN f.sampling_layer = 'alert_enrichment' THEN concat_ws('|', f.unit_group, f.onset_profile, f.rare_alert_group)
      ELSE concat_ws('|', f.unit_group, f.complexity_bucket)
    END AS stratum_key
  FROM features f
),
strata AS (
  SELECT
    p.split,
    p.sampling_layer,
    p.stratum_key,
    COUNT(*) AS stratum_count
  FROM pool p
  GROUP BY 1, 2, 3
),
quota_base AS (
  SELECT
    s.split,
    s.sampling_layer,
    s.stratum_key,
    s.stratum_count,
    t.target_n,
    CAST(FLOOR(1.0 * t.target_n * s.stratum_count / SUM(s.stratum_count) OVER (PARTITION BY s.split, s.sampling_layer)) AS INTEGER) AS base_quota,
    (
      1.0 * t.target_n * s.stratum_count / SUM(s.stratum_count) OVER (PARTITION BY s.split, s.sampling_layer)
    ) - FLOOR(
      1.0 * t.target_n * s.stratum_count / SUM(s.stratum_count) OVER (PARTITION BY s.split, s.sampling_layer)
    ) AS fractional_remainder
  FROM strata s
  JOIN layer_targets t
    ON t.split = s.split
   AND t.sampling_layer = s.sampling_layer
),
quota_ranked AS (
  SELECT
    *,
    target_n - SUM(base_quota) OVER (PARTITION BY split, sampling_layer) AS extra_slots,
    ROW_NUMBER() OVER (
      PARTITION BY split, sampling_layer
      ORDER BY fractional_remainder DESC, stratum_key
    ) AS remainder_rank
  FROM quota_base
),
stratum_quotas AS (
  SELECT
    split,
    sampling_layer,
    stratum_key,
    base_quota + CASE WHEN remainder_rank <= extra_slots THEN 1 ELSE 0 END AS stratum_quota
  FROM quota_ranked
),
ranked_pool AS (
  SELECT
    p.*,
    q.stratum_quota,
    (
      12 * CAST(p.shock_hypoperfusion_alert_by48h AS INTEGER) +
      8 * CAST(p.septic_shock_alert_by48h AS INTEGER) +
      6 * CAST(p.severe_acidemia_ph_le_7_20_by48h AS INTEGER) +
      5 * CAST(p.gcs_severe_impairment_le_8_by48h AS INTEGER) +
      5 * CAST(p.hypoxemia_pf_lt_100_by48h AS INTEGER) +
      4 * CAST(p.coagulopathy_inr_ge_2_by48h AS INTEGER) +
      4 * CAST(p.vasoactive_multi_agent_or_high_intensity_by48h AS INTEGER) +
      3 * CAST(p.aki_stage3_by48h AS INTEGER) +
      2 * CAST(p.crrt_active_by48h AS INTEGER) +
      2 * CAST(p.severe_hyperlactatemia_ge_4_by48h AS INTEGER)
    ) AS alert_priority_score,
    ROW_NUMBER() OVER (
      PARTITION BY p.split, p.sampling_layer, p.stratum_key
      ORDER BY
        CASE WHEN p.sampling_layer = 'alert_enrichment' THEN (
          12 * CAST(p.shock_hypoperfusion_alert_by48h AS INTEGER) +
          8 * CAST(p.septic_shock_alert_by48h AS INTEGER) +
          6 * CAST(p.severe_acidemia_ph_le_7_20_by48h AS INTEGER) +
          5 * CAST(p.gcs_severe_impairment_le_8_by48h AS INTEGER) +
          5 * CAST(p.hypoxemia_pf_lt_100_by48h AS INTEGER) +
          4 * CAST(p.coagulopathy_inr_ge_2_by48h AS INTEGER) +
          4 * CAST(p.vasoactive_multi_agent_or_high_intensity_by48h AS INTEGER) +
          3 * CAST(p.aki_stage3_by48h AS INTEGER) +
          2 * CAST(p.crrt_active_by48h AS INTEGER) +
          2 * CAST(p.severe_hyperlactatemia_ge_4_by48h AS INTEGER)
        ) ELSE 0 END DESC,
        CASE WHEN p.sampling_layer = 'alert_enrichment' THEN CAST(p.rare_alert_group_count AS INTEGER) ELSE 0 END DESC,
        hash(p.subject_id, p.stay_id, p.stratum_key, p.sampling_layer),
        p.stay_id
    ) AS stratum_rank
  FROM pool p
  JOIN stratum_quotas q
    ON q.split = p.split
   AND q.sampling_layer = p.sampling_layer
   AND q.stratum_key = p.stratum_key
),
selected AS (
  SELECT *
  FROM ranked_pool
  WHERE stratum_rank <= stratum_quota
)
SELECT
  split,
  sampling_layer,
  stratum_key,
  unit_group,
  complexity_bucket,
  onset_profile,
  rare_alert_group,
  trajectory_id,
  stay_id,
  subject_id,
  hadm_id,
  first_careunit,
  icu_los_hours,
  core_family_count_24h,
  max_active_family_count_any_checkpoint,
  max_alert_family_count_any_checkpoint,
  total_positive_families_by48h,
  early_positive_families_by12h,
  delayed_alert_24_48h,
  any_alert_by48h,
  any_rare_alert_flag,
  low_signal_flag,
  aki_stage3_by48h,
  crrt_active_by48h,
  septic_shock_alert_by48h,
  shock_hypoperfusion_alert_by48h,
  hypoxemia_pf_lt_100_by48h,
  gcs_severe_impairment_le_8_by48h,
  severe_hyperlactatemia_ge_4_by48h,
  severe_acidemia_ph_le_7_20_by48h,
  coagulopathy_inr_ge_2_by48h,
  vasoactive_multi_agent_or_high_intensity_by48h,
  resp_support_hfnc_or_niv_by48h,
  infection_suspected_by48h,
  sepsis_alert_by48h,
  aki_stage2_by48h,
  resp_support_invasive_vent_by48h
FROM selected
ORDER BY split, sampling_layer, stratum_key, stay_id;
