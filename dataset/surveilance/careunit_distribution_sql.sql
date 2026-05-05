WITH cohort AS (
  SELECT
    stay_id,
    first_careunit
  FROM mimiciv_icu.icustays
  WHERE intime IS NOT NULL
    AND outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (outtime - intime)) / 3600.0 >= 48
)
SELECT
  COALESCE(first_careunit, 'UNKNOWN') AS first_careunit,
  COUNT(*) AS stays,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_stays
FROM cohort
GROUP BY 1
ORDER BY stays DESC, first_careunit;
