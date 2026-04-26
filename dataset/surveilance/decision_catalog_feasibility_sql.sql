WITH cohort AS (
  SELECT
    stay_id,
    subject_id,
    hadm_id,
    intime,
    outtime,
    EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 AS icu_los_hours
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
),
infection_suspected AS (
  SELECT
    stay_id,
    MIN(suspected_infection_time) AS event_time
  FROM mimiciv_derived.suspicion_of_infection
  WHERE suspected_infection = 1
    AND suspected_infection_time IS NOT NULL
  GROUP BY 1
),
infection_confirmed AS (
  SELECT
    stay_id,
    MIN(culture_time) AS event_time
  FROM mimiciv_derived.suspicion_of_infection
  WHERE positive_culture = 1
    AND culture_time IS NOT NULL
  GROUP BY 1
),
sepsis_alert AS (
  SELECT
    stay_id,
    MIN(GREATEST(suspected_infection_time, sofa_time)) AS event_time
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
  SELECT
    c.stay_id,
    MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.pao2fio2ratio < 200
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
hypoxemia_pf_lt_100 AS (
  SELECT
    c.stay_id,
    MIN(bg.charttime) AS event_time
  FROM cohort c
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = c.hadm_id
  WHERE bg.pao2fio2ratio < 100
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
vasoactive_support_any AS (
  SELECT
    stay_id,
    MIN(starttime) AS event_time
  FROM mimiciv_derived.vasoactive_agent
  WHERE COALESCE(dopamine, epinephrine, norepinephrine, phenylephrine, vasopressin, dobutamine, milrinone) IS NOT NULL
    AND starttime IS NOT NULL
  GROUP BY 1
),
vasoactive_multi_agent AS (
  SELECT
    stay_id,
    MIN(starttime) AS event_time
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
  SELECT
    s.stay_id,
    MIN(GREATEST(s.event_time, v.event_time, l.event_time)) AS event_time
  FROM sepsis_alert s
  JOIN vasoactive_support_any v USING (stay_id)
  JOIN hyperlactatemia_ge_2 l USING (stay_id)
  GROUP BY 1
),
shock_hypoperfusion_alert AS (
  SELECT
    s.stay_id,
    MIN(GREATEST(s.event_time, v.event_time, l.event_time)) AS event_time
  FROM sepsis_alert s
  JOIN vasoactive_support_any v USING (stay_id)
  JOIN hyperlactatemia_ge_4 l USING (stay_id)
  GROUP BY 1
),
decision_summary AS (
  SELECT
    'infection_suspected' AS decision_name,
    'immediate_derived' AS definition_status,
    'mimiciv_derived.suspicion_of_infection' AS primary_source,
    (SELECT COUNT(*) FROM infection_suspected) AS ever_positive,
    (SELECT COUNT(*) FROM infection_suspected i JOIN cohort c USING (stay_id) WHERE i.event_time <= c.intime + INTERVAL '24 hours') AS positive_by_24h,
    (SELECT COUNT(*) FROM infection_suspected i JOIN cohort c USING (stay_id) WHERE i.event_time <= c.intime + INTERVAL '48 hours') AS positive_by_48h

  UNION ALL
  SELECT
    'infection_confirmed_or_strongly_supported', 'small_extension', 'suspicion_of_infection.positive_culture',
    (SELECT COUNT(*) FROM infection_confirmed),
    (SELECT COUNT(*) FROM infection_confirmed i JOIN cohort c USING (stay_id) WHERE i.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM infection_confirmed i JOIN cohort c USING (stay_id) WHERE i.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'sepsis_alert', 'immediate_derived', 'mimiciv_derived.sepsis3',
    (SELECT COUNT(*) FROM sepsis_alert),
    (SELECT COUNT(*) FROM sepsis_alert s JOIN cohort c USING (stay_id) WHERE s.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM sepsis_alert s JOIN cohort c USING (stay_id) WHERE s.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'septic_shock_alert', 'small_extension', 'sepsis3 + vasoactive_agent + bg(lactate>=2)',
    (SELECT COUNT(*) FROM septic_shock_alert),
    (SELECT COUNT(*) FROM septic_shock_alert s JOIN cohort c USING (stay_id) WHERE s.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM septic_shock_alert s JOIN cohort c USING (stay_id) WHERE s.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'aki_stage1', 'immediate_derived', 'mimiciv_derived.kdigo_stages',
    (SELECT COUNT(*) FROM aki_stage1),
    (SELECT COUNT(*) FROM aki_stage1 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM aki_stage1 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'aki_stage2', 'immediate_derived', 'mimiciv_derived.kdigo_stages',
    (SELECT COUNT(*) FROM aki_stage2),
    (SELECT COUNT(*) FROM aki_stage2 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM aki_stage2 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'aki_stage3', 'immediate_derived', 'mimiciv_derived.kdigo_stages',
    (SELECT COUNT(*) FROM aki_stage3),
    (SELECT COUNT(*) FROM aki_stage3 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM aki_stage3 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'oliguria_6h', 'immediate_derived', 'mimiciv_derived.urine_output_rate',
    (SELECT COUNT(*) FROM oliguria_6h),
    (SELECT COUNT(*) FROM oliguria_6h o JOIN cohort c USING (stay_id) WHERE o.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM oliguria_6h o JOIN cohort c USING (stay_id) WHERE o.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'severe_oliguria_or_anuria', 'small_extension', 'urine_output_rate 12h/24h thresholds',
    (SELECT COUNT(*) FROM severe_oliguria_or_anuria),
    (SELECT COUNT(*) FROM severe_oliguria_or_anuria o JOIN cohort c USING (stay_id) WHERE o.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM severe_oliguria_or_anuria o JOIN cohort c USING (stay_id) WHERE o.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'crrt_active', 'immediate_derived', 'mimiciv_derived.crrt',
    (SELECT COUNT(*) FROM crrt_active),
    (SELECT COUNT(*) FROM crrt_active r JOIN cohort c USING (stay_id) WHERE r.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM crrt_active r JOIN cohort c USING (stay_id) WHERE r.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'resp_support_hfnc_or_niv', 'immediate_derived', 'mimiciv_derived.ventilation',
    (SELECT COUNT(*) FROM resp_support_hfnc_or_niv),
    (SELECT COUNT(*) FROM resp_support_hfnc_or_niv r JOIN cohort c USING (stay_id) WHERE r.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM resp_support_hfnc_or_niv r JOIN cohort c USING (stay_id) WHERE r.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'resp_support_invasive_vent', 'immediate_derived', 'mimiciv_derived.ventilation',
    (SELECT COUNT(*) FROM resp_support_invasive_vent),
    (SELECT COUNT(*) FROM resp_support_invasive_vent r JOIN cohort c USING (stay_id) WHERE r.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM resp_support_invasive_vent r JOIN cohort c USING (stay_id) WHERE r.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'hypoxemia_pf_lt_200', 'immediate_derived', 'mimiciv_derived.bg',
    (SELECT COUNT(*) FROM hypoxemia_pf_lt_200),
    (SELECT COUNT(*) FROM hypoxemia_pf_lt_200 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM hypoxemia_pf_lt_200 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'hypoxemia_pf_lt_100', 'immediate_derived', 'mimiciv_derived.bg',
    (SELECT COUNT(*) FROM hypoxemia_pf_lt_100),
    (SELECT COUNT(*) FROM hypoxemia_pf_lt_100 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM hypoxemia_pf_lt_100 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'vasoactive_support_any', 'immediate_derived', 'mimiciv_derived.vasoactive_agent',
    (SELECT COUNT(*) FROM vasoactive_support_any),
    (SELECT COUNT(*) FROM vasoactive_support_any v JOIN cohort c USING (stay_id) WHERE v.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM vasoactive_support_any v JOIN cohort c USING (stay_id) WHERE v.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'vasoactive_multi_agent_or_high_intensity', 'small_extension', 'vasoactive_agent multi-agent rows',
    (SELECT COUNT(*) FROM vasoactive_multi_agent),
    (SELECT COUNT(*) FROM vasoactive_multi_agent v JOIN cohort c USING (stay_id) WHERE v.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM vasoactive_multi_agent v JOIN cohort c USING (stay_id) WHERE v.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'shock_hypoperfusion_alert', 'small_extension', 'sepsis3 + vasoactive_agent + bg(lactate>=4)',
    (SELECT COUNT(*) FROM shock_hypoperfusion_alert),
    (SELECT COUNT(*) FROM shock_hypoperfusion_alert s JOIN cohort c USING (stay_id) WHERE s.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM shock_hypoperfusion_alert s JOIN cohort c USING (stay_id) WHERE s.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'gcs_moderate_impairment_9_12', 'immediate_derived', 'mimiciv_derived.gcs',
    (SELECT COUNT(*) FROM gcs_moderate_impairment),
    (SELECT COUNT(*) FROM gcs_moderate_impairment g JOIN cohort c USING (stay_id) WHERE g.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM gcs_moderate_impairment g JOIN cohort c USING (stay_id) WHERE g.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'gcs_severe_impairment_le_8', 'immediate_derived', 'mimiciv_derived.gcs',
    (SELECT COUNT(*) FROM gcs_severe_impairment),
    (SELECT COUNT(*) FROM gcs_severe_impairment g JOIN cohort c USING (stay_id) WHERE g.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM gcs_severe_impairment g JOIN cohort c USING (stay_id) WHERE g.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'hyperlactatemia_ge_2', 'immediate_derived', 'mimiciv_derived.bg',
    (SELECT COUNT(*) FROM hyperlactatemia_ge_2),
    (SELECT COUNT(*) FROM hyperlactatemia_ge_2 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM hyperlactatemia_ge_2 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'severe_hyperlactatemia_ge_4', 'immediate_derived', 'mimiciv_derived.bg',
    (SELECT COUNT(*) FROM hyperlactatemia_ge_4),
    (SELECT COUNT(*) FROM hyperlactatemia_ge_4 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM hyperlactatemia_ge_4 h JOIN cohort c USING (stay_id) WHERE h.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'acidemia_ph_lt_7_30', 'immediate_derived', 'mimiciv_derived.bg',
    (SELECT COUNT(*) FROM acidemia_ph_lt_7_30),
    (SELECT COUNT(*) FROM acidemia_ph_lt_7_30 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM acidemia_ph_lt_7_30 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'severe_acidemia_ph_le_7_20', 'immediate_derived', 'mimiciv_derived.bg',
    (SELECT COUNT(*) FROM acidemia_ph_le_7_20),
    (SELECT COUNT(*) FROM acidemia_ph_le_7_20 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM acidemia_ph_le_7_20 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'coagulopathy_inr_ge_1_5', 'immediate_derived', 'mimiciv_derived.coagulation',
    (SELECT COUNT(*) FROM coagulopathy_inr_ge_1_5),
    (SELECT COUNT(*) FROM coagulopathy_inr_ge_1_5 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM coagulopathy_inr_ge_1_5 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '48 hours')

  UNION ALL
  SELECT
    'coagulopathy_inr_ge_2', 'immediate_derived', 'mimiciv_derived.coagulation',
    (SELECT COUNT(*) FROM coagulopathy_inr_ge_2),
    (SELECT COUNT(*) FROM coagulopathy_inr_ge_2 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '24 hours'),
    (SELECT COUNT(*) FROM coagulopathy_inr_ge_2 a JOIN cohort c USING (stay_id) WHERE a.event_time <= c.intime + INTERVAL '48 hours')
)
SELECT
  decision_name,
  definition_status,
  primary_source,
  ever_positive,
  positive_by_24h,
  ROUND(100.0 * positive_by_24h / (SELECT COUNT(*) FROM cohort), 2) AS pct_by_24h,
  positive_by_48h,
  ROUND(100.0 * positive_by_48h / (SELECT COUNT(*) FROM cohort), 2) AS pct_by_48h
FROM decision_summary
ORDER BY positive_by_24h DESC, decision_name;
