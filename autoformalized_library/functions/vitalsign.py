import pandas as pd
import numpy as np
from datetime import datetime

def vitalsign(stay_id):
    """
    Extract vital sign information for a patient's ICU stay.
    
    This function queries the MIMIC-IV database to retrieve vital sign measurements
    (heart rate, blood pressure) for a specific ICU stay and computes summary statistics
    and clinical flags.
    
    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier (stay_id from mimiciv_icu.icustays table)
    
    Returns:
    --------
    dict : A dictionary containing:
        - 'stay_id': The input stay_id
        - 'heart_rate': dict with min, max, mean, count of heart rate measurements (bpm)
        - 'has_tachycardia': bool - True if any heart rate > 100 bpm
        - 'systolic_bp': dict with min, max, mean, count of systolic BP measurements (mmHg)
        - 'diastolic_bp': dict with min, max, mean, count of diastolic BP measurements (mmHg)
        - 'mean_arterial_pressure': dict with min, max, mean, count of MAP measurements (mmHg)
        - 'has_hypotension': bool - True if any MAP < 65 mmHg
        - 'vital_signs_data': DataFrame with all raw vital sign measurements
    
    Clinical Definitions:
    --------------------
    - Hypotension: Mean arterial pressure (MAP) < 65 mmHg at any point during the stay
    - Tachycardia: Heart rate > 100 bpm at any point during the stay
    
    Vital Sign Item IDs Used:
    -------------------------
    - Heart rate: 220045 (bpm)
    - Arterial BP systolic: 220050 (mmHg)
    - Non-invasive BP systolic: 220179 (mmHg)
    - Arterial BP diastolic: 220051 (mmHg)
    - Non-invasive BP diastolic: 220180 (mmHg)
    - Arterial BP mean: 220052 (mmHg)
    - Non-invasive BP mean: 220181 (mmHg)
    
    Notes:
    ------
    - If no measurements exist for a vital sign type, the stats dict will have
      None values for min, max, mean and count of 0
    - The function combines both arterial and non-invasive blood pressure measurements
    """
    
    # Define vital sign item IDs
    hr_itemid = 220045
    sbp_itemids = [220050, 220179]  # Arterial and Non-invasive systolic
    dbp_itemids = [220051, 220180]  # Arterial and Non-invasive diastolic
    map_itemids = [220052, 220181]  # Arterial and Non-invasive mean
    
    # Query heart rate
    hr_query = f"""
    SELECT ce.stay_id, ce.charttime, ce.valuenum, di.label
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
    WHERE ce.stay_id = {stay_id}
    AND ce.itemid = {hr_itemid}
    AND ce.valuenum IS NOT NULL
    ORDER BY ce.charttime
    """
    hr_df = query_db(hr_query)
    
    # Query systolic BP
    sbp_query = f"""
    SELECT ce.stay_id, ce.charttime, ce.valuenum, di.label
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
    WHERE ce.stay_id = {stay_id}
    AND ce.itemid IN ({','.join(map(str, sbp_itemids))})
    AND ce.valuenum IS NOT NULL
    ORDER BY ce.charttime
    """
    sbp_df = query_db(sbp_query)
    
    # Query diastolic BP
    dbp_query = f"""
    SELECT ce.stay_id, ce.charttime, ce.valuenum, di.label
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
    WHERE ce.stay_id = {stay_id}
    AND ce.itemid IN ({','.join(map(str, dbp_itemids))})
    AND ce.valuenum IS NOT NULL
    ORDER BY ce.charttime
    """
    dbp_df = query_db(dbp_query)
    
    # Query mean arterial pressure
    map_query = f"""
    SELECT ce.stay_id, ce.charttime, ce.valuenum, di.label
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
    WHERE ce.stay_id = {stay_id}
    AND ce.itemid IN ({','.join(map(str, map_itemids))})
    AND ce.valuenum IS NOT NULL
    ORDER BY ce.charttime
    """
    map_df = query_db(map_query)
    
    # Calculate statistics helper function
    def calc_stats(df, column='valuenum'):
        if df.empty:
            return {'min': None, 'max': None, 'mean': None, 'count': 0}
        return {
            'min': float(df[column].min()),
            'max': float(df[column].max()),
            'mean': float(df[column].mean()),
            'count': int(len(df))
        }
    
    # Calculate heart rate stats
    hr_stats = calc_stats(hr_df)
    has_tachycardia = bool(len(hr_df) > 0 and (hr_df['valuenum'] > 100).any())
    
    # Calculate BP stats
    sbp_stats = calc_stats(sbp_df)
    dbp_stats = calc_stats(dbp_df)
    map_stats = calc_stats(map_df)
    
    # Check for hypotension (MAP < 65 mmHg)
    has_hypotension = bool(len(map_df) > 0 and (map_df['valuenum'] < 65).any())
    
    # Combine all vital signs data
    vital_signs_data = pd.concat([
        hr_df.assign(vital_type='heart_rate'),
        sbp_df.assign(vital_type='systolic_bp'),
        dbp_df.assign(vital_type='diastolic_bp'),
        map_df.assign(vital_type='mean_arterial_pressure')
    ], ignore_index=True)
    
    return {
        'stay_id': stay_id,
        'heart_rate': hr_stats,
        'has_tachycardia': has_tachycardia,
        'systolic_bp': sbp_stats,
        'diastolic_bp': dbp_stats,
        'mean_arterial_pressure': map_stats,
        'has_hypotension': has_hypotension,
        'vital_signs_data': vital_signs_data
    }

FINAL_FUNCTION = vitalsign