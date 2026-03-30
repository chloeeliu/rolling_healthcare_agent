import pandas as pd
from datetime import datetime, timedelta

def creatinine_baseline(stay_id):
    """
    Calculate baseline serum creatinine for a patient's ICU stay.
    
    Baseline creatinine is determined as:
    1. Lowest creatinine value during current hospital admission BEFORE ICU admission
    2. If none, first creatinine value during ICU stay
    3. If none, lowest creatinine value in 3 months prior to ICU admission (excluding current admission)
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'stay_id': The ICU stay ID (int)
        - 'subject_id': The patient's subject_id (int)
        - 'hadm_id': The hospital admission ID (int)
        - 'intime': ICU admission time (str, format: 'YYYY-MM-DD HH:MM:SS')
        - 'baseline_creatinine': The baseline creatinine value in mg/dL (float or None)
        - 'baseline_source': How baseline was determined ('current_admission_pre_icu', 'first_icu_value', or 'prior_3_months')
        - 'has_ckd_diagnosis': Boolean indicating if patient has CKD diagnosis codes
        - 'ckd_codes': List of CKD ICD codes found for this patient
        - 'baseline_above_1_5': Boolean indicating if baseline creatinine > 1.5 mg/dL
        - 'prior_creatinine_values': List of creatinine values from prior 3 months
        - 'icu_creatinine_values': List of creatinine values during ICU stay
    
    Raises
    ------
    ValueError
        If stay_id is not provided or no matching ICU stay is found.
    """
    
    # Get ICU stay information
    sql_stay = """
    SELECT s.stay_id, s.subject_id, s.hadm_id, s.intime, s.outtime, a.admittime
    FROM mimiciv_icu.icustays s
    JOIN mimiciv_hosp.admissions a ON s.hadm_id = a.hadm_id
    WHERE s.stay_id = {}
    """.format(stay_id)
    
    stay_info = query_db(sql_stay)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    stay_row = stay_info.iloc[0]
    subject_id = int(stay_row['subject_id'])
    hadm_id = int(stay_row['hadm_id'])
    intime = str(stay_row['intime'])
    outtime = str(stay_row['outtime'])
    admittime = str(stay_row['admittime'])
    
    # Get creatinine values during current admission BEFORE ICU admission
    sql_current_pre_icu = """
    SELECT charttime, valuenum
    FROM mimiciv_hosp.labevents
    WHERE itemid IN (50912, 52546)
      AND subject_id = {}
      AND hadm_id = {}
      AND valuenum IS NOT NULL
      AND charttime >= '{}'
      AND charttime < '{}'
    ORDER BY valuenum
    """.format(subject_id, hadm_id, admittime, intime)
    
    current_pre_icu = query_db(sql_current_pre_icu)
    
    # Get first creatinine value during ICU stay
    sql_icu = """
    SELECT charttime, valuenum
    FROM mimiciv_hosp.labevents
    WHERE itemid IN (50912, 52546)
      AND subject_id = {}
      AND valuenum IS NOT NULL
      AND charttime >= '{}'
    ORDER BY charttime
    LIMIT 1
    """.format(subject_id, intime)
    
    icu_first = query_db(sql_icu)
    
    # Calculate 3 months prior to ICU admission
    intime_dt = datetime.strptime(intime, '%Y-%m-%d %H:%M:%S')
    three_months_prior = intime_dt - timedelta(days=90)
    three_months_prior_str = three_months_prior.strftime('%Y-%m-%d %H:%M:%S')
    
    # Get creatinine values from prior 3 months (excluding current admission)
    # IMPORTANT: Include hadm_id IS NULL to capture outpatient/ED visits
    sql_prior = """
    SELECT charttime, valuenum
    FROM mimiciv_hosp.labevents
    WHERE itemid IN (50912, 52546)
      AND subject_id = {}
      AND valuenum IS NOT NULL
      AND charttime >= '{}'
      AND charttime < '{}'
      AND (hadm_id IS NULL OR hadm_id != {})
    ORDER BY valuenum
    """.format(subject_id, three_months_prior_str, intime, hadm_id)
    
    prior_values = query_db(sql_prior)
    
    # Get all creatinine values during ICU stay for reporting
    sql_icu_all = """
    SELECT charttime, valuenum
    FROM mimiciv_hosp.labevents
    WHERE itemid IN (50912, 52546)
      AND subject_id = {}
      AND valuenum IS NOT NULL
      AND charttime >= '{}'
      AND charttime <= '{}'
    ORDER BY charttime
    """.format(subject_id, intime, outtime)
    
    icu_values = query_db(sql_icu_all)
    
    # Determine baseline creatinine (priority: current admission pre-ICU > first ICU value > prior 3 months)
    baseline_creatinine = None
    baseline_source = None
    
    if not current_pre_icu.empty:
        baseline_creatinine = float(current_pre_icu['valuenum'].min())
        baseline_source = 'current_admission_pre_icu'
    elif not icu_first.empty:
        baseline_creatinine = float(icu_first.iloc[0]['valuenum'])
        baseline_source = 'first_icu_value'
    elif not prior_values.empty:
        baseline_creatinine = float(prior_values['valuenum'].min())
        baseline_source = 'prior_3_months'
    
    # Check for CKD diagnosis codes
    ckd_codes_query = """
    SELECT DISTINCT d.icd_code, d.long_title
    FROM mimiciv_hosp.diagnoses_icd di
    JOIN mimiciv_hosp.d_icd_diagnoses d ON di.icd_code = d.icd_code
    WHERE di.subject_id = {}
      AND (
        d.long_title LIKE '%chronic kidney disease%'
        OR d.long_title LIKE '%chronic renal failure%'
        OR d.long_title LIKE '%end stage renal%'
        OR d.icd_code LIKE 'N18%'
        OR d.icd_code LIKE '585%'
      )
    """.format(subject_id)
    
    ckd_codes = query_db(ckd_codes_query)
    has_ckd_diagnosis = not ckd_codes.empty
    ckd_code_list = ckd_codes['icd_code'].tolist() if has_ckd_diagnosis else []
    
    # Check if baseline creatinine > 1.5 mg/dL (suggests pre-existing renal impairment)
    baseline_above_1_5 = baseline_creatinine is not None and baseline_creatinine > 1.5
    
    # Prepare output
    result = {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': intime,
        'baseline_creatinine': baseline_creatinine,
        'baseline_source': baseline_source,
        'has_ckd_diagnosis': has_ckd_diagnosis,
        'ckd_codes': ckd_code_list,
        'baseline_above_1_5': baseline_above_1_5,
        'prior_creatinine_values': prior_values['valuenum'].tolist() if not prior_values.empty else [],
        'icu_creatinine_values': icu_values['valuenum'].tolist() if not icu_values.empty else []
    }
    
    return result

FINAL_FUNCTION = creatinine_baseline