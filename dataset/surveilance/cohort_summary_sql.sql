WITH icu_eligible AS (
  SELECT
    stay_id,
    subject_id,
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
),
summary_rows AS (
  SELECT
    split,
    COUNT(*) AS eligible_stays,
    COUNT(*) * 13 AS checkpoint_rows,
    ROUND(MIN(icu_los_hours), 2) AS min_los_hours,
    ROUND(AVG(icu_los_hours), 2) AS mean_los_hours,
    ROUND(quantile_cont(icu_los_hours, 0.5), 2) AS median_los_hours,
    ROUND(MAX(icu_los_hours), 2) AS max_los_hours
  FROM icu_eligible
  GROUP BY 1

  UNION ALL

  SELECT
    'all' AS split,
    COUNT(*) AS eligible_stays,
    COUNT(*) * 13 AS checkpoint_rows,
    ROUND(MIN(icu_los_hours), 2) AS min_los_hours,
    ROUND(AVG(icu_los_hours), 2) AS mean_los_hours,
    ROUND(quantile_cont(icu_los_hours, 0.5), 2) AS median_los_hours,
    ROUND(MAX(icu_los_hours), 2) AS max_los_hours
  FROM icu_eligible
)
SELECT *
FROM summary_rows
ORDER BY CASE split WHEN 'train' THEN 1 WHEN 'dev' THEN 2 WHEN 'test' THEN 3 ELSE 4 END;
