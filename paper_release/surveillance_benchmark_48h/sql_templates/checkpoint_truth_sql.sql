WITH cohort AS (
  SELECT
    CONCAT('mimiciv_stay_', CAST(stay_id AS VARCHAR)) AS trajectory_id,
    stay_id,
    subject_id,
    hadm_id,
    first_careunit,
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
),
checkpoints AS (
  SELECT
    c.trajectory_id,
    c.split,
    c.stay_id,
    c.subject_id,
    c.hadm_id,
    c.first_careunit,
    c.icu_intime,
    c.icu_outtime,
    ROUND(c.icu_los_hours, 2) AS icu_los_hours,
    gs.t_hour,
    c.icu_intime + gs.t_hour * INTERVAL '1 hour' AS checkpoint_time,
    CAST(gs.t_hour = 48 AS BOOLEAN) AS terminal
  FROM cohort c
  CROSS JOIN generate_series(0, 48, 4) AS gs(t_hour)
),
infection_first AS (
  SELECT
    stay_id,
    MIN(suspected_infection_time) AS event_time
  FROM mimiciv_derived.suspicion_of_infection
  WHERE suspected_infection = 1
    AND suspected_infection_time IS NOT NULL
  GROUP BY 1
),
infection_confirmed_first AS (
  SELECT
    stay_id,
    MIN(culture_time) AS event_time
  FROM mimiciv_derived.suspicion_of_infection
  WHERE positive_culture = 1
    AND culture_time IS NOT NULL
  GROUP BY 1
),
sepsis_first AS (
  SELECT
    stay_id,
    MIN(GREATEST(suspected_infection_time, sofa_time)) AS event_time
  FROM mimiciv_derived.sepsis3
  WHERE sepsis3 = TRUE
    AND suspected_infection_time IS NOT NULL
    AND sofa_time IS NOT NULL
  GROUP BY 1
),
kdigo_progression AS (
  SELECT
    stay_id,
    charttime,
    MAX(COALESCE(aki_stage_smoothed, 0)) OVER (
      PARTITION BY stay_id
      ORDER BY charttime
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS max_aki_stage_so_far
  FROM mimiciv_derived.kdigo_stages
  WHERE charttime IS NOT NULL
),
checkpoint_kdigo AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    COALESCE(k.max_aki_stage_so_far, 0) AS max_aki_stage_so_far
  FROM checkpoints c
  ASOF LEFT JOIN kdigo_progression k
    ON c.stay_id = k.stay_id
   AND c.checkpoint_time >= k.charttime
),
uo_latest AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    u.charttime AS uo_charttime,
    u.uo_tm_6hr,
    u.uo_mlkghr_6hr,
    u.uo_tm_12hr,
    u.uo_mlkghr_12hr,
    u.uo_tm_24hr,
    u.uo_mlkghr_24hr
  FROM checkpoints c
  ASOF LEFT JOIN (
    SELECT
      stay_id,
      charttime,
      uo_tm_6hr,
      uo_mlkghr_6hr,
      uo_tm_12hr,
      uo_mlkghr_12hr,
      uo_tm_24hr,
      uo_mlkghr_24hr
    FROM mimiciv_derived.urine_output_rate
    WHERE charttime IS NOT NULL
  ) u
    ON c.stay_id = u.stay_id
   AND c.checkpoint_time >= u.charttime
),
gcs_latest AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    g.charttime AS gcs_charttime,
    g.gcs
  FROM checkpoints c
  ASOF LEFT JOIN (
    SELECT stay_id, charttime, gcs
    FROM mimiciv_derived.gcs
    WHERE charttime IS NOT NULL
      AND gcs IS NOT NULL
  ) g
    ON c.stay_id = g.stay_id
   AND c.checkpoint_time >= g.charttime
),
pf_latest AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    bg.charttime AS pf_charttime,
    bg.pao2fio2ratio
  FROM checkpoints c
  ASOF LEFT JOIN (
    SELECT hadm_id, charttime, pao2fio2ratio
    FROM mimiciv_derived.bg
    WHERE charttime IS NOT NULL
      AND pao2fio2ratio IS NOT NULL
  ) bg
    ON c.hadm_id = bg.hadm_id
   AND c.checkpoint_time >= bg.charttime
),
lactate_latest AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    bg.charttime AS lactate_charttime,
    bg.lactate
  FROM checkpoints c
  ASOF LEFT JOIN (
    SELECT hadm_id, charttime, lactate
    FROM mimiciv_derived.bg
    WHERE charttime IS NOT NULL
      AND lactate IS NOT NULL
  ) bg
    ON c.hadm_id = bg.hadm_id
   AND c.checkpoint_time >= bg.charttime
),
ph_latest AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    bg.charttime AS ph_charttime,
    bg.ph
  FROM checkpoints c
  ASOF LEFT JOIN (
    SELECT hadm_id, charttime, ph
    FROM mimiciv_derived.bg
    WHERE charttime IS NOT NULL
      AND ph IS NOT NULL
  ) bg
    ON c.hadm_id = bg.hadm_id
   AND c.checkpoint_time >= bg.charttime
),
inr_latest AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    co.charttime AS inr_charttime,
    co.inr
  FROM checkpoints c
  ASOF LEFT JOIN (
    SELECT hadm_id, charttime, inr
    FROM mimiciv_derived.coagulation
    WHERE charttime IS NOT NULL
      AND inr IS NOT NULL
  ) co
    ON c.hadm_id = co.hadm_id
   AND c.checkpoint_time >= co.charttime
),
crrt_latest AS (
  SELECT
    c.stay_id,
    c.t_hour,
    c.checkpoint_time,
    r.charttime AS crrt_charttime,
    r.crrt_mode,
    r.system_active
  FROM checkpoints c
  ASOF LEFT JOIN (
    SELECT stay_id, charttime, crrt_mode, system_active
    FROM mimiciv_derived.crrt
    WHERE charttime IS NOT NULL
      AND crrt_mode IS NOT NULL
  ) r
    ON c.stay_id = r.stay_id
   AND c.checkpoint_time >= r.charttime
),
ventilation_current AS (
  SELECT
    c.stay_id,
    c.t_hour,
    MAX(CASE WHEN v.ventilation_status IN ('HFNC', 'NonInvasiveVent') THEN 1 ELSE 0 END) AS resp_support_hfnc_or_niv,
    MAX(CASE WHEN v.ventilation_status IN ('InvasiveVent', 'Tracheostomy') THEN 1 ELSE 0 END) AS resp_support_invasive_vent
  FROM checkpoints c
  LEFT JOIN mimiciv_derived.ventilation v
    ON v.stay_id = c.stay_id
   AND v.starttime <= c.checkpoint_time
   AND COALESCE(v.endtime, TIMESTAMP '2100-01-01') > c.checkpoint_time
  GROUP BY 1, 2
),
vasoactive_current AS (
  SELECT
    c.stay_id,
    c.t_hour,
    MAX(
      CASE
        WHEN COALESCE(v.dopamine, v.epinephrine, v.norepinephrine, v.phenylephrine, v.vasopressin, v.dobutamine, v.milrinone) IS NOT NULL
          THEN 1
        ELSE 0
      END
    ) AS vasoactive_support_any,
    MAX(
      CASE
        WHEN (
          CAST(v.dopamine IS NOT NULL AS INTEGER) +
          CAST(v.epinephrine IS NOT NULL AS INTEGER) +
          CAST(v.norepinephrine IS NOT NULL AS INTEGER) +
          CAST(v.phenylephrine IS NOT NULL AS INTEGER) +
          CAST(v.vasopressin IS NOT NULL AS INTEGER) +
          CAST(v.dobutamine IS NOT NULL AS INTEGER) +
          CAST(v.milrinone IS NOT NULL AS INTEGER)
        ) >= 2 THEN 1
        ELSE 0
      END
    ) AS vasoactive_multi_agent_or_high_intensity
  FROM checkpoints c
  LEFT JOIN mimiciv_derived.vasoactive_agent v
    ON v.stay_id = c.stay_id
   AND v.starttime <= c.checkpoint_time
   AND COALESCE(v.endtime, TIMESTAMP '2100-01-01') > c.checkpoint_time
  GROUP BY 1, 2
),
decision_flags AS (
  SELECT
    c.trajectory_id,
    c.split,
    c.stay_id,
    c.subject_id,
    c.hadm_id,
    c.first_careunit,
    c.icu_intime,
    c.icu_outtime,
    c.icu_los_hours,
    c.t_hour,
    c.checkpoint_time,
    c.terminal,
    CAST(i.event_time IS NOT NULL AND i.event_time <= c.checkpoint_time AS INTEGER) AS infection_suspected,
    CAST(ic.event_time IS NOT NULL AND ic.event_time <= c.checkpoint_time AS INTEGER) AS infection_confirmed_or_strongly_supported,
    CAST(s.event_time IS NOT NULL AND s.event_time <= c.checkpoint_time AS INTEGER) AS sepsis_alert,
    CAST(k.max_aki_stage_so_far >= 1 AS INTEGER) AS aki_stage1,
    CAST(k.max_aki_stage_so_far >= 2 AS INTEGER) AS aki_stage2,
    CAST(k.max_aki_stage_so_far >= 3 AS INTEGER) AS aki_stage3,
    CAST(
      u.uo_charttime IS NOT NULL
      AND u.uo_charttime >= c.checkpoint_time - INTERVAL '6 hours'
      AND u.uo_tm_6hr >= 6
      AND u.uo_mlkghr_6hr < 0.5
      AS INTEGER
    ) AS oliguria_6h,
    CAST(
      u.uo_charttime IS NOT NULL
      AND u.uo_charttime >= c.checkpoint_time - INTERVAL '24 hours'
      AND (
        (u.uo_tm_12hr >= 12 AND u.uo_mlkghr_12hr < 0.5)
        OR (u.uo_tm_24hr >= 24 AND u.uo_mlkghr_24hr < 0.3)
      )
      AS INTEGER
    ) AS severe_oliguria_or_anuria,
    CAST(
      cr.crrt_charttime IS NOT NULL
      AND cr.crrt_charttime >= c.checkpoint_time - INTERVAL '12 hours'
      AND COALESCE(cr.system_active, 1) = 1
      AS INTEGER
    ) AS crrt_active,
    COALESCE(v.resp_support_hfnc_or_niv, 0) AS resp_support_hfnc_or_niv,
    COALESCE(v.resp_support_invasive_vent, 0) AS resp_support_invasive_vent,
    CAST(
      pf.pf_charttime IS NOT NULL
      AND pf.pf_charttime >= c.checkpoint_time - INTERVAL '12 hours'
      AND pf.pao2fio2ratio < 200
      AS INTEGER
    ) AS hypoxemia_pf_lt_200,
    CAST(
      pf.pf_charttime IS NOT NULL
      AND pf.pf_charttime >= c.checkpoint_time - INTERVAL '12 hours'
      AND pf.pao2fio2ratio < 100
      AS INTEGER
    ) AS hypoxemia_pf_lt_100,
    COALESCE(vc.vasoactive_support_any, 0) AS vasoactive_support_any,
    COALESCE(vc.vasoactive_multi_agent_or_high_intensity, 0) AS vasoactive_multi_agent_or_high_intensity,
    CAST(
      g.gcs_charttime IS NOT NULL
      AND g.gcs_charttime >= c.checkpoint_time - INTERVAL '8 hours'
      AND g.gcs BETWEEN 9 AND 12
      AS INTEGER
    ) AS gcs_moderate_impairment_9_12,
    CAST(
      g.gcs_charttime IS NOT NULL
      AND g.gcs_charttime >= c.checkpoint_time - INTERVAL '8 hours'
      AND g.gcs <= 8
      AS INTEGER
    ) AS gcs_severe_impairment_le_8,
    CAST(
      l.lactate_charttime IS NOT NULL
      AND l.lactate_charttime >= c.checkpoint_time - INTERVAL '12 hours'
      AND l.lactate >= 2
      AS INTEGER
    ) AS hyperlactatemia_ge_2,
    CAST(
      l.lactate_charttime IS NOT NULL
      AND l.lactate_charttime >= c.checkpoint_time - INTERVAL '12 hours'
      AND l.lactate >= 4
      AS INTEGER
    ) AS severe_hyperlactatemia_ge_4,
    CAST(
      p.ph_charttime IS NOT NULL
      AND p.ph_charttime >= c.checkpoint_time - INTERVAL '12 hours'
      AND p.ph < 7.30
      AS INTEGER
    ) AS acidemia_ph_lt_7_30,
    CAST(
      p.ph_charttime IS NOT NULL
      AND p.ph_charttime >= c.checkpoint_time - INTERVAL '12 hours'
      AND p.ph <= 7.20
      AS INTEGER
    ) AS severe_acidemia_ph_le_7_20,
    CAST(
      n.inr_charttime IS NOT NULL
      AND n.inr_charttime >= c.checkpoint_time - INTERVAL '24 hours'
      AND n.inr >= 1.5
      AS INTEGER
    ) AS coagulopathy_inr_ge_1_5,
    CAST(
      n.inr_charttime IS NOT NULL
      AND n.inr_charttime >= c.checkpoint_time - INTERVAL '24 hours'
      AND n.inr >= 2.0
      AS INTEGER
    ) AS coagulopathy_inr_ge_2
  FROM checkpoints c
  LEFT JOIN infection_first i
    ON i.stay_id = c.stay_id
  LEFT JOIN infection_confirmed_first ic
    ON ic.stay_id = c.stay_id
  LEFT JOIN sepsis_first s
    ON s.stay_id = c.stay_id
  LEFT JOIN checkpoint_kdigo k
    ON k.stay_id = c.stay_id
   AND k.t_hour = c.t_hour
  LEFT JOIN uo_latest u
    ON u.stay_id = c.stay_id
   AND u.t_hour = c.t_hour
  LEFT JOIN crrt_latest cr
    ON cr.stay_id = c.stay_id
   AND cr.t_hour = c.t_hour
  LEFT JOIN ventilation_current v
    ON v.stay_id = c.stay_id
   AND v.t_hour = c.t_hour
  LEFT JOIN pf_latest pf
    ON pf.stay_id = c.stay_id
   AND pf.t_hour = c.t_hour
  LEFT JOIN vasoactive_current vc
    ON vc.stay_id = c.stay_id
   AND vc.t_hour = c.t_hour
  LEFT JOIN gcs_latest g
    ON g.stay_id = c.stay_id
   AND g.t_hour = c.t_hour
  LEFT JOIN lactate_latest l
    ON l.stay_id = c.stay_id
   AND l.t_hour = c.t_hour
  LEFT JOIN ph_latest p
    ON p.stay_id = c.stay_id
   AND p.t_hour = c.t_hour
  LEFT JOIN inr_latest n
    ON n.stay_id = c.stay_id
   AND n.t_hour = c.t_hour
),
checkpoint_truth AS (
  SELECT
    *,
    CAST(
      sepsis_alert = 1
      AND vasoactive_support_any = 1
      AND hyperlactatemia_ge_2 = 1
      AS INTEGER
    ) AS septic_shock_alert,
    CAST(
      sepsis_alert = 1
      AND vasoactive_support_any = 1
      AND severe_hyperlactatemia_ge_4 = 1
      AS INTEGER
    ) AS shock_hypoperfusion_alert
  FROM decision_flags
),
checkpoint_truth_enriched AS (
  SELECT
    *,
    CAST(
      GREATEST(infection_suspected, infection_confirmed_or_strongly_supported) AS INTEGER
    ) AS infection_family_active,
    sepsis_alert AS sepsis_family_active,
    CAST(
      GREATEST(aki_stage1, aki_stage2, aki_stage3, oliguria_6h, severe_oliguria_or_anuria, crrt_active) AS INTEGER
    ) AS renal_family_active,
    CAST(
      GREATEST(resp_support_hfnc_or_niv, resp_support_invasive_vent, hypoxemia_pf_lt_200, hypoxemia_pf_lt_100) AS INTEGER
    ) AS respiratory_family_active,
    CAST(
      GREATEST(vasoactive_support_any, vasoactive_multi_agent_or_high_intensity, septic_shock_alert, shock_hypoperfusion_alert) AS INTEGER
    ) AS hemodynamic_family_active,
    CAST(
      GREATEST(gcs_moderate_impairment_9_12, gcs_severe_impairment_le_8) AS INTEGER
    ) AS neurologic_family_active,
    CAST(
      GREATEST(hyperlactatemia_ge_2, severe_hyperlactatemia_ge_4, acidemia_ph_lt_7_30, severe_acidemia_ph_le_7_20) AS INTEGER
    ) AS metabolic_family_active,
    CAST(
      GREATEST(coagulopathy_inr_ge_1_5, coagulopathy_inr_ge_2) AS INTEGER
    ) AS coagulation_family_active
  FROM checkpoint_truth
),
checkpoint_truth_output AS (
  SELECT
    *,
    CASE
      WHEN infection_confirmed_or_strongly_supported = 1 THEN 'infection_confirmed_or_strongly_supported'
      WHEN infection_suspected = 1 THEN 'infection_suspected'
      ELSE NULL
    END AS infection_primary_decision,
    CASE
      WHEN sepsis_alert = 1 THEN 'sepsis_alert'
      ELSE NULL
    END AS sepsis_primary_decision,
    CASE
      WHEN crrt_active = 1 THEN 'crrt_active'
      WHEN aki_stage3 = 1 THEN 'aki_stage3'
      WHEN aki_stage2 = 1 THEN 'aki_stage2'
      WHEN severe_oliguria_or_anuria = 1 THEN 'severe_oliguria_or_anuria'
      WHEN oliguria_6h = 1 THEN 'oliguria_6h'
      WHEN aki_stage1 = 1 THEN 'aki_stage1'
      ELSE NULL
    END AS renal_primary_decision,
    CASE
      WHEN resp_support_invasive_vent = 1 THEN 'resp_support_invasive_vent'
      WHEN hypoxemia_pf_lt_100 = 1 THEN 'hypoxemia_pf_lt_100'
      WHEN hypoxemia_pf_lt_200 = 1 THEN 'hypoxemia_pf_lt_200'
      WHEN resp_support_hfnc_or_niv = 1 THEN 'resp_support_hfnc_or_niv'
      ELSE NULL
    END AS respiratory_primary_decision,
    CASE
      WHEN shock_hypoperfusion_alert = 1 THEN 'shock_hypoperfusion_alert'
      WHEN septic_shock_alert = 1 THEN 'septic_shock_alert'
      WHEN vasoactive_multi_agent_or_high_intensity = 1 THEN 'vasoactive_multi_agent_or_high_intensity'
      WHEN vasoactive_support_any = 1 THEN 'vasoactive_support_any'
      ELSE NULL
    END AS hemodynamic_primary_decision,
    CASE
      WHEN gcs_severe_impairment_le_8 = 1 THEN 'gcs_severe_impairment_le_8'
      WHEN gcs_moderate_impairment_9_12 = 1 THEN 'gcs_moderate_impairment_9_12'
      ELSE NULL
    END AS neurologic_primary_decision,
    CASE
      WHEN severe_acidemia_ph_le_7_20 = 1 THEN 'severe_acidemia_ph_le_7_20'
      WHEN severe_hyperlactatemia_ge_4 = 1 THEN 'severe_hyperlactatemia_ge_4'
      WHEN acidemia_ph_lt_7_30 = 1 THEN 'acidemia_ph_lt_7_30'
      WHEN hyperlactatemia_ge_2 = 1 THEN 'hyperlactatemia_ge_2'
      ELSE NULL
    END AS metabolic_primary_decision,
    CASE
      WHEN coagulopathy_inr_ge_2 = 1 THEN 'coagulopathy_inr_ge_2'
      WHEN coagulopathy_inr_ge_1_5 = 1 THEN 'coagulopathy_inr_ge_1_5'
      ELSE NULL
    END AS coagulation_primary_decision
  FROM checkpoint_truth_enriched
)
SELECT
  trajectory_id,
  split,
  stay_id,
  subject_id,
  hadm_id,
  first_careunit,
  icu_intime,
  icu_outtime,
  icu_los_hours,
  t_hour,
  checkpoint_time,
  terminal,
  infection_suspected,
  infection_confirmed_or_strongly_supported,
  sepsis_alert,
  septic_shock_alert,
  shock_hypoperfusion_alert,
  aki_stage1,
  aki_stage2,
  aki_stage3,
  oliguria_6h,
  severe_oliguria_or_anuria,
  crrt_active,
  resp_support_hfnc_or_niv,
  resp_support_invasive_vent,
  hypoxemia_pf_lt_200,
  hypoxemia_pf_lt_100,
  vasoactive_support_any,
  vasoactive_multi_agent_or_high_intensity,
  gcs_moderate_impairment_9_12,
  gcs_severe_impairment_le_8,
  hyperlactatemia_ge_2,
  severe_hyperlactatemia_ge_4,
  acidemia_ph_lt_7_30,
  severe_acidemia_ph_le_7_20,
  coagulopathy_inr_ge_1_5,
  coagulopathy_inr_ge_2,
  infection_family_active,
  sepsis_family_active,
  renal_family_active,
  respiratory_family_active,
  hemodynamic_family_active,
  neurologic_family_active,
  metabolic_family_active,
  coagulation_family_active,
  CAST(
    infection_family_active
    + sepsis_family_active
    + renal_family_active
    + respiratory_family_active
    + hemodynamic_family_active
    + neurologic_family_active
    + metabolic_family_active
    + coagulation_family_active
    AS INTEGER
  ) AS active_family_count,
  CAST(
    CASE WHEN infection_primary_decision IN ('infection_suspected', 'infection_confirmed_or_strongly_supported') THEN 1 ELSE 0 END
    + 0
    + CASE WHEN renal_primary_decision IN ('aki_stage1', 'oliguria_6h') THEN 1 ELSE 0 END
    + CASE WHEN respiratory_primary_decision IN ('resp_support_hfnc_or_niv', 'hypoxemia_pf_lt_200') THEN 1 ELSE 0 END
    + CASE WHEN hemodynamic_primary_decision IN ('vasoactive_support_any') THEN 1 ELSE 0 END
    + CASE WHEN neurologic_primary_decision IN ('gcs_moderate_impairment_9_12') THEN 1 ELSE 0 END
    + CASE WHEN metabolic_primary_decision IN ('hyperlactatemia_ge_2', 'acidemia_ph_lt_7_30') THEN 1 ELSE 0 END
    + CASE WHEN coagulation_primary_decision IN ('coagulopathy_inr_ge_1_5') THEN 1 ELSE 0 END
    AS INTEGER
  ) AS suspect_family_count,
  CAST(
    CASE WHEN sepsis_primary_decision IS NOT NULL THEN 1 ELSE 0 END
    + CASE WHEN renal_primary_decision IN ('aki_stage2', 'aki_stage3', 'severe_oliguria_or_anuria', 'crrt_active') THEN 1 ELSE 0 END
    + CASE WHEN respiratory_primary_decision IN ('resp_support_invasive_vent', 'hypoxemia_pf_lt_100') THEN 1 ELSE 0 END
    + CASE WHEN hemodynamic_primary_decision IN ('vasoactive_multi_agent_or_high_intensity', 'septic_shock_alert', 'shock_hypoperfusion_alert') THEN 1 ELSE 0 END
    + CASE WHEN neurologic_primary_decision IN ('gcs_severe_impairment_le_8') THEN 1 ELSE 0 END
    + CASE WHEN metabolic_primary_decision IN ('severe_hyperlactatemia_ge_4', 'severe_acidemia_ph_le_7_20') THEN 1 ELSE 0 END
    + CASE WHEN coagulation_primary_decision IN ('coagulopathy_inr_ge_2') THEN 1 ELSE 0 END
    AS INTEGER
  ) AS alert_family_count,
  infection_primary_decision,
  sepsis_primary_decision,
  renal_primary_decision,
  respiratory_primary_decision,
  hemodynamic_primary_decision,
  neurologic_primary_decision,
  metabolic_primary_decision,
  coagulation_primary_decision,
  concat_ws(
    '|',
    CASE WHEN infection_suspected = 1 THEN 'infection_suspected' END,
    CASE WHEN infection_confirmed_or_strongly_supported = 1 THEN 'infection_confirmed_or_strongly_supported' END,
    CASE WHEN aki_stage1 = 1 THEN 'aki_stage1' END,
    CASE WHEN oliguria_6h = 1 THEN 'oliguria_6h' END,
    CASE WHEN resp_support_hfnc_or_niv = 1 THEN 'resp_support_hfnc_or_niv' END,
    CASE WHEN hypoxemia_pf_lt_200 = 1 THEN 'hypoxemia_pf_lt_200' END,
    CASE WHEN vasoactive_support_any = 1 THEN 'vasoactive_support_any' END,
    CASE WHEN gcs_moderate_impairment_9_12 = 1 THEN 'gcs_moderate_impairment_9_12' END,
    CASE WHEN hyperlactatemia_ge_2 = 1 THEN 'hyperlactatemia_ge_2' END,
    CASE WHEN acidemia_ph_lt_7_30 = 1 THEN 'acidemia_ph_lt_7_30' END,
    CASE WHEN coagulopathy_inr_ge_1_5 = 1 THEN 'coagulopathy_inr_ge_1_5' END
  ) AS active_suspect_decisions,
  concat_ws(
    '|',
    CASE WHEN sepsis_alert = 1 THEN 'sepsis_alert' END,
    CASE WHEN septic_shock_alert = 1 THEN 'septic_shock_alert' END,
    CASE WHEN shock_hypoperfusion_alert = 1 THEN 'shock_hypoperfusion_alert' END,
    CASE WHEN aki_stage2 = 1 THEN 'aki_stage2' END,
    CASE WHEN aki_stage3 = 1 THEN 'aki_stage3' END,
    CASE WHEN severe_oliguria_or_anuria = 1 THEN 'severe_oliguria_or_anuria' END,
    CASE WHEN crrt_active = 1 THEN 'crrt_active' END,
    CASE WHEN resp_support_invasive_vent = 1 THEN 'resp_support_invasive_vent' END,
    CASE WHEN hypoxemia_pf_lt_100 = 1 THEN 'hypoxemia_pf_lt_100' END,
    CASE WHEN vasoactive_multi_agent_or_high_intensity = 1 THEN 'vasoactive_multi_agent_or_high_intensity' END,
    CASE WHEN gcs_severe_impairment_le_8 = 1 THEN 'gcs_severe_impairment_le_8' END,
    CASE WHEN severe_hyperlactatemia_ge_4 = 1 THEN 'severe_hyperlactatemia_ge_4' END,
    CASE WHEN severe_acidemia_ph_le_7_20 = 1 THEN 'severe_acidemia_ph_le_7_20' END,
    CASE WHEN coagulopathy_inr_ge_2 = 1 THEN 'coagulopathy_inr_ge_2' END
  ) AS active_alert_decisions,
  concat_ws(
    '|',
    CASE
      WHEN infection_primary_decision IN ('infection_suspected', 'infection_confirmed_or_strongly_supported')
        THEN infection_primary_decision
    END,
    CASE
      WHEN renal_primary_decision IN ('aki_stage1', 'oliguria_6h')
        THEN renal_primary_decision
    END,
    CASE
      WHEN respiratory_primary_decision IN ('resp_support_hfnc_or_niv', 'hypoxemia_pf_lt_200')
        THEN respiratory_primary_decision
    END,
    CASE
      WHEN hemodynamic_primary_decision IN ('vasoactive_support_any')
        THEN hemodynamic_primary_decision
    END,
    CASE
      WHEN neurologic_primary_decision IN ('gcs_moderate_impairment_9_12')
        THEN neurologic_primary_decision
    END,
    CASE
      WHEN metabolic_primary_decision IN ('hyperlactatemia_ge_2', 'acidemia_ph_lt_7_30')
        THEN metabolic_primary_decision
    END,
    CASE
      WHEN coagulation_primary_decision IN ('coagulopathy_inr_ge_1_5')
        THEN coagulation_primary_decision
    END
  ) AS suspected_conditions,
  concat_ws(
    '|',
    sepsis_primary_decision,
    CASE
      WHEN renal_primary_decision IN ('aki_stage2', 'aki_stage3', 'severe_oliguria_or_anuria', 'crrt_active')
        THEN renal_primary_decision
    END,
    CASE
      WHEN respiratory_primary_decision IN ('resp_support_invasive_vent', 'hypoxemia_pf_lt_100')
        THEN respiratory_primary_decision
    END,
    CASE
      WHEN hemodynamic_primary_decision IN ('vasoactive_multi_agent_or_high_intensity', 'septic_shock_alert', 'shock_hypoperfusion_alert')
        THEN hemodynamic_primary_decision
    END,
    CASE
      WHEN neurologic_primary_decision IN ('gcs_severe_impairment_le_8')
        THEN neurologic_primary_decision
    END,
    CASE
      WHEN metabolic_primary_decision IN ('severe_hyperlactatemia_ge_4', 'severe_acidemia_ph_le_7_20')
        THEN metabolic_primary_decision
    END,
    CASE
      WHEN coagulation_primary_decision IN ('coagulopathy_inr_ge_2')
        THEN coagulation_primary_decision
    END
  ) AS alerts,
  CASE
    WHEN (
      sepsis_primary_decision IS NOT NULL
      OR renal_primary_decision IN ('aki_stage2', 'aki_stage3', 'severe_oliguria_or_anuria', 'crrt_active')
      OR respiratory_primary_decision IN ('resp_support_invasive_vent', 'hypoxemia_pf_lt_100')
      OR hemodynamic_primary_decision IN ('vasoactive_multi_agent_or_high_intensity', 'septic_shock_alert', 'shock_hypoperfusion_alert')
      OR neurologic_primary_decision IN ('gcs_severe_impairment_le_8')
      OR metabolic_primary_decision IN ('severe_hyperlactatemia_ge_4', 'severe_acidemia_ph_le_7_20')
      OR coagulation_primary_decision IN ('coagulopathy_inr_ge_2')
    ) THEN 'escalate'
    ELSE 'continue_monitoring'
  END AS global_action,
  CASE
    WHEN (
      hemodynamic_primary_decision IN ('septic_shock_alert', 'shock_hypoperfusion_alert', 'vasoactive_multi_agent_or_high_intensity')
      OR respiratory_primary_decision IN ('resp_support_invasive_vent', 'hypoxemia_pf_lt_100')
      OR renal_primary_decision IN ('aki_stage3', 'crrt_active')
      OR neurologic_primary_decision IN ('gcs_severe_impairment_le_8')
      OR metabolic_primary_decision IN ('severe_acidemia_ph_le_7_20')
    ) THEN 'high'
    WHEN (
      sepsis_primary_decision IS NOT NULL
      OR renal_primary_decision IN ('aki_stage2', 'severe_oliguria_or_anuria')
      OR coagulation_primary_decision IN ('coagulopathy_inr_ge_2')
      OR alert_family_count >= 1
      OR suspect_family_count >= 3
    ) THEN 'medium'
    ELSE 'low'
  END AS priority
FROM checkpoint_truth_output
ORDER BY split, stay_id, t_hour;
