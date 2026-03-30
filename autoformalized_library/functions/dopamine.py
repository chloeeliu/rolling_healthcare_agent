import pandas as pd

def get_dopamine_info(stay_id):
    """
    Extract dopamine infusion information for a patient's ICU stay.

    This function queries the MIMIC-IV database to retrieve dopamine medication
    administration data for a specific ICU stay. Dopamine is a vasopressor and
    inotropic agent used to treat hypotension and shock.

    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.

    Returns:
    --------
    dict
        A dictionary containing the following keys:
        - 'received_dopamine': bool - Whether the patient received dopamine during this stay
        - 'max_rate': float - Maximum dopamine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no dopamine was received
        - 'min_rate': float - Minimum dopamine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no dopamine was received
        - 'avg_rate': float - Average dopamine infusion rate (mcg/kg/min), rounded to 2 decimals
                         Returns 0.0 if no dopamine was received
        - 'received_high_dose': bool - Whether patient received high-dose dopamine (>10 mcg/kg/min)
        - 'num_records': int - Number of dopamine infusion records
        - 'first_time': datetime or None - First dopamine administration time
        - 'last_time': datetime or None - Last dopamine administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID

    Example:
    --------
    >>> info = get_dopamine_info(37510196)
    >>> info['received_dopamine']
    True
    >>> info['max_rate']
    10.01
    >>> info['received_high_dose']
    True
    """
    # Dopamine itemid in MIMIC-IV
    dopamine_itemid = 221662
    
    # Query the inputevents table for dopamine records
    sql = f"""
    SELECT ie.itemid, ie.starttime, ie.amount, ie.rate, ie.rateuom,
           ie.stay_id, ie.subject_id, ie.hadm_id
    FROM mimiciv_icu.inputevents ie
    WHERE ie.itemid = {dopamine_itemid} 
      AND ie.stay_id = {stay_id}
    ORDER BY ie.starttime
    """
    
    df = query_db(sql)
    
    # Initialize result dictionary
    result = {
        'received_dopamine': False,
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
        result['received_dopamine'] = True
        result['num_records'] = len(df)
        result['subject_id'] = int(df['subject_id'].iloc[0])
        result['hadm_id'] = int(df['hadm_id'].iloc[0])
        
        # Calculate rates (rate column is already in mcg/kg/min)
        rates = df['rate'].dropna()
        
        if len(rates) > 0:
            result['max_rate'] = round(float(rates.max()), 2)
            result['min_rate'] = round(float(rates.min()), 2)
            result['avg_rate'] = round(float(rates.mean()), 2)
            
            # Check for high-dose dopamine (>10 mcg/kg/min)
            result['received_high_dose'] = bool(rates.max() > 10)
        
        # Get first and last administration times
        result['first_time'] = pd.to_datetime(df['starttime'].min())
        result['last_time'] = pd.to_datetime(df['starttime'].max())
    
    return result

FINAL_FUNCTION = get_dopamine_info