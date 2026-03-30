import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def find_longest_consecutive(series, threshold):
    """Find the longest consecutive run of values below threshold."""
    if series.empty:
        return 0
    
    below_threshold = series < threshold
    runs = []
    current_run = 0
    
    for val in below_threshold:
        if val:
            current_run += 1
        else:
            if current_run > 0:
                runs.append(current_run)
            current_run = 0
    
    if current_run > 0:
        runs.append(current_run)
    
    return max(runs) if runs else 0


def find_longest_consecutive_anuria(series):
    """Find the longest consecutive run of zero urine output."""
    if series.empty:
        return 0
    
    anuria = series == 0
    runs = []
    current_run = 0
    
    for val in anuria:
        if val:
            current_run += 1
        else:
            if current_run > 0:
                runs.append(current_run)
            current_run = 0
    
    if current_run > 0:
        runs.append(current_run)
    
    return max(runs) if runs else 0


def kdigo_creatinine(stay_id):
    """
    Calculate KDIGO AKI stage based on creatinine criteria for a patient's ICU stay.
    
    KDIGO Creatinine Criteria:
    - Stage 1: ≥0.3 mg/dL increase OR 1.5-1.9x baseline
    - Stage 2: 2.0-2.9x baseline
    - Stage 3: ≥3.0x baseline OR ≥4.0 mg/dL with acute increase ≥0.5 mg/dL
    """
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    stay_info = stay_info.iloc[0]
    subject_id = stay_info['subject_id']
    hadm_id = stay_info['hadm_id']
    intime = stay_info['intime']
    outtime = stay_info['outtime']
    
    creatinine_items = [50912, 51081, 51977, 52546]
    
    # Try to find baseline creatinine from prior 3 months (excluding current admission)
    baseline_query = f"""
        SELECT MIN(valuenum) as baseline_creatinine
        FROM mimiciv_hosp.labevents
        WHERE subject_id = {subject_id}
        AND itemid IN ({','.join(map(str, creatinine_items))})
        AND charttime < '{intime}'
        AND charttime >= '{intime}'::date - INTERVAL '3 months'
        AND hadm_id != {hadm_id}
        AND valuenum IS NOT NULL
    """
    baseline_result = query_db(baseline_query)
    
    if not baseline_result.empty and not pd.isna(baseline_result['baseline_creatinine'].iloc[0]):
        baseline_creatinine = float(baseline_result['baseline_creatinine'].iloc[0])
        baseline_source = 'prior_3_months'
    else:
        # Use first ICU value as baseline if no prior data available
        first_cr_query = f"""
            SELECT valuenum
            FROM mimiciv_hosp.labevents
            WHERE subject_id = {subject_id}
            AND itemid IN ({','.join(map(str, creatinine_items))})
            AND charttime >= '{intime}'
            AND charttime <= '{outtime}'
            AND valuenum IS NOT NULL
            ORDER BY charttime
            LIMIT 1
        """
        first_cr_result = query_db(first_cr_query)
        if not first_cr_result.empty and not pd.isna(first_cr_result['valuenum'].iloc[0]):
            baseline_creatinine = float(first_cr_result['valuenum'].iloc[0])
            baseline_source = 'first_icu_value'
        else:
            baseline_creatinine = None
            baseline_source = 'none'
    
    # Get all creatinine values during ICU stay
    cr_query = f"""
        SELECT charttime, valuenum
        FROM mimiciv_hosp.labevents
        WHERE subject_id = {subject_id}
        AND itemid IN ({','.join(map(str, creatinine_items))})
        AND charttime >= '{intime}'
        AND charttime <= '{outtime}'
        AND valuenum IS NOT NULL
        ORDER BY charttime
    """
    creatinine_df = query_db(cr_query)
    
    if baseline_creatinine is not None and len(creatinine_df) > 0:
        creatinine_df['ratio_to_baseline'] = creatinine_df['valuenum'] / baseline_creatinine
        creatinine_df['absolute_increase'] = creatinine_df['valuenum'] - baseline_creatinine
        
        max_creatinine = float(creatinine_df['valuenum'].max())
        max_creatinine_ratio = float(creatinine_df['ratio_to_baseline'].max())
        max_absolute_increase = float(creatinine_df['absolute_increase'].max())
        
        # Determine KDIGO stage based on creatinine
        kdigo_stage = 0
        if max_creatinine_ratio >= 3.0 or (max_creatinine >= 4.0 and max_absolute_increase >= 0.5):
            kdigo_stage = 3
        elif max_creatinine_ratio >= 2.0:
            kdigo_stage = 2
        elif max_creatinine_ratio >= 1.5 or max_absolute_increase >= 0.3:
            kdigo_stage = 1
    else:
        max_creatinine = None
        max_creatinine_ratio = None
        max_absolute_increase = None
        kdigo_stage = 0
    
    return {
        'stay_id': int(stay_id),
        'subject_id': int(subject_id),
        'hadm_id': int(hadm_id),
        'intime': str(intime),
        'outtime': str(outtime),
        'baseline_creatinine': baseline_creatinine,
        'baseline_source': baseline_source,
        'max_creatinine': max_creatinine,
        'max_creatinine_ratio': max_creatinine_ratio,
        'max_absolute_increase': max_absolute_increase,
        'kdigo_stage': kdigo_stage,
        'has_aki': kdigo_stage >= 1,
        'has_stage_3': kdigo_stage >= 3,
        'creatinine_values': creatinine_df
    }


def kdigo_uo(stay_id):
    """
    Calculate KDIGO AKI stage based on urine output criteria for a patient's ICU stay.
    
    KDIGO Urine Output Criteria:
    - Stage 1: <0.5 mL/kg/hr for 6 hours
    - Stage 2: <0.5 mL/kg/hr for 12 hours
    - Stage 3: <0.3 mL/kg/hr for 24 hours OR anuria for 12 hours
    """
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    stay_info = stay_info.iloc[0]
    subject_id = stay_info['subject_id']
    hadm_id = stay_info['hadm_id']
    intime = stay_info['intime']
    outtime = stay_info['outtime']
    
    # Get patient weight in kg
    weight_query = f"""
        SELECT valuenum
        FROM mimiciv_icu.chartevents
        WHERE subject_id = {subject_id}
        AND itemid = 226512
        AND charttime >= '{intime}'
        AND charttime <= '{outtime}'
        AND valuenum IS NOT NULL
        AND valuenum > 0
        ORDER BY charttime
        LIMIT 1
    """
    weight_result = query_db(weight_query)
    
    if weight_result.empty or pd.isna(weight_result['valuenum'].iloc[0]):
        # Try weight in lbs
        weight_query_lbs = f"""
            SELECT valuenum
            FROM mimiciv_icu.chartevents
            WHERE subject_id = {subject_id}
            AND itemid = 226531
            AND charttime >= '{intime}'
            AND charttime <= '{outtime}'
            AND valuenum IS NOT NULL
            AND valuenum > 0
            ORDER BY charttime
            LIMIT 1
        """
        weight_result_lbs = query_db(weight_query_lbs)
        if not weight_result_lbs.empty and not pd.isna(weight_result_lbs['valuenum'].iloc[0]):
            weight_kg = float(weight_result_lbs['valuenum'].iloc[0]) / 2.20462
        else:
            weight_kg = 70.0  # Default weight
    else:
        weight_kg = float(weight_result['valuenum'].iloc[0])
    
    # Get urine output values
    uo_items = [226559, 226560, 226567, 226627, 226631, 227489, 226566]
    
    uo_query = f"""
        SELECT charttime, value
        FROM mimiciv_icu.outputevents
        WHERE subject_id = {subject_id}
        AND itemid IN ({','.join(map(str, uo_items))})
        AND charttime >= '{intime}'
        AND charttime <= '{outtime}'
        AND value IS NOT NULL
        ORDER BY charttime
    """
    uo_df = query_db(uo_query)
    
    if len(uo_df) > 0:
        uo_df['charttime'] = pd.to_datetime(uo_df['charttime'])
        uo_df['value'] = pd.to_numeric(uo_df['value'], errors='coerce')
        
        intime_dt = pd.to_datetime(intime)
        outtime_dt = pd.to_datetime(outtime)
        
        # Calculate hourly urine output
        hourly_uo = []
        current_time = intime_dt
        
        while current_time < outtime_dt:
            next_time = current_time + timedelta(hours=1)
            hour_uo = uo_df[(uo_df['charttime'] >= current_time) & (uo_df['charttime'] < next_time)]['value'].sum()
            if pd.isna(hour_uo):
                hour_uo = 0.0
            uo_per_kg_hr = (hour_uo / weight_kg) if weight_kg > 0 else 0.0
            
            hourly_uo.append({
                'hour_start': current_time,
                'hour_end': next_time,
                'urine_output_ml': hour_uo,
                'uo_per_kg_hr': uo_per_kg_hr
            })
            current_time = next_time
        
        hourly_uo_df = pd.DataFrame(hourly_uo)
        
        uo_values = hourly_uo_df['uo_per_kg_hr'].values
        
        # Find longest consecutive periods below thresholds
        longest_below_03 = find_longest_consecutive(pd.Series(uo_values), 0.3)
        longest_anuria = find_longest_consecutive_anuria(pd.Series(uo_values))
        longest_below_05 = find_longest_consecutive(pd.Series(uo_values), 0.5)
        
        # Determine KDIGO stage based on urine output
        kdigo_stage = 0
        
        if longest_below_03 >= 24 or longest_anuria >= 12:
            kdigo_stage = 3
        elif longest_below_05 >= 12:
            kdigo_stage = 2
        elif longest_below_05 >= 6:
            kdigo_stage = 1
    else:
        hourly_uo_df = pd.DataFrame(columns=['hour_start', 'hour_end', 'urine_output_ml', 'uo_per_kg_hr'])
        kdigo_stage = 0
    
    return {
        'stay_id': int(stay_id),
        'subject_id': int(subject_id),
        'hadm_id': int(hadm_id),
        'intime': str(intime),
        'outtime': str(outtime),
        'weight_kg': weight_kg,
        'max_kdigo_stage': kdigo_stage,
        'has_aki': kdigo_stage >= 1,
        'has_stage_2_or_higher': kdigo_stage >= 2,
        'has_stage_3': kdigo_stage >= 3,
        'hourly_uo': hourly_uo_df
    }


def kdigo_stages(stay_id):
    """
    Calculate the overall KDIGO AKI stage for a patient's ICU stay based on 
    both creatinine and urine output criteria.
    
    The overall stage is the higher of the creatinine-based stage and 
    urine output-based stage.
    
    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier
    
    Returns:
    --------
    dict : A dictionary containing:
        - stay_id, subject_id, hadm_id: Patient identifiers
        - intime, outtime: ICU stay timestamps
        - baseline_creatinine: Baseline creatinine value (mg/dL)
        - baseline_source: Source of baseline ('prior_3_months' or 'first_icu_value')
        - max_creatinine: Maximum creatinine during stay (mg/dL)
        - max_creatinine_ratio: Maximum creatinine ratio to baseline
        - max_absolute_increase: Maximum absolute increase in creatinine (mg/dL)
        - weight_kg: Patient weight in kg
        - kdigo_stage_creatinine: KDIGO stage based on creatinine (0-3)
        - kdigo_stage_uo: KDIGO stage based on urine output (0-3)
        - kdigo_stage: Overall KDIGO stage (0-3)
        - has_aki: Boolean indicating if AKI is present (stage >= 1)
        - has_stage_2_or_higher: Boolean indicating if stage >= 2
        - has_stage_3: Boolean indicating if stage >= 3
        - creatinine_values: DataFrame of creatinine values during stay
        - hourly_uo: DataFrame of hourly urine output values
    """
    cr_result = kdigo_creatinine(stay_id)
    uo_result = kdigo_uo(stay_id)
    
    # Overall stage is the higher of creatinine and urine output stages
    overall_stage = max(cr_result['kdigo_stage'], uo_result['max_kdigo_stage'])
    
    result = {
        'stay_id': cr_result['stay_id'],
        'subject_id': cr_result['subject_id'],
        'hadm_id': cr_result['hadm_id'],
        'intime': cr_result['intime'],
        'outtime': cr_result['outtime'],
        'baseline_creatinine': cr_result['baseline_creatinine'],
        'baseline_source': cr_result['baseline_source'],
        'max_creatinine': cr_result['max_creatinine'],
        'max_creatinine_ratio': cr_result['max_creatinine_ratio'],
        'max_absolute_increase': cr_result['max_absolute_increase'],
        'weight_kg': uo_result['weight_kg'],
        'kdigo_stage_creatinine': cr_result['kdigo_stage'],
        'kdigo_stage_uo': uo_result['max_kdigo_stage'],
        'kdigo_stage': overall_stage,
        'has_aki': overall_stage >= 1,
        'has_stage_2_or_higher': overall_stage >= 2,
        'has_stage_3': overall_stage >= 3,
        'creatinine_values': cr_result['creatinine_values'],
        'hourly_uo': uo_result['hourly_uo']
    }
    
    return result

FINAL_FUNCTION = kdigo_stages