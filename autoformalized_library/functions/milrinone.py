import pandas as pd
from datetime import datetime

def get_milrinone_info(stay_id):
    """
    Extract milrinone infusion information for a patient's ICU stay.

    This function queries the MIMIC-IV database to retrieve milrinone medication
    administration data for a specific ICU stay. Milrinone is a phosphodiesterase-3
    inhibitor used as an inotropic agent to increase cardiac output in patients 
    with heart failure or cardiogenic shock.

    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.

    Returns:
    --------
    dict
        A dictionary containing the following keys:
        - 'received_milrinone': bool - Whether the patient received milrinone during this stay
        - 'max_rate': float - Maximum milrinone infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no milrinone was received
        - 'min_rate': float - Minimum milrinone infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no milrinone was received
        - 'avg_rate': float - Average milrinone infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no milrinone was received
        - 'received_high_dose': bool - Whether patient received high-dose milrinone (>0.5 mcg/kg/min)
        - 'num_records': int - Number of milrinone infusion records
        - 'first_time': datetime or None - First milrinone administration time
        - 'last_time': datetime or None - Last milrinone administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID

    Example:
    --------
    >>> info = get_milrinone_info(38857852)
    >>> info['received_milrinone']
    True
    >>> info['max_rate']
    0.73
    >>> info['received_high_dose']
    True
    """
    # Milrinone itemid in MIMIC-IV
    MILRINONE_ITEMID = 221986
    
    # Query milrinone infusion data for the given stay_id
    sql = f"""
    SELECT subject_id, hadm_id, stay_id, rate, patientweight, starttime, endtime
    FROM mimiciv_icu.inputevents 
    WHERE itemid = {MILRINONE_ITEMID} AND stay_id = {stay_id}
    ORDER BY starttime
    """
    
    df = query_db(sql)
    
    # Initialize result dictionary
    result = {
        'received_milrinone': False,
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
    
    # If no records found, return the default result
    if df.empty:
        return result
    
    # Extract patient identifiers
    result['subject_id'] = int(df['subject_id'].iloc[0])
    result['hadm_id'] = int(df['hadm_id'].iloc[0])
    
    # Mark that milrinone was received
    result['received_milrinone'] = True
    result['num_records'] = len(df)
    
    # Calculate rate statistics (rate is already in mcg/kg/min)
    rates = df['rate'].dropna()
    if len(rates) > 0:
        result['max_rate'] = round(float(rates.max()), 2)
        result['min_rate'] = round(float(rates.min()), 2)
        result['avg_rate'] = round(float(rates.mean()), 2)
        
        # High dose threshold for milrinone is typically >0.5 mcg/kg/min
        # Standard dosing is 0.375-0.75 mcg/kg/min, so >0.5 is considered high
        result['received_high_dose'] = result['max_rate'] > 0.5
    
    # Get timing information
    result['first_time'] = df['starttime'].min()
    result['last_time'] = df['endtime'].max()
    
    return result

FINAL_FUNCTION = get_milrinone_info