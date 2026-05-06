WITH manifest AS (
  SELECT
    split,
    stay_id
  FROM read_csv_auto('/Users/chloe/Documents/New project/paper_release/surveillance_benchmark_48h/benchmark_2k_manifest.csv', header = true)
),
truth AS (
  SELECT *
  FROM read_csv_auto('/Users/chloe/Documents/New project/paper_release/surveillance_benchmark_48h/checkpoint_truth_all.csv', header = true)
)
SELECT t.*
FROM truth t
JOIN manifest m
  ON m.split = t.split
 AND m.stay_id = t.stay_id
ORDER BY t.split, t.stay_id, t.t_hour
