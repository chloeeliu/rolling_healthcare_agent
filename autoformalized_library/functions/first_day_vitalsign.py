import pandas as pd

def first_day_vitalsign(stay_id):
    """
    Extract vital sign information for the first day (24 hours) of an ICU stay.
    
    This function retrieves heart rate, mean arterial pressure (MAP), and 
    respiratory rate measurements from the chartevents table for the period 
    from ICU admission (intime) to 24 hours after ICU admission.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing first-day vital sign information:
        - 'stay_id': The ICU stay ID (int)
        - 'subject_id': Patient identifier (int)
        - 'hadm_id': Hospital admission ID (int)
        - 'intime': ICU admission time (str)
        - 'first_day_end': End of first day (intime + 24 hours) (str)
        - 'heart_rate': dict with 'min', 'max', 'avg', 'count'
        - 'map': dict with 'min', 'max', 'avg', 'count' (mean arterial pressure)
        - 'respiratory_rate': dict with 'min', 'max', 'avg', 'count'
        - 'has_hypotension': Boolean - True if minimum MAP < 65 mmHg
        - 'has_tachycardia': Boolean - True if maximum heart rate > 100 bpm
        - 'has_tachypnea': Boolean - True if maximum respiratory rate > 22 breaths/min
        - 'has_bradytachycardia': Boolean - True if heart rate < 60 or > 100 bpm
    
    Raises
    ------
    ValueError
        If stay_id is not provided or not found.
    """
    
    if stay_id is None:
        raise ValueError("stay_id must be provided")
    
    # SQL query to get vital signs for the first day of ICU stay
    sql = """
    WITH stay_info AS (
        SELECT stay_id, subject_id, hadm_id, intime, intime + INTERVAL '24 hours' AS first_day_end
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    ),
    vitals AS (
        SELECT 
            ce.stay_id,
            ce.charttime,
            ce.itemid,
            ce.valuenum,
            CASE 
                WHEN ce.itemid IN (220045, 223764, 223765, 224647) THEN 'heart_rate'
                WHEN ce.itemid IN (220052, 220181, 225312) THEN 'map'
                WHEN ce.itemid IN (220210, 224688, 224689, 224690) THEN 'respiratory_rate'
                ELSE 'other'
            END AS vital_type
        FROM mimiciv_icu.chartevents ce
        JOIN stay_info si ON ce.stay_id = si.stay_id
        WHERE ce.charttime >= si.intime 
          AND ce.charttime <= si.first_day_end
          AND ce.valuenum IS NOT NULL
          AND ce.itemid IN (220045, 223764, 223765, 224647, 220052, 220181, 225312, 220210, 224688, 224689, 224690)
    )
    SELECT 
        si.stay_id,
        si.subject_id,
        si.hadm_id,
        si.intime,
        si.first_day_end,
        vital_type,
        MIN(valuenum) AS min_value,
        MAX(valuenum) AS max_value,
        AVG(valuenum) AS avg_value,
        COUNT(*) AS n_measurements
    FROM vitals v
    JOIN stay_info si ON v.stay_id = si.stay_id
    GROUP BY si.stay_id, si.subject_id, si.hadm_id, si.intime, si.first_day_end, vital_type
    """.format(stay_id=stay_id)
    
    df = query_db(sql)
    
    if df.empty:
        # Return empty result structure if no data found
        stay_info = query_db(f"""
            SELECT stay_id, subject_id, hadm_id, intime, intime + INTERVAL '24 hours' AS first_day_end
            FROM mimiciv_icu.icustays
            WHERE stay_id = {stay_id}
        """)
        
        if stay_info.empty:
            raise ValueError(f"stay_id {stay_id} not found in icustays table")
        
        return {
            'stay_id': int(stay_info.iloc[0]['stay_id']),
            'subject_id': int(stay_info.iloc[0]['subject_id']),
            'hadm_id': int(stay_info.iloc[0]['hadm_id']),
            'intime': str(stay_info.iloc[0]['intime']),
            'first_day_end': str(stay_info.iloc[0]['first_day_end']),
            'heart_rate': {'min': None, 'max': None, 'avg': None, 'count': 0},
            'map': {'min': None, 'max': None, 'avg': None, 'count': 0},
            'respiratory_rate': {'min': None, 'max': None, 'avg': None, 'count': 0},
            'has_hypotension': None,
            'has_tachycardia': None,
            'has_tachypnea': None,
            'has_bradytachycardia': None
        }
    
    # Extract stay info from first row
    stay_row = df.iloc[0]
    
    # Build result dictionary
    result = {
        'stay_id': int(stay_row['stay_id']),
        'subject_id': int(stay_row['subject_id']),
        'hadm_id': int(stay_row['hadm_id']),
        'intime': str(stay_row['intime']),
        'first_day_end': str(stay_row['first_day_end']),
    }
    
    # Extract vital sign stats by vital_type
    vital_stats = {}
    for vital_type in ['heart_rate', 'map', 'respiratory_rate']:
        vital_df = df[df['vital_type'] == vital_type]
        if len(vital_df) > 0:
            vital_stats[vital_type] = {
                'min': float(vital_df.iloc[0]['min_value']),
                'max': float(vital_df.iloc[0]['max_value']),
                'avg': float(vital_df.iloc[0]['avg_value']),
                'count': int(vital_df.iloc[0]['n_measurements'])
            }
        else:
            vital_stats[vital_type] = {'min': None, 'max': None, 'avg': None, 'count': 0}
    
    result['heart_rate'] = vital_stats['heart_rate']
    result['map'] = vital_stats['map']
    result['respiratory_rate'] = vital_stats['respiratory_rate']
    
    # Clinical flags
    result['has_hypotension'] = result['map']['min'] < 65 if result['map']['min'] is not None else None
    result['has_tachycardia'] = result['heart_rate']['max'] > 100 if result['heart_rate']['max'] is not None else None
    result['has_tachypnea'] = result['respiratory_rate']['max'] > 22 if result['respiratory_rate']['max'] is not None else None
    result['has_bradytachycardia'] = (result['heart_rate']['min'] < 60 or result['heart_rate']['max'] > 100) if result['heart_rate']['min'] is not None and result['heart_rate']['max'] is not None else None
    
    return result

FINAL_FUNCTION = first_day_vitalsign