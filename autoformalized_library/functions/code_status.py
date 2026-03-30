import pandas as pd

def get_code_status(stay_id):
    """
    Extract code status information for a patient during their ICU stay.
    
    This function queries the MIMIC-IV database to retrieve code status orders
    (DNR, DNI, Full Code, Comfort Measures Only, etc.) for a specific ICU stay.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier from the icustays table.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        
        - 'has_dnr' (bool): True if patient has a DNR (Do Not Resuscitate) order
          during their ICU stay. Includes DNAR (Do Not Attempt Resuscitation)
          and combined DNR/DNI orders.
        
        - 'has_dni' (bool): True if patient has a DNI (Do Not Intubate) order
          during their ICU stay. Includes combined DNR/DNI orders.
        
        - 'is_full_code' (bool): True if patient is documented as Full Code
          (full resuscitation) at any point during their ICU stay.
        
        - 'comfort_measures_only' (bool): True if patient has a Comfort Measures
          Only order during their ICU stay.
        
        - 'code_status_values' (list): List of all code status values recorded
          during the stay (in chronological order, most recent first).
        
        - 'latest_code_status' (str or None): The most recent code status value
          recorded during the stay, or None if no code status was documented.
    """
    # Query code status from chartevents (ICU charting)
    sql_chartevents = """
    SELECT ce.charttime as eventtime, ce.value as code_status
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.icustays i ON ce.stay_id = i.stay_id
    WHERE ce.stay_id = {stay_id}
    AND ce.itemid IN (223758, 228687)
    AND ce.charttime >= i.intime
    AND ce.charttime <= i.outtime
    """.format(stay_id=stay_id)
    
    df_ce = query_db(sql_chartevents)
    
    # Query code status from poe_detail (Provider Order Entry)
    sql_poe = """
    SELECT p.ordertime as eventtime, pd.field_value as code_status
    FROM mimiciv_hosp.poe_detail pd
    JOIN mimiciv_hosp.poe p ON pd.poe_seq = p.poe_seq
    JOIN mimiciv_hosp.admissions a ON p.hadm_id = a.hadm_id
    JOIN mimiciv_icu.icustays i ON a.hadm_id = i.hadm_id
    WHERE i.stay_id = {stay_id}
    AND pd.field_name = 'Code status'
    AND p.ordertime >= i.intime
    AND p.ordertime <= i.outtime
    """.format(stay_id=stay_id)
    
    df_poe = query_db(sql_poe)
    
    # Combine both sources
    if not df_ce.empty and not df_poe.empty:
        df_ce['source'] = 'chartevents'
        df_poe['source'] = 'poe_detail'
        df = pd.concat([df_ce, df_poe], ignore_index=True)
    elif not df_ce.empty:
        df = df_ce
    elif not df_poe.empty:
        df = df_poe
    else:
        df = pd.DataFrame(columns=['eventtime', 'code_status'])
    
    if df.empty:
        return {
            'has_dnr': False,
            'has_dni': False,
            'is_full_code': False,
            'comfort_measures_only': False,
            'code_status_values': [],
            'latest_code_status': None
        }
    
    # Sort by eventtime descending
    df = df.sort_values('eventtime', ascending=False).reset_index(drop=True)
    
    # Get all code status values
    code_status_values = df['code_status'].tolist()
    latest_code_status = df.iloc[0]['code_status']
    
    # Check for DNR (includes DNR/DNI combinations, DNAR)
    dnr_patterns = ['dnr', 'dnar', 'do not resuscitate', 'do not attempt resuscitation']
    has_dnr = any(
        any(pattern in str(val).lower() for pattern in dnr_patterns)
        for val in code_status_values
    )
    
    # Check for DNI (includes DNR/DNI combinations)
    dni_patterns = ['dni', 'do not intubate']
    has_dni = any(
        any(pattern in str(val).lower() for pattern in dni_patterns)
        for val in code_status_values
    )
    
    # Check for full code
    is_full_code = any('full code' in str(val).lower() for val in code_status_values)
    
    # Check for comfort measures only
    comfort_measures_only = any('comfort' in str(val).lower() for val in code_status_values)
    
    return {
        'has_dnr': has_dnr,
        'has_dni': has_dni,
        'is_full_code': is_full_code,
        'comfort_measures_only': comfort_measures_only,
        'code_status_values': code_status_values,
        'latest_code_status': latest_code_status
    }

FINAL_FUNCTION = get_code_status