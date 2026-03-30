import pandas as pd

def get_liver_enzymes(stay_id):
    """
    Extract liver enzyme and bilirubin values for a patient's ICU stay.
    
    This function retrieves ALT, AST, and bilirubin laboratory values from the 
    ICU chart events during a patient's ICU stay. It provides summary statistics
    and clinical flags for liver enzyme abnormalities.
    
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
        - 'alt': dict with ALT statistics
            - 'max': Maximum ALT value in IU/L (float or None)
            - 'min': Minimum ALT value in IU/L (float or None)
            - 'mean': Mean ALT value in IU/L (float or None)
            - 'count': Number of ALT measurements (int)
            - 'elevated': Boolean indicating if any ALT > 50 IU/L
        - 'ast': dict with AST statistics
            - 'max': Maximum AST value in IU/L (float or None)
            - 'min': Minimum AST value in IU/L (float or None)
            - 'mean': Mean AST value in IU/L (float or None)
            - 'count': Number of AST measurements (int)
            - 'elevated': Boolean indicating if any AST > 50 IU/L
        - 'total_bilirubin': dict with total bilirubin statistics
            - 'max': Maximum total bilirubin value in mg/dL (float or None)
            - 'min': Minimum total bilirubin value in mg/dL (float or None)
            - 'mean': Mean total bilirubin value in mg/dL (float or None)
            - 'count': Number of total bilirubin measurements (int)
            - 'hyperbilirubinemia': Boolean indicating if any total bilirubin > 2.0 mg/dL
        - 'direct_bilirubin': dict with direct bilirubin statistics
            - 'max': Maximum direct bilirubin value in mg/dL (float or None)
            - 'min': Minimum direct bilirubin value in mg/dL (float or None)
            - 'mean': Mean direct bilirubin value in mg/dL (float or None)
            - 'count': Number of direct bilirubin measurements (int)
        - 'elevated_liver_enzymes': Boolean indicating if ALT or AST > 50 IU/L
        - 'all_values': DataFrame with all liver enzyme values during the stay
    
    Raises
    ------
    ValueError
        If stay_id is not provided or no matching ICU stay is found.
    
    Examples
    --------
    >>> get_liver_enzymes(32834587)
    {'stay_id': 32834587, 'subject_id': 10413295, 'hadm_id': 23990047,
     'alt': {'max': 344.0, 'min': 15.0, 'mean': 96.86, 'count': 105, 'elevated': True},
     'ast': {'max': 1717.0, 'min': 23.0, 'mean': 135.77, 'count': 105, 'elevated': True},
     'total_bilirubin': {'max': 7.0, 'min': 0.4, 'mean': 2.51, 'count': 105, 'hyperbilirubinemia': True},
     'elevated_liver_enzymes': True}
    
    Notes
    -----
    This function uses the following item IDs from the MIMIC-IV database:
    - AST: 220587 (unit: IU/L)
    - ALT: 220644 (unit: IU/L)
    - Direct Bilirubin: 225651 (unit: mg/dL)
    - Total Bilirubin: 225690 (unit: mg/dL)
    
    Clinical thresholds used:
    - Elevated liver enzymes: ALT or AST > 50 IU/L
    - Hyperbilirubinemia: total bilirubin > 2.0 mg/dL
    """
    
    # Get ICU stay details
    stay_info = query_db(f"""
        SELECT subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found for stay_id: {stay_id}")
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = str(stay_info.iloc[0]['intime'])
    outtime = str(stay_info.iloc[0]['outtime'])
    
    # Get liver enzyme and bilirubin values from ICU chartevents
    liver_data = query_db(f"""
        SELECT ce.charttime, ce.valuenum, di.label
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
        WHERE ce.stay_id = {stay_id}
          AND ce.itemid IN (220587, 220644, 225651, 225690)
          AND ce.valuenum IS NOT NULL
        ORDER BY ce.charttime
    """)
    
    # Initialize result dictionary with default empty values
    result = {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': intime,
        'outtime': outtime,
        'alt': {'max': None, 'min': None, 'mean': None, 'count': 0, 'elevated': False},
        'ast': {'max': None, 'min': None, 'mean': None, 'count': 0, 'elevated': False},
        'total_bilirubin': {'max': None, 'min': None, 'mean': None, 'count': 0, 'hyperbilirubinemia': False},
        'direct_bilirubin': {'max': None, 'min': None, 'mean': None, 'count': 0},
        'elevated_liver_enzymes': False,
        'all_values': liver_data
    }
    
    if not liver_data.empty:
        # Process ALT (itemid 220644)
        alt_data = liver_data[liver_data['label'] == 'ALT']
        if not alt_data.empty:
            result['alt'] = {
                'max': float(alt_data['valuenum'].max()),
                'min': float(alt_data['valuenum'].min()),
                'mean': float(alt_data['valuenum'].mean()),
                'count': int(len(alt_data)),
                'elevated': bool(alt_data['valuenum'].max() > 50)
            }
        
        # Process AST (itemid 220587)
        ast_data = liver_data[liver_data['label'] == 'AST']
        if not ast_data.empty:
            result['ast'] = {
                'max': float(ast_data['valuenum'].max()),
                'min': float(ast_data['valuenum'].min()),
                'mean': float(ast_data['valuenum'].mean()),
                'count': int(len(ast_data)),
                'elevated': bool(ast_data['valuenum'].max() > 50)
            }
        
        # Process Total Bilirubin (itemid 225690)
        bili_data = liver_data[liver_data['label'] == 'Total Bilirubin']
        if not bili_data.empty:
            result['total_bilirubin'] = {
                'max': float(bili_data['valuenum'].max()),
                'min': float(bili_data['valuenum'].min()),
                'mean': float(bili_data['valuenum'].mean()),
                'count': int(len(bili_data)),
                'hyperbilirubinemia': bool(bili_data['valuenum'].max() > 2.0)
            }
        
        # Process Direct Bilirubin (itemid 225651)
        direct_bili_data = liver_data[liver_data['label'] == 'Direct Bilirubin']
        if not direct_bili_data.empty:
            result['direct_bilirubin'] = {
                'max': float(direct_bili_data['valuenum'].max()),
                'min': float(direct_bili_data['valuenum'].min()),
                'mean': float(direct_bili_data['valuenum'].mean()),
                'count': int(len(direct_bili_data))
            }
        
        # Determine if elevated liver enzymes (ALT or AST > 50)
        if result['alt'].get('elevated') or result['ast'].get('elevated'):
            result['elevated_liver_enzymes'] = True
    
    return result

FINAL_FUNCTION = get_liver_enzymes