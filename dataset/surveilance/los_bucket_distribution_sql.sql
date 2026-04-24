WITH cohort AS (
  SELECT
    EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 AS icu_los_hours
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
),
buckets AS (
  SELECT
    CASE
      WHEN icu_los_hours < 72 THEN '48-72h'
      WHEN icu_los_hours < 96 THEN '72-96h'
      WHEN icu_los_hours < 168 THEN '4-7d'
      WHEN icu_los_hours < 336 THEN '7-14d'
      WHEN icu_los_hours < 720 THEN '14-30d'
      ELSE '30d+'
    END AS los_bucket
  FROM cohort
)
SELECT
  los_bucket,
  COUNT(*) AS stays,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_stays
FROM buckets
GROUP BY 1
ORDER BY CASE los_bucket
  WHEN '48-72h' THEN 1
  WHEN '72-96h' THEN 2
  WHEN '4-7d' THEN 3
  WHEN '7-14d' THEN 4
  WHEN '14-30d' THEN 5
  ELSE 6
END;
