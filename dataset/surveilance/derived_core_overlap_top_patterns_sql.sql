WITH cohort AS (
  SELECT
    stay_id,
    hadm_id,
    intime
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
),
infection_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.suspicion_of_infection s USING (stay_id)
  WHERE s.suspected_infection = 1
    AND s.suspected_infection_time <= c.intime + INTERVAL '24 hours'
),
sepsis_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.sepsis3 s USING (stay_id)
  WHERE s.sepsis3 = TRUE
    AND GREATEST(s.suspected_infection_time, s.sofa_time) <= c.intime + INTERVAL '24 hours'
),
aki_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.kdigo_stages k USING (stay_id)
  WHERE k.aki_stage_smoothed >= 2
    AND k.charttime <= c.intime + INTERVAL '24 hours'
),
oliguria_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.urine_output_rate u USING (stay_id)
  WHERE u.uo_tm_6hr >= 6
    AND u.uo_mlkghr_6hr < 0.5
    AND u.charttime <= c.intime + INTERVAL '24 hours'
),
resp_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.ventilation v USING (stay_id)
  WHERE v.ventilation_status IN ('HFNC', 'NonInvasiveVent', 'InvasiveVent', 'Tracheostomy')
    AND v.starttime <= c.intime + INTERVAL '24 hours'
),
vaso_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.vasoactive_agent v USING (stay_id)
  WHERE COALESCE(v.dopamine, v.epinephrine, v.norepinephrine, v.phenylephrine, v.vasopressin, v.dobutamine, v.milrinone) IS NOT NULL
    AND v.starttime <= c.intime + INTERVAL '24 hours'
),
gcs_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.gcs g USING (stay_id)
  WHERE g.gcs <= 8
    AND g.charttime <= c.intime + INTERVAL '24 hours'
),
lactate_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.bg b
    ON b.hadm_id = c.hadm_id
  WHERE b.lactate >= 4
    AND b.charttime <= c.intime + INTERVAL '24 hours'
),
ph_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.bg b
    ON b.hadm_id = c.hadm_id
  WHERE b.ph <= 7.20
    AND b.charttime <= c.intime + INTERVAL '24 hours'
),
inr_by24 AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_derived.coagulation co
    ON co.hadm_id = c.hadm_id
  WHERE co.inr >= 2.0
    AND co.charttime <= c.intime + INTERVAL '24 hours'
),
patterns AS (
  SELECT
    CAST(c.stay_id IN (SELECT stay_id FROM infection_by24) AS INTEGER) AS infection,
    CAST(c.stay_id IN (SELECT stay_id FROM sepsis_by24) AS INTEGER) AS sepsis,
    CAST(c.stay_id IN (SELECT stay_id FROM aki_by24) AS INTEGER) AS aki_stage23,
    CAST(c.stay_id IN (SELECT stay_id FROM oliguria_by24) AS INTEGER) AS oliguria,
    CAST(c.stay_id IN (SELECT stay_id FROM resp_by24) AS INTEGER) AS respiratory_support,
    CAST(c.stay_id IN (SELECT stay_id FROM vaso_by24) AS INTEGER) AS vasoactive_support,
    CAST(c.stay_id IN (SELECT stay_id FROM gcs_by24) AS INTEGER) AS gcs_le_8,
    CAST(c.stay_id IN (SELECT stay_id FROM lactate_by24) AS INTEGER) AS lactate_ge_4,
    CAST(c.stay_id IN (SELECT stay_id FROM ph_by24) AS INTEGER) AS ph_le_7_20,
    CAST(c.stay_id IN (SELECT stay_id FROM inr_by24) AS INTEGER) AS inr_ge_2
  FROM cohort c
)
SELECT
  infection,
  sepsis,
  aki_stage23,
  oliguria,
  respiratory_support,
  vasoactive_support,
  gcs_le_8,
  lactate_ge_4,
  ph_le_7_20,
  inr_ge_2,
  COUNT(*) AS stays,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_stays
FROM patterns
GROUP BY 1,2,3,4,5,6,7,8,9,10
ORDER BY stays DESC
LIMIT 20;
