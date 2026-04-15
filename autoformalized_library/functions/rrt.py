import pandas as pd
import numpy as np
from datetime import datetime

def get_crrt_info(stay_id):
    """
    Extract CRRT (Continuous Renal Replacement Therapy) information for a patient's ICU stay.

    This function queries the MIMIC-IV database to determine:
    1. Whether the patient received CRRT during their ICU stay
    2. Whether the CRRT system was actively running (not recirculating)
    3. Whether the patient experienced filter clotting during CRRT

    Parameters
    ----------
    stay_id : int
        The ICU stay identifier for the patient
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'received_crrt': bool - True if patient received any CRRT during stay
        - 'crrt_active': bool - True if CRRT was actively running (not recirculating) at any point
        - 'filter_clotting': bool - True if patient experienced filter clotting
        - 'crrt_modes': list - List of CRRT modes used (CVVH, CVVHD, CVVHDF, SCUF)
        - 'system_integrity_states': list - List of all system integrity states observed
        - 'crrt_start_time': datetime or None - First CRRT observation time
        - 'crrt_end_time': datetime or None - Last CRRT observation time
        - 'filter_changes': int - Number of filter changes recorded
        - 'clotting_events': list - List of clotting-related events with timestamps
    """
    
    # CRRT-related item IDs
    crrt_mode_itemid = 227290  # CRRT mode
    system_integrity_itemid = 224146  # System Integrity
    
    # Query for CRRT mode data
    crrt_mode_query = f"""
    SELECT ce.charttime, ce.value
    FROM mimiciv_icu.chartevents ce
    WHERE ce.stay_id = {stay_id}
      AND ce.itemid = {crrt_mode_itemid}
    ORDER BY ce.charttime
    """
    crrt_modes_df = query_db(crrt_mode_query)
    
    # Query for System Integrity data
    system_integrity_query = f"""
    SELECT ce.charttime, ce.value
    FROM mimiciv_icu.chartevents ce
    WHERE ce.stay_id = {stay_id}
      AND ce.itemid = {system_integrity_itemid}
    ORDER BY ce.charttime
    """
    system_integrity_df = query_db(system_integrity_query)
    
    # Determine if patient received CRRT
    received_crrt = len(crrt_modes_df) > 0 or len(system_integrity_df) > 0
    
    if not received_crrt:
        return {
            'received_crrt': False,
            'crrt_active': False,
            'filter_clotting': False,
            'crrt_modes': [],
            'system_integrity_states': [],
            'crrt_start_time': None,
            'crrt_end_time': None,
            'filter_changes': 0,
            'clotting_events': []
        }
    
    # Extract CRRT modes
    crrt_modes = list(crrt_modes_df['value'].dropna().unique())
    
    # Extract system integrity states
    system_integrity_states = list(system_integrity_df['value'].dropna().unique())
    
    # Determine if CRRT was active (not recirculating)
    crrt_active = 'Active' in system_integrity_states
    
    # Determine filter clotting
    clotting_states = ['Clotted', 'Clots Present', 'Clots Increasing']
    filter_clotting = any(state in system_integrity_states for state in clotting_states)
    
    # Calculate start and end times
    all_times = []
    if len(crrt_modes_df) > 0:
        all_times.extend(crrt_modes_df['charttime'].dropna().tolist())
    if len(system_integrity_df) > 0:
        all_times.extend(system_integrity_df['charttime'].dropna().tolist())
    
    crrt_start_time = min(all_times) if all_times else None
    crrt_end_time = max(all_times) if all_times else None
    
    # Count filter changes (New Filter events)
    filter_changes = system_integrity_df[system_integrity_df['value'] == 'New Filter'].shape[0]
    
    # Extract clotting events
    clotting_events = []
    for _, row in system_integrity_df.iterrows():
        if row['value'] in clotting_states:
            clotting_events.append({
                'timestamp': row['charttime'],
                'state': row['value']
            })
    
    return {
        'received_crrt': received_crrt,
        'crrt_active': crrt_active,
        'filter_clotting': filter_clotting,
        'crrt_modes': crrt_modes,
        'system_integrity_states': system_integrity_states,
        'crrt_start_time': crrt_start_time,
        'crrt_end_time': crrt_end_time,
        'filter_changes': int(filter_changes),
        'clotting_events': clotting_events
    }


def get_rrt_info(stay_id):
    """
    Extract Renal Replacement Therapy (RRT) information for a patient's ICU stay.
    
    This function queries the MIMIC-IV database to determine:
    1. Whether the patient received any form of RRT during their ICU stay
    2. The specific modalities of RRT used (CRRT, Hemodialysis, Peritoneal Dialysis)
    3. Whether CRRT was actively running (not recirculating) at any point
    4. Detailed CRRT information including modes, system integrity states, and filter events
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier for the patient
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'received_rrt': bool - True if patient received any RRT during stay
        - 'rrt_modalities': list - List of RRT modalities used (CRRT, Hemodialysis, Peritoneal Dialysis)
        - 'crrt_info': dict - Detailed CRRT information (from get_crrt_info)
        - 'peritoneal_dialysis': bool - True if patient received peritoneal dialysis
        - 'hemodialysis': bool - True if patient received hemodialysis
        - 'rrt_start_time': datetime or None - First RRT observation time
        - 'rrt_end_time': datetime or None - Last RRT observation time
    
    Notes
    -----
    RRT modalities are identified as follows:
    - CRRT: CRRT mode data (itemid 227290) or Dialysis category chart events
    - Peritoneal Dialysis: Peritoneal dialysis-related chart events
    - Hemodialysis: Hemodialysis procedures from procedures_icd table or Hemodialysis Output chart events
    
    Examples
    --------
    >>> result = get_rrt_info(37631039)
    >>> result['received_rrt']
    True
    >>> result['rrt_modalities']
    ['CRRT']
    """
    
    # Get CRRT information using the helper function
    try:
        crrt_info = get_crrt_info(stay_id)
    except:
        crrt_info = {
            'received_crrt': False,
            'crrt_active': False,
            'filter_clotting': False,
            'crrt_modes': [],
            'system_integrity_states': [],
            'crrt_start_time': None,
            'crrt_end_time': None,
            'filter_changes': 0,
            'clotting_events': []
        }
    
    # Check for Peritoneal Dialysis
    pd_itemids = [225953, 225963, 225951, 225965, 225810, 225952, 225961, 225959, 227638, 227640, 227639, 225806, 225807, 225805]
    
    pd_query = f"""
    SELECT COUNT(*) as cnt, MIN(charttime) as pd_start, MAX(charttime) as pd_end
    FROM mimiciv_icu.chartevents
    WHERE stay_id = {stay_id}
      AND itemid IN ({','.join(map(str, pd_itemids))})
    """
    pd_result = query_db(pd_query).iloc[0]
    peritoneal_dialysis = pd_result['cnt'] > 0
    pd_start = pd_result['pd_start']
    pd_end = pd_result['pd_end']
    
    # Check for Hemodialysis from procedures table and chart events
    # First get the hadm_id for this stay
    stay_info = query_db(f"""
    SELECT hadm_id
    FROM mimiciv_icu.icustays
    WHERE stay_id = {stay_id}
    """)
    
    hemodialysis = False
    hd_start = None
    hd_end = None
    
    # Check for hemodialysis chart events (Hemodialysis Output)
    hd_chart_query = f"""
    SELECT COUNT(*) as cnt, MIN(charttime) as hd_start, MAX(charttime) as hd_end
    FROM mimiciv_icu.chartevents
    WHERE stay_id = {stay_id}
      AND itemid = 226499
    """
    hd_chart_result = query_db(hd_chart_query).iloc[0]
    
    if hd_chart_result['cnt'] > 0:
        hemodialysis = True
        hd_start = hd_chart_result['hd_start']
        hd_end = hd_chart_result['hd_end']
    
    # Also check for hemodialysis procedures during this admission
    if len(stay_info) > 0:
        hadm_id = stay_info['hadm_id'].iloc[0]
        
        # Check for hemodialysis procedures during this admission
        hd_proc_query = f"""
        SELECT COUNT(*) as cnt, MIN(chartdate) as hd_start, MAX(chartdate) as hd_end
        FROM mimiciv_hosp.procedures_icd p
        JOIN mimiciv_hosp.d_icd_procedures d ON p.icd_code = d.icd_code
        WHERE p.hadm_id = {hadm_id}
          AND LOWER(d.long_title) LIKE '%hemodialysis%'
        """
        hd_proc_result = query_db(hd_proc_query).iloc[0]
        
        if hd_proc_result['cnt'] > 0:
            hemodialysis = True
            # Update start/end times if procedure times are earlier/later
            if hd_proc_result['hd_start'] and (hd_start is None or pd.Timestamp(hd_proc_result['hd_start']) < pd.Timestamp(hd_start)):
                hd_start = hd_proc_result['hd_start']
            if hd_proc_result['hd_end'] and (hd_end is None or pd.Timestamp(hd_proc_result['hd_end']) > pd.Timestamp(hd_end)):
                hd_end = hd_proc_result['hd_end']
    
    # Determine RRT modalities
    rrt_modalities = []
    if crrt_info.get('received_crrt', False):
        rrt_modalities.append('CRRT')
    if peritoneal_dialysis:
        rrt_modalities.append('Peritoneal Dialysis')
    if hemodialysis:
        rrt_modalities.append('Hemodialysis')
    
    # Determine overall RRT status
    received_rrt = len(rrt_modalities) > 0
    
    # Determine overall RRT start and end times
    rrt_start_time = None
    rrt_end_time = None
    
    times = []
    if crrt_info.get('crrt_start_time'):
        times.append(crrt_info['crrt_start_time'])
    if pd_start:
        times.append(pd_start)
    if hd_start:
        times.append(hd_start)
    
    if times:
        rrt_start_time = min(times)
    
    end_times = []
    if crrt_info.get('crrt_end_time'):
        end_times.append(crrt_info['crrt_end_time'])
    if pd_end:
        end_times.append(pd_end)
    if hd_end:
        end_times.append(hd_end)
    
    if end_times:
        rrt_end_time = max(end_times)
    
    return {
        'received_rrt': received_rrt,
        'rrt_modalities': rrt_modalities,
        'crrt_info': crrt_info,
        'peritoneal_dialysis': peritoneal_dialysis,
        'hemodialysis': hemodialysis,
        'rrt_start_time': rrt_start_time,
        'rrt_end_time': rrt_end_time
    }

FINAL_FUNCTION = get_rrt_info