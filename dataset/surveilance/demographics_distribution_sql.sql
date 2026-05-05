WITH cohort AS (
  SELECT
    i.stay_id,
    i.subject_id,
    i.hadm_id,
    i.intime,
    i.first_careunit,
    p.gender,
    p.anchor_age + (EXTRACT(YEAR FROM i.intime) - p.anchor_year) AS age_at_icu
  FROM mimiciv_icu.icustays i
  JOIN mimiciv_hosp.patients p
    ON p.subject_id = i.subject_id
  WHERE i.intime IS NOT NULL
    AND i.outtime IS NOT NULL
    AND EXTRACT(EPOCH FROM (i.outtime - i.intime)) / 3600.0 >= 48
)
SELECT
  age_bucket,
  gender,
  COUNT(*) AS stays,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_stays
FROM (
  SELECT
    CASE
      WHEN age_at_icu < 40 THEN '<40'
      WHEN age_at_icu < 50 THEN '40-49'
      WHEN age_at_icu < 60 THEN '50-59'
      WHEN age_at_icu < 70 THEN '60-69'
      WHEN age_at_icu < 80 THEN '70-79'
      ELSE '80+'
    END AS age_bucket,
    gender
  FROM cohort
)
GROUP BY 1, 2
ORDER BY
  CASE age_bucket
    WHEN '<40' THEN 1
    WHEN '40-49' THEN 2
    WHEN '50-59' THEN 3
    WHEN '60-69' THEN 4
    WHEN '70-79' THEN 5
    ELSE 6
  END,
  gender;
