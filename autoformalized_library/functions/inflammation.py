import pandas as pd

def inflammation(stay_id=None, subject_id=None, hadm_id=None):
    """
    Extract inflammation-related information for a patient's ICU stay.
    
    This function retrieves C-reactive protein (CRP) measurements during an ICU stay
    and provides summary statistics and clinical flags for inflammation assessment.
    
    CRP is a key marker of inflammation. Elevated CRP levels indicate:
    - Infection (bacterial infections typically cause higher elevations)
    - Inflammatory conditions (autoimmune diseases, tissue injury)
    - Post-surgical inflammation
    
    Clinical thresholds:
    - Normal: < 10 mg/L
    - Mildly elevated: 10-50 mg/L
    - Moderately elevated: 50-100 mg/L
    - Markedly elevated: > 100 mg/L
    
    Parameters
    ----------
    stay_id : int, optional
        The ICU stay identifier. If provided, data is filtered to this specific stay.
    subject_id : int, optional
        The patient identifier. Can be used alone or with hadm_id.
    hadm_id : int, optional
        The hospital admission identifier. Used with subject_id if stay_id not provided.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'subject_id': patient identifier (int or None)
        - 'hadm_id': hospital admission identifier (int or None)
        - 'stay_id': ICU stay identifier (int or None)
        - 'crp': dict with CRP statistics (mg/L)
            - 'values': list of all CRP values
            - 'max': Maximum CRP value (float or None)
            - 'min': Minimum CRP value (float or None)
            - 'mean': Mean CRP value (float or None)
            - 'count': Number of CRP measurements (int)
            - 'has_elevated_crp': Boolean indicating if CRP > 10 mg/L at any point
            - 'has_markedly_elevated_crp': Boolean indicating if CRP > 100 mg/L at any point
        - 'all_values': DataFrame with all CRP values during the stay
    
    Raises
    ------
    ValueError
        If no patient identifier is provided.
    
    Examples
    --------
    >>> inflammation(stay_id=32824762)
    {'subject_id': 10003637, 'hadm_id': 28317408, 'stay_id': 32824762,
     'crp': {'values': [74.1, 66.9], 'max': 74.1, 'min': 66.9, 'mean': 70.5,
             'count': 2, 'has_elevated_crp': True, 'has_markedly_elevated_crp': False},
     'all_values': DataFrame...}
    
    Notes
    -----
    This function uses itemid 227444 (C Reactive Protein) from the MIMIC-IV chartevents table.
    CRP values are in mg/L units.
    
    Clinical interpretation:
    - CRP > 10 mg/L: Elevated, suggests inflammation or infection
    - CRP > 100 mg/L: Markedly elevated, often indicates severe bacterial infection
    """
    
    if stay_id is None and subject_id is None and hadm_id is None:
        raise ValueError("At least one identifier (stay_id, subject_id, or hadm_id) must be provided.")
    
    # Build the WHERE clause based on provided identifiers
    where_clauses = []
    
    if stay_id is not None:
        where_clauses.append(f"ce.stay_id = {stay_id}")
    if subject_id is not None:
        where_clauses.append(f"ce.subject_id = {subject_id}")
    if hadm_id is not None:
        where_clauses.append(f"ce.hadm_id = {hadm_id}")
    
    # Query CRP data from chartevents
    # itemid 227444 is C Reactive Protein (CRP) in mg/L
    sql = f"""
    SELECT ce.subject_id, ce.hadm_id, ce.stay_id, ce.charttime, ce.valuenum as crp_value
    FROM mimiciv_icu.chartevents ce
    WHERE ce.itemid = 227444
      AND ce.valuenum IS NOT NULL
      AND {' AND '.join(where_clauses)}
    ORDER BY ce.charttime
    """
    
    df = query_db(sql)
    
    # Extract identifiers from query results (or use provided values if no data)
    if not df.empty:
        result_ids = {
            'subject_id': int(df['subject_id'].iloc[0]),
            'hadm_id': int(df['hadm_id'].iloc[0]),
            'stay_id': int(df['stay_id'].iloc[0])
        }
    else:
        # No data found - use provided identifiers
        result_ids = {
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'stay_id': stay_id
        }
    
    # If no data found, return empty result
    if df.empty:
        return {
            'subject_id': result_ids['subject_id'],
            'hadm_id': result_ids['hadm_id'],
            'stay_id': result_ids['stay_id'],
            'crp': {
                'values': [],
                'max': None,
                'min': None,
                'mean': None,
                'count': 0,
                'has_elevated_crp': False,
                'has_markedly_elevated_crp': False
            },
            'all_values': pd.DataFrame()
        }
    
    # Extract CRP values
    crp_values = df['crp_value'].tolist()
    
    # Calculate statistics
    crp_max = max(crp_values)
    crp_min = min(crp_values)
    crp_mean = sum(crp_values) / len(crp_values)
    
    # Clinical flags
    has_elevated_crp = any(v > 10 for v in crp_values)
    has_markedly_elevated_crp = any(v > 100 for v in crp_values)
    
    return {
        'subject_id': result_ids['subject_id'],
        'hadm_id': result_ids['hadm_id'],
        'stay_id': result_ids['stay_id'],
        'crp': {
            'values': crp_values,
            'max': crp_max,
            'min': crp_min,
            'mean': crp_mean,
            'count': len(crp_values),
            'has_elevated_crp': has_elevated_crp,
            'has_markedly_elevated_crp': has_markedly_elevated_crp
        },
        'all_values': df
    }

FINAL_FUNCTION = inflammation