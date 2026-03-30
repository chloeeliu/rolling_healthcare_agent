import pandas as pd

def get_acei_info(subject_id, hadm_id):
    """
    Extract ACE inhibitor (ACEI) medication information for a patient during a hospital admission.
    
    This function queries the prescriptions table to identify ACE inhibitor medications
    prescribed to a patient during their hospital admission. ACE inhibitors are commonly
    used for heart failure, hypertension, and other cardiovascular conditions.
    
    Parameters:
    -----------
    subject_id : int
        The unique patient identifier in the MIMIC-IV database.
    hadm_id : int
        The hospital admission identifier.
    
    Returns:
    --------
    dict : A dictionary containing the following keys:
        - 'received_acei' (bool): Whether the patient received any ACE inhibitor during admission
        - 'acei_drugs' (list): List of unique ACE inhibitor drug names received
        - 'num_unique_drugs' (int): Number of unique ACE inhibitor drugs
        - 'total_prescriptions' (int): Total number of ACE inhibitor prescription records
        - 'first_prescription_time' (datetime or None): Timestamp of first ACEI prescription
        - 'last_prescription_time' (datetime or None): Timestamp of last ACEI prescription
        - 'prescriptions_df' (DataFrame): Full prescription details for ACE inhibitors
    
    Notes:
    ------
    ACE inhibitors identified include: lisinopril, enalapril, captopril, benazepril,
    fosinopril, quinapril, ramipril, perindopril, trandolapril, and moexipril.
    
    Examples:
    ---------
    >>> result = get_acei_info(10246275, 24385579)
    >>> result['received_acei']
    True
    >>> result['acei_drugs']
    ['Lisinopril']
    >>> result['num_unique_drugs']
    1
    """
    
    # Define ACE inhibitor drug patterns
    acei_patterns = [
        'lisinopril', 'enalapril', 'captopril', 'benazepril', 
        'fosinopril', 'quinapril', 'ramipril', 'perindopril', 
        'trandolapril', 'moexipril'
    ]
    
    # Build the WHERE clause for ACE inhibitor drugs
    conditions = ' OR '.join([f"LOWER(drug) LIKE '%{pattern}%'" for pattern in acei_patterns])
    
    # Query the prescriptions table
    sql = f"""
    SELECT subject_id, hadm_id, drug, starttime, stoptime
    FROM mimiciv_hosp.prescriptions 
    WHERE subject_id = {subject_id} 
      AND hadm_id = {hadm_id}
      AND drug IS NOT NULL 
      AND ({conditions})
    ORDER BY starttime
    """
    
    df = query_db(sql)
    
    # Process results
    result = {
        'received_acei': len(df) > 0,
        'acei_drugs': [],
        'num_unique_drugs': 0,
        'total_prescriptions': 0,
        'first_prescription_time': None,
        'last_prescription_time': None,
        'prescriptions_df': df
    }
    
    if len(df) > 0:
        result['acei_drugs'] = df['drug'].unique().tolist()
        result['num_unique_drugs'] = len(result['acei_drugs'])
        result['total_prescriptions'] = len(df)
        result['first_prescription_time'] = df['starttime'].min()
        result['last_prescription_time'] = df['stoptime'].max()
    
    return result

FINAL_FUNCTION = get_acei_info