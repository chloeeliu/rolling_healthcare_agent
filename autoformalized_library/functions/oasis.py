import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def calculate_oasis_score(stay_id):
    """
    Calculate the OASIS (Oxford Acute Severity of Illness Score) for a patient's ICU stay.
    
    The OASIS score is a parsimonious ICU severity-of-illness scoring system that uses
    10 routinely collected variables available in the first 24 hours of ICU admission
    to predict in-hospital mortality.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'stay_id': The ICU stay identifier
        - 'subject_id': The patient identifier
        - 'hadm_id': The hospital admission identifier
        - 'oasis_score': Total OASIS score (0-47)
        - 'components': Dictionary with individual component scores
        - 'on_mechanical_ventilation': Boolean indicating if patient was on MV in first 24h
        - 'predicted_mortality': Predicted in-hospital mortality probability
    """
    
    # Get ICU stay information
    stay_info = query_db(f"""
        SELECT i.stay_id, i.subject_id, i.hadm_id, i.intime,
               a.admittime, a.admission_type, p.anchor_age
        FROM mimiciv_icu.icustays i
        JOIN mimiciv_hosp.admissions a ON i.hadm_id = a.hadm_id
        JOIN mimiciv_hosp.patients p ON i.subject_id = p.subject_id
        WHERE i.stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        return {'error': 'Stay ID not found'}
    
    stay_info = stay_info.iloc[0]
    subject_id = stay_info['subject_id']
    hadm_id = stay_info['hadm_id']
    intime = pd.to_datetime(stay_info['intime'])
    admittime = pd.to_datetime(stay_info['admittime'])
    admission_type = stay_info['admission_type']
    age = stay_info['anchor_age']
    
    # Define first 24 hours window
    first_day_end = intime + timedelta(hours=24)
    
    components = {}
    
    # 1. Pre-ICU in-hospital length of stay (days)
    pre_icu_los = (intime - admittime).total_seconds() / 3600 / 24  # in days
    if pre_icu_los < 0.17:
        pre_icu_los_score = 0
    elif pre_icu_los < 1.0:
        pre_icu_los_score = 1
    elif pre_icu_los < 4.94:
        pre_icu_los_score = 2
    elif pre_icu_los < 24.63:
        pre_icu_los_score = 3
    else:
        pre_icu_los_score = 4
    components['pre_icu_los'] = {'value': pre_icu_los, 'score': pre_icu_los_score}
    
    # 2. Age (years)
    if age < 24:
        age_score = 0
    elif age < 54:
        age_score = 1
    elif age < 78:
        age_score = 2
    elif age < 90:
        age_score = 3
    else:
        age_score = 4
    components['age'] = {'value': age, 'score': age_score}
    
    # 3. GCS - get minimum of each component independently in first 24 hours
    gcs_query = query_db(f"""
        SELECT 
            MIN(CASE WHEN itemid = 220739 THEN valuenum END) as min_eye,
            MIN(CASE WHEN itemid = 223900 THEN valuenum END) as min_verbal,
            MIN(CASE WHEN itemid = 223901 THEN valuenum END) as min_motor
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid IN (220739, 223900, 223901)
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
          AND valuenum IS NOT NULL
    """)
    
    if not gcs_query.empty and gcs_query.iloc[0]['min_eye'] is not None and pd.notna(gcs_query.iloc[0]['min_eye']):
        min_eye = gcs_query.iloc[0]['min_eye']
        min_verbal = gcs_query.iloc[0]['min_verbal']
        min_motor = gcs_query.iloc[0]['min_motor']
        
        # Check if all components are available
        if pd.notna(min_eye) and pd.notna(min_verbal) and pd.notna(min_motor):
            gcs_total = min_eye + min_verbal + min_motor
            if gcs_total == 15:
                gcs_score = 0
            elif gcs_total == 14:
                gcs_score = 1
            elif gcs_total >= 12:
                gcs_score = 2
            elif gcs_total >= 8:
                gcs_score = 3
            else:
                gcs_score = 4
            components['gcs'] = {'value': gcs_total, 'score': gcs_score}
        else:
            components['gcs'] = {'value': None, 'score': None}
            gcs_score = None
    else:
        components['gcs'] = {'value': None, 'score': None}
        gcs_score = None
    
    # 4. Heart rate - get most extreme value in first 24 hours
    hr_query = query_db(f"""
        SELECT valuenum FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 220045  -- Heart Rate
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
          AND valuenum IS NOT NULL
          AND valuenum > 0
          AND valuenum < 300
    """)
    
    if not hr_query.empty:
        hr_values = hr_query['valuenum'].tolist()
        # Find most extreme from normal range (75-100)
        most_extreme_hr = max(hr_values, key=lambda x: max(abs(x - 75), abs(x - 100)))
        
        if 75 <= most_extreme_hr < 100:
            hr_score = 0
        elif (100 <= most_extreme_hr < 120) or (60 <= most_extreme_hr < 75):
            hr_score = 1
        elif (120 <= most_extreme_hr < 140) or (40 <= most_extreme_hr < 60):
            hr_score = 2
        else:  # >= 140 or < 40
            hr_score = 3
        components['heart_rate'] = {'value': most_extreme_hr, 'score': hr_score}
    else:
        components['heart_rate'] = {'value': None, 'score': None}
        hr_score = None
    
    # 5. MAP - get most extreme value in first 24 hours
    # Include 225312 (ART BP Mean) in addition to 220052 and 220181
    map_query = query_db(f"""
        SELECT valuenum FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid IN (220052, 220181, 225312)  -- Arterial BP mean, Non-invasive BP mean, ART BP Mean
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
          AND valuenum IS NOT NULL
          AND valuenum > 0
          AND valuenum < 250
    """)
    
    if not map_query.empty:
        map_values = map_query['valuenum'].tolist()
        # Find most extreme from normal range (60-70)
        most_extreme_map = max(map_values, key=lambda x: max(abs(x - 60), abs(x - 70)))
        
        if 60 <= most_extreme_map < 70:
            map_score = 0
        elif (70 <= most_extreme_map < 80) or (50 <= most_extreme_map < 60):
            map_score = 1
        elif (80 <= most_extreme_map < 100) or (40 <= most_extreme_map < 50):
            map_score = 2
        elif 100 <= most_extreme_map < 120:
            map_score = 3
        else:  # >= 120 or < 40
            map_score = 4
        components['map'] = {'value': most_extreme_map, 'score': map_score}
    else:
        components['map'] = {'value': None, 'score': None}
        map_score = None
    
    # 6. Respiratory rate - get most extreme value in first 24 hours
    rr_query = query_db(f"""
        SELECT valuenum FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 220210  -- Respiratory Rate
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
          AND valuenum IS NOT NULL
          AND valuenum > 0
          AND valuenum < 100
    """)
    
    if not rr_query.empty:
        rr_values = rr_query['valuenum'].tolist()
        # Find most extreme from normal range (12-22)
        most_extreme_rr = max(rr_values, key=lambda x: max(abs(x - 12), abs(x - 22)))
        
        if 12 <= most_extreme_rr < 22:
            rr_score = 0
        elif (22 <= most_extreme_rr < 30) or (6 <= most_extreme_rr < 12):
            rr_score = 1
        elif 30 <= most_extreme_rr < 40:
            rr_score = 2
        else:  # >= 40 or < 6
            rr_score = 3
        components['respiratory_rate'] = {'value': most_extreme_rr, 'score': rr_score}
    else:
        components['respiratory_rate'] = {'value': None, 'score': None}
        rr_score = None
    
    # 7. Temperature - get most extreme value in first 24 hours
    # Check for Celsius first, then Fahrenheit
    temp_query = query_db(f"""
        SELECT valuenum, 'C' as unit FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 223762  -- Temperature Celsius
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
          AND valuenum IS NOT NULL
          AND valuenum > 25
          AND valuenum < 45
        UNION ALL
        SELECT valuenum * 5.0 / 9.0 - 17.7778, 'F' as unit FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 223761  -- Temperature Fahrenheit
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
          AND valuenum IS NOT NULL
          AND valuenum > 77
          AND valuenum < 113
    """)
    
    if not temp_query.empty:
        temp_values = temp_query['valuenum'].tolist()
        # Find most extreme from normal range (36-37.5)
        most_extreme_temp = max(temp_values, key=lambda x: max(abs(x - 36), abs(x - 37.5)))
        
        if 36 <= most_extreme_temp < 37.5:
            temp_score = 0
        elif (37.5 <= most_extreme_temp < 38.5) or (35 <= most_extreme_temp < 36):
            temp_score = 1
        elif 38.5 <= most_extreme_temp < 39:
            temp_score = 2
        else:  # >= 39 or < 35
            temp_score = 3
        components['temperature'] = {'value': most_extreme_temp, 'score': temp_score}
    else:
        components['temperature'] = {'value': None, 'score': None}
        temp_score = None
    
    # 8. Urine output - total in first 24 hours
    urine_query = query_db(f"""
        SELECT SUM(value) as total_urine
        FROM mimiciv_icu.outputevents
        WHERE stay_id = {stay_id}
          AND itemid IN (226557, 226558, 226559, 226560, 226561, 226563, 226564, 226565, 226566, 226567, 227489)
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
    """)
    
    if not urine_query.empty and urine_query.iloc[0]['total_urine'] is not None:
        urine_output = urine_query.iloc[0]['total_urine']
        if urine_output >= 2000 and urine_output < 4000:
            urine_score = 0
        elif (urine_output >= 4000 and urine_output < 5500) or (urine_output >= 1000 and urine_output < 2000):
            urine_score = 1
        elif urine_output >= 5500 or (urine_output >= 500 and urine_output < 1000):
            urine_score = 2
        elif urine_output >= 200 and urine_output < 500:
            urine_score = 3
        else:  # < 200
            urine_score = 4
        components['urine_output'] = {'value': urine_output, 'score': urine_score}
    else:
        components['urine_output'] = {'value': None, 'score': None}
        urine_score = None
    
    # 9. Mechanical ventilation - check if ventilated in first 24 hours
    # Check for ventilator type or mode in chartevents
    vent_query = query_db(f"""
        SELECT COUNT(*) as vent_count
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid IN (223848, 223849)  -- Ventilator Type, Ventilator Mode
          AND charttime >= '{intime}'
          AND charttime <= '{first_day_end}'
    """)
    
    # Also check for invasive ventilation in procedureevents
    vent_proc_query = query_db(f"""
        SELECT COUNT(*) as vent_proc_count
        FROM mimiciv_icu.procedureevents
        WHERE stay_id = {stay_id}
          AND itemid = 225792  -- Invasive Ventilation
          AND starttime >= '{intime}'
          AND starttime <= '{first_day_end}'
    """)
    
    # Check for intubation in procedureevents
    intub_query = query_db(f"""
        SELECT COUNT(*) as intub_count
        FROM mimiciv_icu.procedureevents
        WHERE stay_id = {stay_id}
          AND itemid = 224385  -- Intubation
          AND starttime >= '{intime}'
          AND starttime <= '{first_day_end}'
    """)
    
    on_mechanical_ventilation = (
        vent_query.iloc[0]['vent_count'] > 0 or 
        vent_proc_query.iloc[0]['vent_proc_count'] > 0 or 
        intub_query.iloc[0]['intub_count'] > 0
    )
    
    if on_mechanical_ventilation:
        vent_score = 4
    else:
        vent_score = 0
    components['mechanical_ventilation'] = {'value': on_mechanical_ventilation, 'score': vent_score}
    
    # 10. Elective surgery - check admission type
    is_elective = admission_type == 'ELECTIVE'
    if is_elective:
        elective_score = 0
    else:
        elective_score = 3
    components['elective_surgery'] = {'value': is_elective, 'score': elective_score}
    
    # Calculate total OASIS score
    score_list = [
        pre_icu_los_score, age_score, gcs_score, hr_score, map_score,
        rr_score, temp_score, urine_score, vent_score, elective_score
    ]
    
    # Handle missing values - if any component is missing, we can't calculate a valid score
    if None in score_list:
        oasis_score = None
    else:
        oasis_score = sum(score_list)
    
    # Calculate predicted mortality
    if oasis_score is not None:
        # Logistic regression: p = 1 / (1 + exp(-(beta0 + beta1 * OASIS)))
        beta0 = -6.1746
        beta1 = 0.1275
        predicted_mortality = 1 / (1 + np.exp(-(beta0 + beta1 * oasis_score)))
    else:
        predicted_mortality = None
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'oasis_score': oasis_score,
        'components': components,
        'on_mechanical_ventilation': on_mechanical_ventilation,
        'predicted_mortality': predicted_mortality
    }

FINAL_FUNCTION = calculate_oasis_score