import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def compute_sofa_score(stay_id):
    """
    Compute the SOFA (Sequential Organ Failure Assessment) score for an ICU stay.
    
    The SOFA score assesses organ dysfunction across 6 systems:
    - Respiration (PaO2/FiO2 ratio)
    - Coagulation (Platelet count)
    - Liver (Bilirubin)
    - Cardiovascular (MAP and vasopressors)
    - Brain (Glasgow Coma Scale)
    - Kidney (Creatinine)
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier
        
    Returns
    -------
    dict
        Dictionary containing:
        - 'total_score': Total SOFA score (0-24)
        - 'respiration_score': Respiration subscore (0-4)
        - 'coagulation_score': Coagulation subscore (0-4)
        - 'liver_score': Liver subscore (0-4)
        - 'cardiovascular_score': Cardiovascular subscore (0-4)
        - 'brain_score': Brain subscore (0-4)
        - 'kidney_score': Kidney subscore (0-4)
        - 'subject_id': Patient subject ID
        - 'hadm_id': Hospital admission ID
        - 'stay_id': ICU stay ID
        - 'intime': ICU admission time
        - 'outtime': ICU discharge time
        - 'details': Dictionary with detailed component values
    """
    
    # Get stay information
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        return {'error': 'Stay not found'}
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = stay_info.iloc[0]['intime']
    outtime = stay_info.iloc[0]['outtime']
    
    details = {}
    
    # ==========================================
    # 1. RESPIRATION (PaO2/FiO2 ratio)
    # ==========================================
    # Get PaO2 values within the ICU stay
    pao2_data = query_db(f"""
        SELECT charttime, valuenum as pao2
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id} AND itemid = 220224 AND valuenum IS NOT NULL
        AND charttime >= '{intime}' AND charttime <= '{outtime}'
    """)
    
    # Get FiO2 values within the ICU stay
    fio2_data = query_db(f"""
        SELECT charttime, valuenum as fio2
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id} AND itemid = 223835 AND valuenum IS NOT NULL
        AND charttime >= '{intime}' AND charttime <= '{outtime}'
    """)
    
    # Check if patient is on mechanical ventilation
    # Look for ventilator mode or invasive ventilation indicators
    vent_status = query_db(f"""
        SELECT COUNT(*) as vent_count
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
        AND itemid = 223849  -- Ventilator Mode
        AND value IS NOT NULL
        AND value != ''
    """)
    on_vent = vent_status.iloc[0]['vent_count'] > 0 if not vent_status.empty else False
    
    # Also check for PEEP set (indicates mechanical ventilation)
    peep_status = query_db(f"""
        SELECT COUNT(*) as peep_count
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
        AND itemid = 220339  -- PEEP set
        AND valuenum IS NOT NULL
    """)
    on_vent = on_vent or (peep_status.iloc[0]['peep_count'] > 0 if not peep_status.empty else False)
    
    # Calculate PaO2/FiO2 ratio by matching within 2-hour time window
    pao2_fio2_values = []
    if not pao2_data.empty and not fio2_data.empty:
        for _, pao2_row in pao2_data.iterrows():
            pao2_time = pao2_row['charttime']
            pao2_val = pao2_row['pao2']
            
            # Find FiO2 values within 2 hours of this PaO2 measurement
            matching_fio2 = fio2_data[
                (fio2_data['charttime'] >= pao2_time - timedelta(hours=2)) &
                (fio2_data['charttime'] <= pao2_time + timedelta(hours=2))
            ]
            
            if not matching_fio2.empty:
                # Use the closest FiO2 value
                time_diffs = (matching_fio2['charttime'] - pao2_time).abs()
                closest_idx = time_diffs.idxmin()
                closest_fio2 = matching_fio2.loc[closest_idx]
                fio2_fraction = closest_fio2['fio2'] / 100.0  # Convert percentage to fraction
                ratio = pao2_val / fio2_fraction
                pao2_fio2_values.append(ratio)
    
    # Use worst (minimum) PaO2/FiO2 ratio
    if pao2_fio2_values:
        worst_pao2_fio2 = min(pao2_fio2_values)
        details['pao2_fio2'] = worst_pao2_fio2
        details['on_ventilator'] = on_vent
        
        # Score respiration based on SOFA criteria
        if worst_pao2_fio2 >= 400:
            resp_score = 0
        elif worst_pao2_fio2 >= 300:
            resp_score = 1
        elif worst_pao2_fio2 >= 200:
            resp_score = 2
        elif worst_pao2_fio2 >= 100 and on_vent:
            resp_score = 3
        elif worst_pao2_fio2 < 100 and on_vent:
            resp_score = 4
        elif worst_pao2_fio2 < 200 and not on_vent:
            resp_score = 2  # Without support, <200 is score 2
        else:
            resp_score = 2  # Default for <200 without clear vent status
    else:
        resp_score = 0  # No data = assume normal
        details['pao2_fio2'] = None
        details['on_ventilator'] = on_vent
    
    # ==========================================
    # 2. COAGULATION (Platelets)
    # ==========================================
    platelet_data = query_db(f"""
        SELECT MIN(valuenum) as min_platelets
        FROM mimiciv_hosp.labevents
        WHERE hadm_id = {hadm_id}
        AND itemid = 51265
        AND valuenum IS NOT NULL
        AND charttime >= '{intime}'
        AND charttime <= '{outtime}'
    """)
    
    min_platelets = None
    if not platelet_data.empty and platelet_data.iloc[0]['min_platelets'] is not None:
        min_platelets = platelet_data.iloc[0]['min_platelets']
        if not pd.isna(min_platelets):
            details['platelets'] = min_platelets
            
            if min_platelets >= 150:
                coag_score = 0
            elif min_platelets >= 100:
                coag_score = 1
            elif min_platelets >= 50:
                coag_score = 2
            elif min_platelets >= 20:
                coag_score = 3
            else:
                coag_score = 4
        else:
            coag_score = 0
            details['platelets'] = None
    else:
        coag_score = 0
        details['platelets'] = None
    
    # ==========================================
    # 3. LIVER (Bilirubin)
    # ==========================================
    bili_data = query_db(f"""
        SELECT MAX(valuenum) as max_bilirubin
        FROM mimiciv_hosp.labevents
        WHERE hadm_id = {hadm_id}
        AND itemid = 50885
        AND valuenum IS NOT NULL
        AND charttime >= '{intime}'
        AND charttime <= '{outtime}'
    """)
    
    max_bilirubin = None
    if not bili_data.empty and bili_data.iloc[0]['max_bilirubin'] is not None:
        max_bilirubin = bili_data.iloc[0]['max_bilirubin']
        if not pd.isna(max_bilirubin):
            details['bilirubin'] = max_bilirubin
            
            if max_bilirubin < 1.2:
                liver_score = 0
            elif max_bilirubin < 2.0:
                liver_score = 1
            elif max_bilirubin < 6.0:
                liver_score = 2
            elif max_bilirubin < 12.0:
                liver_score = 3
            else:
                liver_score = 4
        else:
            liver_score = 0
            details['bilirubin'] = None
    else:
        liver_score = 0
        details['bilirubin'] = None
    
    # ==========================================
    # 4. CARDIOVASCULAR (MAP and vasopressors)
    # ==========================================
    # Get minimum MAP
    map_data = query_db(f"""
        SELECT MIN(valuenum) as min_map
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
        AND itemid = 220052
        AND valuenum IS NOT NULL
    """)
    
    min_map = None
    if not map_data.empty and map_data.iloc[0]['min_map'] is not None:
        min_map = map_data.iloc[0]['min_map']
        if not pd.isna(min_map):
            details['min_map'] = min_map
        else:
            details['min_map'] = None
    
    # Get vasopressor data
    # Dopamine (221662), Dobutamine (221653), Epinephrine (221289), Norepinephrine (221906)
    vaso_data = query_db(f"""
        SELECT 
            itemid,
            MAX(rate) as max_rate
        FROM mimiciv_icu.inputevents
        WHERE stay_id = {stay_id}
        AND itemid IN (221662, 221653, 221289, 221906)
        AND rate IS NOT NULL
        GROUP BY itemid
    """)
    
    # Create a dictionary of vasopressor max rates
    vaso_rates = {}
    for _, row in vaso_data.iterrows():
        vaso_rates[int(row['itemid'])] = float(row['max_rate'])
    
    details['vasopressors'] = vaso_rates
    
    # Score cardiovascular - check highest score conditions first
    # Item IDs: dopamine=221662, dobutamine=221653, epinephrine=221289, norepinephrine=221906
    dopamine_max = vaso_rates.get(221662, 0)
    dobutamine_max = vaso_rates.get(221653, 0)
    epi_max = vaso_rates.get(221289, 0)
    neo_max = vaso_rates.get(221906, 0)
    
    # Score 4: Dopamine > 15 OR Epinephrine > 0.1 OR Norepinephrine > 0.1
    if dopamine_max > 15 or epi_max > 0.1 or neo_max > 0.1:
        cv_score = 4
    # Score 3: Dopamine > 5 and <= 15 OR Epinephrine > 0 and <= 0.1 OR Norepinephrine > 0 and <= 0.1
    elif (dopamine_max > 5 and dopamine_max <= 15) or (epi_max > 0 and epi_max <= 0.1) or (neo_max > 0 and neo_max <= 0.1):
        cv_score = 3
    # Score 2: Dopamine <= 5 OR Dobutamine (any dose)
    elif (dopamine_max > 0 and dopamine_max <= 5) or (dobutamine_max > 0):
        cv_score = 2
    # Score 1: MAP < 70 without vasopressors
    elif min_map is not None and min_map < 70:
        cv_score = 1
    # Score 0: MAP >= 70 without vasopressors
    else:
        cv_score = 0
    
    # ==========================================
    # 5. BRAIN (GCS)
    # ==========================================
    gcs_data = query_db(f"""
        SELECT 
            (SELECT MIN(valuenum) FROM mimiciv_icu.chartevents 
             WHERE stay_id = {stay_id} AND itemid = 220739 AND valuenum IS NOT NULL) as min_eye,
            (SELECT MIN(valuenum) FROM mimiciv_icu.chartevents 
             WHERE stay_id = {stay_id} AND itemid = 223900 AND valuenum IS NOT NULL) as min_verbal,
            (SELECT MIN(valuenum) FROM mimiciv_icu.chartevents 
             WHERE stay_id = {stay_id} AND itemid = 223901 AND valuenum IS NOT NULL) as min_motor
    """)
    
    min_eye = gcs_data.iloc[0]['min_eye']
    min_verbal = gcs_data.iloc[0]['min_verbal']
    min_motor = gcs_data.iloc[0]['min_motor']
    
    details['gcs_eye'] = min_eye
    details['gcs_verbal'] = min_verbal
    details['gcs_motor'] = min_motor
    
    # Calculate worst GCS (sum of minimum components)
    if (min_eye is not None and not pd.isna(min_eye) and 
        min_verbal is not None and not pd.isna(min_verbal) and 
        min_motor is not None and not pd.isna(min_motor)):
        worst_gcs = min_eye + min_verbal + min_motor
        details['worst_gcs'] = worst_gcs
        
        if worst_gcs == 15:
            brain_score = 0
        elif worst_gcs >= 13:
            brain_score = 1
        elif worst_gcs >= 10:
            brain_score = 2
        elif worst_gcs >= 6:
            brain_score = 3
        else:
            brain_score = 4
    else:
        brain_score = 0
        details['worst_gcs'] = None
    
    # ==========================================
    # 6. KIDNEY (Creatinine)
    # ==========================================
    cr_data = query_db(f"""
        SELECT MAX(valuenum) as max_creatinine
        FROM mimiciv_hosp.labevents
        WHERE hadm_id = {hadm_id}
        AND itemid IN (50912, 51081, 52546)
        AND valuenum IS NOT NULL
        AND charttime >= '{intime}'
        AND charttime <= '{outtime}'
    """)
    
    max_creatinine = None
    if not cr_data.empty and cr_data.iloc[0]['max_creatinine'] is not None:
        max_creatinine = cr_data.iloc[0]['max_creatinine']
        if not pd.isna(max_creatinine):
            details['max_creatinine'] = max_creatinine
            
            if max_creatinine < 1.2:
                kidney_score = 0
            elif max_creatinine < 2.0:
                kidney_score = 1
            elif max_creatinine < 3.5:
                kidney_score = 2
            elif max_creatinine < 5.0:
                kidney_score = 3
            else:
                kidney_score = 4
        else:
            kidney_score = 0
            details['max_creatinine'] = None
    else:
        kidney_score = 0
        details['max_creatinine'] = None
    
    # ==========================================
    # Calculate total score
    # ==========================================
    total_score = resp_score + coag_score + liver_score + cv_score + brain_score + kidney_score
    
    return {
        'total_score': total_score,
        'respiration_score': resp_score,
        'coagulation_score': coag_score,
        'liver_score': liver_score,
        'cardiovascular_score': cv_score,
        'brain_score': brain_score,
        'kidney_score': kidney_score,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'stay_id': stay_id,
        'intime': str(intime),
        'outtime': str(outtime),
        'details': details
    }

FINAL_FUNCTION = compute_sofa_score