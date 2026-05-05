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
  CONCAT('mimiciv_stay_', CAST(s.stay_id AS VARCHAR)) AS trajectory_id,
  s.split,
  s.stay_id,
  s.subject_id,
  s.hadm_id,
  s.icu_intime,
  s.icu_outtime,
  ROUND(s.icu_los_hours, 2) AS icu_los_hours,
  gs.t_hour,
  s.icu_intime + gs.t_hour * INTERVAL '1 hour' AS checkpoint_time,
  CAST(gs.t_hour = 48 AS BOOLEAN) AS terminal
FROM icu_eligible s
CROSS JOIN generate_series(0, 48, 4) AS gs(t_hour)
ORDER BY s.split, s.stay_id, gs.t_hour;
