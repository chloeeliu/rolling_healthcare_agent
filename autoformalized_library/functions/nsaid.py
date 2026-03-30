import pandas as pd
from typing import Optional, Dict, List, Any, Union

def get_nsaid_info(stay_id: Optional[int] = None, 
                   hadm_id: Optional[int] = None, 
                   subject_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Extract NSAID (Non-Steroidal Anti-Inflammatory Drug) administration information for a patient.
    
    This function queries both ICU input events and hospital prescriptions/pharmacy
    records to identify NSAID administrations. It can answer questions such as:
    - Did this patient receive NSAIDs during their hospital admission?
    - How many distinct NSAIDs did this patient receive?
    - Did this patient receive NSAIDs within the first 48 hours of ICU admission?
    
    NSAIDs are identified from:
    - ICU inputevents table (Ketorolac is the primary IV NSAID in ICU)
    - Hospital prescriptions table (Aspirin, Ibuprofen, Naproxen, Ketorolac, 
      Diclofenac, Indomethacin, Celecoxib, Meloxicam, Sulindac)
    
    Parameters
    ----------
    stay_id : int, optional
        ICU stay identifier. If provided, returns ICU-specific NSAID data.
    hadm_id : int, optional
        Hospital admission identifier. If provided, returns hospital-wide NSAID data.
    subject_id : int, optional
        Patient identifier. If provided with hadm_id, filters to that admission.
        If provided alone, returns all NSAID data for the patient across all admissions.
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'nsaid_administrations': DataFrame with all NSAID administrations
          (columns: source, stay_id, hadm_id, subject_id, nsaid_name, admin_time)
        - 'received_nsaids': bool indicating if any NSAIDs were received
        - 'distinct_nsaids': list of unique NSAID names received
        - 'distinct_nsaids_count': int count of unique NSAIDs
        - 'icu_intime': datetime of ICU admission (if stay_id provided)
        - 'within_48hrs_icu': bool indicating if NSAIDs received within 48h of ICU admission
        - 'nsaids_within_48hrs_icu': list of NSAIDs received within 48h of ICU admission
        - 'total_nsaid_doses': int total number of NSAID administrations
    
    Notes
    ----
    - At least one identifier (stay_id, hadm_id, or subject_id) must be provided.
    - NSAIDs include: Aspirin, Ibuprofen, Naproxen, Ketorolac, Diclofenac, 
      Indomethacin, Celecoxib, Meloxicam, Sulindac
    - The function normalizes NSAID names for consistent counting.
    """
    
    # Validate input
    if stay_id is None and hadm_id is None and subject_id is None:
        raise ValueError("At least one identifier (stay_id, hadm_id, or subject_id) must be provided.")
    
    # If stay_id is provided, get the corresponding hadm_id and subject_id
    if stay_id is not None and hadm_id is None:
        stay_info_sql = f"""
        SELECT hadm_id, subject_id
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
        """
        stay_info = query_db(stay_info_sql)
        if stay_info.empty:
            # stay_id doesn't exist - return empty result
            return {
                'nsaid_administrations': pd.DataFrame(columns=['source', 'stay_id', 'hadm_id', 'subject_id', 'nsaid_name', 'admin_time']),
                'received_nsaids': False,
                'distinct_nsaids': [],
                'distinct_nsaids_count': 0,
                'total_nsaid_doses': 0,
                'icu_intime': None,
                'within_48hrs_icu': False,
                'nsaids_within_48hrs_icu': []
            }
        hadm_id = stay_info['hadm_id'].iloc[0]
        subject_id = stay_info['subject_id'].iloc[0]
    
    # NSAID name patterns for prescriptions
    nsaid_patterns = [
        '%aspirin%', '%ibuprofen%', '%naproxen%', '%ketorolac%',
        '%diclofenac%', '%indomethacin%', '%celecoxib%', 
        '%meloxicam%', '%sulindac%'
    ]
    nsaid_pattern_or = ' OR '.join([f"LOWER(drug) LIKE '{p}'" for p in nsaid_patterns])
    
    # Query hospital prescriptions for NSAIDs
    presc_where = []
    if hadm_id is not None:
        presc_where.append(f"p.hadm_id = {hadm_id}")
    if subject_id is not None:
        presc_where.append(f"p.subject_id = {subject_id}")
    presc_where_clause = ' AND '.join(presc_where) if presc_where else "1=1"
    
    presc_sql = f"""
    SELECT 
        'prescription' as source,
        NULL as stay_id,
        p.hadm_id,
        p.subject_id,
        p.drug as nsaid_name,
        p.starttime as admin_time
    FROM mimiciv_hosp.prescriptions p
    WHERE {presc_where_clause}
      AND ({nsaid_pattern_or})
    """
    
    presc_df = query_db(presc_sql)
    
    # Query ICU inputevents for NSAIDs
    icu_where = []
    if stay_id is not None:
        icu_where.append(f"ie.stay_id = {stay_id}")
    if hadm_id is not None:
        icu_where.append(f"ie.hadm_id = {hadm_id}")
    if subject_id is not None:
        icu_where.append(f"ie.subject_id = {subject_id}")
    icu_where_clause = ' AND '.join(icu_where) if icu_where else "1=1"
    
    icu_sql = f"""
    SELECT 
        'icu_input' as source,
        ie.stay_id,
        ie.hadm_id,
        ie.subject_id,
        di.label as nsaid_name,
        ie.starttime as admin_time
    FROM mimiciv_icu.inputevents ie
    JOIN mimiciv_icu.d_items di ON ie.itemid = di.itemid
    WHERE {icu_where_clause}
      AND (LOWER(di.label) LIKE '%ketorolac%'
        OR LOWER(di.label) LIKE '%aspirin%'
        OR LOWER(di.label) LIKE '%ibuprofen%'
        OR LOWER(di.label) LIKE '%naproxen%'
        OR LOWER(di.label) LIKE '%diclofenac%'
        OR LOWER(di.label) LIKE '%indomethacin%'
        OR LOWER(di.label) LIKE '%celecoxib%'
        OR LOWER(di.label) LIKE '%meloxicam%'
        OR LOWER(di.label) LIKE '%sulindac%')
    """
    
    icu_df = query_db(icu_sql)
    
    # Combine results
    if presc_df.empty and icu_df.empty:
        all_nsaids = pd.DataFrame(columns=['source', 'stay_id', 'hadm_id', 'subject_id', 'nsaid_name', 'admin_time'])
    else:
        all_nsaids = pd.concat([presc_df, icu_df], ignore_index=True)
    
    # Normalize NSAID names for counting
    def normalize_nsaid_name(name):
        if pd.isna(name):
            return 'Unknown'
        name_lower = name.lower().strip()
        # Normalize common variations
        if 'aspirin' in name_lower:
            return 'Aspirin'
        elif 'ibuprofen' in name_lower:
            return 'Ibuprofen'
        elif 'naproxen' in name_lower:
            return 'Naproxen'
        elif 'ketorolac' in name_lower:
            return 'Ketorolac'
        elif 'diclofenac' in name_lower:
            return 'Diclofenac'
        elif 'indomethacin' in name_lower:
            return 'Indomethacin'
        elif 'celecoxib' in name_lower:
            return 'Celecoxib'
        elif 'meloxicam' in name_lower:
            return 'Meloxicam'
        elif 'sulindac' in name_lower:
            return 'Sulindac'
        else:
            return name
    
    if not all_nsaids.empty:
        all_nsaids['normalized_nsaid'] = all_nsaids['nsaid_name'].apply(normalize_nsaid_name)
    
    # Get distinct NSAIDs
    distinct_nsaids = all_nsaids['normalized_nsaid'].unique().tolist() if not all_nsaids.empty else []
    
    # Calculate ICU-specific metrics if stay_id provided
    icu_intime = None
    within_48hrs_icu = False
    nsaids_within_48hrs_icu = []
    
    if stay_id is not None:
        # Get ICU admission time
        intime_sql = f"""
        SELECT intime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
        """
        intime_df = query_db(intime_sql)
        if not intime_df.empty:
            icu_intime = intime_df['intime'].iloc[0]
            
            # Check for NSAIDs within 48 hours of ICU admission
            if not all_nsaids.empty:
                all_nsaids = all_nsaids.copy()
                all_nsaids['admin_time'] = pd.to_datetime(all_nsaids['admin_time'])
                all_nsaids['hours_from_intime'] = (all_nsaids['admin_time'] - icu_intime).dt.total_seconds() / 3600
                
                within_48hrs = all_nsaids[(all_nsaids['hours_from_intime'] >= 0) & (all_nsaids['hours_from_intime'] <= 48)]
                
                if not within_48hrs.empty:
                    within_48hrs_icu = True
                    nsaids_within_48hrs_icu = within_48hrs['normalized_nsaid'].unique().tolist()
    
    # Build result dictionary
    result = {
        'nsaid_administrations': all_nsaids.drop(columns=['normalized_nsaid']) if 'normalized_nsaid' in all_nsaids.columns else all_nsaids,
        'received_nsaids': len(all_nsaids) > 0,
        'distinct_nsaids': distinct_nsaids,
        'distinct_nsaids_count': len(distinct_nsaids),
        'total_nsaid_doses': len(all_nsaids),
        'icu_intime': icu_intime,
        'within_48hrs_icu': within_48hrs_icu,
        'nsaids_within_48hrs_icu': nsaids_within_48hrs_icu
    }
    
    return result

FINAL_FUNCTION = get_nsaid_info