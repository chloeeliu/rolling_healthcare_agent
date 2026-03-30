import pandas as pd

def get_rhythm_info(stay_id):
    """
    Extract cardiac rhythm information for a specific ICU stay.
    
    This function retrieves all documented cardiac rhythms and ectopy events
    for a patient during their ICU stay, and provides answers to key clinical
    questions about arrhythmias.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict or None
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'subject_id': Patient identifier (int)
        - 'hadm_id': Hospital admission identifier (int)
        - 'icu_intime': ICU admission timestamp (datetime or None)
        - 'icu_outtime': ICU discharge timestamp (datetime or None)
        - 'has_atrial_fibrillation': Boolean indicating if AF was documented (bool)
        - 'has_cardiac_ectopy': Boolean indicating if any ectopy was documented (bool)
        - 'has_ventricular_tachycardia': Boolean indicating if VT was documented (bool)
        - 'all_rhythms': List of all unique rhythm values observed (list of str)
        - 'all_ectopy_types': List of all unique ectopy types observed (list of str)
        - 'rhythm_timeline': List of dicts with charttime and rhythm value (list of dict)
        - 'ectopy_timeline': List of dicts with charttime and ectopy value (list of dict)
        
        Returns None if no matching ICU stay is found.
    
    Raises
    ------
    ValueError
        If stay_id is not provided.
    
    Examples
    --------
    >>> get_rhythm_info(36223916)
    {'stay_id': 36223916, 'subject_id': 10135398, 'hadm_id': 28054572,
     'has_atrial_fibrillation': True, 'has_cardiac_ectopy': True,
     'has_ventricular_tachycardia': False, ...}
    """
    if stay_id is None:
        raise ValueError("stay_id must be provided")
    
    # Get ICU stay details
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        return None
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = stay_info.iloc[0]['intime']
    outtime = stay_info.iloc[0]['outtime']
    
    # Get all rhythm events during the ICU stay
    rhythm_data = query_db(f"""
        SELECT ce.charttime, ce.value
        FROM mimiciv_icu.chartevents ce
        WHERE ce.stay_id = {stay_id}
          AND ce.itemid = 220048  -- Heart Rhythm
          AND ce.charttime >= '{intime}'
          AND ce.charttime <= '{outtime}'
        ORDER BY ce.charttime
    """)
    
    # Get all ectopy events during the ICU stay
    ectopy_data = query_db(f"""
        SELECT ce.charttime, ce.value
        FROM mimiciv_icu.chartevents ce
        WHERE ce.stay_id = {stay_id}
          AND ce.itemid IN (224650, 226479)  -- Ectopy Type 1 and 2
          AND ce.charttime >= '{intime}'
          AND ce.charttime <= '{outtime}'
          AND ce.value NOT IN ('None', 'none', '')
        ORDER BY ce.charttime
    """)
    
    # Extract unique rhythms
    all_rhythms = rhythm_data['value'].dropna().unique().tolist() if not rhythm_data.empty else []
    
    # Extract unique ectopy types
    all_ectopy_types = ectopy_data['value'].dropna().unique().tolist() if not ectopy_data.empty else []
    
    # Check for atrial fibrillation
    has_af = any('AF' in str(r) or 'Atrial Fibrillation' in str(r) for r in all_rhythms)
    
    # Check for ventricular tachycardia
    has_vt = any('VT' in str(r) or 'Ventricular Tachycardia' in str(r) for r in all_rhythms)
    
    # Check for cardiac ectopy (any non-empty ectopy type)
    has_ectopy = len(all_ectopy_types) > 0
    
    # Build timeline
    rhythm_timeline = []
    if not rhythm_data.empty:
        for _, row in rhythm_data.iterrows():
            rhythm_timeline.append({
                'charttime': row['charttime'],
                'rhythm': row['value']
            })
    
    ectopy_timeline = []
    if not ectopy_data.empty:
        for _, row in ectopy_data.iterrows():
            ectopy_timeline.append({
                'charttime': row['charttime'],
                'ectopy_type': row['value']
            })
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'icu_intime': intime,
        'icu_outtime': outtime,
        'has_atrial_fibrillation': has_af,
        'has_cardiac_ectopy': has_ectopy,
        'has_ventricular_tachycardia': has_vt,
        'all_rhythms': all_rhythms,
        'all_ectopy_types': all_ectopy_types,
        'rhythm_timeline': rhythm_timeline,
        'ectopy_timeline': ectopy_timeline
    }

FINAL_FUNCTION = get_rhythm_info