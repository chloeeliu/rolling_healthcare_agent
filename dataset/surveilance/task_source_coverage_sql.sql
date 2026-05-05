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
micro_culture AS (
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN COALESCE(m.charttime, CAST(m.chartdate AS TIMESTAMP)) <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_hosp.microbiologyevents m
    ON m.subject_id = c.subject_id
   AND m.hadm_id = c.hadm_id
  WHERE COALESCE(m.charttime, CAST(m.chartdate AS TIMESTAMP)) >= c.intime
    AND COALESCE(m.charttime, CAST(m.chartdate AS TIMESTAMP)) <= c.intime + INTERVAL '48 hours'
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
    i.starttime AS admin_time,
    lower(d.label) AS antibiotic_name
  FROM cohort c
  JOIN mimiciv_icu.inputevents i
    ON i.stay_id = c.stay_id
  JOIN mimiciv_icu.d_items d
    ON d.itemid = i.itemid
  WHERE d.category = 'Antibiotics'
    AND i.starttime >= c.intime
    AND i.starttime <= c.intime + INTERVAL '48 hours'

  UNION ALL

  SELECT
    c.stay_id,
    p.starttime AS admin_time,
    lower(p.drug) AS antibiotic_name
  FROM cohort c
  JOIN mimiciv_hosp.prescriptions p
    ON p.subject_id = c.subject_id
   AND p.hadm_id = c.hadm_id
  WHERE p.starttime >= c.intime
    AND p.starttime <= c.intime + INTERVAL '48 hours'
    AND regexp_matches(
      lower(p.drug),
      'vancomycin|cefepime|meropenem|piperacillin|cefazolin|ceftriaxone|ampicillin|gentamicin|levofloxacin|ciprofloxacin|metronidazole|linezolid|daptomycin|cefotaxime|ceftazidime|aztreonam|imipenem|tigecycline|colistin|polymyxin|teicoplanin'
    )
),
abx_non_prophylaxis AS (
  SELECT *
  FROM abx_admins
  WHERE antibiotic_name NOT LIKE '%cefazolin%'
),
abx_summary AS (
  SELECT
    stay_id,
    CASE WHEN admin_time <= (SELECT intime FROM cohort WHERE cohort.stay_id = abx_non_prophylaxis.stay_id) + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h,
    COUNT(*) AS admin_count,
    COUNT(DISTINCT antibiotic_name) AS distinct_abx
  FROM abx_non_prophylaxis
  GROUP BY 1, 2
),
infection_source AS (
  SELECT stay_id, window_h
  FROM micro_culture
  UNION
  SELECT DISTINCT
    stay_id,
    CASE WHEN admin_time <= (SELECT intime FROM cohort WHERE cohort.stay_id = abx_admins.stay_id) + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM abx_admins
),
infection_positive_proxy AS (
  SELECT stay_id, window_h
  FROM micro_culture
  UNION
  SELECT stay_id, window_h
  FROM abx_summary
  WHERE admin_count >= 2 OR distinct_abx >= 2
),
creatinine_source AS (
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN le.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_hosp.labevents le
    ON le.subject_id = c.subject_id
  WHERE le.itemid IN (50912, 51081, 51977, 52546)
    AND le.valuenum IS NOT NULL
    AND le.charttime >= c.intime
    AND le.charttime <= c.intime + INTERVAL '48 hours'
),
urine_source AS (
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN oe.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_icu.outputevents oe
    ON oe.stay_id = c.stay_id
  WHERE oe.itemid IN (226557, 226558, 226559, 226560, 226561, 226563, 226564, 226565, 226566, 226567, 226582, 226627, 226631, 227489)
    AND oe.value IS NOT NULL
    AND oe.charttime >= c.intime
    AND oe.charttime <= c.intime + INTERVAL '48 hours'
),
weight_source AS (
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (224639, 226512, 226846)
    AND ce.valuenum IS NOT NULL
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '48 hours'
),
aki_source AS (
  SELECT stay_id, window_h
  FROM creatinine_source
  UNION
  SELECT stay_id, window_h
  FROM urine_source
),
oliguria_source AS (
  SELECT DISTINCT u.stay_id, u.window_h
  FROM urine_source u
  JOIN weight_source w
    ON u.stay_id = w.stay_id
   AND u.window_h = w.window_h
),
vent_o2 AS (
  SELECT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h,
    ce.value
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid = 226732
    AND ce.value IS NOT NULL
    AND ce.value != 'None'
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '48 hours'
),
niv_extra AS (
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (227577, 227578, 225949, 227583)
    AND ce.value IS NOT NULL
    AND ce.value != 'Not applicable'
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '48 hours'
),
resp_source AS (
  SELECT DISTINCT stay_id, window_h
  FROM vent_o2
  UNION
  SELECT stay_id, window_h
  FROM niv_extra
),
resp_positive_proxy AS (
  SELECT DISTINCT stay_id, window_h
  FROM vent_o2
  WHERE value IN ('Endotracheal tube', 'Tracheostomy tube', 'Bipap mask', 'CPAP mask', 'High flow nasal cannula')
  UNION
  SELECT stay_id, window_h
  FROM niv_extra
),
vaso_source AS (
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN ie.starttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_icu.inputevents ie
    ON ie.stay_id = c.stay_id
  WHERE ie.itemid IN (221289, 229617, 221653, 221662, 221986, 221906, 221749, 229632, 229631, 229630, 222315)
    AND ie.starttime >= c.intime
    AND ie.starttime <= c.intime + INTERVAL '48 hours'
),
gcs_records AS (
  SELECT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h,
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
    AND ce.charttime <= c.intime + INTERVAL '48 hours'
  GROUP BY 1, 2, 3
),
gcs_source AS (
  SELECT DISTINCT stay_id, window_h
  FROM gcs_records
),
gcs_positive_proxy AS (
  SELECT DISTINCT stay_id, window_h
  FROM gcs_records
  WHERE eye IS NOT NULL
    AND verbal IS NOT NULL
    AND motor IS NOT NULL
    AND (eye + verbal + motor) <= 8
),
bg_measurements AS (
  SELECT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h,
    ce.charttime,
    ce.itemid,
    ce.valuenum
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (223830, 220274, 225668)
    AND ce.valuenum IS NOT NULL
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '48 hours'

  UNION ALL

  SELECT
    c.stay_id,
    CASE WHEN le.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h,
    le.charttime,
    le.itemid,
    le.valuenum
  FROM cohort c
  JOIN mimiciv_hosp.labevents le
    ON le.hadm_id = c.hadm_id
  WHERE le.itemid IN (50820, 50813, 52442, 53154)
    AND le.valuenum IS NOT NULL
    AND le.charttime >= c.intime
    AND le.charttime <= c.intime + INTERVAL '48 hours'
),
bg_source AS (
  SELECT DISTINCT stay_id, window_h
  FROM bg_measurements
),
lactate_positive_proxy AS (
  SELECT DISTINCT stay_id, window_h
  FROM bg_measurements
  WHERE itemid IN (225668, 50813, 52442, 53154)
    AND valuenum >= 4.0
),
acidemia_positive_proxy AS (
  SELECT DISTINCT stay_id, window_h
  FROM bg_measurements
  WHERE itemid IN (223830, 220274, 50820)
    AND valuenum <= 7.20
),
coag_values AS (
  SELECT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h,
    ce.itemid,
    ce.valuenum
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (220561, 227467, 220562, 227466)
    AND ce.valuenum IS NOT NULL
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '48 hours'
),
coag_source AS (
  SELECT DISTINCT stay_id, window_h
  FROM coag_values
),
coag_positive_proxy AS (
  SELECT DISTINCT stay_id, window_h
  FROM coag_values
  WHERE itemid IN (220561, 227467)
    AND valuenum >= 2.0
),
crrt_source AS (
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid = 227290
    AND ce.value IS NOT NULL
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '48 hours'
),
sofa_source AS (
  SELECT stay_id, window_h
  FROM creatinine_source
  UNION
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN ce.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_icu.chartevents ce
    ON ce.stay_id = c.stay_id
  WHERE ce.itemid IN (220224, 223835, 220052, 220739, 223900, 223901)
    AND ce.valuenum IS NOT NULL
    AND ce.charttime >= c.intime
    AND ce.charttime <= c.intime + INTERVAL '48 hours'
  UNION
  SELECT DISTINCT
    c.stay_id,
    CASE WHEN le.charttime <= c.intime + INTERVAL '24 hours' THEN 24 ELSE 48 END AS window_h
  FROM cohort c
  JOIN mimiciv_hosp.labevents le
    ON le.hadm_id = c.hadm_id
  WHERE le.itemid IN (51265, 50885, 50912, 51081, 51977, 52546)
    AND le.valuenum IS NOT NULL
    AND le.charttime >= c.intime
    AND le.charttime <= c.intime + INTERVAL '48 hours'
  UNION
  SELECT stay_id, window_h
  FROM vaso_source
),
sepsis_source AS (
  SELECT DISTINCT i.stay_id, i.window_h
  FROM infection_source i
  JOIN sofa_source s
    ON i.stay_id = s.stay_id
   AND i.window_h = s.window_h
),
summary AS (
  SELECT
    'infection' AS task_name,
    'suspicion_of_infection' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM infection_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM infection_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM infection_positive_proxy WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM infection_positive_proxy WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Positive proxy uses non-screening cultures or non-prophylaxis antibiotic treatment pattern.' AS notes

  UNION ALL

  SELECT
    'sepsis' AS task_name,
    'suspicion_of_infection + sofa' AS auto_function,
    'composed_task' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM sepsis_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM sepsis_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    NULL AS positive_proxy_by_24h,
    NULL AS positive_proxy_by_48h,
    'Composed head. Final label builder should combine infection and sofa contracts rather than direct sepsis3.py.' AS notes

  UNION ALL

  SELECT
    'aki' AS task_name,
    'kdigo_stages' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM aki_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM aki_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    NULL AS positive_proxy_by_24h,
    NULL AS positive_proxy_by_48h,
    'Stage label should come from frozen autoformalized KDIGO contract, not direct source presence.' AS notes

  UNION ALL

  SELECT
    'oliguria' AS task_name,
    'urine_output_rate' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM oliguria_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM oliguria_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    NULL AS positive_proxy_by_24h,
    NULL AS positive_proxy_by_48h,
    'Source coverage requires both urine output and weight; final label should use frozen urine-output-rate contract.' AS notes

  UNION ALL

  SELECT
    'respiratory_support' AS task_name,
    'ventilation' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM resp_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM resp_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM resp_positive_proxy WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM resp_positive_proxy WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Positive proxy corresponds to HFNC, NIV, or invasive support evidence used by the function.' AS notes

  UNION ALL

  SELECT
    'vasoactive_support' AS task_name,
    'vasoactive_agent' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM vaso_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM vaso_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM vaso_source WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM vaso_source WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Positive proxy is direct vasoactive/inotrope exposure.' AS notes

  UNION ALL

  SELECT
    'neurologic_deterioration' AS task_name,
    'gcs' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM gcs_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM gcs_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM gcs_positive_proxy WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM gcs_positive_proxy WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Positive proxy uses GCS total <= 8 from raw component rows.' AS notes

  UNION ALL

  SELECT
    'hyperlactatemia' AS task_name,
    'bg' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM bg_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM bg_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM lactate_positive_proxy WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM lactate_positive_proxy WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Positive proxy uses lactate >= 4.0 from chart or lab blood-gas sources.' AS notes

  UNION ALL

  SELECT
    'severe_acidemia' AS task_name,
    'bg' AS auto_function,
    'ready' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM bg_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM bg_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM acidemia_positive_proxy WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM acidemia_positive_proxy WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Positive proxy uses minimum pH <= 7.20 from chart or lab blood-gas sources.' AS notes

  UNION ALL

  SELECT
    'coagulopathy' AS task_name,
    'coagulation' AS auto_function,
    'adapter_needed' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM coag_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM coag_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM coag_positive_proxy WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM coag_positive_proxy WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Positive proxy uses INR >= 2.0 from the raw ICU coagulation sources used by the autoformalized function.' AS notes

  UNION ALL

  SELECT
    'crrt' AS task_name,
    'crrt' AS auto_function,
    'optional_adapter' AS runtime_status,
    (SELECT COUNT(DISTINCT stay_id) FROM crrt_source WHERE window_h = 24) AS source_signal_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM crrt_source WHERE window_h IN (24, 48)) AS source_signal_by_48h,
    (SELECT COUNT(DISTINCT stay_id) FROM crrt_source WHERE window_h = 24) AS positive_proxy_by_24h,
    (SELECT COUNT(DISTINCT stay_id) FROM crrt_source WHERE window_h IN (24, 48)) AS positive_proxy_by_48h,
    'Optional advanced-support head. Positive proxy equals observed CRRT mode data.' AS notes
)
SELECT *
FROM summary
ORDER BY CASE
  WHEN task_name = 'infection' THEN 1
  WHEN task_name = 'sepsis' THEN 2
  WHEN task_name = 'aki' THEN 3
  WHEN task_name = 'oliguria' THEN 4
  WHEN task_name = 'respiratory_support' THEN 5
  WHEN task_name = 'vasoactive_support' THEN 6
  WHEN task_name = 'neurologic_deterioration' THEN 7
  WHEN task_name = 'hyperlactatemia' THEN 8
  WHEN task_name = 'severe_acidemia' THEN 9
  WHEN task_name = 'coagulopathy' THEN 10
  ELSE 11
END;
