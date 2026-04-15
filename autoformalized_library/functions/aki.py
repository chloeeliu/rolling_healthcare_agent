import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def aki(stay_id):
    """
    Calculate Acute Kidney Injury (AKI) status for a patient's ICU stay based on KDIGO criteria.
    
    This function evaluates AKI using both creatinine and urine output criteria according to
    KDIGO (Kidney Disease: Improving Global Outcomes) guidelines. The AKI stage is determined
    as the higher of the creatinine-based stage or urine output-based stage.
    
    KDIGO AKI Staging Criteria:
    - Stage 0: No AKI
    - Stage 1: 
      * Creatinine: Increase ≥0.3 mg/dL within 48 hours OR 1.5-1.9 times baseline
      * Urine Output: < 0.5 mL/kg/hr for 6 consecutive hours
    - Stage 2:
      * Creatinine: 2.0-2.9 times baseline
      * Urine Output: < 0.5 mL/kg/hr for 12 consecutive hours
    - Stage 3:
      * Creatinine: ≥3.0 times baseline OR ≥4.0 mg/dL with acute increase ≥0.5 mg/dL
      * Urine Output: < 0.3 mL/kg/hr for 24 consecutive hours OR anuria for 12 consecutive hours
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier for the patient.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'subject_id': The patient's subject_id (int)
        - 'hadm_id': The hospital admission ID (int)
        - 'intime': ICU admission time (str)
        - 'outtime': ICU discharge time (str)
        - 'has_aki': Boolean indicating if patient developed AKI (stage >= 1)
        - 'max_aki_stage': Maximum AKI stage reached (0, 1, 2, or 3)
        - 'has_stage_3': Boolean indicating if patient reached stage 3 AKI (severe)
        - 'creatinine_stage': KDIGO stage based on creatinine criteria (0-3)
        - 'urine_output_stage': KDIGO stage based on urine output criteria (0-3)
        - 'baseline_creatinine': The baseline creatinine value in mg/dL (float or None)
        - 'max_creatinine': Maximum creatinine during ICU stay (float or None)
        - 'max_creatinine_ratio': Maximum creatinine / baseline ratio (float or None)
        - 'max_absolute_increase': Maximum absolute increase from baseline (float or None)
        - 'weight_kg': Patient weight in kg (float or None)
        - 'creatinine_values': DataFrame with all creatinine values during ICU stay
        - 'hourly_urine_output': DataFrame with hourly urine output calculations
    """
    
    # Get ICU stay information
    stay_query = """
    SELECT subject_id, hadm_id, intime, outtime
    FROM mimiciv_icu.icustays
    WHERE stay_id = %d
    """ % stay_id
    stay_df = query_db(stay_query)
    
    if stay_df.empty:
        raise ValueError(f"No ICU stay found for stay_id {stay_id}")
    
    stay_info = stay_df.iloc[0]
    subject_id = int(stay_info['subject_id'])
    hadm_id = int(stay_info['hadm_id'])
    intime = stay_info['intime']
    outtime = stay_info['outtime']
    
    # Parse ICU times
    intime_dt = pd.to_datetime(intime)
    outtime_dt = pd.to_datetime(outtime)
    
    # Format datetime strings for SQL
    intime_str = intime_dt.strftime('%Y-%m-%d %H:%M:%S')
    outtime_str = outtime_dt.strftime('%Y-%m-%d %H:%M:%S')
    prior_90_days_str = (intime_dt - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    prior_1_hour_str = (intime_dt - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
    
    # ============================================
    # CREATININE-BASED AKI ASSESSMENT
    # ============================================
    
    # Creatinine item IDs
    cr_itemids = [50912, 52546]
    cr_itemids_str = ','.join(map(str, cr_itemids))
    
    # Filter for reasonable creatinine values (0.1 to 15 mg/dL)
    # This excludes implausible outliers while keeping clinically relevant values
    cr_min = 0.1
    cr_max = 15.0
    
    # Get baseline creatinine: lowest in 3 months prior to ICU admission, excluding current admission
    baseline_query = f"""
    SELECT le.valuenum
    FROM mimiciv_hosp.labevents le
    WHERE le.subject_id = {subject_id}
      AND le.itemid IN ({cr_itemids_str})
      AND le.charttime >= '{prior_90_days_str}'
      AND le.charttime < '{intime_str}'
      AND le.hadm_id != {hadm_id}
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= {cr_min}
      AND le.valuenum <= {cr_max}
    ORDER BY le.valuenum ASC
    LIMIT 1
    """
    
    baseline_df = query_db(baseline_query)
    
    if not baseline_df.empty:
        baseline_creatinine = float(baseline_df.iloc[0]['valuenum'])
        baseline_source = 'prior_3_months'
    else:
        # Use first creatinine value during ICU stay
        icu_cr_query = f"""
        SELECT le.valuenum
        FROM mimiciv_hosp.labevents le
        WHERE le.subject_id = {subject_id}
          AND le.itemid IN ({cr_itemids_str})
          AND le.charttime >= '{intime_str}'
          AND le.charttime <= '{outtime_str}'
          AND le.valuenum IS NOT NULL
          AND le.valuenum >= {cr_min}
          AND le.valuenum <= {cr_max}
        ORDER BY le.charttime ASC
        LIMIT 1
        """
        
        icu_first_cr = query_db(icu_cr_query)
        if not icu_first_cr.empty:
            baseline_creatinine = float(icu_first_cr.iloc[0]['valuenum'])
            baseline_source = 'first_icu_value'
        else:
            baseline_creatinine = None
            baseline_source = 'none'
    
    # Get all creatinine values during ICU stay
    icu_cr_query = f"""
    SELECT le.charttime, le.valuenum
    FROM mimiciv_hosp.labevents le
    WHERE le.subject_id = {subject_id}
      AND le.itemid IN ({cr_itemids_str})
      AND le.charttime >= '{intime_str}'
      AND le.charttime <= '{outtime_str}'
      AND le.valuenum IS NOT NULL
      AND le.valuenum >= {cr_min}
      AND le.valuenum <= {cr_max}
    ORDER BY le.charttime ASC
    """
    
    icu_cr_df = query_db(icu_cr_query)
    
    # Calculate creatinine stage
    creatinine_stage = 0
    max_creatinine = None
    max_creatinine_ratio = None
    max_absolute_increase = None
    
    if baseline_creatinine is not None and not icu_cr_df.empty:
        icu_cr_df['ratio_to_baseline'] = icu_cr_df['valuenum'] / baseline_creatinine
        icu_cr_df['absolute_increase'] = icu_cr_df['valuenum'] - baseline_creatinine
        
        max_creatinine = float(icu_cr_df['valuenum'].max())
        max_creatinine_ratio = float(icu_cr_df['ratio_to_baseline'].max())
        max_absolute_increase = float(icu_cr_df['absolute_increase'].max())
        
        # Check for Stage 3 first (highest priority)
        # Stage 3: ≥3.0x baseline OR ≥4.0 mg/dL with acute increase ≥0.5 mg/dL
        if max_creatinine_ratio >= 3.0:
            creatinine_stage = 3
        elif max_creatinine >= 4.0 and max_absolute_increase >= 0.5:
            creatinine_stage = 3
        # Stage 2: 2.0-2.9x baseline
        elif max_creatinine_ratio >= 2.0:
            creatinine_stage = 2
        # Stage 1: 1.5-1.9x baseline OR ≥0.3 mg/dL increase within 48 hours
        elif max_creatinine_ratio >= 1.5:
            creatinine_stage = 1
        else:
            # Check for ≥0.3 mg/dL increase within 48 hours
            # Need to check if any value increased by ≥0.3 from a value within 48 hours prior
            if len(icu_cr_df) > 1:
                for i in range(len(icu_cr_df)):
                    current_time = icu_cr_df.iloc[i]['charttime']
                    current_val = icu_cr_df.iloc[i]['valuenum']
                    
                    # Look for values within 48 hours before current
                    for j in range(i):
                        prior_time = icu_cr_df.iloc[j]['charttime']
                        prior_val = icu_cr_df.iloc[j]['valuenum']
                        
                        time_diff = (current_time - prior_time).total_seconds() / 3600
                        if 0 < time_diff <= 48:
                            if current_val - prior_val >= 0.3:
                                creatinine_stage = max(creatinine_stage, 1)
                                break
                        elif time_diff > 48:
                            break
    
    # ============================================
    # URINE OUTPUT-BASED AKI ASSESSMENT
    # ============================================
    
    # Urine output item IDs
    uo_itemids = [226557, 226558, 226559, 226560, 226561, 226563, 226564, 226565, 
                  226566, 226567, 226627, 226631, 227489]
    uo_itemids_str = ','.join(map(str, uo_itemids))
    
    # Get patient weight - include weights from 1 hour before ICU admission
    # Weight item IDs: 224639 (Daily Weight), 226512 (Admission Weight), 226846 (Feeding Weight)
    # Note: 226531 is Admission Weight in lbs, need to convert to kg
    weight_itemids = [224639, 226512, 226846]  # These are in kg
    weight_itemids_lbs = [226531]  # This is in lbs
    weight_itemids_str = ','.join(map(str, weight_itemids))
    weight_itemids_lbs_str = ','.join(map(str, weight_itemids_lbs))
    
    # First try to get weight in kg
    weight_query = f"""
    SELECT ce.valuenum, ce.itemid, ce.charttime
    FROM mimiciv_icu.chartevents ce
    WHERE ce.subject_id = {subject_id}
      AND ce.itemid IN ({weight_itemids_str})
      AND ce.charttime >= '{prior_1_hour_str}'
      AND ce.charttime <= '{outtime_str}'
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0
    ORDER BY ce.charttime ASC
    LIMIT 1
    """
    
    weight_df = query_db(weight_query)
    
    if not weight_df.empty:
        weight_kg = float(weight_df.iloc[0]['valuenum'])
    else:
        # Try to get weight in lbs and convert to kg
        weight_lbs_query = f"""
        SELECT ce.valuenum, ce.itemid, ce.charttime
        FROM mimiciv_icu.chartevents ce
        WHERE ce.subject_id = {subject_id}
          AND ce.itemid IN ({weight_itemids_lbs_str})
          AND ce.charttime >= '{prior_1_hour_str}'
          AND ce.charttime <= '{outtime_str}'
          AND ce.valuenum IS NOT NULL
          AND ce.valuenum > 0
        ORDER BY ce.charttime ASC
        LIMIT 1
        """
        
        weight_lbs_df = query_db(weight_lbs_query)
        if not weight_lbs_df.empty:
            weight_kg = float(weight_lbs_df.iloc[0]['valuenum']) / 2.2  # Convert lbs to kg
        else:
            # Try to get weight from prior admission
            weight_query = f"""
            SELECT ce.valuenum
            FROM mimiciv_icu.chartevents ce
            JOIN mimiciv_icu.icustays icu ON ce.stay_id = icu.stay_id
            WHERE ce.subject_id = {subject_id}
              AND ce.itemid IN ({weight_itemids_str})
              AND icu.outtime < '{intime_str}'
              AND ce.valuenum IS NOT NULL
              AND ce.valuenum > 0
            ORDER BY icu.outtime DESC
            LIMIT 1
            """
            
            weight_df = query_db(weight_query)
            if not weight_df.empty:
                weight_kg = float(weight_df.iloc[0]['valuenum'])
            else:
                weight_kg = None
    
    # Get urine output events during ICU stay
    uo_query = f"""
    SELECT oe.charttime, oe.value
    FROM mimiciv_icu.outputevents oe
    WHERE oe.subject_id = {subject_id}
      AND oe.itemid IN ({uo_itemids_str})
      AND oe.charttime >= '{intime_str}'
      AND oe.charttime <= '{outtime_str}'
      AND oe.value IS NOT NULL
    ORDER BY oe.charttime ASC
    """
    
    uo_df = query_db(uo_query)
    
    # Calculate hourly urine output
    hourly_uo = []
    
    if not uo_df.empty and weight_kg is not None:
        # Create hourly bins starting from ICU admission
        current_hour = intime_dt
        while current_hour < outtime_dt:
            next_hour = current_hour + timedelta(hours=1)
            
            # Sum urine output in this hour
            hour_uo = uo_df[
                (uo_df['charttime'] >= current_hour) & 
                (uo_df['charttime'] < next_hour)
            ]['value'].sum()
            
            uo_per_kg_hr = hour_uo / weight_kg if weight_kg > 0 else 0
            
            hourly_uo.append({
                'hour_start': current_hour,
                'hour_end': next_hour,
                'urine_output_ml': hour_uo,
                'uo_per_kg_hr': uo_per_kg_hr
            })
            
            current_hour = next_hour
        
        hourly_uo_df = pd.DataFrame(hourly_uo)
    else:
        hourly_uo_df = pd.DataFrame(columns=['hour_start', 'hour_end', 'urine_output_ml', 'uo_per_kg_hr'])
    
    # Calculate urine output-based KDIGO stage
    urine_output_stage = 0
    
    if not hourly_uo_df.empty and weight_kg is not None:
        # Stage 3: < 0.3 mL/kg/hr for 24 consecutive hours OR anuria for 12 consecutive hours
        # Check for anuria (0 mL/kg/hr) for 12 consecutive hours
        anuria_count = 0
        max_anuria_count = 0
        for _, row in hourly_uo_df.iterrows():
            if row['uo_per_kg_hr'] == 0:
                anuria_count += 1
                max_anuria_count = max(max_anuria_count, anuria_count)
            else:
                anuria_count = 0
        
        if max_anuria_count >= 12:
            urine_output_stage = 3
        else:
            # Check for < 0.3 mL/kg/hr for 24 consecutive hours
            low_uo_count = 0
            max_low_uo_count = 0
            for _, row in hourly_uo_df.iterrows():
                if row['uo_per_kg_hr'] < 0.3:
                    low_uo_count += 1
                    max_low_uo_count = max(max_low_uo_count, low_uo_count)
                else:
                    low_uo_count = 0
            
            if max_low_uo_count >= 24:
                urine_output_stage = 3
            else:
                # Stage 2: < 0.5 mL/kg/hr for 12 consecutive hours
                low_uo_05_count = 0
                max_low_uo_05_count = 0
                for _, row in hourly_uo_df.iterrows():
                    if row['uo_per_kg_hr'] < 0.5:
                        low_uo_05_count += 1
                        max_low_uo_05_count = max(max_low_uo_05_count, low_uo_05_count)
                    else:
                        low_uo_05_count = 0
                
                if max_low_uo_05_count >= 12:
                    urine_output_stage = 2
                else:
                    # Stage 1: < 0.5 mL/kg/hr for 6 consecutive hours
                    if max_low_uo_05_count >= 6:
                        urine_output_stage = 1
    
    # ============================================
    # COMBINE RESULTS
    # ============================================
    
    max_aki_stage = max(creatinine_stage, urine_output_stage)
    
    result = {
        'stay_id': int(stay_id),
        'subject_id': int(subject_id),
        'hadm_id': int(hadm_id),
        'intime': str(intime),
        'outtime': str(outtime),
        'has_aki': max_aki_stage >= 1,
        'max_aki_stage': max_aki_stage,
        'has_stage_3': max_aki_stage == 3,
        'creatinine_stage': creatinine_stage,
        'urine_output_stage': urine_output_stage,
        'baseline_creatinine': float(baseline_creatinine) if baseline_creatinine is not None else None,
        'max_creatinine': float(max_creatinine) if max_creatinine is not None else None,
        'max_creatinine_ratio': float(max_creatinine_ratio) if max_creatinine_ratio is not None else None,
        'max_absolute_increase': float(max_absolute_increase) if max_absolute_increase is not None else None,
        'weight_kg': float(weight_kg) if weight_kg is not None else None,
        'creatinine_values': icu_cr_df,
        'hourly_urine_output': hourly_uo_df
    }
    
    return result

FINAL_FUNCTION = aki