WITH truth AS (
  SELECT *
  FROM read_csv_auto('/Users/chloe/Documents/New project/dataset/surveilance/benchmark_2k_checkpoint_truth.csv', header = true)
),
horizons AS (
  SELECT 24 AS horizon_hours
  UNION ALL
  SELECT 48 AS horizon_hours
),
truth_by_horizon AS (
  SELECT
    h.horizon_hours,
    t.*
  FROM truth t
  JOIN horizons h
    ON CAST(t.t_hour AS INTEGER) <= h.horizon_hours
),
stay_level AS (
  SELECT
    horizon_hours,
    split,
    stay_id,
    MAX(CASE WHEN global_action = 'escalate' THEN 1 ELSE 0 END) AS any_alert,
    MAX(CASE WHEN sepsis_alert = 1 THEN 1 ELSE 0 END) AS sepsis_alert,
    MAX(CASE WHEN septic_shock_alert = 1 THEN 1 ELSE 0 END) AS septic_shock_alert,
    MAX(CASE WHEN shock_hypoperfusion_alert = 1 THEN 1 ELSE 0 END) AS shock_hypoperfusion_alert,
    MAX(CASE WHEN aki_stage2 = 1 THEN 1 ELSE 0 END) AS aki_stage2,
    MAX(CASE WHEN aki_stage3 = 1 THEN 1 ELSE 0 END) AS aki_stage3,
    MAX(CASE WHEN resp_support_invasive_vent = 1 THEN 1 ELSE 0 END) AS resp_support_invasive_vent,
    MAX(CASE WHEN hypoxemia_pf_lt_100 = 1 THEN 1 ELSE 0 END) AS hypoxemia_pf_lt_100,
    MAX(CASE WHEN gcs_severe_impairment_le_8 = 1 THEN 1 ELSE 0 END) AS gcs_severe_impairment_le_8,
    MAX(CASE WHEN severe_hyperlactatemia_ge_4 = 1 THEN 1 ELSE 0 END) AS severe_hyperlactatemia_ge_4,
    MAX(CASE WHEN severe_acidemia_ph_le_7_20 = 1 THEN 1 ELSE 0 END) AS severe_acidemia_ph_le_7_20,
    MAX(CASE WHEN coagulopathy_inr_ge_2 = 1 THEN 1 ELSE 0 END) AS coagulopathy_inr_ge_2,
    MAX(CASE WHEN vasoactive_multi_agent_or_high_intensity = 1 THEN 1 ELSE 0 END) AS vasoactive_multi_agent_or_high_intensity,
    MAX(CASE WHEN crrt_active = 1 THEN 1 ELSE 0 END) AS crrt_active
  FROM truth_by_horizon
  GROUP BY 1, 2, 3
),
checkpoint_level AS (
  SELECT
    horizon_hours,
    COUNT(*) AS checkpoint_rows,
    COUNT(DISTINCT stay_id) AS stays,
    COUNT(DISTINCT CAST(t_hour AS INTEGER)) AS checkpoints_per_stay,
    SUM(CASE WHEN global_action = 'escalate' THEN 1 ELSE 0 END) AS checkpoint_escalate_rows
  FROM truth_by_horizon
  GROUP BY 1
),
stay_summary AS (
  SELECT
    horizon_hours,
    COUNT(*) AS stays,
    SUM(any_alert) AS stays_with_any_alert,
    SUM(sepsis_alert) AS sepsis_alert_stays,
    SUM(septic_shock_alert) AS septic_shock_stays,
    SUM(shock_hypoperfusion_alert) AS shock_hypoperfusion_stays,
    SUM(aki_stage2) AS aki_stage2_stays,
    SUM(aki_stage3) AS aki_stage3_stays,
    SUM(resp_support_invasive_vent) AS resp_support_invasive_vent_stays,
    SUM(hypoxemia_pf_lt_100) AS hypoxemia_pf_lt_100_stays,
    SUM(gcs_severe_impairment_le_8) AS gcs_severe_stays,
    SUM(severe_hyperlactatemia_ge_4) AS severe_hyperlactatemia_stays,
    SUM(severe_acidemia_ph_le_7_20) AS severe_acidemia_stays,
    SUM(coagulopathy_inr_ge_2) AS coagulopathy_alert_stays,
    SUM(vasoactive_multi_agent_or_high_intensity) AS vaso_multi_stays,
    SUM(crrt_active) AS crrt_stays
  FROM stay_level
  GROUP BY 1
)
SELECT
  c.horizon_hours,
  c.stays,
  c.checkpoints_per_stay,
  c.checkpoint_rows,
  s.stays_with_any_alert,
  ROUND(100.0 * s.stays_with_any_alert / c.stays, 2) AS pct_stays_with_any_alert,
  c.checkpoint_escalate_rows,
  ROUND(100.0 * c.checkpoint_escalate_rows / c.checkpoint_rows, 2) AS pct_checkpoint_escalate,
  s.sepsis_alert_stays,
  s.septic_shock_stays,
  s.shock_hypoperfusion_stays,
  s.aki_stage2_stays,
  s.aki_stage3_stays,
  s.resp_support_invasive_vent_stays,
  s.hypoxemia_pf_lt_100_stays,
  s.gcs_severe_stays,
  s.severe_hyperlactatemia_stays,
  s.severe_acidemia_stays,
  s.coagulopathy_alert_stays,
  s.vaso_multi_stays,
  s.crrt_stays
FROM checkpoint_level c
JOIN stay_summary s
  ON c.horizon_hours = s.horizon_hours
ORDER BY c.horizon_hours;
