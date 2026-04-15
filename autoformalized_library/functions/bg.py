import pandas as pd
import numpy as np
from datetime import datetime

def get_blood_gas_info(stay_id=None, subject_id=None, hadm_id=None):
    """
    Extract blood gas information for a patient's ICU stay.
    
    This function retrieves blood gas measurements (pH, lactate, pCO2, pO2, 
    base excess, bicarbonate) from both chartevents (ICU) and labevents 
    (hospital) tables for a specified ICU stay.
    
    Parameters
    ----------
    stay_id : int, optional
        The ICU stay ID. If provided, returns data for that specific stay.
    subject_id : int, optional
        The patient's subject_id. If provided with hadm_id, returns data for 
        all ICU stays during that admission.
    hadm_id : int, optional
        The hospital admission ID. Used with subject_id to identify the admission.
    
    Returns
    -------
    dict
        A dictionary containing blood gas information:
        - 'stay_id': The ICU stay ID (or list if multiple stays)
        - 'subject_id': Patient identifier
        - 'hadm_id': Hospital admission ID
        - 'peak_lactate': Maximum lactate value (mmol/L) during the stay
        - 'min_pH': Minimum pH value during the stay
        - 'max_pH': Maximum pH value during the stay
        - 'mean_pH': Mean pH value during the stay
        - 'has_elevated_lactate': Boolean indicating if peak lactate >= 2 mmol/L
        - 'has_acidosis': Boolean indicating if any pH < 7.35
        - 'has_severe_acidosis': Boolean indicating if any pH <= 7.20
        - 'min_pco2': Minimum arterial pCO2 (mmHg)
        - 'max_pco2': Maximum arterial pCO2 (mmHg)
        - 'min_po2': Minimum arterial pO2 (mmHg)
        - 'max_po2': Maximum arterial pO2 (mmHg)
        - 'min_base_excess': Minimum arterial base excess (mEq/L)
        - 'min_bicarbonate': Minimum bicarbonate (TCO2) (mEq/L)
        - 'all_measurements': DataFrame with all blood gas measurements
    
    Raises
    ------
    ValueError
        If no valid identifier is provided.
    """
    
    # Validate input
    if stay_id is None and (subject_id is None or hadm_id is None):
        raise ValueError("Must provide stay_id OR both subject_id and hadm_id")
    
    # Build the base query to get stay information
    if stay_id is not None:
        stay_filter = f"stay_id = {stay_id}"
    else:
        stay_filter = f"subject_id = {subject_id} AND hadm_id = {hadm_id}"
    
    # Get stay information
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE {stay_filter}
    """)
    
    if stay_info.empty:
        return None
    
    # Handle multiple stays
    if len(stay_info) > 1:
        results = []
        for _, row in stay_info.iterrows():
            result = get_blood_gas_info(stay_id=row['stay_id'])
            results.append(result)
        return results
    
    stay_id = stay_info.iloc[0]['stay_id']
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = stay_info.iloc[0]['intime']
    outtime = stay_info.iloc[0]['outtime']
    
    # Define blood gas item IDs for chartevents
    chartevent_itemids = {
        'ph_arterial': 223830,
        'ph_venous': 220274,
        'lactate': 225668,
        'pco2_arterial': 220235,
        'pco2_venous': 226062,
        'po2_arterial': 220224,
        'po2_venous': 226063,
        'base_excess': 224828,
        'tc02_arterial': 225698,
        'tc02_venous': 223679
    }
    
    # Query chartevents for blood gas measurements during ICU stay
    chartevent_ids = list(chartevent_itemids.values())
    chartevent_query = f"""
        SELECT ce.charttime, di.label, ce.valuenum, ce.valueuom, di.itemid
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
        WHERE ce.stay_id = {stay_id}
        AND di.itemid IN ({','.join(map(str, chartevent_ids))})
        AND ce.valuenum IS NOT NULL
        ORDER BY ce.charttime
    """
    
    chartevents_df = query_db(chartevent_query)
    
    # Query labevents for blood gas measurements during the ICU stay period
    labevent_itemids = [50820, 50813, 52442, 53154, 50804, 51739, 50818, 50821, 50802]
    labevent_query = f"""
        SELECT le.charttime, dli.label, le.valuenum, le.valueuom, dli.itemid
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_hosp.d_labitems dli ON le.itemid = dli.itemid
        WHERE le.hadm_id = {hadm_id}
        AND dli.itemid IN ({','.join(map(str, labevent_itemids))})
        AND le.valuenum IS NOT NULL
        AND le.charttime >= '{intime}'
        AND le.charttime <= '{outtime}'
        ORDER BY le.charttime
    """
    
    labevents_df = query_db(labevent_query)
    
    # Combine and process data
    all_measurements = []
    
    # Process chartevents
    for _, row in chartevents_df.iterrows():
        measurement_type = None
        if row['itemid'] == 223830:
            measurement_type = 'ph_arterial'
        elif row['itemid'] == 220274:
            measurement_type = 'ph_venous'
        elif row['itemid'] == 225668:
            measurement_type = 'lactate'
        elif row['itemid'] == 220235:
            measurement_type = 'pco2_arterial'
        elif row['itemid'] == 226062:
            measurement_type = 'pco2_venous'
        elif row['itemid'] == 220224:
            measurement_type = 'po2_arterial'
        elif row['itemid'] == 226063:
            measurement_type = 'po2_venous'
        elif row['itemid'] == 224828:
            measurement_type = 'base_excess'
        elif row['itemid'] == 225698:
            measurement_type = 'tc02_arterial'
        elif row['itemid'] == 223679:
            measurement_type = 'tc02_venous'
        
        if measurement_type:
            all_measurements.append({
                'source': 'chartevents',
                'charttime': row['charttime'],
                'measurement_type': measurement_type,
                'value': row['valuenum'],
                'unit': row['valueuom'],
                'label': row['label']
            })
    
    # Process labevents
    for _, row in labevents_df.iterrows():
        measurement_type = None
        if row['itemid'] == 50820:
            measurement_type = 'ph_arterial'
        elif row['itemid'] in [50813, 52442, 53154]:
            measurement_type = 'lactate'
        elif row['itemid'] in [50804, 51739]:
            measurement_type = 'tc02'
        elif row['itemid'] == 50818:
            measurement_type = 'pco2'
        elif row['itemid'] == 50821:
            measurement_type = 'po2'
        elif row['itemid'] == 50802:
            measurement_type = 'base_excess'
        
        if measurement_type:
            all_measurements.append({
                'source': 'labevents',
                'charttime': row['charttime'],
                'measurement_type': measurement_type,
                'value': row['valuenum'],
                'unit': row['valueuom'],
                'label': row['label']
            })
    
    measurements_df = pd.DataFrame(all_measurements)
    
    # Calculate summary statistics
    result = {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': str(intime),
        'outtime': str(outtime),
        'all_measurements': measurements_df
    }
    
    if not measurements_df.empty:
        # pH statistics (combine arterial and venous)
        ph_data = measurements_df[measurements_df['measurement_type'].isin(['ph_arterial', 'ph_venous'])]['value']
        if len(ph_data) > 0:
            result['min_pH'] = float(ph_data.min())
            result['max_pH'] = float(ph_data.max())
            result['mean_pH'] = float(ph_data.mean())
            result['has_acidosis'] = ph_data.min() < 7.35
            result['has_severe_acidosis'] = ph_data.min() <= 7.20
        else:
            result['min_pH'] = None
            result['max_pH'] = None
            result['mean_pH'] = None
            result['has_acidosis'] = False
            result['has_severe_acidosis'] = False
        
        # Lactate statistics
        lactate_data = measurements_df[measurements_df['measurement_type'] == 'lactate']['value']
        if len(lactate_data) > 0:
            result['peak_lactate'] = float(lactate_data.max())
            result['min_lactate'] = float(lactate_data.min())
            result['mean_lactate'] = float(lactate_data.mean())
            result['has_elevated_lactate'] = lactate_data.max() >= 2.0
        else:
            result['peak_lactate'] = None
            result['min_lactate'] = None
            result['mean_lactate'] = None
            result['has_elevated_lactate'] = False
        
        # pCO2 statistics (arterial)
        pco2_data = measurements_df[measurements_df['measurement_type'] == 'pco2_arterial']['value']
        if len(pco2_data) > 0:
            result['min_pco2'] = float(pco2_data.min())
            result['max_pco2'] = float(pco2_data.max())
            result['mean_pco2'] = float(pco2_data.mean())
        else:
            result['min_pco2'] = None
            result['max_pco2'] = None
            result['mean_pco2'] = None
        
        # pO2 statistics (arterial)
        po2_data = measurements_df[measurements_df['measurement_type'] == 'po2_arterial']['value']
        if len(po2_data) > 0:
            result['min_po2'] = float(po2_data.min())
            result['max_po2'] = float(po2_data.max())
            result['mean_po2'] = float(po2_data.mean())
        else:
            result['min_po2'] = None
            result['max_po2'] = None
            result['mean_po2'] = None
        
        # Base excess statistics
        be_data = measurements_df[measurements_df['measurement_type'] == 'base_excess']['value']
        if len(be_data) > 0:
            result['min_base_excess'] = float(be_data.min())
            result['max_base_excess'] = float(be_data.max())
            result['mean_base_excess'] = float(be_data.mean())
        else:
            result['min_base_excess'] = None
            result['max_base_excess'] = None
            result['mean_base_excess'] = None
        
        # Bicarbonate/TCO2 statistics
        tc02_data = measurements_df[measurements_df['measurement_type'].isin(['tc02_arterial', 'tc02_venous', 'tc02'])]['value']
        if len(tc02_data) > 0:
            result['min_bicarbonate'] = float(tc02_data.min())
            result['max_bicarbonate'] = float(tc02_data.max())
            result['mean_bicarbonate'] = float(tc02_data.mean())
        else:
            result['min_bicarbonate'] = None
            result['max_bicarbonate'] = None
            result['mean_bicarbonate'] = None
    
    return result

FINAL_FUNCTION = get_blood_gas_info