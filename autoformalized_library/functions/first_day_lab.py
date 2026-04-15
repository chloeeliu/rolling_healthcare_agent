# Now let me write the final self-contained code block
import pandas as pd

def first_day_lab(stay_id=None, subject_id=None, hadm_id=None):
    """
    Extract laboratory values for the first day (24 hours) of an ICU stay.
    
    This function retrieves key laboratory measurements from the ICU chart events
    during the first 24 hours after ICU admission. It provides summary statistics
    and clinical flags for common lab abnormalities.
    
    Parameters
    ----------
    stay_id : int, optional
        The ICU stay identifier. If provided, data is filtered to this specific stay.
    subject_id : int, optional
        The patient identifier. Can be used alone or with hadm_id.
    hadm_id : int, optional
        The hospital admission identifier. Used with subject_id if stay_id not provided.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'subject_id': patient identifier (int or None)
        - 'hadm_id': hospital admission identifier (int or None)
        - 'stay_id': ICU stay identifier (int or None)
        - 'intime': ICU admission time (str or None)
        - 'wbc_count': dict with WBC count statistics (K/uL or x10^9/L)
            - 'values': list of all WBC values
            - 'max': Maximum WBC value (float or None)
            - 'min': Minimum WBC value (float or None)
            - 'mean': Mean WBC value (float or None)
            - 'count': Number of WBC measurements (int)
            - 'has_elevated_wbc': Boolean indicating if any WBC > 12 K/uL
        - 'platelet_count': dict with platelet count statistics (K/uL)
            - 'values': list of all platelet values
            - 'max': Maximum platelet value (float or None)
            - 'min': Minimum platelet value (float or None)
            - 'mean': Mean platelet value (float or None)
            - 'count': Number of platelet measurements (int)
            - 'has_thrombocytopenia': Boolean indicating if any platelet < 150 K/uL
        - 'creatinine': dict with creatinine statistics (mg/dL)
            - 'values': list of all creatinine values
            - 'max': Maximum creatinine value (float or None)
            - 'min': Minimum creatinine value (float or None)
            - 'mean': Mean creatinine value (float or None)
            - 'count': Number of creatinine measurements (int)
        - 'all_values': DataFrame with all lab values during the first day
            Columns: charttime, valuenum, parameter, unit
    
    Raises
    ------
    ValueError
        If no patient identifier is provided.
    
    Examples
    --------
    >>> first_day_lab(stay_id=32359580)
    {'subject_id': 10007818, 'hadm_id': 22987108, 'stay_id': 32359580,
     'wbc_count': {'values': [...], 'max': 23.1, 'min': 8.4, 'mean': 15.8, 
                   'count': 7, 'has_elevated_wbc': True},
     'platelet_count': {'values': [...], 'max': 394.0, 'min': 50.0, 
                        'mean': 150.6, 'count': 7, 'has_thrombocytopenia': True},
     'creatinine': {'values': [...], 'max': 4.5, 'min': 2.6, 'mean': 3.1, 'count': 7}}
    
    Notes
    -----
    This function uses the following item IDs from the MIMIC-IV database:
    - WBC: 220546 (K/uL)
    - Platelet Count: 227457 (K/uL)
    - Creatinine (serum): 220615 (mg/dL)
    - Creatinine (whole blood): 229761 (mg/dL)
    
    Clinical thresholds used:
    - Elevated WBC: > 12 K/uL (x10^9/L)
    - Thrombocytopenia: platelet count < 150 K/uL
    """
    
    if stay_id is None and subject_id is None:
        raise ValueError("Either stay_id or subject_id must be provided")
    
    # Build the base query to get ICU stay info
    if stay_id is not None:
        stay_filter = f"stay_id = {stay_id}"
    elif subject_id is not None and hadm_id is not None:
        # Get the first ICU stay for this admission
        stay_filter = f"stay_id IN (SELECT stay_id FROM mimiciv_icu.icustays WHERE subject_id = {subject_id} AND hadm_id = {hadm_id} ORDER BY intime LIMIT 1)"
    elif subject_id is not None:
        # Get the first ICU stay for this patient
        stay_filter = f"stay_id IN (SELECT stay_id FROM mimiciv_icu.icustays WHERE subject_id = {subject_id} ORDER BY intime LIMIT 1)"
    else:
        raise ValueError("Either stay_id or subject_id must be provided")
    
    # Query for first day labs
    sql = f"""
    WITH stay_info AS (
        SELECT stay_id, subject_id, hadm_id, intime
        FROM mimiciv_icu.icustays
        WHERE {stay_filter}
    ),
    first_day_labs AS (
        SELECT 
            s.stay_id,
            s.subject_id,
            s.hadm_id,
            s.intime,
            ce.charttime,
            ce.valuenum,
            ce.itemid
        FROM stay_info s
        JOIN mimiciv_icu.chartevents ce 
          ON s.stay_id = ce.stay_id 
          AND ce.itemid IN (220546, 227457, 220615, 229761)
          AND ce.valuenum IS NOT NULL
          AND ce.charttime >= s.intime
          AND ce.charttime <= s.intime + INTERVAL '24' HOUR
    )
    SELECT 
        stay_id,
        subject_id,
        hadm_id,
        intime,
        charttime,
        valuenum,
        CASE 
            WHEN itemid = 220546 THEN 'wbc'
            WHEN itemid = 227457 THEN 'platelet'
            WHEN itemid IN (220615, 229761) THEN 'creatinine'
            ELSE 'unknown'
        END as parameter,
        CASE 
            WHEN itemid = 220546 THEN 'K/uL'
            WHEN itemid = 227457 THEN 'K/uL'
            WHEN itemid IN (220615, 229761) THEN 'mg/dL'
            ELSE 'unknown'
        END as unit
    FROM first_day_labs
    ORDER BY charttime
    """
    
    df = query_db(sql)
    
    if df.empty:
        # Return empty result structure
        stay_info = query_db(f"""
            SELECT stay_id, subject_id, hadm_id, intime
            FROM mimiciv_icu.icustays
            WHERE {stay_filter}
        """)
        
        if stay_info.empty:
            return {
                'subject_id': None,
                'hadm_id': None,
                'stay_id': None,
                'intime': None,
                'wbc_count': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0, 'has_elevated_wbc': False},
                'platelet_count': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0, 'has_thrombocytopenia': False},
                'creatinine': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0},
                'all_values': pd.DataFrame()
            }
        
        return {
            'subject_id': stay_info.iloc[0]['subject_id'],
            'hadm_id': stay_info.iloc[0]['hadm_id'],
            'stay_id': stay_info.iloc[0]['stay_id'],
            'intime': str(stay_info.iloc[0]['intime']),
            'wbc_count': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0, 'has_elevated_wbc': False},
            'platelet_count': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0, 'has_thrombocytopenia': False},
            'creatinine': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0},
            'all_values': pd.DataFrame()
        }
    
    # Extract stay info
    stay_info = df.iloc[0][['stay_id', 'subject_id', 'hadm_id', 'intime']]
    
    # Extract WBC values
    wbc_df = df[df['parameter'] == 'wbc']
    wbc_values = wbc_df['valuenum'].tolist()
    wbc_count = {
        'values': wbc_values,
        'max': max(wbc_values) if wbc_values else None,
        'min': min(wbc_values) if wbc_values else None,
        'mean': sum(wbc_values) / len(wbc_values) if wbc_values else None,
        'count': len(wbc_values),
        'has_elevated_wbc': any(v > 12 for v in wbc_values) if wbc_values else False
    }
    
    # Extract platelet values
    platelet_df = df[df['parameter'] == 'platelet']
    platelet_values = platelet_df['valuenum'].tolist()
    platelet_count = {
        'values': platelet_values,
        'max': max(platelet_values) if platelet_values else None,
        'min': min(platelet_values) if platelet_values else None,
        'mean': sum(platelet_values) / len(platelet_values) if platelet_values else None,
        'count': len(platelet_values),
        'has_thrombocytopenia': any(v < 150 for v in platelet_values) if platelet_values else False
    }
    
    # Extract creatinine values
    creatinine_df = df[df['parameter'] == 'creatinine']
    creatinine_values = creatinine_df['valuenum'].tolist()
    creatinine = {
        'values': creatinine_values,
        'max': max(creatinine_values) if creatinine_values else None,
        'min': min(creatinine_values) if creatinine_values else None,
        'mean': sum(creatinine_values) / len(creatinine_values) if creatinine_values else None,
        'count': len(creatinine_values)
    }
    
    return {
        'subject_id': int(stay_info['subject_id']),
        'hadm_id': int(stay_info['hadm_id']),
        'stay_id': int(stay_info['stay_id']),
        'intime': str(stay_info['intime']),
        'wbc_count': wbc_count,
        'platelet_count': platelet_count,
        'creatinine': creatinine,
        'all_values': df
    }

FINAL_FUNCTION = first_day_lab