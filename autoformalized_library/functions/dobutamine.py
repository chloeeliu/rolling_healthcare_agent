import pandas as pd
import numpy as np

def get_dobutamine_info(stay_id):
    """
    Extract dobutamine infusion information for a patient's ICU stay.
    
    This function queries the MIMIC-IV database to retrieve dobutamine medication
    administration data for a specific ICU stay. Dobutamine is an inotropic agent
    used to increase cardiac output in patients with heart failure or cardiogenic shock.
    
    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.
    
    Returns:
    --------
    dict
        A dictionary containing the following keys:
        - 'received_dobutamine': bool - Whether the patient received dobutamine during this stay
        - 'max_rate': float - Maximum dobutamine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no dobutamine was received
        - 'min_rate': float - Minimum dobutamine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no dobutamine was received
        - 'avg_rate': float - Average dobutamine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no dobutamine was received
        - 'received_high_dose': bool - Whether patient received high-dose dobutamine (>10 mcg/kg/min)
        - 'num_records': int - Number of dobutamine infusion records
        - 'first_time': datetime or None - First dobutamine administration time
        - 'last_time': datetime or None - Last dobutamine administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID
    
    Example:
    --------
    >>> info = get_dobutamine_info(32333965)
    >>> info['received_dobutamine']
    True
    >>> info['max_rate']
    2.09
    >>> info['received_high_dose']
    False
    """
    
    sql = """
    SELECT 
        ie.subject_id,
        ie.hadm_id,
        ie.stay_id,
        MIN(ie.starttime) as first_time,
        MAX(ie.endtime) as last_time,
        MAX(ie.rate) as max_rate,
        MIN(ie.rate) as min_rate,
        AVG(ie.rate) as avg_rate,
        COUNT(*) as num_records,
        MAX(CASE WHEN ie.rate > 10 THEN 1 ELSE 0 END) as received_high_dose
    FROM mimiciv_icu.inputevents ie
    JOIN mimiciv_icu.d_items di ON ie.itemid = di.itemid
    WHERE di.label ILIKE '%dobutamine%'
    AND ie.stay_id = {stay_id}
    GROUP BY ie.subject_id, ie.hadm_id, ie.stay_id
    """.format(stay_id=stay_id)
    
    result = query_db(sql)
    
    # If no records found, return default values with 0.0 for numerical fields
    if result.empty:
        return {
            'received_dobutamine': False,
            'max_rate': 0.0,
            'min_rate': 0.0,
            'avg_rate': 0.0,
            'received_high_dose': False,
            'num_records': 0,
            'first_time': None,
            'last_time': None,
            'subject_id': None,
            'hadm_id': None
        }
    
    row = result.iloc[0]
    
    return {
        'received_dobutamine': True,
        'max_rate': round(float(row['max_rate']), 2),
        'min_rate': round(float(row['min_rate']), 2),
        'avg_rate': round(float(row['avg_rate']), 2),
        'received_high_dose': bool(row['received_high_dose']),
        'num_records': int(row['num_records']),
        'first_time': row['first_time'],
        'last_time': row['last_time'],
        'subject_id': int(row['subject_id']),
        'hadm_id': int(row['hadm_id'])
    }

FINAL_FUNCTION = get_dobutamine_info