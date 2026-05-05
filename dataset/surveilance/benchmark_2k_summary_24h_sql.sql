WITH manifest AS (
  SELECT *
  FROM read_csv_auto('/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_manifest.csv', header = true)
),
truth AS (
  SELECT *
  FROM read_csv_auto('/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth.csv', header = true)
  WHERE CAST(t_hour AS INTEGER) <= 24
),
stay_level AS (
  SELECT
    split,
    stay_id,
    MAX(active_family_count) AS max_active_family_count_to24h,
    MAX(CASE WHEN global_action = 'escalate' THEN 1 ELSE 0 END) AS any_alert_by24h,
    MAX(CASE WHEN aki_stage3 = 1 THEN 1 ELSE 0 END) AS aki_stage3_by24h,
    MAX(CASE WHEN crrt_active = 1 THEN 1 ELSE 0 END) AS crrt_active_by24h,
    MAX(CASE WHEN septic_shock_alert = 1 THEN 1 ELSE 0 END) AS septic_shock_alert_by24h,
    MAX(CASE WHEN shock_hypoperfusion_alert = 1 THEN 1 ELSE 0 END) AS shock_hypoperfusion_alert_by24h,
    MAX(CASE WHEN hypoxemia_pf_lt_100 = 1 THEN 1 ELSE 0 END) AS hypoxemia_pf_lt_100_by24h,
    MAX(CASE WHEN gcs_severe_impairment_le_8 = 1 THEN 1 ELSE 0 END) AS gcs_severe_impairment_le_8_by24h,
    MAX(CASE WHEN severe_hyperlactatemia_ge_4 = 1 THEN 1 ELSE 0 END) AS severe_hyperlactatemia_ge_4_by24h,
    MAX(CASE WHEN severe_acidemia_ph_le_7_20 = 1 THEN 1 ELSE 0 END) AS severe_acidemia_ph_le_7_20_by24h,
    MAX(CASE WHEN coagulopathy_inr_ge_2 = 1 THEN 1 ELSE 0 END) AS coagulopathy_inr_ge_2_by24h,
    MAX(CASE WHEN vasoactive_multi_agent_or_high_intensity = 1 THEN 1 ELSE 0 END) AS vasoactive_multi_agent_or_high_intensity_by24h,
    MAX(CASE WHEN resp_support_hfnc_or_niv = 1 THEN 1 ELSE 0 END) AS resp_support_hfnc_or_niv_by24h,
    MAX(CASE WHEN infection_suspected = 1 THEN 1 ELSE 0 END) AS infection_suspected_by24h,
    MAX(CASE WHEN sepsis_alert = 1 THEN 1 ELSE 0 END) AS sepsis_alert_by24h,
    MAX(CASE WHEN aki_stage2 = 1 THEN 1 ELSE 0 END) AS aki_stage2_by24h,
    MAX(CASE WHEN resp_support_invasive_vent = 1 THEN 1 ELSE 0 END) AS resp_support_invasive_vent_by24h
  FROM truth
  GROUP BY 1, 2
)
SELECT
  m.split,
  m.sampling_layer,
  COUNT(*) AS stays,
  ROUND(AVG(m.core_family_count_24h), 2) AS mean_core_family_count_24h,
  ROUND(AVG(s.max_active_family_count_to24h), 2) AS mean_max_active_family_count_to24h,
  SUM(s.any_alert_by24h) AS stays_with_any_alert_by24h,
  SUM(s.aki_stage3_by24h) AS aki_stage3_stays,
  SUM(s.septic_shock_alert_by24h) AS septic_shock_stays,
  SUM(s.shock_hypoperfusion_alert_by24h) AS shock_hypoperfusion_stays,
  SUM(s.hypoxemia_pf_lt_100_by24h) AS hypoxemia_pf_lt_100_stays,
  SUM(s.gcs_severe_impairment_le_8_by24h) AS gcs_severe_stays,
  SUM(s.severe_hyperlactatemia_ge_4_by24h) AS severe_hyperlactatemia_stays,
  SUM(s.severe_acidemia_ph_le_7_20_by24h) AS severe_acidemia_stays,
  SUM(s.coagulopathy_inr_ge_2_by24h) AS coagulopathy_alert_stays,
  SUM(s.vasoactive_multi_agent_or_high_intensity_by24h) AS vaso_multi_stays,
  SUM(s.resp_support_hfnc_or_niv_by24h) AS hfnc_niv_stays,
  SUM(s.crrt_active_by24h) AS crrt_stays
FROM manifest m
JOIN stay_level s
  ON m.split = s.split
 AND m.stay_id = s.stay_id
GROUP BY 1, 2
ORDER BY m.split, m.sampling_layer;
