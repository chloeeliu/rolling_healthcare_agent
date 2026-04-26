WITH cohort AS (
  SELECT
    stay_id,
    subject_id,
    hadm_id,
    intime,
    outtime
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
),
infection_suspected AS (
  SELECT stay_id, MIN(suspected_infection_time) AS event_time
  FROM mimiciv_derived.suspicion_of_infection
  WHERE suspected_infection = 1
    AND suspected_infection_time IS NOT NULL
  GROUP BY 1
),
infection_confirmed AS (
  SELECT stay_id, MIN(culture_time) AS event_time
  FROM mimiciv_derived.suspicion_of_infection
  WHERE positive_culture = 1
    AND culture_time IS NOT NULL
  GROUP BY 1
),
sepsis_alert AS (
  SELECT stay_id, MIN(GREATEST(suspected_infection_time, sofa_time)) AS event_time
  FROM mimiciv_derived.sepsis3
  WHERE sepsis3 = TRUE
    AND suspected_infection_time IS NOT NULL
    AND sofa_time IS NOT NULL
  GROUP BY 1
),
aki_stage1 AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.kdigo_stages
  WHERE aki_stage_smoothed >= 1
    AND charttime IS NOT NULL
  GROUP BY 1
),
aki_stage2 AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.kdigo_stages
  WHERE aki_stage_smoothed >= 2
    AND charttime IS NOT NULL
  GROUP BY 1
),
aki_stage3 AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.kdigo_stages
  WHERE aki_stage_smoothed >= 3
    AND charttime IS NOT NULL
  GROUP BY 1
),
oliguria_6h AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.urine_output_rate
  WHERE uo_tm_6hr >= 6
    AND uo_mlkghr_6hr < 0.5
    AND charttime IS NOT NULL
  GROUP BY 1
),
severe_oliguria_or_anuria AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.urine_output_rate
  WHERE (
      (uo_tm_12hr >= 12 AND uo_mlkghr_12hr < 0.5)
      OR (uo_tm_24hr >= 24 AND uo_mlkghr_24hr < 0.3)
    )
    AND charttime IS NOT NULL
  GROUP BY 1
),
crrt_active AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.crrt
  WHERE crrt_mode IS NOT NULL
    AND charttime IS NOT NULL
  GROUP BY 1
),
resp_support_hfnc_or_niv AS (
  SELECT stay_id, MIN(starttime) AS event_time
  FROM mimiciv_derived.ventilation
  WHERE ventilation_status IN ('HFNC', 'NonInvasiveVent')
    AND starttime IS NOT NULL
  GROUP BY 1
),
resp_support_invasive_vent AS (
  SELECT stay_id, MIN(starttime) AS event_time
  FROM mimiciv_derived.ventilation
  WHERE ventilation_status IN ('InvasiveVent', 'Tracheostomy')
    AND starttime IS NOT NULL
  GROUP BY 1
),
hypoxemia_pf_lt_200 AS (
  SELECT c.stay_id, MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.pao2fio2ratio < 200
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
hypoxemia_pf_lt_100 AS (
  SELECT c.stay_id, MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.pao2fio2ratio < 100
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
vasoactive_support_any AS (
  SELECT stay_id, MIN(starttime) AS event_time
  FROM mimiciv_derived.vasoactive_agent
  WHERE COALESCE(dopamine, epinephrine, norepinephrine, phenylephrine, vasopressin, dobutamine, milrinone) IS NOT NULL
    AND starttime IS NOT NULL
  GROUP BY 1
),
vasoactive_multi_agent AS (
  SELECT stay_id, MIN(starttime) AS event_time
  FROM mimiciv_derived.vasoactive_agent
  WHERE (
    CAST(dopamine IS NOT NULL AS INTEGER) +
    CAST(epinephrine IS NOT NULL AS INTEGER) +
    CAST(norepinephrine IS NOT NULL AS INTEGER) +
    CAST(phenylephrine IS NOT NULL AS INTEGER) +
    CAST(vasopressin IS NOT NULL AS INTEGER) +
    CAST(dobutamine IS NOT NULL AS INTEGER) +
    CAST(milrinone IS NOT NULL AS INTEGER)
  ) >= 2
    AND starttime IS NOT NULL
  GROUP BY 1
),
gcs_moderate_impairment AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.gcs
  WHERE gcs BETWEEN 9 AND 12
    AND charttime IS NOT NULL
  GROUP BY 1
),
gcs_severe_impairment AS (
  SELECT stay_id, MIN(charttime) AS event_time
  FROM mimiciv_derived.gcs
  WHERE gcs <= 8
    AND charttime IS NOT NULL
  GROUP BY 1
),
hyperlactatemia_ge_2 AS (
  SELECT c.stay_id, MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.lactate >= 2
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
hyperlactatemia_ge_4 AS (
  SELECT c.stay_id, MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.lactate >= 4
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
acidemia_ph_lt_7_30 AS (
  SELECT c.stay_id, MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.ph < 7.30
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
acidemia_ph_le_7_20 AS (
  SELECT c.stay_id, MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.ph <= 7.20
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
coagulopathy_inr_ge_1_5 AS (
  SELECT c.stay_id, MIN(co.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.coagulation co
    ON co.hadm_id = c.hadm_id
  WHERE co.inr >= 1.5
    AND co.charttime IS NOT NULL
  GROUP BY 1
),
coagulopathy_inr_ge_2 AS (
  SELECT c.stay_id, MIN(co.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.coagulation co
    ON co.hadm_id = c.hadm_id
  WHERE co.inr >= 2.0
    AND co.charttime IS NOT NULL
  GROUP BY 1
),
septic_shock_alert AS (
  SELECT s.stay_id, MIN(GREATEST(s.event_time, v.event_time, l.event_time)) AS event_time
  FROM sepsis_alert s
  JOIN vasoactive_support_any v USING (stay_id)
  JOIN hyperlactatemia_ge_2 l USING (stay_id)
  GROUP BY 1
),
shock_hypoperfusion_alert AS (
  SELECT s.stay_id, MIN(GREATEST(s.event_time, v.event_time, l.event_time)) AS event_time
  FROM sepsis_alert s
  JOIN vasoactive_support_any v USING (stay_id)
  JOIN hyperlactatemia_ge_4 l USING (stay_id)
  GROUP BY 1
),
decision_events AS (
  SELECT 'infection_suspected' AS decision_name, stay_id, event_time FROM infection_suspected
  UNION ALL SELECT 'infection_confirmed_or_strongly_supported', stay_id, event_time FROM infection_confirmed
  UNION ALL SELECT 'sepsis_alert', stay_id, event_time FROM sepsis_alert
  UNION ALL SELECT 'septic_shock_alert', stay_id, event_time FROM septic_shock_alert
  UNION ALL SELECT 'aki_stage1', stay_id, event_time FROM aki_stage1
  UNION ALL SELECT 'aki_stage2', stay_id, event_time FROM aki_stage2
  UNION ALL SELECT 'aki_stage3', stay_id, event_time FROM aki_stage3
  UNION ALL SELECT 'oliguria_6h', stay_id, event_time FROM oliguria_6h
  UNION ALL SELECT 'severe_oliguria_or_anuria', stay_id, event_time FROM severe_oliguria_or_anuria
  UNION ALL SELECT 'crrt_active', stay_id, event_time FROM crrt_active
  UNION ALL SELECT 'resp_support_hfnc_or_niv', stay_id, event_time FROM resp_support_hfnc_or_niv
  UNION ALL SELECT 'resp_support_invasive_vent', stay_id, event_time FROM resp_support_invasive_vent
  UNION ALL SELECT 'hypoxemia_pf_lt_200', stay_id, event_time FROM hypoxemia_pf_lt_200
  UNION ALL SELECT 'hypoxemia_pf_lt_100', stay_id, event_time FROM hypoxemia_pf_lt_100
  UNION ALL SELECT 'vasoactive_support_any', stay_id, event_time FROM vasoactive_support_any
  UNION ALL SELECT 'vasoactive_multi_agent_or_high_intensity', stay_id, event_time FROM vasoactive_multi_agent
  UNION ALL SELECT 'gcs_moderate_impairment_9_12', stay_id, event_time FROM gcs_moderate_impairment
  UNION ALL SELECT 'gcs_severe_impairment_le_8', stay_id, event_time FROM gcs_severe_impairment
  UNION ALL SELECT 'hyperlactatemia_ge_2', stay_id, event_time FROM hyperlactatemia_ge_2
  UNION ALL SELECT 'severe_hyperlactatemia_ge_4', stay_id, event_time FROM hyperlactatemia_ge_4
  UNION ALL SELECT 'acidemia_ph_lt_7_30', stay_id, event_time FROM acidemia_ph_lt_7_30
  UNION ALL SELECT 'severe_acidemia_ph_le_7_20', stay_id, event_time FROM acidemia_ph_le_7_20
  UNION ALL SELECT 'coagulopathy_inr_ge_1_5', stay_id, event_time FROM coagulopathy_inr_ge_1_5
  UNION ALL SELECT 'coagulopathy_inr_ge_2', stay_id, event_time FROM coagulopathy_inr_ge_2
  UNION ALL SELECT 'shock_hypoperfusion_alert', stay_id, event_time FROM shock_hypoperfusion_alert
)
SELECT
  decision_name,
  onset_bin,
  COUNT(*) AS stays,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY decision_name), 2) AS pct_of_positive_stays
FROM (
  SELECT
    d.decision_name,
    CASE
      WHEN d.event_time <= c.intime + INTERVAL '4 hours' THEN '0-4h'
      WHEN d.event_time <= c.intime + INTERVAL '12 hours' THEN '4-12h'
      WHEN d.event_time <= c.intime + INTERVAL '24 hours' THEN '12-24h'
      WHEN d.event_time <= c.intime + INTERVAL '48 hours' THEN '24-48h'
      ELSE 'after_48h'
    END AS onset_bin
  FROM decision_events d
  JOIN cohort c USING (stay_id)
  WHERE d.event_time IS NOT NULL
    AND d.event_time <= c.intime + INTERVAL '48 hours'
)
GROUP BY 1, 2
ORDER BY decision_name,
  CASE onset_bin
    WHEN '0-4h' THEN 1
    WHEN '4-12h' THEN 2
    WHEN '12-24h' THEN 3
    WHEN '24-48h' THEN 4
    ELSE 5
  END;
