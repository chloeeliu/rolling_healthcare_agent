import pandas as pd

def get_patient_age(subject_id=None, hadm_id=None, stay_id=None):
    """
    Calculate patient age at hospital admission.
    
    This function retrieves patient age information from the MIMIC-IV database
    and calculates the precise age at the time of hospital admission.
    
    The age calculation uses the anchor_age and anchor_year from the patients
    table, adjusted by the number of days from the anchor date to the admission
    date, divided by 365.242 (the average length of a year in the Gregorian calendar).
    
    Parameters
    ----------
    subject_id : int, optional
        The patient's subject_id. If provided, returns age for all admissions.
    hadm_id : int, optional
        The hospital admission ID. If provided, returns age for that specific admission.
    stay_id : int, optional
        The ICU stay ID. If provided, returns age for the associated admission.
    
    Returns
    -------
    dict or list of dict or None
        If a single admission is queried (hadm_id or stay_id), returns a dict with:
        - 'subject_id': patient identifier (int)
        - 'hadm_id': admission identifier (int)
        - 'age_at_admission': calculated age in years (float)
        - 'age_65_or_older': boolean indicating if age >= 65
        - 'age_80_or_older': boolean indicating if age >= 80
        
        If subject_id is provided (multiple admissions), returns a list of dicts
        with the same structure, ordered by admission time.
        
        Returns None if no matching patient/admission is found.
    
    Raises
    ------
    ValueError
        If none of subject_id, hadm_id, or stay_id is provided.
    
    Examples
    --------
    >>> get_patient_age(hadm_id=22595853)
    {'subject_id': 10000032, 'hadm_id': 22595853, 'age_at_admission': 52.34753023718217, 
     'age_65_or_older': False, 'age_80_or_older': False}
    
    >>> get_patient_age(subject_id=10000032)
    [{'subject_id': 10000032, 'hadm_id': 22595853, 'age_at_admission': 52.34753023718217, ...}, ...]
    
    >>> get_patient_age(stay_id=39553978)
    {'subject_id': 10000032, 'hadm_id': 29079034, 'age_at_admission': 52.55996929585194, ...}
    """
    
    # Build query based on input parameters
    if stay_id is not None:
        # First get hadm_id from stay_id
        stay_query = query_db(f"""
            SELECT hadm_id 
            FROM mimiciv_icu.icustays 
            WHERE stay_id = {stay_id}
        """)
        
        if stay_query.empty:
            return None
        
        hadm_id = stay_query.iloc[0]['hadm_id']
    
    if hadm_id is not None:
        # Query for specific admission with precise age calculation
        df = query_db(f"""
            SELECT 
                p.subject_id,
                a.hadm_id,
                p.anchor_age + EXTRACT(EPOCH FROM (a.admittime - (DATE '2000-01-01' + INTERVAL (p.anchor_year - 2000) YEAR))) / 86400.0 / 365.242 as age_at_admission
            FROM mimiciv_hosp.patients p
            JOIN mimiciv_hosp.admissions a ON p.subject_id = a.subject_id
            WHERE a.hadm_id = {hadm_id}
        """)
        
        if df.empty:
            return None
        
        age = float(df.iloc[0]['age_at_admission'])
        result = {
            'subject_id': int(df.iloc[0]['subject_id']),
            'hadm_id': int(df.iloc[0]['hadm_id']),
            'age_at_admission': age,
            'age_65_or_older': bool(age >= 65),
            'age_80_or_older': bool(age >= 80)
        }
        return result
    
    elif subject_id is not None:
        # Query for all admissions of a patient with precise age calculation
        df = query_db(f"""
            SELECT 
                p.subject_id,
                a.hadm_id,
                p.anchor_age + EXTRACT(EPOCH FROM (a.admittime - (DATE '2000-01-01' + INTERVAL (p.anchor_year - 2000) YEAR))) / 86400.0 / 365.242 as age_at_admission
            FROM mimiciv_hosp.patients p
            JOIN mimiciv_hosp.admissions a ON p.subject_id = a.subject_id
            WHERE p.subject_id = {subject_id}
            ORDER BY a.admittime
        """)
        
        if df.empty:
            return None
        
        results = []
        for _, row in df.iterrows():
            age = float(row['age_at_admission'])
            results.append({
                'subject_id': int(row['subject_id']),
                'hadm_id': int(row['hadm_id']),
                'age_at_admission': age,
                'age_65_or_older': bool(age >= 65),
                'age_80_or_older': bool(age >= 80)
            })
        return results
    
    else:
        raise ValueError("Must provide at least one of: subject_id, hadm_id, or stay_id")

FINAL_FUNCTION = get_patient_age