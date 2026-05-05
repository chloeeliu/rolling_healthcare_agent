WITH icu_eligible AS (
  SELECT
    stay_id,
    subject_id,
    hadm_id,
    intime AS icu_intime,
    outtime AS icu_outtime,
    EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 AS icu_los_hours,
    CASE
      WHEN MOD(hash(subject_id), 20) < 14 THEN 'train'
      WHEN MOD(hash(subject_id), 20) < 17 THEN 'dev'
      ELSE 'test'
    END AS split
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
)
SELECT
  CONCAT('mimiciv_stay_', CAST(stay_id AS VARCHAR)) AS trajectory_id,
  split,
  stay_id,
  subject_id,
  hadm_id,
  icu_intime,
  icu_outtime,
  ROUND(icu_los_hours, 2) AS icu_los_hours,
  'icu_intime' AS anchor,
  4 AS step_hours,
  48 AS horizon_hours
FROM icu_eligible
ORDER BY split, stay_id;
