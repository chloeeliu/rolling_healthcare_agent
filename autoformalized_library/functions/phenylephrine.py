import pandas as pd

def get_phenylephrine_info(stay_id):
    """
    Extract phenylephrine infusion information for a patient's ICU stay.

    This function queries the MIMIC-IV database to retrieve phenylephrine medication
    administration data for a specific ICU stay. Phenylephrine is a vasopressor 
    (alpha-1 adrenergic agonist) used to treat hypotension and shock.

    Parameters
    ----------
    stay_id : int
        The ICU stay identifier for the patient.

    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'received_phenylephrine': bool - Whether the patient received phenylephrine during this stay
        - 'max_rate': float - Maximum phenylephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                            Returns 0.0 if no phenylephrine was received
        - 'min_rate': float - Minimum phenylephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                            Returns 0.0 if no phenylephrine was received
        - 'avg_rate': float - Average phenylephrine infusion rate (mcg/kg/min), rounded to 2 decimals
                            Returns 0.0 if no phenylephrine was received
        - 'num_records': int - Number of phenylephrine infusion records
        - 'first_time': datetime or None - First phenylephrine administration time
        - 'last_time': datetime or None - Last phenylephrine administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID
        - 'total_duration_minutes': float or None - Total duration of phenylephrine infusion in minutes

    Example
    -------
    >>> info = get_phenylephrine_info(37081114)
    >>> info['received_phenylephrine']
    True
    >>> info['max_rate']
    0.6
    >>> info['min_rate']
    0.2
    """
    # Phenylephrine item IDs from d_items table
    # 221749: Phenylephrine
    # 229630: Phenylephrine (50/250)
    # 229631: Phenylephrine (200/250)_OLD_1
    # 229632: Phenylephrine (200/250)
    phenylephrine_itemids = [221749, 229630, 229631, 229632]
    
    # Query the database for phenylephrine infusion records
    sql = f"""
    SELECT 
        subject_id, hadm_id, stay_id,
        itemid, rate, rateuom,
        patientweight, starttime, endtime, statusdescription
    FROM mimiciv_icu.inputevents 
    WHERE itemid IN ({','.join(map(str, phenylephrine_itemids))})
      AND stay_id = {stay_id}
    ORDER BY starttime
    """
    
    df = query_db(sql)
    
    # Initialize result dictionary with default values
    result = {
        'received_phenylephrine': False,
        'max_rate': 0.0,
        'min_rate': 0.0,
        'avg_rate': 0.0,
        'num_records': 0,
        'first_time': None,
        'last_time': None,
        'subject_id': None,
        'hadm_id': None,
        'total_duration_minutes': None
    }
    
    # If no records found, return default result
    if df.empty:
        return result
    
    # Patient received phenylephrine
    result['received_phenylephrine'] = True
    result['num_records'] = int(len(df))
    result['subject_id'] = int(df['subject_id'].iloc[0])
    result['hadm_id'] = int(df['hadm_id'].iloc[0])
    
    # Filter to records with valid rates
    valid_rates = df['rate'].dropna()
    
    if len(valid_rates) > 0:
        # Convert to float and round properly to 2 decimal places
        max_val = float(valid_rates.max())
        min_val = float(valid_rates.min())
        avg_val = float(valid_rates.mean())
        
        result['max_rate'] = round(max_val, 2)
        result['min_rate'] = round(min_val, 2)
        result['avg_rate'] = round(avg_val, 2)
    
    # Get first and last times
    result['first_time'] = df['starttime'].min()
    result['last_time'] = df['endtime'].max()
    
    # Calculate total duration of infusion
    if pd.notna(result['first_time']) and pd.notna(result['last_time']):
        duration = result['last_time'] - result['first_time']
        result['total_duration_minutes'] = float(duration.total_seconds() / 60)
    
    return result

FINAL_FUNCTION = get_phenylephrine_info