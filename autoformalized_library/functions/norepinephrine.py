import pandas as pd

def get_norepinephrine_info(stay_id):
    """
    Extract norepinephrine infusion information for a patient's ICU stay.

    This function queries the MIMIC-IV database to retrieve norepinephrine medication
    administration data for a specific ICU stay. Norepinephrine is a vasopressor
    used to treat hypotension and shock.

    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.

    Returns:
    --------
    dict
        A dictionary containing the following keys:
        - 'received_norepinephrine': bool - Whether the patient received norepinephrine during this stay
        - 'max_rate': float - Maximum norepinephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no norepinephrine was received
        - 'min_rate': float - Minimum norepinephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no norepinephrine was received
        - 'avg_rate': float - Average norepinephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no norepinephrine was received
        - 'received_high_dose': bool - Whether patient received high-dose norepinephrine (>0.25 mcg/kg/min)
        - 'num_records': int - Number of norepinephrine infusion records
        - 'first_time': datetime or None - First norepinephrine administration time
        - 'last_time': datetime or None - Last norepinephrine administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID

    Example:
    --------
    >>> info = get_norepinephrine_info(39602181)
    >>> info['received_norepinephrine']
    True
    >>> info['max_rate']
    0.66
    >>> info['received_high_dose']
    True
    """
    # Norepinephrine itemid in MIMIC-IV
    norepinephrine_itemid = 221906
    
    # Query for norepinephrine data with unit conversion
    # Convert mg/kg/min to mcg/kg/min by multiplying by 1000
    sql = f"""
    SELECT 
        ANY_VALUE(subject_id) as subject_id,
        ANY_VALUE(hadm_id) as hadm_id,
        stay_id,
        MIN(starttime) as first_time,
        MAX(endtime) as last_time,
        COUNT(*) as num_records,
        MAX(CASE 
            WHEN rateuom = 'mg/kg/min' THEN rate * 1000
            ELSE rate
        END) as max_rate,
        MIN(CASE 
            WHEN rateuom = 'mg/kg/min' THEN rate * 1000
            ELSE rate
        END) as min_rate,
        AVG(CASE 
            WHEN rateuom = 'mg/kg/min' THEN rate * 1000
            ELSE rate
        END) as avg_rate
    FROM mimiciv_icu.inputevents
    WHERE itemid = {norepinephrine_itemid}
      AND stay_id = {stay_id}
    GROUP BY stay_id
    """
    
    result = query_db(sql)
    
    if len(result) == 0:
        return {
            'received_norepinephrine': False,
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
    max_rate = float(row['max_rate'])
    
    return {
        'received_norepinephrine': True,
        'max_rate': round(max_rate, 2),
        'min_rate': round(float(row['min_rate']), 2),
        'avg_rate': round(float(row['avg_rate']), 2),
        'received_high_dose': max_rate > 0.25,
        'num_records': int(row['num_records']),
        'first_time': row['first_time'],
        'last_time': row['last_time'],
        'subject_id': int(row['subject_id']),
        'hadm_id': int(row['hadm_id'])
    }

FINAL_FUNCTION = get_norepinephrine_info