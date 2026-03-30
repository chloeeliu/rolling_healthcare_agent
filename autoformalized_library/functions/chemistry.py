import pandas as pd

def get_chemistry(stay_id):
    """
    Extract chemistry lab values for a patient's ICU stay.
    
    This function retrieves key chemistry laboratory values (creatinine and sodium)
    from the ICU chart events during a patient's ICU stay. It provides summary
    statistics and clinical flags for common chemistry abnormalities.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'stay_id': The ICU stay ID (int)
        - 'subject_id': The patient's subject_id (int)
        - 'hadm_id': The hospital admission ID (int)
        - 'intime': ICU admission time (str)
        - 'outtime': ICU discharge time (str)
        - 'creatinine': dict with creatinine statistics
            - 'max': Maximum creatinine value in mg/dL (float or None)
            - 'min': Minimum creatinine value in mg/dL (float or None)
            - 'mean': Mean creatinine value in mg/dL (float or None)
            - 'count': Number of creatinine measurements (int)
            - 'peak_ge_2_0': Boolean indicating if peak creatinine >= 2.0 mg/dL
        - 'sodium': dict with sodium statistics
            - 'max': Maximum sodium value in mEq/L (float or None)
            - 'min': Minimum sodium value in mEq/L (float or None)
            - 'mean': Mean sodium value in mEq/L (float or None)
            - 'count': Number of sodium measurements (int)
            - 'hyponatremia': Boolean indicating if any sodium < 135 mEq/L
            - 'hypernatremia': Boolean indicating if any sodium > 145 mEq/L
        - 'all_values': DataFrame with all chemistry values during the stay
            Columns: charttime, valuenum, label, parameter, unit
    
    Raises
    ------
    ValueError
        If stay_id is not provided or no matching ICU stay is found.
    
    Examples
    --------
    >>> get_chemistry(32359580)
    {'stay_id': 32359580, 'subject_id': 10007818, 'hadm_id': 22987108, 
     'creatinine': {'max': 4.5, 'min': 1.5, 'mean': 2.41, 'count': 41, 'peak_ge_2_0': True},
     'sodium': {'max': 141.0, 'min': 131.0, 'mean': 136.19, 'count': 48, 
                'hyponatremia': True, 'hypernatremia': False}}
    
    Notes
    -----
    This function uses the following item IDs from the MIMIC-IV database:
    - Creatinine (serum): 220615
    - Creatinine (whole blood): 229761
    - Sodium (serum): 220645
    - Sodium (whole blood): 226534
    - Sodium (serum) (soft): 228389
    - Sodium (whole blood) (soft): 228390
    
    Clinical thresholds used:
    - Hyponatremia: sodium < 135 mEq/L
    - Hypernatremia: sodium > 145 mEq/L
    - Elevated creatinine: peak >= 2.0 mg/dL
    """
    
    # Get ICU stay information
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    stay_row = stay_info.iloc[0]
    subject_id = stay_row['subject_id']
    hadm_id = stay_row['hadm_id']
    intime = stay_row['intime']
    outtime = stay_row['outtime']
    
    # Get creatinine values (serum and whole blood)
    # itemid 220615 = Creatinine (serum), 229761 = Creatinine (whole blood)
    creatinine_df = query_db(f"""
        SELECT ce.charttime, ce.valuenum, di.label
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
        WHERE ce.stay_id = {stay_id}
          AND ce.itemid IN (220615, 229761)
          AND ce.valuenum IS NOT NULL
          AND ce.charttime >= '{intime}'
          AND ce.charttime <= '{outtime}'
        ORDER BY ce.charttime
    """)
    
    # Get sodium values (serum and whole blood)
    # itemid 220645 = Sodium (serum), 226534 = Sodium (whole blood)
    # itemid 228389 = Sodium (serum) (soft), 228390 = Sodium (whole blood) (soft)
    sodium_df = query_db(f"""
        SELECT ce.charttime, ce.valuenum, di.label
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
        WHERE ce.stay_id = {stay_id}
          AND ce.itemid IN (220645, 226534, 228389, 228390)
          AND ce.valuenum IS NOT NULL
          AND ce.charttime >= '{intime}'
          AND ce.charttime <= '{outtime}'
        ORDER BY ce.charttime
    """)
    
    # Calculate creatinine statistics
    if len(creatinine_df) > 0:
        creatinine_stats = {
            'max': float(creatinine_df['valuenum'].max()),
            'min': float(creatinine_df['valuenum'].min()),
            'mean': float(creatinine_df['valuenum'].mean()),
            'count': int(len(creatinine_df)),
            'peak_ge_2_0': bool(creatinine_df['valuenum'].max() >= 2.0)
        }
    else:
        creatinine_stats = {
            'max': None,
            'min': None,
            'mean': None,
            'count': 0,
            'peak_ge_2_0': False
        }
    
    # Calculate sodium statistics
    if len(sodium_df) > 0:
        sodium_stats = {
            'max': float(sodium_df['valuenum'].max()),
            'min': float(sodium_df['valuenum'].min()),
            'mean': float(sodium_df['valuenum'].mean()),
            'count': int(len(sodium_df)),
            'hyponatremia': bool(sodium_df['valuenum'].min() < 135),
            'hypernatremia': bool(sodium_df['valuenum'].max() > 145)
        }
    else:
        sodium_stats = {
            'max': None,
            'min': None,
            'mean': None,
            'count': 0,
            'hyponatremia': False,
            'hypernatremia': False
        }
    
    # Combine all values into a single DataFrame
    if len(creatinine_df) > 0 or len(sodium_df) > 0:
        creatinine_df['parameter'] = 'creatinine'
        creatinine_df['unit'] = 'mg/dL'
        sodium_df['parameter'] = 'sodium'
        sodium_df['unit'] = 'mEq/L'
        
        all_values = pd.concat([
            creatinine_df[['charttime', 'valuenum', 'label', 'parameter', 'unit']],
            sodium_df[['charttime', 'valuenum', 'label', 'parameter', 'unit']]
        ], ignore_index=True).sort_values('charttime')
    else:
        all_values = pd.DataFrame(columns=['charttime', 'valuenum', 'label', 'parameter', 'unit'])
    
    return {
        'stay_id': int(stay_id),
        'subject_id': int(subject_id),
        'hadm_id': int(hadm_id),
        'intime': str(intime),
        'outtime': str(outtime),
        'creatinine': creatinine_stats,
        'sodium': sodium_stats,
        'all_values': all_values
    }

FINAL_FUNCTION = get_chemistry