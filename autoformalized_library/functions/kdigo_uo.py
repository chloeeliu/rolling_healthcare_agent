import pandas as pd
import numpy as np

def kdigo_uo(stay_id):
    """
    Calculate KDIGO AKI stage based on urine output criteria for a patient's ICU stay.
    
    KDIGO AKI Staging based on Urine Output:
    - Stage 0: No AKI (urine output >= 0.5 mL/kg/hr)
    - Stage 1: Urine output < 0.5 mL/kg/hr for 6 consecutive hours
    - Stage 2: Urine output < 0.5 mL/kg/hr for 12 consecutive hours
    - Stage 3: Urine output < 0.3 mL/kg/hr for 24 consecutive hours OR anuria for 12 consecutive hours
    
    Urine output items included:
    - Foley (226559)
    - Void (226560)
    - Straight Cath (226567)
    - OR Urine (226627)
    - PACU Urine (226631)
    - GU Irrigant/Urine Volume Out (227489)
    - Urine and GU Irrigant Out (226566)
    
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
        - 'weight_kg': Patient weight in kg (float or None)
        - 'max_kdigo_stage': Maximum KDIGO stage reached (0, 1, 2, or 3)
        - 'has_aki': Boolean indicating if patient developed AKI (stage >= 1)
        - 'has_stage_2_or_higher': Boolean indicating if patient reached stage 2 or higher
        - 'has_stage_3': Boolean indicating if patient reached stage 3 AKI
        - 'hourly_uo': DataFrame with hourly urine output calculations
            Columns: hour_start, hour_end, urine_output_ml, uo_per_kg_hr
    
    Raises
    ------
    ValueError
        If stay_id is not provided or no matching ICU stay is found.
    """
    
    if stay_id is None:
        raise ValueError("stay_id must be provided")
    
    # Get ICU stay information
    stay_info = query_db(f"""
        SELECT subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id = {stay_id}")
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = stay_info.iloc[0]['intime']
    outtime = stay_info.iloc[0]['outtime']
    
    # Get patient weight in kg
    weight_df = query_db(f"""
        SELECT ce.valuenum
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
        WHERE ce.stay_id = {stay_id}
          AND di.itemid = 226512  -- Admission Weight (Kg)
        ORDER BY ce.charttime
        LIMIT 1
    """)
    
    weight_kg = None
    if not weight_df.empty and pd.notna(weight_df.iloc[0]['valuenum']):
        weight_kg = weight_df.iloc[0]['valuenum']
    
    # Get urine output data
    urine_items = [226559, 226560, 226567, 226627, 226631, 227489, 226566]
    urine_items_str = ','.join(map(str, urine_items))
    
    uo_df = query_db(f"""
        SELECT oe.charttime, oe.value as urine_output_ml
        FROM mimiciv_icu.outputevents oe
        WHERE oe.stay_id = {stay_id}
          AND oe.itemid IN ({urine_items_str})
          AND oe.value IS NOT NULL
        ORDER BY oe.charttime
    """)
    
    if uo_df.empty:
        # No urine output data - cannot calculate KDIGO stage
        return {
            'stay_id': stay_id,
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'intime': str(intime),
            'outtime': str(outtime),
            'weight_kg': weight_kg,
            'max_kdigo_stage': 0,
            'has_aki': False,
            'has_stage_2_or_higher': False,
            'has_stage_3': False,
            'hourly_uo': pd.DataFrame(columns=['hour_start', 'hour_end', 'urine_output_ml', 'uo_per_kg_hr'])
        }
    
    # Convert charttime to datetime
    uo_df['charttime'] = pd.to_datetime(uo_df['charttime'])
    
    # Calculate hourly urine output
    # First, get the ICU stay time range
    intime_dt = pd.to_datetime(intime)
    outtime_dt = pd.to_datetime(outtime)
    
    # Create hourly bins
    hourly_bins = pd.date_range(start=intime_dt, end=outtime_dt, freq='h')
    
    # Aggregate urine output by hour
    hourly_uo = pd.DataFrame({
        'hour_start': hourly_bins[:-1],
        'hour_end': hourly_bins[1:]
    })
    
    # Calculate urine output per hour
    hourly_uo['urine_output_ml'] = 0.0
    
    for idx, row in hourly_uo.iterrows():
        hour_start = row['hour_start']
        hour_end = row['hour_end']
        # Sum urine output within this hour
        hourly_uo.loc[idx, 'urine_output_ml'] = uo_df[
            (uo_df['charttime'] >= hour_start) & 
            (uo_df['charttime'] < hour_end)
        ]['urine_output_ml'].sum()
    
    # Calculate urine output per kg per hour
    if weight_kg is not None and weight_kg > 0:
        hourly_uo['uo_per_kg_hr'] = hourly_uo['urine_output_ml'] / weight_kg
    else:
        hourly_uo['uo_per_kg_hr'] = np.nan
    
    # Calculate KDIGO stage based on urine output
    # Stage 1: < 0.5 mL/kg/hr for 6 consecutive hours
    # Stage 2: < 0.5 mL/kg/hr for 12 consecutive hours
    # Stage 3: < 0.3 mL/kg/hr for 24 consecutive hours OR anuria for 12 consecutive hours
    
    max_stage = 0
    
    if weight_kg is not None and weight_kg > 0:
        # Find longest consecutive period of low urine output
        def find_longest_consecutive(series, threshold):
            """Find the longest consecutive run of values below threshold."""
            below_threshold = series < threshold
            if not below_threshold.any():
                return 0
            
            # Group consecutive True values
            groups = (below_threshold != below_threshold.shift()).cumsum()
            group_sizes = below_threshold.groupby(groups).sum()
            return group_sizes.max() if not group_sizes.empty else 0
        
        # Find longest consecutive period of anuria
        def find_longest_consecutive_anuria(series):
            """Find the longest consecutive run of zero urine output."""
            anuria = series == 0
            if not anuria.any():
                return 0
            
            groups = (anuria != anuria.shift()).cumsum()
            group_sizes = anuria.groupby(groups).sum()
            return group_sizes.max() if not group_sizes.empty else 0
        
        max_consecutive_low_05 = find_longest_consecutive(hourly_uo['uo_per_kg_hr'], 0.5)
        max_consecutive_low_03 = find_longest_consecutive(hourly_uo['uo_per_kg_hr'], 0.3)
        max_consecutive_anuria = find_longest_consecutive_anuria(hourly_uo['urine_output_ml'])
        
        # Stage 3: < 0.3 mL/kg/hr for >= 24 consecutive hours OR anuria for >= 12 consecutive hours
        if max_consecutive_low_03 >= 24 or max_consecutive_anuria >= 12:
            max_stage = 3
        # Stage 2: < 0.5 mL/kg/hr for >= 12 consecutive hours
        elif max_consecutive_low_05 >= 12:
            max_stage = 2
        # Stage 1: < 0.5 mL/kg/hr for >= 6 consecutive hours
        elif max_consecutive_low_05 >= 6:
            max_stage = 1
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': str(intime),
        'outtime': str(outtime),
        'weight_kg': weight_kg,
        'max_kdigo_stage': max_stage,
        'has_aki': max_stage >= 1,
        'has_stage_2_or_higher': max_stage >= 2,
        'has_stage_3': max_stage >= 3,
        'hourly_uo': hourly_uo
    }

FINAL_FUNCTION = kdigo_uo