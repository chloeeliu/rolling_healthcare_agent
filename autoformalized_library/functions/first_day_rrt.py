import pandas as pd

def get_first_day_rrt(stay_id):
    """
    Extract Renal Replacement Therapy (RRT) information for a patient's first ICU day.
    
    This function queries the MIMIC-IV database to determine whether the patient
    received any form of RRT during their first 24 hours in the ICU.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier for the patient
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'rrt_on_first_day': bool - True if patient received any RRT on first ICU day
        - 'crrt_on_first_day': bool - True if patient received CRRT on first ICU day
        - 'crrt_active_on_first_day': bool - True if CRRT was actively running (not recirculating) on first day
        - 'hemodialysis_on_first_day': bool - True if patient received hemodialysis on first day
        - 'peritoneal_dialysis_on_first_day': bool - True if patient received peritoneal dialysis on first day
        - 'rrt_modalities': list - List of RRT modalities used on first day
        - 'crrt_modes': list - List of CRRT modes used on first day (CVVH, CVVHD, CVVHDF, SCUF)
        - 'first_rrt_time': datetime or None - First RRT observation time on first day
        - 'system_integrity_states': list - List of system integrity states observed on first day
    
    Notes
    -----
    First ICU day is defined as the 24-hour period starting from ICU admission (intime).
    RRT modalities are identified as follows:
    - CRRT: CRRT mode data (itemid 227290) or Dialysis category chart events
    - Hemodialysis: Hemodialysis Output chart events (itemid 226499)
    - Peritoneal Dialysis: Peritoneal dialysis-related chart events
    
    Examples
    --------
    >>> result = get_first_day_rrt(33630048)
    >>> result['rrt_on_first_day']
    True
    >>> result['crrt_on_first_day']
    True
    """
    # Query to get RRT information on first ICU day
    sql = """
    WITH stay_info AS (
        SELECT stay_id, intime, intime + INTERVAL '24 hours' as first_day_end
        FROM mimiciv_icu.icustays 
        WHERE stay_id = {stay_id}
    ),
    dialysis_events AS (
        SELECT 
            ce.charttime,
            ce.value,
            di.label,
            di.itemid
        FROM stay_info si
        JOIN mimiciv_icu.chartevents ce ON ce.stay_id = si.stay_id
        JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
        WHERE ce.charttime >= si.intime 
          AND ce.charttime < si.first_day_end
          AND di.category = 'Dialysis'
    )
    SELECT * FROM dialysis_events
    """
    
    df = query_db(sql.format(stay_id=stay_id))
    
    result = {
        'rrt_on_first_day': False,
        'crrt_on_first_day': False,
        'crrt_active_on_first_day': False,
        'hemodialysis_on_first_day': False,
        'peritoneal_dialysis_on_first_day': False,
        'rrt_modalities': [],
        'crrt_modes': [],
        'first_rrt_time': None,
        'system_integrity_states': []
    }
    
    if len(df) == 0:
        return result
    
    # Check for any RRT
    result['rrt_on_first_day'] = True
    
    # Check for CRRT mode (itemid 227290)
    crrt_modes = df[df['itemid'] == 227290]['value'].dropna().unique().tolist()
    if len(crrt_modes) > 0:
        result['crrt_on_first_day'] = True
        result['crrt_modes'] = crrt_modes
        if 'CRRT' not in result['rrt_modalities']:
            result['rrt_modalities'].append('CRRT')
    
    # Check for System Integrity = Active (indicates CRRT was running)
    system_integrity = df[df['label'] == 'System Integrity']['value'].dropna().unique().tolist()
    result['system_integrity_states'] = system_integrity
    if 'Active' in system_integrity:
        result['crrt_active_on_first_day'] = True
        if 'CRRT' not in result['rrt_modalities']:
            result['crrt_on_first_day'] = True
            result['rrt_modalities'].append('CRRT')
    
    # Check for Hemodialysis Output (itemid 226499)
    hemodialysis_events = df[df['itemid'] == 226499]
    if len(hemodialysis_events) > 0:
        result['hemodialysis_on_first_day'] = True
        if 'Hemodialysis' not in result['rrt_modalities']:
            result['rrt_modalities'].append('Hemodialysis')
    
    # Check for Peritoneal Dialysis (labels containing 'Peritoneal')
    pd_events = df[df['label'].str.contains('Peritoneal', case=False, na=False)]
    if len(pd_events) > 0:
        result['peritoneal_dialysis_on_first_day'] = True
        if 'Peritoneal Dialysis' not in result['rrt_modalities']:
            result['rrt_modalities'].append('Peritoneal Dialysis')
    
    # Get first RRT time
    if len(df) > 0:
        result['first_rrt_time'] = df['charttime'].min()
    
    return result

FINAL_FUNCTION = get_first_day_rrt