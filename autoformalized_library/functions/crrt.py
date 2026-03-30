import pandas as pd
from typing import Dict, Any, List, Optional

def get_crrt_info(stay_id: int) -> Dict[str, Any]:
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
        
    Notes
    -----
    CRRT is identified by the presence of CRRT mode data (itemid 227290) or
    Dialysis category chart events. System integrity states include:
    - 'Active': CRRT running normally
    - 'Recirculating': CRRT not effectively treating patient
    - 'Clotted': Filter completely clotted
    - 'Clots Present': Some clotting observed
    - 'Clots Increasing': Worsening clotting
    - 'New Filter': Fresh filter installed
    - 'No Clot Present': No clotting observed
    
    Examples
    --------
    >>> result = get_crrt_info(38838420)
    >>> result['received_crrt']
    True
    >>> result['crrt_active']
    True
    >>> result['filter_clotting']
    True
    """
    
    # Define CRRT-related item IDs
    CRRT_MODE_ITEMID = 227290  # CRRT mode
    SYSTEM_INTEGRITY_ITEMID = 224146  # System Integrity
    FILTER_CHANGE_ITEMID = 225436  # CRRT Filter Change
    
    # Query for CRRT mode data
    crrt_mode_query = f"""
    SELECT charttime, value as crrt_mode
    FROM mimiciv_icu.chartevents
    WHERE stay_id = {stay_id}
    AND itemid = {CRRT_MODE_ITEMID}
    ORDER BY charttime
    """
    
    crrt_modes_df = query_db(crrt_mode_query)
    
    # Query for System Integrity data
    system_integrity_query = f"""
    SELECT charttime, value as system_integrity
    FROM mimiciv_icu.chartevents
    WHERE stay_id = {stay_id}
    AND itemid = {SYSTEM_INTEGRITY_ITEMID}
    ORDER BY charttime
    """
    
    system_integrity_df = query_db(system_integrity_query)
    
    # Query for CRRT Filter Change events
    filter_change_query = f"""
    SELECT COUNT(*) as filter_change_count
    FROM mimiciv_icu.chartevents
    WHERE stay_id = {stay_id}
    AND itemid = {FILTER_CHANGE_ITEMID}
    """
    
    filter_changes_df = query_db(filter_change_query)
    filter_changes = filter_changes_df['filter_change_count'].iloc[0] if not filter_changes_df.empty else 0
    
    # Determine if patient received CRRT
    received_crrt = len(crrt_modes_df) > 0
    
    # Get unique CRRT modes
    crrt_modes = list(crrt_modes_df['crrt_mode'].unique()) if received_crrt else []
    
    # Get all system integrity states
    system_integrity_states = list(system_integrity_df['system_integrity'].unique()) if not system_integrity_df.empty else []
    
    # Determine if CRRT was actively running (not recirculating)
    # Active states: 'Active', 'New Filter', 'No Clot Present'
    # Non-active states: 'Recirculating', 'Clotted', 'Discontinued'
    active_states = ['Active', 'New Filter', 'No Clot Present']
    crrt_active = any(state in active_states for state in system_integrity_states)
    
    # Determine if filter clotting occurred
    # Clotting states: 'Clotted', 'Clots Present', 'Clots Increasing'
    clotting_states = ['Clotted', 'Clots Present', 'Clots Increasing']
    filter_clotting = any(state in clotting_states for state in system_integrity_states)
    
    # Get CRRT start and end times
    crrt_start_time = None
    crrt_end_time = None
    if received_crrt:
        crrt_start_time = crrt_modes_df['charttime'].min()
        crrt_end_time = crrt_modes_df['charttime'].max()
    
    # Get clotting events with timestamps
    clotting_events = []
    if not system_integrity_df.empty:
        clotting_df = system_integrity_df[
            system_integrity_df['system_integrity'].isin(clotting_states)
        ]
        for _, row in clotting_df.iterrows():
            clotting_events.append({
                'timestamp': row['charttime'],
                'state': row['system_integrity']
            })
    
    return {
        'received_crrt': received_crrt,
        'crrt_active': crrt_active,
        'filter_clotting': filter_clotting,
        'crrt_modes': crrt_modes,
        'system_integrity_states': system_integrity_states,
        'crrt_start_time': crrt_start_time,
        'crrt_end_time': crrt_end_time,
        'filter_changes': filter_changes,
        'clotting_events': clotting_events
    }


FINAL_FUNCTION = get_crrt_info