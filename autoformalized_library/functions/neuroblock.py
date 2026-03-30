import pandas as pd
from datetime import datetime

def get_neuroblock_info(stay_id=None, subject_id=None, hadm_id=None):
    """
    Extract neuromuscular blocking agent (NMBA) administration information for a patient.
    
    Neuromuscular blocking agents (NMBAs) are medications used to induce paralysis,
    typically for intubation, mechanical ventilation, or surgical procedures.
    Common NMBAs include:
    - Cisatracurium
    - Rocuronium
    - Vecuronium
    - Pancuronium
    - Succinylcholine
    
    This function searches both ICU input events and pharmacy/prescription records
    to identify all NMBA administrations for a patient.
    
    Parameters
    ----------
    stay_id : int, optional
        ICU stay identifier. If provided, searches within this specific ICU stay.
        This is the most specific identifier and will also look up the corresponding
        hadm_id for pharmacy queries.
    subject_id : int, optional
        Patient identifier. If provided without stay_id, searches across all 
        admissions for this patient.
    hadm_id : int, optional
        Hospital admission identifier. If provided without stay_id, searches 
        within this admission.
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'received_nmbs': bool - Whether patient received any NMBA
        - 'nmbs_administered': list - List of unique NMBA names administered
        - 'icu_events': DataFrame - NMBA events from ICU input events
        - 'pharmacy_events': DataFrame - NMBA events from pharmacy/prescriptions
        - 'total_doses': int - Total number of NMBA administrations
        - 'first_administration': datetime - Timestamp of first NMBA administration
        - 'last_administration': datetime - Timestamp of last NMBA administration
        - 'duration_hours': float - Duration from first to last NMBA administration (hours)
    
    Examples
    --------
    >>> get_neuroblock_info(stay_id=34475151)
    {'received_nmbs': True, 'nmbs_administered': ['Cisatracurium'], ...}
    
    >>> get_neuroblock_info(hadm_id=24913532)
    {'received_nmbs': True, 'nmbs_administered': ['Cisatracurium'], ...}
    
    >>> get_neuroblock_info(subject_id=12329981)
    {'received_nmbs': True, 'nmbs_administered': ['Cisatracurium'], ...}
    """
    
    # Define NMBA item IDs from ICU input events
    nmba_itemids = {
        221555: 'Cisatracurium',
        229233: 'Rocuronium',
        222062: 'Vecuronium'
    }
    
    # Define NMBA medication patterns for pharmacy/prescriptions
    nmba_patterns = [
        'cisatracurium',
        'rocuronium',
        'vecuronium',
        'pancuronium',
        'succinylcholine'
    ]
    
    # Determine hadm_id from stay_id if needed
    actual_hadm_id = hadm_id
    if stay_id is not None and hadm_id is None:
        stay_info = query_db(f"""
            SELECT hadm_id FROM mimiciv_icu.icustays WHERE stay_id = {stay_id}
        """)
        if not stay_info.empty:
            actual_hadm_id = stay_info.iloc[0]['hadm_id']
    
    # Build query conditions for ICU input events
    if stay_id is not None:
        icu_condition = f"stay_id = {stay_id}"
    elif hadm_id is not None:
        icu_condition = f"hadm_id = {hadm_id}"
    elif subject_id is not None:
        icu_condition = f"subject_id = {subject_id}"
    else:
        raise ValueError("At least one of stay_id, hadm_id, or subject_id must be provided")
    
    # Build query conditions for pharmacy/prescriptions (no stay_id)
    if actual_hadm_id is not None:
        pharmacy_condition = f"hadm_id = {actual_hadm_id}"
    elif subject_id is not None:
        pharmacy_condition = f"subject_id = {subject_id}"
    else:
        raise ValueError("Cannot query pharmacy without hadm_id or subject_id")
    
    # Query ICU input events for NMBAs
    itemid_list = ','.join(map(str, nmba_itemids.keys()))
    icu_query = f"""
    SELECT 
        ie.subject_id,
        ie.hadm_id,
        ie.stay_id,
        ie.starttime,
        ie.endtime,
        ie.amount,
        ie.amountuom,
        ie.rate,
        ie.rateuom,
        ie.statusdescription,
        di.label as medication_name
    FROM mimiciv_icu.inputevents ie
    JOIN mimiciv_icu.d_items di ON ie.itemid = di.itemid
    WHERE ie.itemid IN ({itemid_list})
      AND {icu_condition}
    ORDER BY ie.starttime
    """
    
    icu_events = query_db(icu_query)
    
    # Query pharmacy table for NMBAs
    pharmacy_conditions = ' OR '.join([f"LOWER(medication) LIKE '%{pattern}%'" for pattern in nmba_patterns])
    pharmacy_query = f"""
    SELECT 
        p.subject_id,
        p.hadm_id,
        p.starttime,
        p.stoptime,
        p.medication as medication_name
    FROM mimiciv_hosp.pharmacy p
    WHERE ({pharmacy_conditions})
      AND {pharmacy_condition}
    ORDER BY p.starttime
    """
    
    pharmacy_events = query_db(pharmacy_query)
    
    # Query prescriptions table for NMBAs
    prescription_conditions = ' OR '.join([f"LOWER(drug) LIKE '%{pattern}%'" for pattern in nmba_patterns])
    prescription_query = f"""
    SELECT 
        pr.subject_id,
        pr.hadm_id,
        pr.starttime,
        pr.stoptime,
        pr.drug as medication_name
    FROM mimiciv_hosp.prescriptions pr
    WHERE ({prescription_conditions})
      AND {pharmacy_condition}
    ORDER BY pr.starttime
    """
    
    prescription_events = query_db(prescription_query)
    
    # Combine pharmacy and prescription events
    if not pharmacy_events.empty and not prescription_events.empty:
        pharmacy_events = pd.concat([pharmacy_events, prescription_events], ignore_index=True)
    elif not prescription_events.empty:
        pharmacy_events = prescription_events
    
    # Get unique NMBAs administered
    nmbs_from_icu = icu_events['medication_name'].unique().tolist() if not icu_events.empty else []
    nmbs_from_pharmacy = pharmacy_events['medication_name'].unique().tolist() if not pharmacy_events.empty else []
    
    # Normalize NMBA names
    def normalize_nmbs(name):
        name_lower = name.lower().strip()
        for pattern in nmba_patterns:
            if pattern in name_lower:
                return pattern.capitalize()
        return name
    
    nmbs_administered = list(set([normalize_nmbs(n) for n in nmbs_from_icu + nmbs_from_pharmacy]))
    
    # Calculate timing information
    all_times = []
    if not icu_events.empty:
        all_times.extend(icu_events['starttime'].dropna().tolist())
    if not pharmacy_events.empty:
        all_times.extend(pharmacy_events['starttime'].dropna().tolist())
    
    first_admin = min(all_times) if all_times else None
    last_admin = max(all_times) if all_times else None
    
    duration_hours = None
    if first_admin and last_admin:
        duration_hours = (last_admin - first_admin).total_seconds() / 3600
    
    # Build result
    result = {
        'received_nmbs': len(nmbs_administered) > 0,
        'nmbs_administered': sorted(nmbs_administered),
        'icu_events': icu_events,
        'pharmacy_events': pharmacy_events,
        'total_doses': len(icu_events) + len(pharmacy_events),
        'first_administration': first_admin,
        'last_administration': last_admin,
        'duration_hours': duration_hours
    }
    
    return result

FINAL_FUNCTION = get_neuroblock_info