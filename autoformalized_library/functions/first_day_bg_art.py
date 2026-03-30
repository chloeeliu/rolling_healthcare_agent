import pandas as pd

def first_day_bg_art(stay_id=None, subject_id=None, hadm_id=None):
    """
    Extract arterial blood gas (PaO2) information for the first day of an ICU stay.

    This function retrieves arterial oxygen partial pressure (PaO2) measurements 
    from both chartevents (ICU) and labevents (hospital) tables for the period 
    from ICU admission (intime) to 24 hours after ICU admission.

    Parameters
    ----------
    stay_id : int, optional
        The ICU stay ID. If provided, returns data for that specific stay.
    subject_id : int, optional
        The patient's subject_id. If provided with hadm_id, returns data for 
        the first ICU stay during that admission.
    hadm_id : int, optional
        The hospital admission ID. Used with subject_id to identify the admission.

    Returns
    -------
    dict
        A dictionary containing first-day arterial blood gas information:
        - 'stay_id': The ICU stay ID (int or None)
        - 'subject_id': Patient identifier (int or None)
        - 'hadm_id': Hospital admission ID (int or None)
        - 'intime': ICU admission time (str or None)
        - 'min_pao2': Minimum arterial PaO2 (mmHg) during the first day (float or None)
        - 'max_pao2': Maximum arterial PaO2 (mmHg) during the first day (float or None)
        - 'mean_pao2': Mean arterial PaO2 (mmHg) during the first day (float or None)
        - 'has_hypoxemia': Boolean indicating if any PaO2 < 80 mmHg (bool or None)
        - 'has_severe_hypoxemia': Boolean indicating if any PaO2 < 60 mmHg (bool or None)
        - 'num_measurements': Number of PaO2 measurements (int)
        - 'measurements': List of dictionaries with individual measurements

    Raises
    ------
    ValueError
        If no valid identifier is provided.

    Notes
    -----
    - Hypoxemia is defined as PaO2 < 80 mmHg (based on clinical guidelines)
    - Severe hypoxemia is defined as PaO2 < 60 mmHg
    - Data is sourced from both chartevents (itemid=220224) and labevents (itemid=50821)
    """
    # Validate input
    if stay_id is None and (subject_id is None or hadm_id is None):
        raise ValueError("Must provide either stay_id or both subject_id and hadm_id")
    
    # Build the query to get stay information
    if stay_id is not None:
        stay_filter = f"stay_id = {stay_id}"
    else:
        # Get the first ICU stay for this admission
        stay_filter = f"stay_id IN (SELECT stay_id FROM mimiciv_icu.icustays WHERE subject_id = {subject_id} AND hadm_id = {hadm_id} ORDER BY intime LIMIT 1)"
    
    # Query for arterial blood gas data on first ICU day
    sql = f"""
    WITH stay_info AS (
        SELECT stay_id, subject_id, hadm_id, intime
        FROM mimiciv_icu.icustays
        WHERE {stay_filter}
    ),
    first_day_abg AS (
        SELECT 
            si.stay_id,
            si.subject_id,
            si.hadm_id,
            si.intime,
            c.charttime,
            c.valuenum as pao2,
            'chartevents' as source
        FROM stay_info si
        JOIN mimiciv_icu.chartevents c 
            ON si.stay_id = c.stay_id 
            AND c.itemid = 220224  -- Arterial O2 pressure
        WHERE c.charttime >= si.intime
          AND c.charttime <= si.intime + INTERVAL '24 hours'
        
        UNION ALL
        
        SELECT 
            si.stay_id,
            si.subject_id,
            si.hadm_id,
            si.intime,
            l.charttime,
            l.valuenum as pao2,
            'labevents' as source
        FROM stay_info si
        JOIN mimiciv_hosp.labevents l 
            ON si.subject_id = l.subject_id 
            AND l.itemid = 50821  -- pO2
        WHERE l.charttime >= si.intime
          AND l.charttime <= si.intime + INTERVAL '24 hours'
    )
    SELECT * FROM first_day_abg
    ORDER BY charttime
    """
    
    df = query_db(sql)
    
    if df.empty:
        return {
            'stay_id': stay_id,
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'intime': None,
            'min_pao2': None,
            'max_pao2': None,
            'mean_pao2': None,
            'has_hypoxemia': None,
            'has_severe_hypoxemia': None,
            'num_measurements': 0,
            'measurements': []
        }
    
    # Get stay info
    stay_info = df.iloc[0][['stay_id', 'subject_id', 'hadm_id', 'intime']]
    
    # Calculate statistics
    min_pao2 = df['pao2'].min()
    max_pao2 = df['pao2'].max()
    mean_pao2 = df['pao2'].mean()
    
    # Check for hypoxemia (PaO2 < 80 mmHg)
    has_hypoxemia = bool(min_pao2 < 80) if pd.notna(min_pao2) else None
    # Check for severe hypoxemia (PaO2 < 60 mmHg)
    has_severe_hypoxemia = bool(min_pao2 < 60) if pd.notna(min_pao2) else None
    
    # Build measurements list with clean types
    measurements = []
    for _, row in df.iterrows():
        measurements.append({
            'stay_id': int(row['stay_id']),
            'subject_id': int(row['subject_id']),
            'hadm_id': int(row['hadm_id']),
            'intime': str(row['intime']),
            'charttime': str(row['charttime']),
            'pao2': float(row['pao2']),
            'source': row['source']
        })
    
    return {
        'stay_id': int(stay_info['stay_id']),
        'subject_id': int(stay_info['subject_id']),
        'hadm_id': int(stay_info['hadm_id']),
        'intime': str(stay_info['intime']),
        'min_pao2': float(min_pao2) if pd.notna(min_pao2) else None,
        'max_pao2': float(max_pao2) if pd.notna(max_pao2) else None,
        'mean_pao2': float(mean_pao2) if pd.notna(mean_pao2) else None,
        'has_hypoxemia': has_hypoxemia,
        'has_severe_hypoxemia': has_severe_hypoxemia,
        'num_measurements': len(df),
        'measurements': measurements
    }

FINAL_FUNCTION = first_day_bg_art