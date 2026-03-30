import pandas as pd
from typing import Optional, Dict, Any

def ventilation_info(stay_id: Optional[int] = None, 
                     subject_id: Optional[int] = None,
                     hadm_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Extract ventilation-related clinical information for a patient during their ICU stay.
    
    This function identifies whether a patient received:
    - Invasive mechanical ventilation (IMV) via endotracheal tube or tracheostomy
    - Non-invasive mechanical ventilation (NIV) via BiPAP, CPAP, or other non-invasive methods
    - High-flow nasal cannula (HFNC) oxygen therapy
    
    Parameters
    ----------
    stay_id : int, optional
        The ICU stay ID. If provided, this is the primary identifier.
    subject_id : int, optional
        The patient subject ID. Can be used with hadm_id to identify a stay.
    hadm_id : int, optional
        The hospital admission ID. Used with subject_id to identify a stay.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'invasive_mechanical_ventilation': bool - True if patient received IMV
        - 'non_invasive_mechanical_ventilation': bool - True if patient received NIV
        - 'high_flow_nasal_cannula': bool - True if patient received HFNC
        - 'any_mechanical_ventilation': bool - True if patient received any form of MV
        - 'ventilation_details': dict - Additional details about ventilation types used
        - 'oxygen_delivery_devices': list - List of all oxygen delivery devices used
        - 'stay_id': int - The ICU stay ID used for the query
        - 'subject_id': int - The patient subject ID
        - 'hadm_id': int - The hospital admission ID
    
    Notes
    -----
    The function uses the following data sources from MIMIC-IV:
    - O2 Delivery Device(s) (itemid 226732) - primary source for oxygen delivery method
    - Ventilator Type (itemid 223848) - confirms invasive ventilation
    - Ventilator Mode (itemid 223849) - confirms invasive ventilation
    - BiPap Mode (itemid 227577) - confirms non-invasive ventilation
    - BiPap Mask (itemid 227578) - confirms non-invasive ventilation
    - NIV Mask (itemid 225949) - confirms non-invasive ventilation
    - Autoset/CPAP (itemid 227583) - confirms non-invasive ventilation
    
    Invasive mechanical ventilation is identified by:
    - Endotracheal tube or Tracheostomy tube in O2 Delivery Device(s)
    
    Non-invasive mechanical ventilation is identified by:
    - Bipap mask or CPAP mask in O2 Delivery Device(s)
    - Any BiPap Mode (not "Not applicable")
    - Any BiPap Mask (not "Not applicable")
    - Any NIV Mask (not "Not applicable")
    - Any Autoset/CPAP recorded
    
    High-flow nasal cannula is identified by:
    - "High flow nasal cannula" in O2 Delivery Device(s)
    """
    
    # Build the WHERE clause based on provided identifiers
    if stay_id is not None:
        where_clause = f"stay_id = {stay_id}"
    elif subject_id is not None and hadm_id is not None:
        # Need to find the stay_id for this subject_id and hadm_id
        stay_query = query_db(f"""
            SELECT stay_id 
            FROM mimiciv_icu.icustays 
            WHERE subject_id = {subject_id} AND hadm_id = {hadm_id}
            LIMIT 1
        """)
        if stay_query.empty:
            return {
                'invasive_mechanical_ventilation': False,
                'non_invasive_mechanical_ventilation': False,
                'high_flow_nasal_cannula': False,
                'any_mechanical_ventilation': False,
                'ventilation_details': {},
                'oxygen_delivery_devices': [],
                'stay_id': None,
                'subject_id': subject_id,
                'hadm_id': hadm_id,
                'error': 'No ICU stay found for this patient/admission'
            }
        stay_id = stay_query.iloc[0]['stay_id']
        where_clause = f"stay_id = {stay_id}"
    else:
        raise ValueError("Must provide either stay_id or both subject_id and hadm_id")
    
    # Get patient identifiers
    patient_info = query_db(f"""
        SELECT subject_id, hadm_id, stay_id
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if patient_info.empty:
        return {
            'invasive_mechanical_ventilation': False,
            'non_invasive_mechanical_ventilation': False,
            'high_flow_nasal_cannula': False,
            'any_mechanical_ventilation': False,
            'ventilation_details': {},
            'oxygen_delivery_devices': [],
            'stay_id': stay_id,
            'subject_id': None,
            'hadm_id': None,
            'error': 'Stay ID not found'
        }
    
    subject_id = patient_info.iloc[0]['subject_id']
    hadm_id = patient_info.iloc[0]['hadm_id']
    
    # Query for O2 Delivery Device(s) - itemid 226732
    o2_devices = query_db(f"""
        SELECT DISTINCT value
        FROM mimiciv_icu.chartevents
        WHERE itemid = 226732 AND {where_clause}
        AND value IS NOT NULL AND value != 'None'
    """)
    
    o2_device_list = o2_devices['value'].tolist() if not o2_devices.empty else []
    
    # Query for Ventilator Type - itemid 223848
    ventilator_type = query_db(f"""
        SELECT DISTINCT value
        FROM mimiciv_icu.chartevents
        WHERE itemid = 223848 AND {where_clause}
        AND value IS NOT NULL
    """)
    
    # Query for Ventilator Mode - itemid 223849
    ventilator_mode = query_db(f"""
        SELECT DISTINCT value
        FROM mimiciv_icu.chartevents
        WHERE itemid = 223849 AND {where_clause}
        AND value IS NOT NULL
    """)
    
    # Query for BiPap Mode - itemid 227577
    bipap_mode = query_db(f"""
        SELECT DISTINCT value
        FROM mimiciv_icu.chartevents
        WHERE itemid = 227577 AND {where_clause}
        AND value IS NOT NULL AND value != 'Not applicable'
    """)
    
    # Query for BiPap Mask - itemid 227578
    bipap_mask = query_db(f"""
        SELECT DISTINCT value
        FROM mimiciv_icu.chartevents
        WHERE itemid = 227578 AND {where_clause}
        AND value IS NOT NULL AND value != 'Not applicable'
    """)
    
    # Query for NIV Mask - itemid 225949
    niv_mask = query_db(f"""
        SELECT DISTINCT value
        FROM mimiciv_icu.chartevents
        WHERE itemid = 225949 AND {where_clause}
        AND value IS NOT NULL AND value != 'Not applicable'
    """)
    
    # Query for Autoset/CPAP - itemid 227583
    autoset_cpap = query_db(f"""
        SELECT DISTINCT value
        FROM mimiciv_icu.chartevents
        WHERE itemid = 227583 AND {where_clause}
        AND value IS NOT NULL
    """)
    
    # Determine invasive mechanical ventilation
    # Invasive: Endotracheal tube or Tracheostomy tube in O2 Delivery Device(s)
    # This is the PRIMARY indicator - ventilator type/mode alone is not sufficient
    invasive_devices = ['Endotracheal tube', 'Tracheostomy tube']
    has_invasive_o2 = any(dev.strip() in invasive_devices for dev in o2_device_list)
    
    invasive_mechanical_ventilation = has_invasive_o2
    
    # Determine non-invasive mechanical ventilation
    # Non-invasive: Bipap mask, CPAP mask, or any BiPap/NIV/CPAP settings
    niv_devices = ['Bipap mask', 'CPAP mask']
    has_niv_o2 = any(dev.strip() in niv_devices for dev in o2_device_list)
    has_bipap_mode = not bipap_mode.empty
    has_bipap_mask = not bipap_mask.empty
    has_niv_mask = not niv_mask.empty
    has_autoset_cpap = not autoset_cpap.empty
    
    non_invasive_mechanical_ventilation = (has_niv_o2 or has_bipap_mode or 
                                           has_bipap_mask or has_niv_mask or 
                                           has_autoset_cpap)
    
    # Determine high-flow nasal cannula
    hfnc_devices = ['High flow nasal cannula']
    has_hfnc = any(dev.strip() in hfnc_devices for dev in o2_device_list)
    
    # Any mechanical ventilation
    any_mechanical_ventilation = invasive_mechanical_ventilation or non_invasive_mechanical_ventilation
    
    # Build ventilation details
    ventilation_details = {
        'oxygen_delivery_devices_used': o2_device_list,
        'ventilator_types': ventilator_type['value'].tolist() if not ventilator_type.empty else [],
        'ventilator_modes': ventilator_mode['value'].tolist() if not ventilator_mode.empty else [],
        'bipap_modes': bipap_mode['value'].tolist() if not bipap_mode.empty else [],
        'bipap_masks': bipap_mask['value'].tolist() if not bipap_mask.empty else [],
        'niv_masks': niv_mask['value'].tolist() if not niv_mask.empty else [],
        'autoset_cpap': autoset_cpap['value'].tolist() if not autoset_cpap.empty else []
    }
    
    return {
        'invasive_mechanical_ventilation': invasive_mechanical_ventilation,
        'non_invasive_mechanical_ventilation': non_invasive_mechanical_ventilation,
        'high_flow_nasal_cannula': has_hfnc,
        'any_mechanical_ventilation': any_mechanical_ventilation,
        'ventilation_details': ventilation_details,
        'oxygen_delivery_devices': o2_device_list,
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id
    }

FINAL_FUNCTION = ventilation_info