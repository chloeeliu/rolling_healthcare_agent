import pandas as pd
import numpy as np

def get_epinephrine_info(stay_id):
    """
    Extract epinephrine infusion information for a patient's ICU stay.

    This function queries the MIMIC-IV database to retrieve epinephrine medication
    administration data for a specific ICU stay. Epinephrine is a vasopressor and
    inotropic agent used to treat hypotension, cardiac arrest, and shock.

    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.

    Returns:
    --------
    dict
        A dictionary containing the following keys:
        - 'received_epinephrine': bool - Whether the patient received epinephrine during this stay
        - 'max_rate': float - Maximum epinephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no epinephrine was received
        - 'min_rate': float - Minimum epinephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no epinephrine was received
        - 'avg_rate': float - Average epinephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no epinephrine was received
        - 'received_high_dose': bool - Whether patient received high-dose epinephrine (>0.1 mcg/kg/min)
        - 'num_records': int - Number of epinephrine infusion records
        - 'first_time': datetime or None - First epinephrine administration time
        - 'last_time': datetime or None - Last epinephrine administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID

    Example:
    --------
    >>> info = get_epinephrine_info(31831386)
    >>> info['received_epinephrine']
    True
    >>> info['max_rate']
    0.02
    >>> info['received_high_dose']
    False
    """
    # Query for epinephrine data (itemid 221289 and 229617 are epinephrine in MIMIC-IV)
    sql = """
    SELECT 
        subject_id, 
        hadm_id, 
        stay_id,
        COUNT(*) as num_records,
        MAX(rate) as max_rate,
        MIN(rate) as min_rate,
        AVG(rate) as avg_rate,
        MAX(CASE WHEN rate > 0.1 THEN 1 ELSE 0 END) as received_high_dose,
        MIN(starttime) as first_time,
        MAX(endtime) as last_time
    FROM mimiciv_icu.inputevents 
    WHERE itemid IN (221289, 229617)
    AND stay_id = {stay_id}
    GROUP BY subject_id, hadm_id, stay_id
    """.format(stay_id=stay_id)
    
    df = query_db(sql)
    
    # Initialize result dictionary
    result = {
        'received_epinephrine': False,
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
    
    if len(df) > 0:
        row = df.iloc[0]
        result['received_epinephrine'] = True
        result['max_rate'] = round(float(row['max_rate']), 2)
        result['min_rate'] = round(float(row['min_rate']), 2)
        result['avg_rate'] = round(float(row['avg_rate']), 2)
        result['received_high_dose'] = bool(row['received_high_dose'])
        result['num_records'] = int(row['num_records'])
        result['first_time'] = row['first_time']
        result['last_time'] = row['last_time']
        result['subject_id'] = int(row['subject_id'])
        result['hadm_id'] = int(row['hadm_id'])
    
    return result

FINAL_FUNCTION = get_epinephrine_info