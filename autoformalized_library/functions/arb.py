# Now let me create the final self-contained code block with all necessary components

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
    """
    # Define ACEi drug patterns
    acei_patterns = [
        '%lisinopril%',
        '%enalapril%',
        '%captopril%',
        '%benazepril%',
        '%fosinopril%',
        '%quinapril%',
        '%ramipril%',
        '%perindopril%',
        '%trandolapril%',
        '%moexipril%'
    ]
    
    # Build the WHERE clause for ACEi drugs
    acei_conditions = ' OR '.join([f"LOWER(drug) LIKE '{pattern}'" for pattern in acei_patterns])
    
    # Query prescriptions table
    prescriptions_query = f"""
    SELECT subject_id, hadm_id, drug, starttime, stoptime
    FROM mimiciv_hosp.prescriptions
    WHERE subject_id = {subject_id} AND hadm_id = {hadm_id}
    AND ({acei_conditions})
    ORDER BY starttime
    """
    prescriptions_df = query_db(prescriptions_query)
    
    # Extract unique drug names
    acei_drugs = prescriptions_df['drug'].unique().tolist() if not prescriptions_df.empty else []
    
    # Get timing information
    first_prescription_time = None
    last_prescription_time = None
    if not prescriptions_df.empty:
        first_prescription_time = prescriptions_df['starttime'].min()
        last_prescription_time = prescriptions_df['stoptime'].max()
    
    # Build result dictionary
    result = {
        'received_acei': len(acei_drugs) > 0,
        'acei_drugs': acei_drugs,
        'num_unique_drugs': len(acei_drugs),
        'total_prescriptions': len(prescriptions_df),
        'first_prescription_time': first_prescription_time,
        'last_prescription_time': last_prescription_time,
        'prescriptions_df': prescriptions_df
    }
    
    return result


def get_arb_info(subject_id, hadm_id):
    """
    Extract Angiotensin Receptor Blocker (ARB) medication information for a patient during a hospital admission.

    This function queries the prescriptions and emar tables to identify ARB medications
    prescribed to or administered to a patient during their hospital admission. ARBs are commonly
    used for heart failure, hypertension, and other cardiovascular conditions.

    ARBs work by blocking the binding of angiotensin II to the AT1 receptor, resulting in
    vasodilation and reduced aldosterone secretion.

    This function can help answer clinical questions such as:
    - Did this patient receive an ARB during their hospital admission?
    - Was this patient prescribed an ARB, suggesting a history of hypertension or heart failure?
    - Did this patient receive RAAS blockade (ACEi or ARB) during their hospital admission?

    Parameters:
    -----------
    subject_id : int
        The unique patient identifier in the MIMIC-IV database.
    hadm_id : int
        The hospital admission identifier.

    Returns:
    --------
    dict : A dictionary containing the following keys:
        - 'received_arb' (bool): Whether the patient received any ARB during admission
        - 'arb_drugs' (list): List of unique ARB drug names received
        - 'num_unique_drugs' (int): Number of unique ARB drugs
        - 'total_prescriptions' (int): Total number of ARB prescription records
        - 'total_administrations' (int): Total number of ARB administrations (from EMAR)
        - 'first_prescription_time' (datetime or None): Timestamp of first ARB prescription
        - 'last_prescription_time' (datetime or None): Timestamp of last ARB prescription
        - 'first_administration_time' (datetime or None): Timestamp of first ARB administration
        - 'last_administration_time' (datetime or None): Timestamp of last ARB administration
        - 'prescriptions_df' (DataFrame): Full prescription details for ARBs
        - 'administrations_df' (DataFrame): Full administration details from EMAR
        - 'received_acei' (bool): Whether the patient received any ACE inhibitor (for RAAS blockade assessment)
        - 'acei_drugs' (list): List of ACE inhibitor drugs (for RAAS blockade assessment)
        - 'received_raas_blockade' (bool): Whether patient received any RAAS blockade (ACEi or ARB)

    Notes:
    ------
    ARBs identified include: losartan, valsartan, candesartan, irbesartan,
    olmesartan, telmisartan, eprosartan, and azilsartan.
    Combined formulations (e.g., ARB-HCTZ) are also included.
    Sacubitril/valsartan (ARNI) is included as it contains valsartan.

    Examples:
    ---------
    >>> result = get_arb_info(10484877, 24516728)
    >>> result['received_arb']
    True
    >>> result['arb_drugs']
    ['Losartan Potassium']
    >>> result['received_raas_blockade']
    True
    """
    # Define ARB drug patterns
    arb_patterns = [
        '%losartan%',
        '%valsartan%',
        '%candesartan%',
        '%irbesartan%',
        '%olmesartan%',
        '%telmisartan%',
        '%eprosartan%',
        '%azilsartan%'
    ]
    
    # Build the WHERE clause for ARB drugs
    arb_conditions = ' OR '.join([f"LOWER(drug) LIKE '{pattern}'" for pattern in arb_patterns])
    
    # Query prescriptions table
    prescriptions_query = f"""
    SELECT subject_id, hadm_id, drug, starttime, stoptime
    FROM mimiciv_hosp.prescriptions
    WHERE subject_id = {subject_id} AND hadm_id = {hadm_id}
    AND ({arb_conditions})
    ORDER BY starttime
    """
    prescriptions_df = query_db(prescriptions_query)
    
    # Query EMAR table for actual administrations
    emar_conditions = ' OR '.join([f"LOWER(medication) LIKE '{pattern}'" for pattern in arb_patterns])
    emar_query = f"""
    SELECT subject_id, hadm_id, medication, charttime
    FROM mimiciv_hosp.emar
    WHERE subject_id = {subject_id} AND hadm_id = {hadm_id}
    AND ({emar_conditions})
    ORDER BY charttime
    """
    emar_df = query_db(emar_query)
    
    # Extract unique drug names
    arb_drugs = prescriptions_df['drug'].unique().tolist() if not prescriptions_df.empty else []
    
    # Get timing information for prescriptions
    first_prescription_time = None
    last_prescription_time = None
    if not prescriptions_df.empty:
        first_prescription_time = prescriptions_df['starttime'].min()
        last_prescription_time = prescriptions_df['stoptime'].max()
    
    # Get timing information for administrations
    first_administration_time = None
    last_administration_time = None
    if not emar_df.empty:
        first_administration_time = emar_df['charttime'].min()
        last_administration_time = emar_df['charttime'].max()
    
    # Get ACEi information for RAAS blockade assessment
    acei_result = get_acei_info(subject_id, hadm_id)
    
    # Build result dictionary
    result = {
        'received_arb': len(arb_drugs) > 0 or len(emar_df) > 0,
        'arb_drugs': arb_drugs,
        'num_unique_drugs': len(arb_drugs),
        'total_prescriptions': len(prescriptions_df),
        'total_administrations': len(emar_df),
        'first_prescription_time': first_prescription_time,
        'last_prescription_time': last_prescription_time,
        'first_administration_time': first_administration_time,
        'last_administration_time': last_administration_time,
        'prescriptions_df': prescriptions_df,
        'administrations_df': emar_df,
        # RAAS blockade information
        'received_acei': acei_result['received_acei'],
        'acei_drugs': acei_result['acei_drugs'],
        'received_raas_blockade': acei_result['received_acei'] or (len(arb_drugs) > 0 or len(emar_df) > 0)
    }
    
    return result


FINAL_FUNCTION = get_arb_info