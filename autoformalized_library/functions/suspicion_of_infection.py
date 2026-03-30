import pandas as pd
from datetime import datetime, timedelta

# Screening cultures that should NOT count as suspicion of infection
SCREENING_CULTURES = [
    'MRSA SCREEN',
    'CRE Screen', 
    'Cipro Resistant Screen',
    'C, E, & A Screening',
    'Infection Control Yeast',
    'Swab R/O Yeast Screen',
    'MICRO PROBLEM PATIENT',
    'Isolate',
    'XXX'
]

# Prophylaxis antibiotics (typically single dose, surgical prophylaxis)
PROPHYLAXIS_ANTIBIOTICS = ['cefazolin', 'cefazolin sodium']

# Cardiac surgery ICD procedure codes (Vancomycin often used for prophylaxis)
CARDIAC_SURGERY_ICD_CODES = [
    '3610', '3613', '3614', '3615', '3616', '3617',  # Coronary artery bypass
    '3961', '3962', '3963', '3964', '3965', '3966', '3967', '3968', '3969',  # Extracorporeal circulation
    '3510', '3511', '3512', '3513', '3514', '3515', '3516', '3517', '3518',  # Heart valve procedures
    '3520', '3521', '3522', '3523', '3524', '3525', '3526', '3527', '3528',  # Heart valve procedures
    '3530', '3531', '3532', '3533', '3534', '3535', '3536', '3537', '3538',  # Heart valve procedures
    '3540', '3541', '3542', '3543', '3544', '3545', '3546', '3547', '3548',  # Heart valve procedures
    '3550', '3551', '3552', '3553', '3554', '3555', '3556', '3557', '3558',  # Heart valve procedures
    '3560', '3561', '3562', '3563', '3564', '3565', '3566', '3567', '3568',  # Heart valve procedures
    '3570', '3571', '3572', '3573', '3574', '3575', '3576', '3577', '3578',  # Heart valve procedures
    '3580', '3581', '3582', '3583', '3584', '3585', '3586', '3587', '3588',  # Heart valve procedures
    '3590', '3591', '3592', '3593', '3594', '3595', '3596', '3597', '3598',  # Heart valve procedures
]

def get_antibiotic_info(stay_id=None, hadm_id=None, subject_id=None):
    """
    Extract antibiotic administration information for a patient.
    
    Parameters
    ----------
    stay_id : int, optional
        ICU stay identifier. If provided, returns ICU-specific antibiotic data.
    hadm_id : int, optional
        Hospital admission identifier. If provided, returns hospital-wide antibiotic data.
    subject_id : int, optional
        Patient identifier. If provided with hadm_id, filters to that admission.
        If provided alone, returns all antibiotic data for the patient across all admissions.
    
    Returns
    -------
    dict
        A dictionary containing antibiotic administration information.
    """
    if stay_id is None and hadm_id is None and subject_id is None:
        raise ValueError("At least one identifier (stay_id, hadm_id, or subject_id) must be provided.")
    
    all_admins = []
    
    # Get hadm_id and subject_id from stay_id if needed
    stay_hadm_id = None
    stay_subject_id = None
    if stay_id is not None:
        stay_info = query_db(f"""
        SELECT hadm_id, subject_id FROM mimiciv_icu.icustays WHERE stay_id = {stay_id}
        """)
        if len(stay_info) > 0:
            stay_hadm_id = stay_info['hadm_id'].iloc[0]
            stay_subject_id = stay_info['subject_id'].iloc[0]
    
    # Query ICU input events for antibiotics
    if stay_id is not None:
        sql = f"""
        SELECT i.stay_id, i.hadm_id, i.subject_id, d.label as antibiotic_name, i.starttime as admin_time
        FROM mimiciv_icu.inputevents i
        JOIN mimiciv_icu.d_items d ON i.itemid = d.itemid
        WHERE i.stay_id = {stay_id}
          AND d.category = 'Antibiotics'
        """
        icu_abx = query_db(sql)
        if len(icu_abx) > 0:
            icu_abx['source'] = 'ICU_inputevents'
            all_admins.append(icu_abx)
    
    # Query hospital prescriptions for antibiotics
    query_hadm_id = stay_hadm_id if stay_id is not None else hadm_id
    query_subject_id = stay_subject_id if stay_id is not None else subject_id
    
    if query_hadm_id is not None or query_subject_id is not None:
        if query_hadm_id is not None and query_subject_id is not None:
            sql = f"""
            SELECT p.subject_id, p.hadm_id, p.drug as antibiotic_name, p.starttime as admin_time
            FROM mimiciv_hosp.prescriptions p
            WHERE p.hadm_id = {query_hadm_id}
              AND p.subject_id = {query_subject_id}
              AND (p.drug ILIKE '%vancomycin%' OR p.drug ILIKE '%cefepime%' OR p.drug ILIKE '%meropenem%' 
                   OR p.drug ILIKE '%piperacillin%' OR p.drug ILIKE '%cefazolin%' OR p.drug ILIKE '%ceftriaxone%'
                   OR p.drug ILIKE '%ampicillin%' OR p.drug ILIKE '%gentamicin%' OR p.drug ILIKE '%levofloxacin%'
                   OR p.drug ILIKE '%ciprofloxacin%' OR p.drug ILIKE '%metronidazole%' OR p.drug ILIKE '%linezolid%'
                   OR p.drug ILIKE '%daptomycin%' OR p.drug ILIKE '%cefotaxime%' OR p.drug ILIKE '%ceftazidime%'
                   OR p.drug ILIKE '%aztreonam%' OR p.drug ILIKE '%imipenem%' OR p.drug ILIKE '%tigecycline%'
                   OR p.drug ILIKE '%colistin%' OR p.drug ILIKE '%polymyxin%' OR p.drug ILIKE '%teicoplanin%')
            """
        elif query_hadm_id is not None:
            sql = f"""
            SELECT p.subject_id, p.hadm_id, p.drug as antibiotic_name, p.starttime as admin_time
            FROM mimiciv_hosp.prescriptions p
            WHERE p.hadm_id = {query_hadm_id}
              AND (p.drug ILIKE '%vancomycin%' OR p.drug ILIKE '%cefepime%' OR p.drug ILIKE '%meropenem%' 
                   OR p.drug ILIKE '%piperacillin%' OR p.drug ILIKE '%cefazolin%' OR p.drug ILIKE '%ceftriaxone%'
                   OR p.drug ILIKE '%ampicillin%' OR p.drug ILIKE '%gentamicin%' OR p.drug ILIKE '%levofloxacin%'
                   OR p.drug ILIKE '%ciprofloxacin%' OR p.drug ILIKE '%metronidazole%' OR p.drug ILIKE '%linezolid%'
                   OR p.drug ILIKE '%daptomycin%' OR p.drug ILIKE '%cefotaxime%' OR p.drug ILIKE '%ceftazidime%'
                   OR p.drug ILIKE '%aztreonam%' OR p.drug ILIKE '%imipenem%' OR p.drug ILIKE '%tigecycline%'
                   OR p.drug ILIKE '%colistin%' OR p.drug ILIKE '%polymyxin%' OR p.drug ILIKE '%teicoplanin%')
            """
        else:
            sql = f"""
            SELECT p.subject_id, p.hadm_id, p.drug as antibiotic_name, p.starttime as admin_time
            FROM mimiciv_hosp.prescriptions p
            WHERE p.subject_id = {query_subject_id}
              AND (p.drug ILIKE '%vancomycin%' OR p.drug ILIKE '%cefepime%' OR p.drug ILIKE '%meropenem%' 
                   OR p.drug ILIKE '%piperacillin%' OR p.drug ILIKE '%cefazolin%' OR p.drug ILIKE '%ceftriaxone%'
                   OR p.drug ILIKE '%ampicillin%' OR p.drug ILIKE '%gentamicin%' OR p.drug ILIKE '%levofloxacin%'
                   OR p.drug ILIKE '%ciprofloxacin%' OR p.drug ILIKE '%metronidazole%' OR p.drug ILIKE '%linezolid%'
                   OR p.drug ILIKE '%daptomycin%' OR p.drug ILIKE '%cefotaxime%' OR p.drug ILIKE '%ceftazidime%'
                   OR p.drug ILIKE '%aztreonam%' OR p.drug ILIKE '%imipenem%' OR p.drug ILIKE '%tigecycline%'
                   OR p.drug ILIKE '%colistin%' OR p.drug ILIKE '%polymyxin%' OR p.drug ILIKE '%teicoplanin%')
            """
        hosp_abx = query_db(sql)
        if len(hosp_abx) > 0:
            hosp_abx['source'] = 'hospital_prescriptions'
            all_admins.append(hosp_abx)
    
    # Combine all administrations
    if all_admins:
        antibiotic_admins = pd.concat(all_admins, ignore_index=True)
    else:
        antibiotic_admins = pd.DataFrame(columns=['source', 'stay_id', 'hadm_id', 'subject_id', 'antibiotic_name', 'admin_time'])
    
    # Get distinct antibiotics
    distinct_antibiotics = antibiotic_admins['antibiotic_name'].dropna().unique().tolist() if len(antibiotic_admins) > 0 else []
    
    # Get ICU intime if stay_id provided
    icu_intime = None
    within_48hrs_icu = False
    antibiotics_within_48hrs_icu = []
    
    if stay_id is not None:
        stay_info = query_db(f"""
        SELECT intime FROM mimiciv_icu.icustays WHERE stay_id = {stay_id}
        """)
        if len(stay_info) > 0:
            icu_intime = stay_info['intime'].iloc[0]
            
            # Check for antibiotics within 48 hours of ICU admission
            if len(antibiotic_admins) > 0:
                antibiotic_admins['admin_time'] = pd.to_datetime(antibiotic_admins['admin_time'])
                within_48 = antibiotic_admins[
                    (antibiotic_admins['admin_time'] >= icu_intime) & 
                    (antibiotic_admins['admin_time'] <= icu_intime + timedelta(hours=48))
                ]
                within_48hrs_icu = len(within_48) > 0
                antibiotics_within_48hrs_icu = within_48['antibiotic_name'].dropna().unique().tolist()
    
    result = {
        'antibiotic_administrations': antibiotic_admins,
        'received_antibiotics': len(distinct_antibiotics) > 0,
        'distinct_antibiotics': distinct_antibiotics,
        'distinct_antibiotic_count': len(distinct_antibiotics),
        'icu_intime': icu_intime,
        'within_48hrs_icu': within_48hrs_icu,
        'antibiotics_within_48hrs_icu': antibiotics_within_48hrs_icu
    }
    
    return result


def has_cardiac_surgery(hadm_id):
    """Check if patient had cardiac surgery during admission."""
    cardiac_codes_str = "', '".join(CARDIAC_SURGERY_ICD_CODES)
    result = query_db(f"""
    SELECT COUNT(*) as cnt
    FROM mimiciv_hosp.procedures_icd p
    WHERE p.hadm_id = {hadm_id}
      AND p.icd_code IN ('{cardiac_codes_str}')
    """)
    return result['cnt'].iloc[0] > 0 if len(result) > 0 else False


def get_suspicion_of_infection(stay_id=None, hadm_id=None, subject_id=None):
    """
    Determine if a patient had suspicion of infection during their ICU stay or hospital admission.
    
    Suspicion of infection is identified by:
    1. Diagnostic culture orders (blood, urine, sputum, wound, etc.) - indicates clinician suspected infection
       - Excludes screening cultures (MRSA SCREEN, CRE Screen, etc.)
    2. Antibiotic administration with treatment pattern (multiple doses or extended duration)
       - Excludes prophylaxis antibiotics (Cefazolin)
       - Excludes antibiotics administered before ICU admission
       - Excludes cardiac surgery prophylaxis (Vancomycin in cardiac surgery patients without cultures)
    
    Parameters
    ----------
    stay_id : int, optional
        ICU stay identifier.
    hadm_id : int, optional
        Hospital admission identifier.
    subject_id : int, optional
        Patient identifier.
    
    Returns
    -------
    dict
        Dictionary with suspicion of infection information.
    """
    
    # Build the NOT IN clause for screening cultures
    not_in_clause = "', '".join(SCREENING_CULTURES)
    
    # Build the query based on provided identifiers
    if stay_id is not None:
        # Query for diagnostic cultures during ICU stay (excluding screening)
        sql = f"""
        SELECT m.subject_id, m.hadm_id, i.stay_id, 
               m.spec_type_desc,
               CAST(m.chartdate AS DATE) + CAST(m.charttime AS TIME) as culture_time,
               i.intime as icu_intime,
               i.outtime as icu_outtime
        FROM mimiciv_hosp.microbiologyevents m
        JOIN mimiciv_icu.icustays i ON m.subject_id = i.subject_id AND m.hadm_id = i.hadm_id
        WHERE i.stay_id = {stay_id}
          AND m.hadm_id IS NOT NULL
          AND (CAST(m.chartdate AS DATE) + CAST(m.charttime AS TIME)) >= i.intime
          AND (CAST(m.chartdate AS DATE) + CAST(m.charttime AS TIME)) <= i.outtime
          AND m.spec_type_desc NOT IN ('{not_in_clause}')
        ORDER BY culture_time
        """
        culture_df = query_db(sql)
        
        # Get ICU stay times
        stay_info = query_db(f"""
        SELECT intime, outtime, hadm_id FROM mimiciv_icu.icustays WHERE stay_id = {stay_id}
        """)
        icu_intime = stay_info['intime'].iloc[0] if len(stay_info) > 0 else None
        icu_outtime = stay_info['outtime'].iloc[0] if len(stay_info) > 0 else None
        stay_hadm_id = stay_info['hadm_id'].iloc[0] if len(stay_info) > 0 else None
        
        # Get antibiotic info for this stay
        antibiotic_info = get_antibiotic_info(stay_id=stay_id)
        
    elif hadm_id is not None:
        # Query for diagnostic cultures during hospital admission (excluding screening)
        if subject_id is not None:
            sql = f"""
            SELECT m.subject_id, m.hadm_id, 
                   m.spec_type_desc,
                   CAST(m.chartdate AS DATE) + CAST(m.charttime AS TIME) as culture_time
            FROM mimiciv_hosp.microbiologyevents m
            WHERE m.hadm_id = {hadm_id}
              AND m.subject_id = {subject_id}
              AND m.hadm_id IS NOT NULL
              AND m.spec_type_desc NOT IN ('{not_in_clause}')
            ORDER BY culture_time
            """
        else:
            sql = f"""
            SELECT m.subject_id, m.hadm_id, 
                   m.spec_type_desc,
                   CAST(m.chartdate AS DATE) + CAST(m.charttime AS TIME) as culture_time
            FROM mimiciv_hosp.microbiologyevents m
            WHERE m.hadm_id = {hadm_id}
              AND m.hadm_id IS NOT NULL
              AND m.spec_type_desc NOT IN ('{not_in_clause}')
            ORDER BY culture_time
            """
        culture_df = query_db(sql)
        
        icu_intime = None
        icu_outtime = None
        stay_hadm_id = hadm_id
        
        # Get antibiotic info for this admission
        antibiotic_info = get_antibiotic_info(hadm_id=hadm_id, subject_id=subject_id)
        
    elif subject_id is not None:
        # Query for all diagnostic cultures for this patient across all admissions (excluding screening)
        sql = f"""
        SELECT m.subject_id, m.hadm_id, 
               m.spec_type_desc,
               CAST(m.chartdate AS DATE) + CAST(m.charttime AS TIME) as culture_time
        FROM mimiciv_hosp.microbiologyevents m
        WHERE m.subject_id = {subject_id}
          AND m.hadm_id IS NOT NULL
          AND m.spec_type_desc NOT IN ('{not_in_clause}')
        ORDER BY culture_time
        """
        culture_df = query_db(sql)
        
        icu_intime = None
        icu_outtime = None
        stay_hadm_id = None
        
        # Get antibiotic info for this patient
        antibiotic_info = get_antibiotic_info(subject_id=subject_id)
    else:
        raise ValueError("At least one identifier must be provided.")
    
    # Determine if there was suspicion of infection
    has_cultures = len(culture_df) > 0
    
    # For antibiotics, check if there's a treatment pattern
    has_antibiotics = antibiotic_info.get('received_antibiotics', False)
    antibiotic_admins = antibiotic_info.get('antibiotic_administrations', pd.DataFrame())
    
    # Check for treatment pattern: multiple doses of the same antibiotic (excluding prophylaxis)
    has_treatment_pattern = False
    if len(antibiotic_admins) > 0:
        # Filter out prophylaxis antibiotics (Cefazolin)
        non_prophylaxis_abx = antibiotic_admins[
            ~antibiotic_admins['antibiotic_name'].str.lower().isin(PROPHYLAXIS_ANTIBIOTICS)
        ].copy()
        
        if len(non_prophylaxis_abx) > 0:
            # For ICU stays, only count antibiotics administered during or after ICU admission
            if stay_id is not None and icu_intime is not None:
                non_prophylaxis_abx['admin_time'] = pd.to_datetime(non_prophylaxis_abx['admin_time'])
                non_prophylaxis_abx = non_prophylaxis_abx[
                    non_prophylaxis_abx['admin_time'] >= icu_intime
                ]
            
            if len(non_prophylaxis_abx) > 0:
                # Count doses per antibiotic
                dose_counts = non_prophylaxis_abx.groupby('antibiotic_name').size()
                
                # If any antibiotic has >= 2 doses, consider it treatment
                if dose_counts.max() >= 2:
                    has_treatment_pattern = True
                # Or if there are multiple distinct antibiotics
                elif len(dose_counts) >= 2:
                    has_treatment_pattern = True
                
                # Special case: Vancomycin in cardiac surgery patients without cultures
                # If only Vancomycin and no cultures, and patient had cardiac surgery, exclude
                if has_treatment_pattern and not has_cultures:
                    if len(non_prophylaxis_abx) > 0:
                        abx_names = non_prophylaxis_abx['antibiotic_name'].str.lower().unique()
                        if 'vancomycin' in abx_names and len(abx_names) == 1:
                            # Check if cardiac surgery
                            if stay_hadm_id is not None and has_cardiac_surgery(stay_hadm_id):
                                has_treatment_pattern = False
    
    has_suspicion = has_cultures or has_treatment_pattern
    
    # Get distinct culture types
    distinct_culture_types = culture_df['spec_type_desc'].dropna().unique().tolist() if len(culture_df) > 0 else []
    
    # Build result
    result = {
        'has_suspicion_of_infection': has_suspicion,
        'culture_orders': culture_df,
        'antibiotic_info': antibiotic_info,
        'distinct_culture_types': distinct_culture_types,
        'culture_count': len(culture_df),
        'has_treatment_pattern': has_treatment_pattern,
        'icu_intime': icu_intime,
        'icu_outtime': icu_outtime
    }
    
    return result

FINAL_FUNCTION = get_suspicion_of_infection