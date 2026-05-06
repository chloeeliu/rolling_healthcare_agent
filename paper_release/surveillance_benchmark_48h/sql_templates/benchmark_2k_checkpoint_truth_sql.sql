WITH manifest AS (
  SELECT
    split,
    stay_id
  FROM read_csv_auto('{{BENCHMARK_2K_MANIFEST_CSV}}', header = true)
),
truth AS (
  SELECT *
  FROM read_csv_auto('{{CHECKPOINT_TRUTH_ALL_CSV}}', header = true)
)
SELECT t.*
FROM truth t
JOIN manifest m
  ON m.split = t.split
 AND m.stay_id = t.stay_id
ORDER BY t.split, t.stay_id, t.t_hour;
