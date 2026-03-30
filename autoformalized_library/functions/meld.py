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
    # Query CRRT mode data (itemid 227290)
    crrt_modes = query_db(f"""
        SELECT charttime, valuenum
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
        AND itemid = 227290
        AND valuenum IS NOT NULL
    """)
    
    # Query dialysis category events
    dialysis_events = query_db(f"""
        SELECT charttime, itemid, value
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
        AND itemid IN (225802, 225803, 225809, 225955)  -- CRRT, CVVHD, CVVHDF, SCUF
    """)
    
    # Query system integrity states
    integrity_states = query_db(f"""
        SELECT charttime, value
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
        AND itemid = 227291  -- System integrity state
        AND value IS NOT NULL
    """)
    
    # Query filter changes
    filter_changes = query_db(f"""
        SELECT charttime
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
        AND itemid = 225436  -- CRRT Filter Change
    """)
    
    # Determine if patient received CRRT
    received_crrt = len(crrt_modes) > 0 or len(dialysis_events) > 0
    
    # Determine if CRRT was active
    crrt_active = False
    if len(integrity_states) > 0:
        crrt_active = 'Active' in integrity_states['value'].values
    
    # Determine if filter clotting occurred
    filter_clotting = False
    if len(integrity_states) > 0:
        clotting_states = ['Clotted', 'Clots Present', 'Clots Increasing']
        filter_clotting = any(state in integrity_states['value'].values for state in clotting_states)
    
    # Get unique CRRT modes
    crrt_mode_list = []
    if len(crrt_modes) > 0:
        mode_mapping = {
            1: 'CVVH',
            2: 'CVVHD', 
            3: 'CVVHDF',
            4: 'SCUF'
        }
        crrt_mode_list = list(set([mode_mapping.get(v, str(v)) for v in crrt_modes['valuenum'].values]))
    
    # Get unique system integrity states
    system_states = list(integrity_states['value'].unique()) if len(integrity_states) > 0 else []
    
    # Get CRRT start and end times
    crrt_start_time = None
    crrt_end_time = None
    all_crrt_times = []
    if len(crrt_modes) > 0:
        all_crrt_times.extend(crrt_modes['charttime'].values)
    if len(dialysis_events) > 0:
        all_crrt_times.extend(dialysis_events['charttime'].values)
    
    if all_crrt_times:
        crrt_start_time = min(all_crrt_times)
        crrt_end_time = max(all_crrt_times)
    
    # Count filter changes
    filter_change_count = len(filter_changes)
    
    # Get clotting events
    clotting_events = []
    if len(integrity_states) > 0:
        clotting_states = ['Clotted', 'Clots Present', 'Clots Increasing']
        for _, row in integrity_states.iterrows():
            if row['value'] in clotting_states:
                clotting_events.append({'time': row['charttime'], 'state': row['value']})
    
    return {
        'received_crrt': received_crrt,
        'crrt_active': crrt_active,
        'filter_clotting': filter_clotting,
        'crrt_modes': crrt_mode_list,
        'system_integrity_states': system_states,
        'crrt_start_time': crrt_start_time,
        'crrt_end_time': crrt_end_time,
        'filter_changes': filter_change_count,
        'clotting_events': clotting_events
    }


def compute_meld_score(stay_id):
    """
    Calculate the MELD (Model for End-Stage Liver Disease) score for a patient's ICU stay.
    
    The MELD score is used to assess the severity of chronic liver disease and prioritize
    patients for liver transplantation. It is calculated using three laboratory values:
    - Total bilirubin (mg/dL)
    - INR (International Normalized Ratio)
    - Creatinine (mg/dL)
    
    The formula is:
    MELD = 3.78 × ln(bilirubin) + 11.2 × ln(INR) + 9.57 × ln(creatinine) + 6.43
    
    Rules:
    - All values are capped at a minimum of 1.0 (if less than 1, use 1)
    - If the patient received dialysis/RRT, creatinine is set to 4.0
    - The score is rounded to the nearest integer
    - The score is capped at a maximum of 40
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier for the patient
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'stay_id': The ICU stay ID (int)
        - 'subject_id': The patient's subject_id (int)
        - 'hadm_id': The hospital admission ID (int)
        - 'meld_score': The calculated MELD score (int, 0-40) or None if insufficient data
        - 'bilirubin': The bilirubin value used in calculation (float) or None
        - 'inr': The INR value used in calculation (float) or None
        - 'creatinine': The creatinine value used in calculation (float) or None
        - 'on_dialysis': Boolean indicating if patient received dialysis/RRT
        - 'meld_ge_15': Boolean indicating if MELD score >= 15, or None if score unavailable
        - 'bilirubin_raw': Raw bilirubin value from lab (float or None)
        - 'inr_raw': Raw INR value from lab (float or None)
        - 'creatinine_raw': Raw creatinine value from lab (float or None)
    
    Notes
    -----
    This function uses the most recent laboratory values from the hospital labevents
    table during the patient's admission. If no values are available for any of the
    three required labs (bilirubin, INR, creatinine), the function returns None for
    the MELD score.
    
    Examples
    --------
    >>> result = compute_meld_score(39553978)
    >>> result['meld_score']
    16
    >>> result['meld_ge_15']
    True
    >>> result['on_dialysis']
    False
    """
    
    # Get stay information
    stay_info = query_db(f"""
        SELECT subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    
    # Get the most recent lab values for bilirubin, INR, and creatinine
    # during the admission
    lab_values = query_db(f"""
        SELECT 
            dli.label,
            le.valuenum,
            le.charttime,
            ROW_NUMBER() OVER (PARTITION BY dli.label ORDER BY le.charttime DESC) as rn
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_hosp.d_labitems dli ON le.itemid = dli.itemid
        WHERE le.subject_id = {subject_id}
        AND le.hadm_id = {hadm_id}
        AND dli.label IN ('Bilirubin, Total', 'INR(PT)', 'Creatinine')
        AND le.valuenum IS NOT NULL
    """)
    
    # Get the most recent value for each lab
    most_recent = lab_values[lab_values['rn'] == 1][['label', 'valuenum']].set_index('label')['valuenum'].to_dict()
    
    # Check if patient received dialysis/CRRT
    crrt_info = get_crrt_info(stay_id)
    on_dialysis = crrt_info.get('received_crrt', False)
    
    # Extract raw values
    bilirubin_raw = most_recent.get('Bilirubin, Total')
    inr_raw = most_recent.get('INR(PT)')
    creatinine_raw = most_recent.get('Creatinine')
    
    # Check if we have all required values
    if bilirubin_raw is None or inr_raw is None or creatinine_raw is None:
        return {
            'stay_id': stay_id,
            'subject_id': int(subject_id),
            'hadm_id': int(hadm_id),
            'meld_score': None,
            'bilirubin': None,
            'inr': None,
            'creatinine': None,
            'on_dialysis': on_dialysis,
            'meld_ge_15': None,
            'bilirubin_raw': bilirubin_raw,
            'inr_raw': inr_raw,
            'creatinine_raw': creatinine_raw
        }
    
    # Apply MELD calculation rules
    # 1. Cap values at minimum 1.0
    bilirubin = max(bilirubin_raw, 1.0)
    inr = max(inr_raw, 1.0)
    creatinine = max(creatinine_raw, 1.0)
    
    # 2. If on dialysis, set creatinine to 4.0
    if on_dialysis:
        creatinine = 4.0
    
    # 3. Calculate MELD score
    meld_score = 3.78 * np.log(bilirubin) + 11.2 * np.log(inr) + 9.57 * np.log(creatinine) + 6.43
    
    # 4. Round to nearest integer
    meld_score = round(meld_score)
    
    # 5. Cap at maximum 40
    meld_score = min(meld_score, 40)
    
    return {
        'stay_id': stay_id,
        'subject_id': int(subject_id),
        'hadm_id': int(hadm_id),
        'meld_score': meld_score,
        'bilirubin': bilirubin,
        'inr': inr,
        'creatinine': creatinine,
        'on_dialysis': on_dialysis,
        'meld_ge_15': meld_score >= 15,
        'bilirubin_raw': float(bilirubin_raw),
        'inr_raw': float(inr_raw),
        'creatinine_raw': float(creatinine_raw)
    }


FINAL_FUNCTION = compute_meld_score