WITH truth AS (
  SELECT *
  FROM read_csv_auto('/Users/chloe/Documents/New project/dataset/surveilance/checkpoint_truth_all.csv', header = true)
),
heldout AS (
  SELECT *
  FROM truth
  WHERE split IN ('dev', 'test')
),
stay_base AS (
  SELECT
    split,
    trajectory_id,
    stay_id,
    subject_id,
    hadm_id,
    first_careunit,
    MAX(icu_los_hours) AS icu_los_hours
  FROM heldout
  GROUP BY 1, 2, 3, 4, 5, 6
),
family_onsets AS (
  SELECT
    stay_id,
    MIN(CASE WHEN infection_family_active = 1 THEN t_hour END) AS infection_first_hour,
    MIN(CASE WHEN sepsis_family_active = 1 THEN t_hour END) AS sepsis_first_hour,
    MIN(CASE WHEN renal_family_active = 1 THEN t_hour END) AS renal_first_hour,
    MIN(CASE WHEN respiratory_family_active = 1 THEN t_hour END) AS respiratory_first_hour,
    MIN(CASE WHEN hemodynamic_family_active = 1 THEN t_hour END) AS hemodynamic_first_hour,
    MIN(CASE WHEN neurologic_family_active = 1 THEN t_hour END) AS neurologic_first_hour,
    MIN(CASE WHEN metabolic_family_active = 1 THEN t_hour END) AS metabolic_first_hour,
    MIN(CASE WHEN coagulation_family_active = 1 THEN t_hour END) AS coagulation_first_hour,
    MIN(CASE WHEN sepsis_primary_decision IS NOT NULL THEN t_hour END) AS sepsis_alert_first_hour,
    MIN(CASE WHEN renal_primary_decision IN ('aki_stage2', 'aki_stage3', 'severe_oliguria_or_anuria', 'crrt_active') THEN t_hour END) AS renal_alert_first_hour,
    MIN(CASE WHEN respiratory_primary_decision IN ('resp_support_invasive_vent', 'hypoxemia_pf_lt_100') THEN t_hour END) AS respiratory_alert_first_hour,
    MIN(CASE WHEN hemodynamic_primary_decision IN ('vasoactive_multi_agent_or_high_intensity', 'septic_shock_alert', 'shock_hypoperfusion_alert') THEN t_hour END) AS hemodynamic_alert_first_hour,
    MIN(CASE WHEN neurologic_primary_decision = 'gcs_severe_impairment_le_8' THEN t_hour END) AS neurologic_alert_first_hour,
    MIN(CASE WHEN metabolic_primary_decision IN ('severe_hyperlactatemia_ge_4', 'severe_acidemia_ph_le_7_20') THEN t_hour END) AS metabolic_alert_first_hour,
    MIN(CASE WHEN coagulation_primary_decision = 'coagulopathy_inr_ge_2' THEN t_hour END) AS coagulation_alert_first_hour
  FROM heldout
  GROUP BY 1
),
stay_rollup AS (
  SELECT
    trajectory_id,
    split,
    stay_id,
    subject_id,
    hadm_id,
    first_careunit,
    icu_los_hours,
    MAX(CASE WHEN t_hour = 24 THEN active_family_count END) AS core_family_count_24h,
    MAX(active_family_count) AS max_active_family_count_any_checkpoint,
    MAX(alert_family_count) AS max_alert_family_count_any_checkpoint,
    MAX(CASE WHEN global_action = 'escalate' THEN 1 ELSE 0 END) AS any_alert_by48h,
    MAX(CASE WHEN aki_stage3 = 1 THEN 1 ELSE 0 END) AS aki_stage3_by48h,
    MAX(CASE WHEN crrt_active = 1 THEN 1 ELSE 0 END) AS crrt_active_by48h,
    MAX(CASE WHEN septic_shock_alert = 1 THEN 1 ELSE 0 END) AS septic_shock_alert_by48h,
    MAX(CASE WHEN shock_hypoperfusion_alert = 1 THEN 1 ELSE 0 END) AS shock_hypoperfusion_alert_by48h,
    MAX(CASE WHEN hypoxemia_pf_lt_100 = 1 THEN 1 ELSE 0 END) AS hypoxemia_pf_lt_100_by48h,
    MAX(CASE WHEN gcs_severe_impairment_le_8 = 1 THEN 1 ELSE 0 END) AS gcs_severe_impairment_le_8_by48h,
    MAX(CASE WHEN severe_hyperlactatemia_ge_4 = 1 THEN 1 ELSE 0 END) AS severe_hyperlactatemia_ge_4_by48h,
    MAX(CASE WHEN severe_acidemia_ph_le_7_20 = 1 THEN 1 ELSE 0 END) AS severe_acidemia_ph_le_7_20_by48h,
    MAX(CASE WHEN coagulopathy_inr_ge_2 = 1 THEN 1 ELSE 0 END) AS coagulopathy_inr_ge_2_by48h,
    MAX(CASE WHEN vasoactive_multi_agent_or_high_intensity = 1 THEN 1 ELSE 0 END) AS vasoactive_multi_agent_or_high_intensity_by48h,
    MAX(CASE WHEN resp_support_hfnc_or_niv = 1 THEN 1 ELSE 0 END) AS resp_support_hfnc_or_niv_by48h,
    MAX(CASE WHEN infection_suspected = 1 THEN 1 ELSE 0 END) AS infection_suspected_by48h,
    MAX(CASE WHEN sepsis_alert = 1 THEN 1 ELSE 0 END) AS sepsis_alert_by48h,
    MAX(CASE WHEN aki_stage2 = 1 THEN 1 ELSE 0 END) AS aki_stage2_by48h,
    MAX(CASE WHEN resp_support_invasive_vent = 1 THEN 1 ELSE 0 END) AS resp_support_invasive_vent_by48h
  FROM heldout
  GROUP BY 1, 2, 3, 4, 5, 6, 7
),
features AS (
  SELECT
    r.*,
    CASE
      WHEN first_careunit IN ('Medical Intensive Care Unit (MICU)', 'Cardiac Vascular Intensive Care Unit (CVICU)') THEN 'micu_cvicu'
      WHEN first_careunit IN ('Medical/Surgical Intensive Care Unit (MICU/SICU)', 'Surgical Intensive Care Unit (SICU)', 'Trauma SICU (TSICU)', 'Surgery/Vascular/Intermediate', 'PACU', 'Surgery/Trauma') THEN 'mixed_surgical_trauma'
      WHEN first_careunit = 'Coronary Care Unit (CCU)' THEN 'ccu'
      WHEN first_careunit IN ('Neuro Intermediate', 'Neuro Surgical Intensive Care Unit (Neuro SICU)', 'Neuro Stepdown', 'Neurology') THEN 'neuro_facing'
      ELSE 'other'
    END AS unit_group,
    CASE
      WHEN core_family_count_24h <= 1 THEN '0_1'
      WHEN core_family_count_24h <= 3 THEN '2_3'
      ELSE '4_plus'
    END AS complexity_bucket,
    (
      CAST(COALESCE(f.infection_first_hour IS NOT NULL, FALSE) AS INTEGER) +
      CAST(COALESCE(f.sepsis_first_hour IS NOT NULL, FALSE) AS INTEGER) +
      CAST(COALESCE(f.renal_first_hour IS NOT NULL, FALSE) AS INTEGER) +
      CAST(COALESCE(f.respiratory_first_hour IS NOT NULL, FALSE) AS INTEGER) +
      CAST(COALESCE(f.hemodynamic_first_hour IS NOT NULL, FALSE) AS INTEGER) +
      CAST(COALESCE(f.neurologic_first_hour IS NOT NULL, FALSE) AS INTEGER) +
      CAST(COALESCE(f.metabolic_first_hour IS NOT NULL, FALSE) AS INTEGER) +
      CAST(COALESCE(f.coagulation_first_hour IS NOT NULL, FALSE) AS INTEGER)
    ) AS total_positive_families_by48h,
    (
      CAST(COALESCE(f.infection_first_hour <= 12, FALSE) AS INTEGER) +
      CAST(COALESCE(f.sepsis_first_hour <= 12, FALSE) AS INTEGER) +
      CAST(COALESCE(f.renal_first_hour <= 12, FALSE) AS INTEGER) +
      CAST(COALESCE(f.respiratory_first_hour <= 12, FALSE) AS INTEGER) +
      CAST(COALESCE(f.hemodynamic_first_hour <= 12, FALSE) AS INTEGER) +
      CAST(COALESCE(f.neurologic_first_hour <= 12, FALSE) AS INTEGER) +
      CAST(COALESCE(f.metabolic_first_hour <= 12, FALSE) AS INTEGER) +
      CAST(COALESCE(f.coagulation_first_hour <= 12, FALSE) AS INTEGER)
    ) AS early_positive_families_by12h,
    CAST(
      COALESCE(f.sepsis_alert_first_hour BETWEEN 24 AND 48, FALSE)
      OR COALESCE(f.renal_alert_first_hour BETWEEN 24 AND 48, FALSE)
      OR COALESCE(f.respiratory_alert_first_hour BETWEEN 24 AND 48, FALSE)
      OR COALESCE(f.hemodynamic_alert_first_hour BETWEEN 24 AND 48, FALSE)
      OR COALESCE(f.neurologic_alert_first_hour BETWEEN 24 AND 48, FALSE)
      OR COALESCE(f.metabolic_alert_first_hour BETWEEN 24 AND 48, FALSE)
      OR COALESCE(f.coagulation_alert_first_hour BETWEEN 24 AND 48, FALSE)
      AS INTEGER
    ) AS delayed_alert_24_48h,
    CAST(
      shock_hypoperfusion_alert_by48h = 1
      OR septic_shock_alert_by48h = 1
      OR vasoactive_multi_agent_or_high_intensity_by48h = 1
      AS INTEGER
    ) AS hemodynamic_rare_alert_group,
    CAST(
      aki_stage3_by48h = 1
      OR crrt_active_by48h = 1
      AS INTEGER
    ) AS renal_rare_alert_group,
    hypoxemia_pf_lt_100_by48h AS respiratory_rare_alert_group,
    gcs_severe_impairment_le_8_by48h AS neurologic_rare_alert_group,
    CAST(
      severe_hyperlactatemia_ge_4_by48h = 1
      OR severe_acidemia_ph_le_7_20_by48h = 1
      AS INTEGER
    ) AS metabolic_rare_alert_group,
    coagulopathy_inr_ge_2_by48h AS coagulation_rare_alert_group
  FROM stay_rollup r
  LEFT JOIN family_onsets f
    ON f.stay_id = r.stay_id
)
SELECT
  *,
  CASE
    WHEN delayed_alert_24_48h = 1 THEN 'delayed'
    WHEN total_positive_families_by48h > 0
      AND 1.0 * early_positive_families_by12h / total_positive_families_by48h >= 0.6 THEN 'mostly_early'
    ELSE 'mixed'
  END AS onset_profile,
  (
    hemodynamic_rare_alert_group +
    renal_rare_alert_group +
    respiratory_rare_alert_group +
    neurologic_rare_alert_group +
    metabolic_rare_alert_group +
    coagulation_rare_alert_group
  ) AS rare_alert_group_count,
  CASE
    WHEN (
      hemodynamic_rare_alert_group +
      renal_rare_alert_group +
      respiratory_rare_alert_group +
      neurologic_rare_alert_group +
      metabolic_rare_alert_group +
      coagulation_rare_alert_group
    ) >= 2 THEN 'multi_severe'
    WHEN hemodynamic_rare_alert_group = 1 THEN 'hemodynamic'
    WHEN renal_rare_alert_group = 1 THEN 'renal'
    WHEN respiratory_rare_alert_group = 1 THEN 'respiratory'
    WHEN neurologic_rare_alert_group = 1 THEN 'neurologic'
    WHEN metabolic_rare_alert_group = 1 THEN 'metabolic'
    WHEN coagulation_rare_alert_group = 1 THEN 'coagulation'
    ELSE 'none'
  END AS rare_alert_group,
  CAST(core_family_count_24h <= 1 AS INTEGER) AS low_signal_flag,
  CAST(
    hemodynamic_rare_alert_group = 1
    OR renal_rare_alert_group = 1
    OR respiratory_rare_alert_group = 1
    OR neurologic_rare_alert_group = 1
    OR metabolic_rare_alert_group = 1
    OR coagulation_rare_alert_group = 1
    AS INTEGER
  ) AS any_rare_alert_flag,
  CASE
    WHEN core_family_count_24h <= 1 THEN 'low_signal'
    WHEN (
      hemodynamic_rare_alert_group = 1
      OR renal_rare_alert_group = 1
      OR respiratory_rare_alert_group = 1
      OR neurologic_rare_alert_group = 1
      OR metabolic_rare_alert_group = 1
      OR coagulation_rare_alert_group = 1
    ) THEN 'alert_enrichment'
    ELSE 'core_diversity'
  END AS sampling_layer
FROM features
ORDER BY split, stay_id;
