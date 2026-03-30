# Now I'll write the final self-contained code block
import pandas as pd

def get_vasopressin_info(stay_id):
    """
    Extract vasopressin infusion information for a patient's ICU stay.

    This function queries the MIMIC-IV database to retrieve vasopressin medication
    administration data for a specific ICU stay. Vasopressin is a vasopressor
    used to treat hypotension and shock, often as an adjunct to other vasopressors.

    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.

    Returns:
    --------
    dict
        A dictionary containing the following keys:
        - 'received_vasopressin': bool - Whether the patient received vasopressin during this stay
        - 'max_rate': float - Maximum vasopressin infusion rate (units/hour), rounded to 2 decimals
                         Returns 0.0 if no vasopressin was received
        - 'min_rate': float - Minimum vasopressin infusion rate (units/hour), rounded to 2 decimals
                         Returns 0.0 if no vasopressin was received
        - 'avg_rate': float - Average vasopressin infusion rate (units/hour), rounded to 2 decimals
                         Returns 0.0 if no vasopressin was received
        - 'used_as_adjunct': bool - Whether vasopressin was used alongside other vasopressors
                                   (norepinephrine, epinephrine, dopamine, or phenylephrine)
        - 'num_records': int - Number of vasopressin infusion records
        - 'first_time': datetime or None - First vasopressin administration time
        - 'last_time': datetime or None - Last vasopressin administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID

    Example:
    --------
    >>> info = get_vasopressin_info(32969947)
    >>> info['received_vasopressin']
    True
    >>> info['max_rate']
    2.41
    >>> info['used_as_adjunct']
    True
    """
    # Query vasopressin data (itemid 222315)
    sql = """
    SELECT 
        ie.subject_id,
        ie.hadm_id,
        ie.stay_id,
        ie.starttime,
        ie.endtime,
        ie.rate,
        ie.rateuom,
        ie.patientweight
    FROM mimiciv_icu.inputevents ie
    WHERE ie.stay_id = {stay_id} AND ie.itemid = 222315
    ORDER BY ie.starttime
    """.format(stay_id=stay_id)
    
    df = query_db(sql)
    
    result = {
        'received_vasopressin': False,
        'max_rate': 0.0,
        'min_rate': 0.0,
        'avg_rate': 0.0,
        'used_as_adjunct': False,
        'num_records': 0,
        'first_time': None,
        'last_time': None,
        'subject_id': None,
        'hadm_id': None
    }
    
    if df.empty:
        return result
    
    # Convert rate to units/hour if it's in units/min
    df = df.copy()
    df['rate_uh'] = df.apply(
        lambda row: row['rate'] * 60 if row['rateuom'] == 'units/min' else row['rate'],
        axis=1
    )
    
    result['received_vasopressin'] = True
    result['max_rate'] = round(float(df['rate_uh'].max()), 2)
    result['min_rate'] = round(float(df['rate_uh'].min()), 2)
    result['avg_rate'] = round(float(df['rate_uh'].mean()), 2)
    result['num_records'] = len(df)
    result['first_time'] = df['starttime'].min()
    result['last_time'] = df['endtime'].max()
    result['subject_id'] = int(df['subject_id'].iloc[0])
    result['hadm_id'] = int(df['hadm_id'].iloc[0])
    
    # Check if other vasopressors were also administered (adjunct use)
    # Common vasopressor itemids: norepinephrine (221906), epinephrine (221289), 
    # dopamine (221662), phenylephrine (221749) and variants
    adjunct_sql = """
    SELECT DISTINCT ie.itemid
    FROM mimiciv_icu.inputevents ie
    WHERE ie.stay_id = {stay_id} 
      AND ie.itemid IN (221906, 221289, 221662, 221749, 229617, 229630, 229631, 229632, 229789)
    """.format(stay_id=stay_id)
    
    adjunct_df = query_db(adjunct_sql)
    
    if not adjunct_df.empty:
        result['used_as_adjunct'] = True
    
    return result

FINAL_FUNCTION = get_vasopressin_info