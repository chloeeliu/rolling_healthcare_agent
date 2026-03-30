import pandas as pd

def get_coagulation(stay_id):
    """
    Extract coagulation lab values (INR and PTT) for a patient's ICU stay.

    This function retrieves International Normalized Ratio (INR) and Partial
    Thromboplastin Time (PTT) values from the ICU chart events during a patient's
    ICU stay. It provides summary statistics and clinical flags for common
    coagulation abnormalities.

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
        - 'inr': dict with INR statistics
            - 'max': Maximum INR value (float or None)
            - 'min': Minimum INR value (float or None)
            - 'mean': Mean INR value (float or None)
            - 'count': Number of INR measurements (int)
            - 'elevated': Boolean indicating if any INR > 1.5
        - 'ptt': dict with PTT statistics
            - 'max': Maximum PTT value in seconds (float or None)
            - 'min': Minimum PTT value in seconds (float or None)
            - 'mean': Mean PTT value in seconds (float or None)
            - 'count': Number of PTT measurements (int)
            - 'elevated': Boolean indicating if any PTT > 60 seconds
        - 'all_values': DataFrame with all coagulation values during the stay
            Columns: charttime, valuenum, label, parameter, unit

    Raises
    ------
    ValueError
        If stay_id is not provided or no matching ICU stay is found.

    Examples
    --------
    >>> get_coagulation(37510196)
    {'stay_id': 37510196, 'subject_id': 10007818, 'hadm_id': 22987108,
     'inr': {'max': 1.5, 'min': 1.0, 'mean': 1.26, 'count': 15, 'elevated': False},
     'ptt': {'max': 150.0, 'min': 21.3, 'mean': 58.06, 'count': 34, 'elevated': True}}

    Notes
    -----
    This function uses the following item IDs from the MIMIC-IV database:
    - INR: 220561 (ZINR), 227467 (INR)
    - PTT: 220562 (ZPTT), 227466 (PTT)
    - Prothrombin time: 220560 (ZProthrombin time), 227465 (Prothrombin time)

    Clinical thresholds used:
    - Elevated INR: > 1.5
    - Elevated PTT: > 60 seconds
    """
    
    if stay_id is None:
        raise ValueError("stay_id must be provided")
    
    # Get stay details
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    stay_info = stay_info.iloc[0]
    
    # Get INR and PTT values
    coag_data = query_db(f"""
        SELECT 
            ce.itemid,
            di.label,
            ce.valuenum,
            ce.charttime
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
        WHERE ce.stay_id = {stay_id}
        AND ce.itemid IN (220561, 227467, 220562, 227466, 220560, 227465)
        ORDER BY ce.charttime
    """)
    
    # Separate INR and PTT data
    inr_item_ids = [220561, 227467]
    ptt_item_ids = [220562, 227466]
    
    inr_data = coag_data[coag_data['itemid'].isin(inr_item_ids)]
    ptt_data = coag_data[coag_data['itemid'].isin(ptt_item_ids)]
    
    # Calculate INR statistics
    if not inr_data.empty:
        inr_stats = {
            'max': float(inr_data['valuenum'].max()),
            'min': float(inr_data['valuenum'].min()),
            'mean': float(inr_data['valuenum'].mean()),
            'count': len(inr_data),
            'elevated': bool(inr_data['valuenum'].max() > 1.5)
        }
    else:
        inr_stats = {
            'max': None,
            'min': None,
            'mean': None,
            'count': 0,
            'elevated': False
        }
    
    # Calculate PTT statistics
    if not ptt_data.empty:
        ptt_stats = {
            'max': float(ptt_data['valuenum'].max()),
            'min': float(ptt_data['valuenum'].min()),
            'mean': float(ptt_data['valuenum'].mean()),
            'count': len(ptt_data),
            'elevated': bool(ptt_data['valuenum'].max() > 60)
        }
    else:
        ptt_stats = {
            'max': None,
            'min': None,
            'mean': None,
            'count': 0,
            'elevated': False
        }
    
    # Prepare all_values DataFrame
    all_values = coag_data.copy()
    
    def get_parameter(label):
        if label in ['INR', 'ZINR']:
            return 'INR'
        elif label in ['PTT', 'ZPTT']:
            return 'PTT'
        else:
            return 'Prothrombin time'
    
    def get_unit(parameter):
        if parameter == 'INR':
            return 'ratio'
        else:
            return 'seconds'
    
    all_values['parameter'] = all_values['label'].apply(get_parameter)
    all_values['unit'] = all_values['parameter'].apply(get_unit)
    
    return {
        'stay_id': int(stay_info['stay_id']),
        'subject_id': int(stay_info['subject_id']),
        'hadm_id': int(stay_info['hadm_id']),
        'intime': str(stay_info['intime']),
        'outtime': str(stay_info['outtime']),
        'inr': inr_stats,
        'ptt': ptt_stats,
        'all_values': all_values[['charttime', 'valuenum', 'label', 'parameter', 'unit']]
    }

FINAL_FUNCTION = get_coagulation