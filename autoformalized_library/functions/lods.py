# Let me verify the cardiovascular scoring logic more carefully
# For stay 37743005: HR 185, SBP 45
# HR 185 >= 160 → score 3
# SBP 45 is in 40-69 range → score 3
# Max = 3 ✓

# Let me also verify the renal scoring for stay 37293400
# BUN 20.349 mmol/L >= 20 → score 5
# Cr 450.84 µmol/L is in 141-495 range → score 3
# UO 1182 mL >= 750 → score 0
# Max = 5 ✓

# Let me verify the hepatic scoring for stay 39553978
# Bili 46.17 µmol/L is in 34.2-68.4 range → score 1
# PT 19.5 - 12.5 = 7 sec above control (>6 → score 3)
# Max = 3 ✓

# All looks correct! Now let me create the final self-contained function

import pandas as pd
import numpy as np
from datetime import timedelta

def compute_lods_score(stay_id):
    """
    Compute the LODS (Logistic Organ Dysfunction System) score for an ICU stay.
    
    The LODS score assesses organ dysfunction across 6 systems:
    - Neurologic (Glasgow Coma Scale)
    - Cardiovascular (Heart Rate and Systolic Blood Pressure)
    - Renal (BUN, Creatinine, Urine Output)
    - Pulmonary (Mechanical Ventilation and PaO2/FiO2 ratio)
    - Hematologic (WBC and Platelet Count)
    - Hepatic (Bilirubin and Prothrombin Time)
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier
    
    Returns
    -------
    dict
        Dictionary containing LODS scores and details
    """
    
    # Get stay information
    stay_info = query_db(f"""
        SELECT subject_id, hadm_id, stay_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        return None
    
    subject_id = stay_info.iloc[0]['subject_id']
    hadm_id = stay_info.iloc[0]['hadm_id']
    intime = stay_info.iloc[0]['intime']
    outtime = stay_info.iloc[0]['outtime']
    
    # Define the scoring window (first 24 hours of ICU stay)
    window_end = intime + timedelta(hours=24)
    
    details = {}
    
    # ============================================
    # NEUROLOGIC SCORE (0-5) - based on GCS
    # ============================================
    gcs_query = f"""
        SELECT 
            SUM(CASE WHEN itemid = 220739 THEN valuenum ELSE 0 END) as eye,
            SUM(CASE WHEN itemid = 223901 THEN valuenum ELSE 0 END) as motor,
            SUM(CASE WHEN itemid = 223900 THEN valuenum ELSE 0 END) as verbal
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND charttime >= '{intime}'
          AND charttime <= '{window_end}'
          AND itemid IN (220739, 223901, 223900)
          AND valuenum IS NOT NULL
        GROUP BY charttime
    """
    gcs_data = query_db(gcs_query)
    
    neurologic_score = 0
    gcs_total = None
    
    if not gcs_data.empty:
        # Calculate total GCS for each time point and find the minimum (worst)
        gcs_data['gcs_total'] = gcs_data['eye'] + gcs_data['motor'] + gcs_data['verbal']
        gcs_total = gcs_data['gcs_total'].min()
        
        if gcs_total is not None and not pd.isna(gcs_total):
            gcs_total = int(gcs_total)
            if gcs_total == 15:
                neurologic_score = 0
            elif gcs_total in [13, 14]:
                neurologic_score = 1
            elif gcs_total in [9, 10, 11, 12]:
                neurologic_score = 3
            elif gcs_total <= 8:
                neurologic_score = 5
    
    details['neurologic'] = {'gcs_total': gcs_total, 'score': neurologic_score}
    
    # ============================================
    # CARDIOVASCULAR SCORE (0-5) - based on HR and SBP
    # ============================================
    cv_query = f"""
        SELECT 
            charttime,
            MAX(CASE WHEN itemid IN (220045) THEN valuenum END) as hr,
            MAX(CASE WHEN itemid IN (220050, 220179) THEN valuenum END) as sbp
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND charttime >= '{intime}'
          AND charttime <= '{window_end}'
          AND itemid IN (220045, 220050, 220179)
          AND valuenum IS NOT NULL
          AND valuenum > 0
        GROUP BY charttime
    """
    cv_data = query_db(cv_query)
    
    cardiovascular_score = 0
    worst_hr = None
    worst_sbp = None
    
    if not cv_data.empty:
        hr_values = cv_data['hr'].dropna()
        sbp_values = cv_data['sbp'].dropna()
        
        # Filter out physiologically impossible values
        hr_values = hr_values[(hr_values > 0) & (hr_values < 300)]
        sbp_values = sbp_values[(sbp_values > 0) & (sbp_values < 300)]
        
        if len(hr_values) > 0:
            worst_hr = max(hr_values)
            worst_hr_low = min(hr_values)
        
        if len(sbp_values) > 0:
            worst_sbp = sbp_values.min()
            worst_sbp_high = sbp_values.max()
        
        # Calculate HR score
        hr_score = 0
        if worst_hr is not None:
            if worst_hr >= 160 or worst_hr_low < 30:
                hr_score = 3
            elif worst_hr >= 140:
                hr_score = 1
        
        # Calculate SBP score
        sbp_score = 0
        if worst_sbp is not None:
            if worst_sbp < 40:
                sbp_score = 5
            elif worst_sbp < 70:
                sbp_score = 3
            elif worst_sbp < 90:
                sbp_score = 1
        
        # Calculate high SBP score
        if worst_sbp_high is not None and worst_sbp_high >= 270:
            sbp_score = max(sbp_score, 3)
        
        cardiovascular_score = max(hr_score, sbp_score)
    
    details['cardiovascular'] = {'worst_hr': worst_hr, 'worst_sbp': worst_sbp, 'score': cardiovascular_score}
    
    # ============================================
    # RENAL SCORE (0-5) - based on BUN, Creatinine, Urine Output
    # ============================================
    renal_query = f"""
        SELECT 
            MIN(CASE WHEN itemid IN (51006, 52647) THEN valuenum END) as bun_min,
            MAX(CASE WHEN itemid IN (51006, 52647) THEN valuenum END) as bun_max,
            MIN(CASE WHEN itemid IN (50912, 52546) THEN valuenum END) as cr_min,
            MAX(CASE WHEN itemid IN (50912, 52546) THEN valuenum END) as cr_max
        FROM mimiciv_hosp.labevents
        WHERE hadm_id = {hadm_id}
          AND charttime >= '{intime}'
          AND charttime <= '{window_end}'
          AND itemid IN (51006, 52647, 50912, 52546)
          AND valuenum IS NOT NULL
    """
    renal_lab = query_db(renal_query)
    
    uo_query = f"""
        SELECT SUM(value) as total_uo
        FROM mimiciv_icu.outputevents
        WHERE stay_id = {stay_id}
          AND charttime >= '{intime}'
          AND charttime <= '{window_end}'
          AND itemid IN (226559, 226560, 226566, 226627, 226631, 227489)
          AND value IS NOT NULL
    """
    uo_data = query_db(uo_query)
    
    renal_score = 0
    bun_mmol = None
    cr_umol = None
    urine_output = None
    
    if not renal_lab.empty:
        bun_mgdl = renal_lab['bun_max'].iloc[0] if not pd.isna(renal_lab['bun_max'].iloc[0]) else None
        if bun_mgdl is not None:
            bun_mmol = bun_mgdl * 0.357
        
        cr_mgdl = renal_lab['cr_max'].iloc[0] if not pd.isna(renal_lab['cr_max'].iloc[0]) else None
        if cr_mgdl is not None:
            cr_umol = cr_mgdl * 88.4
    
    if not uo_data.empty:
        urine_output = uo_data['total_uo'].iloc[0] if not pd.isna(uo_data['total_uo'].iloc[0]) else None
    
    # Calculate BUN score
    bun_score = 0
    if bun_mmol is not None:
        if bun_mmol >= 20:
            bun_score = 5
        elif bun_mmol >= 10:
            bun_score = 3
        elif bun_mmol >= 6:
            bun_score = 1
    
    # Calculate Creatinine score
    cr_score = 0
    if cr_umol is not None:
        if cr_umol > 495:
            cr_score = 5
        elif cr_umol >= 141:
            cr_score = 3
        elif cr_umol >= 106:
            cr_score = 1
    
    # Calculate Urine Output score
    uo_score = 0
    if urine_output is not None:
        if urine_output < 500:
            uo_score = 3
        elif urine_output < 750:
            uo_score = 1
    
    renal_score = max(bun_score, cr_score, uo_score)
    
    details['renal'] = {'bun_mmol': bun_mmol, 'cr_umol': cr_umol, 'urine_output': urine_output, 'score': renal_score}
    
    # ============================================
    # PULMONARY SCORE (0-3) - based on MV and P/F ratio
    # ============================================
    pulmonary_score = 0
    pf_ratio = None
    
    mv_query = f"""
        SELECT COUNT(*) as mv_count
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND charttime >= '{intime}'
          AND charttime <= '{window_end}'
          AND itemid = 223849
          AND value IS NOT NULL
          AND value NOT IN ('Standby', 'SPONT', 'CPAP')
    """
    mv_data = query_db(mv_query)
    
    on_mv = mv_data['mv_count'].iloc[0] > 0 if not mv_data.empty else False
    
    if on_mv:
        pao2_query = f"""
            SELECT MIN(valuenum) as pao2_min
            FROM mimiciv_hosp.labevents
            WHERE hadm_id = {hadm_id}
              AND charttime >= '{intime}'
              AND charttime <= '{window_end}'
              AND itemid = 50821
              AND valuenum IS NOT NULL
        """
        pao2_data = query_db(pao2_query)
        
        fio2_query = f"""
            SELECT MIN(valuenum) as fio2_min
            FROM mimiciv_icu.chartevents
            WHERE stay_id = {stay_id}
              AND charttime >= '{intime}'
              AND charttime <= '{window_end}'
              AND itemid IN (229841, 226754, 227010)
              AND valuenum IS NOT NULL
        """
        fio2_data = query_db(fio2_query)
        
        pao2 = pao2_data['pao2_min'].iloc[0] if not pao2_data.empty and not pd.isna(pao2_data['pao2_min'].iloc[0]) else None
        fio2 = fio2_data['fio2_min'].iloc[0] if not fio2_data.empty and not pd.isna(fio2_data['fio2_min'].iloc[0]) else None
        
        if pao2 is not None and fio2 is not None and fio2 > 0:
            pf_ratio = pao2 / (fio2 / 100.0)
        
        if pf_ratio is not None:
            if pf_ratio < 150:
                pulmonary_score = 3
            else:
                pulmonary_score = 1
        else:
            pulmonary_score = 1
    
    details['pulmonary'] = {'on_mv': on_mv, 'pf_ratio': pf_ratio, 'score': pulmonary_score}
    
    # ============================================
    # HEMATOLOGIC SCORE (0-3) - based on WBC and Platelets
    # ============================================
    heme_query = f"""
        SELECT 
            MIN(CASE WHEN itemid IN (51300, 51755, 51301) THEN valuenum END) as wbc_min,
            MAX(CASE WHEN itemid IN (51300, 51755, 51301) THEN valuenum END) as wbc_max,
            MIN(CASE WHEN itemid IN (51265, 53189) THEN valuenum END) as platelet_min,
            MAX(CASE WHEN itemid IN (51265, 53189) THEN valuenum END) as platelet_max
        FROM mimiciv_hosp.labevents
        WHERE hadm_id = {hadm_id}
          AND charttime >= '{intime}'
          AND charttime <= '{window_end}'
          AND itemid IN (51300, 51755, 51301, 51265, 53189)
          AND valuenum IS NOT NULL
    """
    heme_data = query_db(heme_query)
    
    hematologic_score = 0
    wbc = None
    platelets = None
    
    if not heme_data.empty:
        wbc_kul = heme_data['wbc_min'].iloc[0] if not pd.isna(heme_data['wbc_min'].iloc[0]) else None
        wbc_high = heme_data['wbc_max'].iloc[0] if not pd.isna(heme_data['wbc_max'].iloc[0]) else None
        if wbc_kul is not None:
            wbc = wbc_kul
        if wbc_high is not None:
            wbc_high = wbc_high
        
        platelets_kul = heme_data['platelet_min'].iloc[0] if not pd.isna(heme_data['platelet_min'].iloc[0]) else None
        if platelets_kul is not None:
            platelets = platelets_kul
    
    # Calculate WBC score
    wbc_score = 0
    if wbc is not None or wbc_high is not None:
        if wbc is not None and wbc < 2.5:
            wbc_score = 3
        elif wbc_high is not None and wbc_high >= 50:
            wbc_score = 3
        elif wbc is not None and wbc >= 2.5 and wbc < 5:
            wbc_score = 1
    
    # Calculate Platelet score
    platelet_score = 0
    if platelets is not None:
        if platelets < 50:
            platelet_score = 3
        elif platelets < 150:
            platelet_score = 1
    
    hematologic_score = max(wbc_score, platelet_score)
    
    details['hematologic'] = {'wbc': wbc, 'platelets': platelets, 'score': hematologic_score}
    
    # ============================================
    # HEPATIC SCORE (0-3) - based on Bilirubin and PT
    # ============================================
    hep_query = f"""
        SELECT 
            MAX(CASE WHEN itemid IN (50885, 53089) THEN valuenum END) as bili_max,
            MAX(CASE WHEN itemid IN (52923, 51274) THEN valuenum END) as pt_max,
            MIN(CASE WHEN itemid IN (52923, 51274) THEN ref_range_upper END) as pt_ref_upper
        FROM mimiciv_hosp.labevents
        WHERE hadm_id = {hadm_id}
          AND charttime >= '{intime}'
          AND charttime <= '{window_end}'
          AND itemid IN (50885, 53089, 52923, 51274)
          AND valuenum IS NOT NULL
    """
    hep_data = query_db(hep_query)
    
    hepatic_score = 0
    bilirubin = None
    pt = None
    pt_ref = None
    
    if not hep_data.empty:
        bili_mgdl = hep_data['bili_max'].iloc[0] if not pd.isna(hep_data['bili_max'].iloc[0]) else None
        if bili_mgdl is not None:
            bilirubin = bili_mgdl * 17.1
        
        pt = hep_data['pt_max'].iloc[0] if not pd.isna(hep_data['pt_max'].iloc[0]) else None
        pt_ref = hep_data['pt_ref_upper'].iloc[0] if not pd.isna(hep_data['pt_ref_upper'].iloc[0]) else None
    
    # Calculate Bilirubin score
    bili_score = 0
    if bilirubin is not None:
        if bilirubin >= 68.4:
            bili_score = 3
        elif bilirubin >= 34.2:
            bili_score = 1
    
    # Calculate PT score (seconds above control)
    pt_score = 0
    if pt is not None and pt_ref is not None:
        pt_above = pt - pt_ref
        if pt_above > 6:
            pt_score = 3
        elif pt_above > 3:
            pt_score = 1
    
    hepatic_score = max(bili_score, pt_score)
    
    details['hepatic'] = {'bilirubin_umol': bilirubin, 'pt': pt, 'pt_ref': pt_ref, 'score': hepatic_score}
    
    # ============================================
    # TOTAL SCORE
    # ============================================
    total_score = neurologic_score + cardiovascular_score + renal_score + pulmonary_score + hematologic_score + hepatic_score
    
    return {
        'total_score': total_score,
        'neurologic_score': neurologic_score,
        'cardiovascular_score': cardiovascular_score,
        'renal_score': renal_score,
        'pulmonary_score': pulmonary_score,
        'hematologic_score': hematologic_score,
        'hepatic_score': hepatic_score,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'stay_id': stay_id,
        'intime': str(intime),
        'outtime': str(outtime),
        'details': details
    }

FINAL_FUNCTION = compute_lods_score