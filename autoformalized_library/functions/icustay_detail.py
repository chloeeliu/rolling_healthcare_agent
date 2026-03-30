import pandas as pd

def icustay_detail(stay_id):
    """
    Extract critical clinical information for an ICU stay.
    
    This function retrieves comprehensive details about a specific ICU stay,
    including mortality status, length of stay, and whether this is the first
    ICU admission during the hospitalization.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict or None
        A dictionary containing the following keys:
        - 'subject_id': patient identifier (int)
        - 'hadm_id': hospital admission identifier (int)
        - 'stay_id': ICU stay identifier (int)
        - 'first_careunit': first ICU unit the patient was in (str or None)
        - 'last_careunit': last ICU unit the patient was in (str or None)
        - 'intime': ICU admission timestamp (datetime or None)
        - 'outtime': ICU discharge timestamp (datetime or None)
        - 'icu_los_days': length of ICU stay in days (float)
        - 'died_during_admission': boolean indicating if patient died during hospital admission
        - 'deathtime': time of death if applicable (datetime or None)
        - 'is_first_icu_stay': boolean indicating if this is the first ICU stay for this admission
        - 'icu_stay_order': the order number of this ICU stay within the admission (int)
        - 'gender': patient gender (str)
        - 'anchor_age': patient age at anchor date (int or None)
        
        Returns None if no matching ICU stay is found.
    
    Raises
    ------
    ValueError
        If stay_id is not provided.
    
    Examples
    --------
    >>> icustay_detail(39553978)
    {'subject_id': 10000032, 'hadm_id': 29079034, 'stay_id': 39553978, 
     'first_careunit': 'Medical Intensive Care Unit (MICU)', 
     'last_careunit': 'Medical Intensive Care Unit (MICU)', 
     'intime': Timestamp('2180-07-23 14:00:00'), 
     'outtime': Timestamp('2180-07-23 23:50:47'), 
     'icu_los_days': 0.4102661907672882, 
     'died_during_admission': False, 
     'deathtime': NaT, 
     'is_first_icu_stay': True, 
     'icu_stay_order': 1, 
     'gender': 'F', 
     'anchor_age': 52}
    """
    if stay_id is None:
        raise ValueError("stay_id must be provided")
    
    # Query to get all ICU stay details with proper stay ordering
    # Use a CTE to calculate stay order before filtering
    query = f"""
    WITH stay_ordering AS (
        SELECT 
            i.stay_id,
            i.hadm_id,
            ROW_NUMBER() OVER (PARTITION BY i.hadm_id ORDER BY i.intime) as icu_stay_order
        FROM mimiciv_icu.icustays i
    )
    SELECT 
        i.subject_id,
        i.hadm_id,
        i.stay_id,
        i.first_careunit,
        i.last_careunit,
        i.intime,
        i.outtime,
        i.los as icu_los_days,
        a.deathtime,
        a.hospital_expire_flag,
        p.gender,
        p.anchor_age,
        so.icu_stay_order
    FROM mimiciv_icu.icustays i
    JOIN mimiciv_hosp.admissions a ON i.hadm_id = a.hadm_id
    JOIN mimiciv_hosp.patients p ON i.subject_id = p.subject_id
    JOIN stay_ordering so ON i.stay_id = so.stay_id
    WHERE i.stay_id = {stay_id}
    """
    
    result = query_db(query)
    
    if result.empty:
        return None
    
    row = result.iloc[0]
    
    # Determine if patient died during admission
    died_during_admission = (
        (row['deathtime'] is not None and pd.notna(row['deathtime']))
        or row['hospital_expire_flag'] == 1
    )
    
    # Determine if this is the first ICU stay
    is_first_icu_stay = row['icu_stay_order'] == 1
    
    return {
        'subject_id': int(row['subject_id']),
        'hadm_id': int(row['hadm_id']),
        'stay_id': int(row['stay_id']),
        'first_careunit': row['first_careunit'],
        'last_careunit': row['last_careunit'],
        'intime': row['intime'],
        'outtime': row['outtime'],
        'icu_los_days': float(row['icu_los_days']) if pd.notna(row['icu_los_days']) else None,
        'died_during_admission': bool(died_during_admission),
        'deathtime': row['deathtime'],
        'is_first_icu_stay': bool(is_first_icu_stay),
        'icu_stay_order': int(row['icu_stay_order']),
        'gender': row['gender'],
        'anchor_age': int(row['anchor_age']) if pd.notna(row['anchor_age']) else None
    }

FINAL_FUNCTION = icustay_detail