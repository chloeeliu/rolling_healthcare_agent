WITH base_stays AS (
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
),
infection_first AS (
  SELECT
    stay_id,
    MIN(suspected_infection_time) AS event_time
  FROM mimiciv_derived.suspicion_of_infection
  WHERE suspected_infection = 1
    AND suspected_infection_time IS NOT NULL
  GROUP BY 1
),
sepsis_first AS (
  SELECT
    stay_id,
    MIN(GREATEST(suspected_infection_time, sofa_time)) AS event_time
  FROM mimiciv_derived.sepsis3
  WHERE sepsis3 = TRUE
    AND suspected_infection_time IS NOT NULL
    AND sofa_time IS NOT NULL
  GROUP BY 1
),
aki23_first AS (
  SELECT
    stay_id,
    MIN(charttime) AS event_time
  FROM mimiciv_derived.kdigo_stages
  WHERE aki_stage_smoothed >= 2
    AND charttime IS NOT NULL
  GROUP BY 1
),
oliguria_first AS (
  SELECT
    stay_id,
    MIN(charttime) AS event_time
  FROM mimiciv_derived.urine_output_rate
  WHERE uo_tm_6hr >= 6
    AND uo_mlkghr_6hr < 0.5
    AND charttime IS NOT NULL
  GROUP BY 1
),
resp_first AS (
  SELECT
    stay_id,
    MIN(starttime) AS event_time
  FROM mimiciv_derived.ventilation
  WHERE ventilation_status IN ('HFNC', 'NonInvasiveVent', 'InvasiveVent', 'Tracheostomy')
    AND starttime IS NOT NULL
  GROUP BY 1
),
vaso_first AS (
  SELECT
    stay_id,
    MIN(starttime) AS event_time
  FROM mimiciv_derived.vasoactive_agent
  WHERE COALESCE(dopamine, epinephrine, norepinephrine, phenylephrine, vasopressin, dobutamine, milrinone) IS NOT NULL
    AND starttime IS NOT NULL
  GROUP BY 1
),
gcs_first AS (
  SELECT
    stay_id,
    MIN(charttime) AS event_time
  FROM mimiciv_derived.gcs
  WHERE gcs <= 8
    AND charttime IS NOT NULL
  GROUP BY 1
),
lactate_first AS (
  SELECT
    b.stay_id,
    MIN(bg.charttime) AS event_time
  FROM base_stays b
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = b.hadm_id
  WHERE bg.lactate >= 4
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
ph_first AS (
  SELECT
    b.stay_id,
    MIN(bg.charttime) AS event_time
  FROM base_stays b
  JOIN mimiciv_derived.bg bg
    ON bg.hadm_id = b.hadm_id
  WHERE bg.ph <= 7.20
    AND bg.charttime IS NOT NULL
  GROUP BY 1
),
inr_first AS (
  SELECT
    b.stay_id,
    MIN(c.charttime) AS event_time
  FROM base_stays b
  JOIN mimiciv_derived.coagulation c
    ON c.hadm_id = b.hadm_id
  WHERE c.inr >= 2.0
    AND c.charttime IS NOT NULL
  GROUP BY 1
),
core_events AS (
  SELECT
    s.stay_id,
    s.intime,
    s.icu_los_hours,
    CAST(i.event_time IS NOT NULL AND i.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS infection,
    CAST(se.event_time IS NOT NULL AND se.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS sepsis,
    CAST(a.event_time IS NOT NULL AND a.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS aki_stage23,
    CAST(o.event_time IS NOT NULL AND o.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS oliguria,
    CAST(r.event_time IS NOT NULL AND r.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS respiratory_support,
    CAST(v.event_time IS NOT NULL AND v.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS vasoactive_support,
    CAST(g.event_time IS NOT NULL AND g.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS gcs_le_8,
    CAST(l.event_time IS NOT NULL AND l.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS lactate_ge_4,
    CAST(p.event_time IS NOT NULL AND p.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS ph_le_7_20,
    CAST(n.event_time IS NOT NULL AND n.event_time <= s.intime + INTERVAL '24 hours' AS INTEGER) AS inr_ge_2
  FROM base_stays s
  LEFT JOIN infection_first i USING (stay_id)
  LEFT JOIN sepsis_first se USING (stay_id)
  LEFT JOIN aki23_first a USING (stay_id)
  LEFT JOIN oliguria_first o USING (stay_id)
  LEFT JOIN resp_first r USING (stay_id)
  LEFT JOIN vaso_first v USING (stay_id)
  LEFT JOIN gcs_first g USING (stay_id)
  LEFT JOIN lactate_first l USING (stay_id)
  LEFT JOIN ph_first p USING (stay_id)
  LEFT JOIN inr_first n USING (stay_id)
)
SELECT
  cohort_name,
  min_los_hours,
  eligible_stays,
  stays_with_ge1_core_family_by24h,
  ROUND(100.0 * stays_with_ge1_core_family_by24h / eligible_stays, 2) AS pct_ge1_core_family_by24h,
  stays_with_ge3_core_families_by24h,
  ROUND(100.0 * stays_with_ge3_core_families_by24h / eligible_stays, 2) AS pct_ge3_core_families_by24h,
  median_los_hours
FROM (
  SELECT
    'los_ge_24h' AS cohort_name,
    24 AS min_los_hours,
    COUNT(*) AS eligible_stays,
    COUNT(*) FILTER (
      WHERE infection + sepsis + aki_stage23 + oliguria + respiratory_support + vasoactive_support + gcs_le_8 + lactate_ge_4 + ph_le_7_20 + inr_ge_2 >= 1
    ) AS stays_with_ge1_core_family_by24h,
    COUNT(*) FILTER (
      WHERE infection + sepsis + aki_stage23 + oliguria + respiratory_support + vasoactive_support + gcs_le_8 + lactate_ge_4 + ph_le_7_20 + inr_ge_2 >= 3
    ) AS stays_with_ge3_core_families_by24h,
    ROUND(quantile_cont(icu_los_hours, 0.5), 2) AS median_los_hours
  FROM core_events
  WHERE icu_los_hours >= 24

  UNION ALL

  SELECT
    'los_ge_48h' AS cohort_name,
    48 AS min_los_hours,
    COUNT(*) AS eligible_stays,
    COUNT(*) FILTER (
      WHERE infection + sepsis + aki_stage23 + oliguria + respiratory_support + vasoactive_support + gcs_le_8 + lactate_ge_4 + ph_le_7_20 + inr_ge_2 >= 1
    ) AS stays_with_ge1_core_family_by24h,
    COUNT(*) FILTER (
      WHERE infection + sepsis + aki_stage23 + oliguria + respiratory_support + vasoactive_support + gcs_le_8 + lactate_ge_4 + ph_le_7_20 + inr_ge_2 >= 3
    ) AS stays_with_ge3_core_families_by24h,
    ROUND(quantile_cont(icu_los_hours, 0.5), 2) AS median_los_hours
  FROM core_events
  WHERE icu_los_hours >= 48

  UNION ALL

  SELECT
    'los_ge_72h' AS cohort_name,
    72 AS min_los_hours,
    COUNT(*) AS eligible_stays,
    COUNT(*) FILTER (
      WHERE infection + sepsis + aki_stage23 + oliguria + respiratory_support + vasoactive_support + gcs_le_8 + lactate_ge_4 + ph_le_7_20 + inr_ge_2 >= 1
    ) AS stays_with_ge1_core_family_by24h,
    COUNT(*) FILTER (
      WHERE infection + sepsis + aki_stage23 + oliguria + respiratory_support + vasoactive_support + gcs_le_8 + lactate_ge_4 + ph_le_7_20 + inr_ge_2 >= 3
    ) AS stays_with_ge3_core_families_by24h,
    ROUND(quantile_cont(icu_los_hours, 0.5), 2) AS median_los_hours
  FROM core_events
  WHERE icu_los_hours >= 72
)
ORDER BY min_los_hours;
