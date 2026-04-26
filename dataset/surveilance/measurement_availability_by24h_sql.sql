WITH cohort AS (
  SELECT
    stay_id,
    hadm_id,
    intime
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
)
SELECT
  source_name,
  stays_with_any_signal_by24h,
  ROUND(100.0 * stays_with_any_signal_by24h / (SELECT COUNT(*) FROM cohort), 2) AS pct_stays_with_any_signal_by24h
FROM (
  SELECT
    'suspicion_of_infection' AS source_name,
    COUNT(DISTINCT c.stay_id) AS stays_with_any_signal_by24h
  FROM cohort c
  JOIN mimiciv_derived.suspicion_of_infection s USING (stay_id)
  WHERE s.suspected_infection_time <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'sepsis3',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.sepsis3 s USING (stay_id)
  WHERE GREATEST(s.suspected_infection_time, s.sofa_time) <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'kdigo_stages',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.kdigo_stages k USING (stay_id)
  WHERE k.charttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'urine_output_rate',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.urine_output_rate u USING (stay_id)
  WHERE u.charttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'ventilation',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.ventilation v USING (stay_id)
  WHERE v.starttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'vasoactive_agent',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.vasoactive_agent v USING (stay_id)
  WHERE v.starttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'gcs',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.gcs g USING (stay_id)
  WHERE g.charttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'bg',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.bg b
    ON b.hadm_id = c.hadm_id
  WHERE b.charttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'coagulation',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.coagulation co
    ON co.hadm_id = c.hadm_id
  WHERE co.charttime <= c.intime + INTERVAL '24 hours'

  UNION ALL

  SELECT
    'crrt',
    COUNT(DISTINCT c.stay_id)
  FROM cohort c
  JOIN mimiciv_derived.crrt r USING (stay_id)
  WHERE r.charttime <= c.intime + INTERVAL '24 hours'
)
ORDER BY stays_with_any_signal_by24h DESC, source_name;
