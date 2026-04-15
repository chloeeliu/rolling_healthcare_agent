import pandas as pd
from datetime import timedelta

def kdigo_creatinine(stay_id):
    """
    Calculate KDIGO AKI stage based on creatinine criteria for a patient's ICU stay.
    
    KDIGO AKI Staging based on Creatinine:
    - Stage 0: No AKI
    - Stage 1: Serum creatinine increase ≥0.3 mg/dL within 48 hours OR 1.5-1.9 times baseline
    - Stage 2: Serum creatinine increase 2.0-2.9 times baseline
    - Stage 3: Serum creatinine increase ≥3.0 times baseline OR serum creatinine ≥4.0 mg/dL 
               with an acute increase ≥0.5 mg/dL
    
    Baseline creatinine is determined as:
    - The lowest creatinine value in the 3 months prior to ICU admission, 
      excluding values from the current hospital admission
    - If no prior values exist, use the first creatinine value during the ICU stay
    
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
        - 'intime': ICU admission time (str)
        - 'outtime': ICU discharge time (str)
        - 'baseline_creatinine': The baseline creatinine value in mg/dL (float or None)
        - 'baseline_source': How baseline was determined ('prior_3_months' or 'first_icu_value')
        - 'max_creatinine': Maximum creatinine during ICU stay (float or None)
        - 'max_creatinine_ratio': Maximum creatinine / baseline ratio (float or None)
        - 'max_absolute_increase': Maximum absolute increase from baseline (float or None)
        - 'kdigo_stage': Maximum KDIGO stage reached (0, 1, 2, or 3)
        - 'has_aki': Boolean indicating if patient developed AKI (stage >= 1)
        - 'has_stage_3': Boolean indicating if patient reached stage 3 AKI
        - 'creatinine_values': DataFrame with all creatinine values during ICU stay
            Columns: charttime, valuenum, ratio_to_baseline, absolute_increase
    
    Raises
    ------
    ValueError
        If stay_id is not provided or no matching ICU stay is found.
    """
    
    # Get ICU stay information
    stay_info = query_db(f"""
        SELECT subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = stay_info.iloc[0]['intime']
    outtime = stay_info.iloc[0]['outtime']
    
    # Convert to datetime
    intime_dt = pd.to_datetime(intime)
    outtime_dt = pd.to_datetime(outtime)
    
    # Calculate 3 months prior to ICU admission for baseline window
    three_months_prior = intime_dt - timedelta(days=90)
    
    # Get all creatinine values from labevents (hospital labs)
    # Item IDs: 50912 (Creatinine), 51081 (Creatinine, Serum), 52546 (Creatinine)
    lab_creatinine = query_db(f"""
        SELECT subject_id, hadm_id, charttime, valuenum
        FROM mimiciv_hosp.labevents
        WHERE itemid IN (50912, 51081, 52546)
        AND subject_id = {subject_id}
        AND valuenum IS NOT NULL
        AND charttime >= '{three_months_prior}'
        AND charttime <= '{outtime_dt}'
        ORDER BY charttime
    """)
    
    # Get creatinine values from chartevents (ICU charted values)
    # Item IDs: 220615 (Creatinine serum), 229761 (Creatinine whole blood)
    chart_creatinine = query_db(f"""
        SELECT subject_id, hadm_id, stay_id, charttime, valuenum
        FROM mimiciv_icu.chartevents
        WHERE itemid IN (220615, 229761)
        AND stay_id = {stay_id}
        AND valuenum IS NOT NULL
        ORDER BY charttime
    """)
    
    # Combine and deduplicate
    if not lab_creatinine.empty:
        lab_creatinine['charttime'] = pd.to_datetime(lab_creatinine['charttime'])
    
    if not chart_creatinine.empty:
        chart_creatinine['charttime'] = pd.to_datetime(chart_creatinine['charttime'])
    
    # Combine all creatinine values
    all_creatinine = pd.concat([
        lab_creatinine[['subject_id', 'hadm_id', 'charttime', 'valuenum']],
        chart_creatinine[['subject_id', 'hadm_id', 'charttime', 'valuenum']]
    ], ignore_index=True)
    
    if all_creatinine.empty:
        return {
            'stay_id': stay_id,
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'intime': str(intime),
            'outtime': str(outtime),
            'baseline_creatinine': None,
            'baseline_source': None,
            'max_creatinine': None,
            'max_creatinine_ratio': None,
            'max_absolute_increase': None,
            'kdigo_stage': 0,
            'has_aki': False,
            'has_stage_3': False,
            'creatinine_values': pd.DataFrame(columns=['charttime', 'valuenum', 'ratio_to_baseline', 'absolute_increase'])
        }
    
    # Remove duplicates (same charttime)
    all_creatinine = all_creatinine.drop_duplicates(subset=['charttime'], keep='first')
    all_creatinine = all_creatinine.sort_values('charttime')
    
    # Get the current hospital admission time to exclude values from this admission
    admission_info = query_db(f"""
        SELECT admittime, dischtime
        FROM mimiciv_hosp.admissions
        WHERE subject_id = {subject_id}
        AND hadm_id = {hadm_id}
    """)
    
    if not admission_info.empty:
        admittime_dt = pd.to_datetime(admission_info.iloc[0]['admittime'])
    else:
        admittime_dt = intime_dt  # Fallback to ICU admission time
    
    # Determine baseline creatinine
    # Baseline = lowest creatinine in 3 months prior to ICU admission, 
    # excluding values from the current hospital admission
    prior_creatinine = all_creatinine[
        (all_creatinine['charttime'] >= three_months_prior) & 
        (all_creatinine['charttime'] < admittime_dt)
    ]
    
    if not prior_creatinine.empty and prior_creatinine['valuenum'].notna().any():
        baseline_creatinine = prior_creatinine['valuenum'].min()
        baseline_source = 'prior_3_months'
    else:
        # Use first creatinine value during ICU stay as baseline
        icu_creatinine = all_creatinine[
            (all_creatinine['charttime'] >= intime_dt) & 
            (all_creatinine['charttime'] <= outtime_dt)
        ]
        if not icu_creatinine.empty and icu_creatinine['valuenum'].notna().any():
            baseline_creatinine = icu_creatinine['valuenum'].iloc[0]
            baseline_source = 'first_icu_value'
        else:
            baseline_creatinine = None
            baseline_source = None
    
    if baseline_creatinine is None or baseline_creatinine == 0:
        return {
            'stay_id': stay_id,
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'intime': str(intime),
            'outtime': str(outtime),
            'baseline_creatinine': baseline_creatinine,
            'baseline_source': baseline_source,
            'max_creatinine': None,
            'max_creatinine_ratio': None,
            'max_absolute_increase': None,
            'kdigo_stage': 0,
            'has_aki': False,
            'has_stage_3': False,
            'creatinine_values': pd.DataFrame(columns=['charttime', 'valuenum', 'ratio_to_baseline', 'absolute_increase'])
        }
    
    # Get creatinine values during ICU stay
    icu_creatinine = all_creatinine[
        (all_creatinine['charttime'] >= intime_dt) & 
        (all_creatinine['charttime'] <= outtime_dt)
    ]
    
    if icu_creatinine.empty:
        return {
            'stay_id': stay_id,
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'intime': str(intime),
            'outtime': str(outtime),
            'baseline_creatinine': baseline_creatinine,
            'baseline_source': baseline_source,
            'max_creatinine': None,
            'max_creatinine_ratio': None,
            'max_absolute_increase': None,
            'kdigo_stage': 0,
            'has_aki': False,
            'has_stage_3': False,
            'creatinine_values': pd.DataFrame(columns=['charttime', 'valuenum', 'ratio_to_baseline', 'absolute_increase'])
        }
    
    # Calculate ratios and absolute increases
    icu_creatinine = icu_creatinine.copy()
    icu_creatinine['ratio_to_baseline'] = icu_creatinine['valuenum'] / baseline_creatinine
    icu_creatinine['absolute_increase'] = icu_creatinine['valuenum'] - baseline_creatinine
    
    # Calculate maximum values
    max_creatinine = icu_creatinine['valuenum'].max()
    max_ratio = icu_creatinine['ratio_to_baseline'].max()
    max_absolute_increase = icu_creatinine['absolute_increase'].max()
    
    # Check for acute increase ≥0.3 mg/dL within 48 hours
    # Sort by charttime and check consecutive values
    icu_creatinine_sorted = icu_creatinine.sort_values('charttime').reset_index(drop=True)
    
    acute_increase_48h = False
    for i in range(1, len(icu_creatinine_sorted)):
        prev_time = icu_creatinine_sorted.iloc[i-1]['charttime']
        curr_time = icu_creatinine_sorted.iloc[i]['charttime']
        time_diff = (curr_time - prev_time).total_seconds() / 3600  # hours
        
        if time_diff <= 48:
            increase = icu_creatinine_sorted.iloc[i]['valuenum'] - icu_creatinine_sorted.iloc[i-1]['valuenum']
            if increase >= 0.3:
                acute_increase_48h = True
                break
    
    # Also check if any value increased ≥0.3 from baseline within 48 hours of ICU admission
    early_icu = icu_creatinine_sorted[
        (icu_creatinine_sorted['charttime'] >= intime_dt) & 
        (icu_creatinine_sorted['charttime'] <= intime_dt + timedelta(hours=48))
    ]
    if not early_icu.empty:
        max_early = early_icu['valuenum'].max()
        if max_early - baseline_creatinine >= 0.3:
            acute_increase_48h = True
    
    # Determine KDIGO stage
    kdigo_stage = 0
    
    # Stage 3 criteria
    if max_ratio >= 3.0 or (max_creatinine >= 4.0 and max_absolute_increase >= 0.5):
        kdigo_stage = 3
    # Stage 2 criteria
    elif max_ratio >= 2.0:
        kdigo_stage = 2
    # Stage 1 criteria
    elif max_ratio >= 1.5 or acute_increase_48h:
        kdigo_stage = 1
    
    # Prepare creatinine values output
    creatinine_values_output = icu_creatinine[['charttime', 'valuenum', 'ratio_to_baseline', 'absolute_increase']].copy()
    creatinine_values_output['charttime'] = creatinine_values_output['charttime'].astype(str)
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': str(intime),
        'outtime': str(outtime),
        'baseline_creatinine': round(baseline_creatinine, 2),
        'baseline_source': baseline_source,
        'max_creatinine': round(max_creatinine, 2),
        'max_creatinine_ratio': round(max_ratio, 2),
        'max_absolute_increase': round(max_absolute_increase, 2),
        'kdigo_stage': kdigo_stage,
        'has_aki': kdigo_stage >= 1,
        'has_stage_3': kdigo_stage == 3,
        'creatinine_values': creatinine_values_output
    }

FINAL_FUNCTION = kdigo_creatinine