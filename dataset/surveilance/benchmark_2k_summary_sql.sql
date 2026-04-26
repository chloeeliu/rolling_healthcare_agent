WITH manifest AS (
  SELECT *
  FROM read_csv_auto('/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_manifest.csv', header = true)
)
SELECT
  split,
  sampling_layer,
  COUNT(*) AS stays,
  ROUND(AVG(core_family_count_24h), 2) AS mean_core_family_count_24h,
  ROUND(AVG(max_active_family_count_any_checkpoint), 2) AS mean_max_active_family_count_any_checkpoint,
  SUM(any_alert_by48h) AS stays_with_any_alert_by48h,
  SUM(any_rare_alert_flag) AS stays_with_any_rare_alert,
  SUM(low_signal_flag) AS low_signal_stays,
  SUM(aki_stage3_by48h) AS aki_stage3_stays,
  SUM(septic_shock_alert_by48h) AS septic_shock_stays,
  SUM(shock_hypoperfusion_alert_by48h) AS shock_hypoperfusion_stays,
  SUM(hypoxemia_pf_lt_100_by48h) AS hypoxemia_pf_lt_100_stays,
  SUM(gcs_severe_impairment_le_8_by48h) AS gcs_severe_stays,
  SUM(severe_acidemia_ph_le_7_20_by48h) AS severe_acidemia_stays,
  SUM(coagulopathy_inr_ge_2_by48h) AS coagulopathy_alert_stays,
  SUM(vasoactive_multi_agent_or_high_intensity_by48h) AS vaso_multi_stays,
  SUM(resp_support_hfnc_or_niv_by48h) AS hfnc_niv_stays,
  SUM(crrt_active_by48h) AS crrt_stays
FROM manifest
GROUP BY 1, 2
ORDER BY split, sampling_layer;
