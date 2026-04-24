WITH cohort AS (
  SELECT
    stay_id,
    subject_id,
    hadm_id,
    intime
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
),
micro_culture AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_hosp.microbiologyevents m
    ON m.subject_id = c.subject_id
   AND m.hadm_id = c.hadm_id
  WHERE COALESCE(m.charttime, CAST(m.chartdate AS TIMESTAMP)) >= c.intime
    AND COALESCE(m.charttime, CAST(m.chartdate AS TIMESTAMP)) <= c.intime + INTERVAL '24 hours'
    AND m.spec_type_desc IS NOT NULL
    AND m.spec_type_desc NOT IN (
      'MRSA SCREEN',
      'CRE Screen',
      'Cipro Resistant Screen',
      'C, E, & A Screening',
      'Infection Control Yeast',
      'Swab R/O Yeast Screen',
      'MICRO PROBLEM PATIENT',
      'Isolate',
      'XXX'
    )
),
abx_admins AS (
  SELECT
    c.stay_id,
    lower(d.label) AS antibiotic_name
  FROM cohort c
  JOIN mimiciv_icu.inputevents i
    ON i.stay_id = c.stay_id
  JOIN mimiciv_icu.d_items d
    ON d.itemid = i.itemid
  WHERE d.category = 'Antibiotics'
    AND i.starttime >= c.intime
    AND i.starttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    c.stay_id,
    lower(p.drug) AS antibiotic_name
  FROM cohort c
  JOIN mimiciv_hosp.prescriptions p
    ON p.subject_id = c.subject_id
   AND p.hadm_id = c.hadm_id
  WHERE p.starttime >= c.intime
    AND p.starttime <= c.intime + INTERVAL '24 hours'
    AND regexp_matches(
      lower(p.drug),
      'vancomycin|cefepime|meropenem|piperacillin|cefazolin|ceftriaxone|ampicillin|gentamicin|levofloxacin|ciprofloxacin|metronidazole|linezolid|daptomycin|cefotaxime|ceftazidime|aztreonam|imipenem|tigecycline|colistin|polymyxin|teicoplanin'
    )
),
abx_summary AS (
  SELECT
    stay_id,
    COUNT(*) FILTER (WHERE antibiotic_name NOT LIKE '%cefazolin%') AS admin_count,
    COUNT(DISTINCT CASE WHEN antibiotic_name NOT LIKE '%cefazolin%' THEN antibiotic_name END) AS distinct_abx
  FROM abx_admins
  GROUP BY 1
),
infection_positive AS (
  SELECT stay_id FROM micro_culture
  UNION
  SELECT stay_id
  FROM abx_summary
  WHERE admin_count >= 2 OR distinct_abx >= 2
),
vent_positive AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid = 226732
    AND ce.value IN ('Endotracheal tube', 'Tracheostomy tube', 'Bipap mask', 'CPAP mask', 'High flow nasal cannula')
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '24 hours'

  UNION

  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (227577, 227578, 225949, 227583)
    AND ce.value IS NOT NULL
    AND ce.value != 'Not applicable'
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '24 hours'
),
vaso_positive AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_icu.inputevents ie
    ON ie.stay_id = c.stay_id
  WHERE ie.itemid IN (221289, 229617, 221653, 221662, 221986, 221906, 221749, 229632, 229631, 229630, 222315)
    AND ie.starttime >= c.intime
    AND ie.starttime <= c.intime + INTERVAL '24 hours'
),
gcs_positive AS (
  SELECT DISTINCT stay_id
  FROM (
    SELECT
      c.stay_id,
      ce.charttime,
      MAX(CASE WHEN ce.itemid = 220739 THEN ce.valuenum END) AS eye,
      MAX(CASE WHEN ce.itemid = 223900 THEN ce.valuenum END) AS verbal,
      MAX(CASE WHEN ce.itemid = 223901 THEN ce.valuenum END) AS motor
    FROM cohort c
    JOIN mimiciv_icu.chartevents ce
      ON ce.stay_id = c.stay_id
    WHERE ce.itemid IN (220739, 223900, 223901)
      AND ce.valuenum IS NOT NULL
      AND ce.charttime >= c.intime
      AND ce.charttime <= c.intime + INTERVAL '24 hours'
    GROUP BY 1, 2
  ) g
  WHERE eye IS NOT NULL AND verbal IS NOT NULL AND motor IS NOT NULL
    AND (eye + verbal + motor) <= 8
),
bg_measurements AS (
  SELECT
    c.stay_id,
    ce.itemid,
    ce.valuenum
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (223830, 220274, 225668)
    AND ce.valuenum IS NOT NULL
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    c.stay_id,
    le.itemid,
    le.valuenum
  FROM cohort c
  JOIN mimiciv_hosp.labevents le
    ON le.hadm_id = c.hadm_id
  WHERE le.itemid IN (50820, 50813, 52442, 53154)
    AND le.valuenum IS NOT NULL
    AND le.charttime >= c.intime
    AND le.charttime <= c.intime + INTERVAL '24 hours'
),
lactate_positive AS (
  SELECT DISTINCT stay_id
  FROM bg_measurements
  WHERE itemid IN (225668, 50813, 52442, 53154)
    AND valuenum >= 4.0
),
acidemia_positive AS (
  SELECT DISTINCT stay_id
  FROM bg_measurements
  WHERE itemid IN (223830, 220274, 50820)
    AND valuenum <= 7.20
),
coag_positive AS (
  SELECT DISTINCT c.stay_id
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (220561, 227467)
    AND ce.valuenum >= 2.0
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '24 hours'
),
patterns AS (
  SELECT
    CAST(c.stay_id IN (SELECT stay_id FROM infection_positive) AS INTEGER) AS infection,
    CAST(c.stay_id IN (SELECT stay_id FROM vent_positive) AS INTEGER) AS respiratory_support,
    CAST(c.stay_id IN (SELECT stay_id FROM vaso_positive) AS INTEGER) AS vasoactive_support,
    CAST(c.stay_id IN (SELECT stay_id FROM gcs_positive) AS INTEGER) AS neurologic_deterioration,
    CAST(c.stay_id IN (SELECT stay_id FROM lactate_positive) AS INTEGER) AS hyperlactatemia,
    CAST(c.stay_id IN (SELECT stay_id FROM acidemia_positive) AS INTEGER) AS severe_acidemia,
    CAST(c.stay_id IN (SELECT stay_id FROM coag_positive) AS INTEGER) AS coagulopathy
  FROM cohort c
)
SELECT
  infection,
  respiratory_support,
  vasoactive_support,
  neurologic_deterioration,
  hyperlactatemia,
  severe_acidemia,
  coagulopathy,
  COUNT(*) AS stays,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_stays
FROM patterns
GROUP BY 1,2,3,4,5,6,7
ORDER BY stays DESC
LIMIT 15;
