import pandas as pd
import numpy as np

def first_day_sofa(stay_id):
    """
    Calculate the SOFA (Sequential Organ Failure Assessment) score for the first day of an ICU stay.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing SOFA scores for each organ system and total score.
    """
    # Get ICU stay information
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        raise ValueError(f"Stay ID {stay_id} not found")
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = stay_info.iloc[0]['intime']
    first_day_end = pd.Timestamp(intime) + pd.Timedelta(hours=24)
    
    # Initialize result dictionary
    result = {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': str(intime),
        'first_day_end': str(first_day_end),
        'respiration_score': None,
        'coagulation_score': None,
        'liver_score': None,
        'cardiovascular_score': None,
        'brain_score': None,
        'kidney_score': None,
        'total_sofa_score': None,
        'respiration_data': {},
        'coagulation_data': {},
        'liver_data': {},
        'cardiovascular_data': {},
        'brain_data': {},
        'kidney_data': {}
    }
    
    # 1. RESPIRATION: PaO2/FiO2 ratio
    pao2_data = query_db(f"""
        SELECT valuenum as pao2, charttime
        FROM mimiciv_hosp.labevents
        WHERE subject_id = {subject_id}
          AND hadm_id = {hadm_id}
          AND itemid = 50821
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND valuenum IS NOT NULL
    """)
    
    fio2_data = query_db(f"""
        SELECT valuenum as fio2, charttime
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 223835
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND valuenum IS NOT NULL
    """)
    
    pao2_values = pao2_data['pao2'].tolist() if not pao2_data.empty else []
    fio2_values = fio2_data['fio2'].tolist() if not fio2_data.empty else []
    
    fio2_fraction = [f/100 if f > 1 else f for f in fio2_values]
    
    if pao2_values and fio2_fraction:
        min_pao2 = min(pao2_values)
        max_fio2 = max(fio2_fraction)
        pao2_fio2_ratio = min_pao2 / max_fio2 if max_fio2 > 0 else None
    else:
        pao2_fio2_ratio = None
    
    result['respiration_data'] = {
        'pao2_values': pao2_values,
        'fio2_values': fio2_values,
        'pao2_fio2_ratio': pao2_fio2_ratio
    }
    
    if pao2_fio2_ratio is not None:
        if pao2_fio2_ratio >= 400:
            result['respiration_score'] = 0
        elif pao2_fio2_ratio >= 300:
            result['respiration_score'] = 1
        elif pao2_fio2_ratio >= 200:
            result['respiration_score'] = 2
        elif pao2_fio2_ratio >= 100:
            result['respiration_score'] = 3
        else:
            result['respiration_score'] = 4
    
    # 2. COAGULATION: Platelet count
    platelet_data = query_db(f"""
        SELECT valuenum as platelet, charttime
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 227457
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND valuenum IS NOT NULL
    """)
    
    platelet_values = platelet_data['platelet'].tolist() if not platelet_data.empty else []
    min_platelet = min(platelet_values) if platelet_values else None
    
    result['coagulation_data'] = {
        'platelet_values': platelet_values,
        'min_platelet': min_platelet
    }
    
    if min_platelet is not None:
        if min_platelet >= 150:
            result['coagulation_score'] = 0
        elif min_platelet >= 100:
            result['coagulation_score'] = 1
        elif min_platelet >= 50:
            result['coagulation_score'] = 2
        elif min_platelet >= 20:
            result['coagulation_score'] = 3
        else:
            result['coagulation_score'] = 4
    
    # 3. LIVER: Total bilirubin
    bilirubin_data = query_db(f"""
        SELECT valuenum as bilirubin, charttime
        FROM mimiciv_hosp.labevents
        WHERE subject_id = {subject_id}
          AND hadm_id = {hadm_id}
          AND itemid = 50885
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND valuenum IS NOT NULL
    """)
    
    bilirubin_values = bilirubin_data['bilirubin'].tolist() if not bilirubin_data.empty else []
    max_bilirubin = max(bilirubin_values) if bilirubin_values else None
    
    result['liver_data'] = {
        'bilirubin_values': bilirubin_values,
        'max_bilirubin': max_bilirubin
    }
    
    if max_bilirubin is not None:
        if max_bilirubin < 1.2:
            result['liver_score'] = 0
        elif max_bilirubin < 2.0:
            result['liver_score'] = 1
        elif max_bilirubin < 6.0:
            result['liver_score'] = 2
        elif max_bilirubin < 12.0:
            result['liver_score'] = 3
        else:
            result['liver_score'] = 4
    
    # 4. CARDIOVASCULAR: MAP and vasopressors
    map_data = query_db(f"""
        SELECT valuenum as map, charttime
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 220052
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND valuenum IS NOT NULL
    """)
    
    map_values = map_data['map'].tolist() if not map_data.empty else []
    min_map = min(map_values) if map_values else None
    
    # Use table aliases to avoid ambiguous column reference
    vasopressor_data = query_db(f"""
        SELECT ie.itemid, di.label, MAX(ie.rate) as max_rate, ie.rateuom, ie.patientweight
        FROM mimiciv_icu.inputevents ie
        JOIN mimiciv_icu.d_items di ON ie.itemid = di.itemid
        WHERE ie.stay_id = {stay_id}
          AND ie.starttime >= '{intime}'
          AND ie.starttime < '{first_day_end}'
          AND ie.itemid IN (221662, 221653, 221289, 221906)
          AND ie.rate IS NOT NULL
        GROUP BY ie.itemid, di.label, ie.rateuom, ie.patientweight
    """)
    
    result['cardiovascular_data'] = {
        'map_values': map_values,
        'min_map': min_map,
        'vasopressors': vasopressor_data.to_dict('records') if not vasopressor_data.empty else []
    }
    
    cv_score = 0
    
    if min_map is not None and min_map < 70:
        cv_score = 1
    
    if not vasopressor_data.empty:
        max_rates = {}
        for _, row in vasopressor_data.iterrows():
            itemid = row['itemid']
            rate = row['max_rate']
            if itemid not in max_rates:
                max_rates[itemid] = rate
            else:
                max_rates[itemid] = max(max_rates[itemid], rate)
        
        dopamine = max_rates.get(221662, 0)
        dobutamine = max_rates.get(221653, 0)
        epinephrine = max_rates.get(221289, 0)
        norepinephrine = max_rates.get(221906, 0)
        
        if dopamine > 15 or epinephrine > 0.1 or norepinephrine > 0.1:
            cv_score = 4
        elif dopamine > 5 or epinephrine > 0 or norepinephrine > 0:
            cv_score = 3
        elif dopamine > 0 or dobutamine > 0:
            cv_score = 2
    
    result['cardiovascular_score'] = cv_score
    
    # 5. BRAIN: GCS
    gcs_data = query_db(f"""
        SELECT 
            charttime,
            MAX(CASE WHEN itemid = 220739 THEN valuenum END) as eye,
            MAX(CASE WHEN itemid = 223900 THEN valuenum END) as verbal,
            MAX(CASE WHEN itemid = 223901 THEN valuenum END) as motor
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid IN (220739, 223900, 223901)
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND valuenum IS NOT NULL
        GROUP BY charttime
    """)
    
    if not gcs_data.empty:
        gcs_data['gcs_total'] = gcs_data['eye'].fillna(0) + gcs_data['verbal'].fillna(0) + gcs_data['motor'].fillna(0)
        min_gcs = gcs_data['gcs_total'].min()
        gcs_values = gcs_data['gcs_total'].tolist()
    else:
        min_gcs = None
        gcs_values = []
    
    result['brain_data'] = {
        'gcs_records': gcs_data.to_dict('records') if not gcs_data.empty else [],
        'min_gcs': min_gcs,
        'gcs_values': gcs_values
    }
    
    if min_gcs is not None:
        if min_gcs == 15:
            result['brain_score'] = 0
        elif min_gcs >= 13:
            result['brain_score'] = 1
        elif min_gcs >= 10:
            result['brain_score'] = 2
        elif min_gcs >= 6:
            result['brain_score'] = 3
        else:
            result['brain_score'] = 4
    
    # 6. KIDNEY: Creatinine and urine output
    creatinine_data = query_db(f"""
        SELECT valuenum as creatinine, charttime
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid = 220615
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND valuenum IS NOT NULL
    """)
    
    creatinine_values = creatinine_data['creatinine'].tolist() if not creatinine_data.empty else []
    max_creatinine = max(creatinine_values) if creatinine_values else None
    
    urine_data = query_db(f"""
        SELECT SUM(value) as total_urine
        FROM mimiciv_icu.outputevents
        WHERE stay_id = {stay_id}
          AND charttime >= '{intime}'
          AND charttime < '{first_day_end}'
          AND itemid IN (226557, 226558, 226559, 226560, 226561, 226563, 226564, 226565, 226566, 226567, 227489)
    """)
    
    total_urine = urine_data.iloc[0]['total_urine'] if not urine_data.empty else None
    
    result['kidney_data'] = {
        'creatinine_values': creatinine_values,
        'max_creatinine': max_creatinine,
        'total_urine_output': total_urine
    }
    
    kidney_score = 0
    if max_creatinine is not None:
        if max_creatinine >= 5.0:
            kidney_score = 4
        elif max_creatinine >= 3.5:
            kidney_score = 3
        elif max_creatinine >= 2.0:
            kidney_score = 2
        elif max_creatinine >= 1.2:
            kidney_score = 1
    
    if total_urine is not None:
        if total_urine < 200:
            kidney_score = max(kidney_score, 4)
        elif total_urine < 500:
            kidney_score = max(kidney_score, 3)
    
    result['kidney_score'] = kidney_score
    
    # Calculate total SOFA score
    scores = [
        result['respiration_score'],
        result['coagulation_score'],
        result['liver_score'],
        result['cardiovascular_score'],
        result['brain_score'],
        result['kidney_score']
    ]
    
    valid_scores = [s if s is not None else 0 for s in scores]
    result['total_sofa_score'] = sum(valid_scores)
    
    return result

FINAL_FUNCTION = first_day_sofa