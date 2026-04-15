import pandas as pd
import numpy as np
from datetime import timedelta

def compute_saps_ii(subject_id, hadm_id=None, stay_id=None):
    """
    Calculate SAPS II (Simplified Acute Physiology Score II) for a patient.
    
    Parameters
    ----------
    subject_id : int
        Patient identifier
    hadm_id : int, optional
        Hospital admission identifier (required if stay_id not provided)
    stay_id : int, optional
        ICU stay identifier (required if hadm_id not provided)
    
    Returns
    -------
    dict
        Dictionary containing:
        - 'saps_ii_score': Total SAPS II score (0-163)
        - 'predicted_mortality': Predicted hospital mortality probability
        - 'components': Dictionary with individual component scores
        - 'values': Dictionary with raw values used for scoring
    """
    
    # Convert to Python native types
    subject_id = int(subject_id)
    if hadm_id is not None:
        hadm_id = int(hadm_id)
    if stay_id is not None:
        stay_id = int(stay_id)
    
    # Get stay_id if not provided
    if stay_id is None:
        if hadm_id is None:
            raise ValueError("Either hadm_id or stay_id must be provided")
        sql = """
        SELECT stay_id, intime, outtime
        FROM mimiciv_icu.icustays
        WHERE subject_id = ? AND hadm_id = ?
        ORDER BY intime
        LIMIT 1
        """
        df = query_db(sql, [subject_id, hadm_id])
        if df.empty:
            return None
        stay_id = int(df.iloc[0]['stay_id'])
        intime = df.iloc[0]['intime']
    else:
        sql = """
        SELECT intime, outtime, hadm_id
        FROM mimiciv_icu.icustays
        WHERE stay_id = ?
        """
        df = query_db(sql, [stay_id])
        if df.empty:
            return None
        intime = df.iloc[0]['intime']
        hadm_id = int(df.iloc[0]['hadm_id'])
    
    # Define time window (first 24 hours)
    window_end = intime + timedelta(hours=24)
    
    # Get patient demographics
    sql = """
    SELECT p.subject_id, p.gender, p.anchor_age,
           a.admission_type, a.hospital_expire_flag
    FROM mimiciv_hosp.patients p
    JOIN mimiciv_hosp.admissions a ON p.subject_id = a.subject_id
    WHERE p.subject_id = ? AND a.hadm_id = ?
    """
    demo_df = query_db(sql, [subject_id, hadm_id])
    if demo_df.empty:
        return None
    
    anchor_age = int(demo_df.iloc[0]['anchor_age'])
    admission_type = demo_df.iloc[0]['admission_type']
    
    # Initialize results
    components = {}
    values = {}
    
    # 1. AGE SCORE
    age = anchor_age
    if age < 40:
        age_score = 0
    elif age < 60:
        age_score = 7
    elif age < 70:
        age_score = 12
    elif age < 75:
        age_score = 15
    elif age < 80:
        age_score = 16
    else:
        age_score = 18
    components['age'] = age_score
    values['age'] = age
    
    # 2. HEART RATE (bpm) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_icu.chartevents
    WHERE subject_id = ? AND stay_id = ?
      AND itemid = 220045
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, stay_id, intime, window_end])
    if not df.empty:
        hr = df['valuenum'].values
        worst_hr = float(hr[0])
        worst_hr_score = 0
        for h in hr:
            h = float(h)
            if h < 40:
                s = 11
            elif h < 70:
                s = 2
            elif h < 120:
                s = 0
            elif h < 160:
                s = 4
            else:
                s = 7
            if s > worst_hr_score:
                worst_hr_score = s
                worst_hr = h
        components['heart_rate'] = worst_hr_score
        values['heart_rate'] = worst_hr
    else:
        components['heart_rate'] = 0
        values['heart_rate'] = None
    
    # 3. SYSTOLIC BP (mmHg) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_icu.chartevents
    WHERE subject_id = ? AND stay_id = ?
      AND itemid IN (220050, 220179)
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, stay_id, intime, window_end])
    if not df.empty:
        sbp = df['valuenum'].values
        worst_sbp = float(sbp[0])
        worst_sbp_score = 0
        for b in sbp:
            b = float(b)
            if b < 70:
                s = 13
            elif b < 100:
                s = 5
            elif b < 200:
                s = 0
            else:
                s = 2
            if s > worst_sbp_score:
                worst_sbp_score = s
                worst_sbp = b
        components['systolic_bp'] = worst_sbp_score
        values['systolic_bp'] = worst_sbp
    else:
        components['systolic_bp'] = 0
        values['systolic_bp'] = None
    
    # 4. TEMPERATURE (°C) - worst value in 24h
    sql = """
    SELECT itemid, valuenum
    FROM mimiciv_icu.chartevents
    WHERE subject_id = ? AND stay_id = ?
      AND itemid IN (223762, 223761)
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, stay_id, intime, window_end])
    temp_score = 0
    temp_value = None
    if not df.empty:
        temps_celsius = []
        for _, row in df.iterrows():
            val = float(row['valuenum'])
            itemid = int(row['itemid'])
            if itemid == 223761:  # Fahrenheit
                val = (val - 32) * 5 / 9
            temps_celsius.append(val)
        
        worst_temp = temps_celsius[0]
        worst_temp_score = 0
        for t in temps_celsius:
            if t < 39.0:
                s = 0
            else:
                s = 3
            if s > worst_temp_score:
                worst_temp_score = s
                worst_temp = t
        temp_score = worst_temp_score
        temp_value = worst_temp
    components['temperature'] = temp_score
    values['temperature'] = temp_value
    
    # 5. GCS (lowest value in 24h)
    sql = """
    SELECT itemid, valuenum, charttime
    FROM mimiciv_icu.chartevents
    WHERE subject_id = ? AND stay_id = ?
      AND itemid IN (220739, 223900, 223901)
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, stay_id, intime, window_end])
    gcs_score = 0
    gcs_value = 15
    if not df.empty:
        df['valuenum'] = df['valuenum'].astype(int)
        gcs_by_time = df.groupby('charttime')['valuenum'].sum().reset_index()
        if not gcs_by_time.empty:
            gcs_value = int(gcs_by_time['valuenum'].min())
            if gcs_value >= 14:
                gcs_score = 0
            elif gcs_value >= 11:
                gcs_score = 5
            elif gcs_value >= 9:
                gcs_score = 7
            elif gcs_value >= 6:
                gcs_score = 13
            else:
                gcs_score = 26
    components['gcs'] = gcs_score
    values['gcs'] = gcs_value
    
    # 6. WBC (×10³/mm³) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_hosp.labevents
    WHERE subject_id = ? AND hadm_id = ?
      AND itemid = 51300
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, hadm_id, intime, window_end])
    if not df.empty:
        wbc = df['valuenum'].values
        worst_wbc = float(wbc[0])
        worst_wbc_score = 0
        for w in wbc:
            w = float(w)
            if w < 1.0:
                s = 12
            elif w < 20.0:
                s = 0
            else:
                s = 3
            if s > worst_wbc_score:
                worst_wbc_score = s
                worst_wbc = w
        components['wbc'] = worst_wbc_score
        values['wbc'] = worst_wbc
    else:
        components['wbc'] = 0
        values['wbc'] = None
    
    # 7. POTASSIUM (mEq/L) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_hosp.labevents
    WHERE subject_id = ? AND hadm_id = ?
      AND itemid IN (50971, 50822)
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, hadm_id, intime, window_end])
    if not df.empty:
        k = df['valuenum'].values
        worst_k = float(k[0])
        worst_k_score = 0
        for pot in k:
            pot = float(pot)
            if pot < 3.0:
                s = 3
            elif pot < 5.0:
                s = 0
            else:
                s = 3
            if s > worst_k_score:
                worst_k_score = s
                worst_k = pot
        components['potassium'] = worst_k_score
        values['potassium'] = worst_k
    else:
        components['potassium'] = 0
        values['potassium'] = None
    
    # 8. SODIUM (mEq/L) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_hosp.labevents
    WHERE subject_id = ? AND hadm_id = ?
      AND itemid IN (50983, 50824)
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, hadm_id, intime, window_end])
    if not df.empty:
        na = df['valuenum'].values
        worst_na = float(na[0])
        worst_na_score = 0
        for n in na:
            n = float(n)
            if n < 125:
                s = 5
            elif n < 145:
                s = 0
            else:
                s = 1
            if s > worst_na_score:
                worst_na_score = s
                worst_na = n
        components['sodium'] = worst_na_score
        values['sodium'] = worst_na
    else:
        components['sodium'] = 0
        values['sodium'] = None
    
    # 9. BICARBONATE (mEq/L) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_hosp.labevents
    WHERE subject_id = ? AND hadm_id = ?
      AND itemid IN (50882, 50803)
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, hadm_id, intime, window_end])
    if not df.empty:
        bicarb = df['valuenum'].values
        worst_bicarb = float(bicarb[0])
        worst_bicarb_score = 0
        for b in bicarb:
            b = float(b)
            if b < 15:
                s = 6
            elif b < 20:
                s = 3
            else:
                s = 0
            if s > worst_bicarb_score:
                worst_bicarb_score = s
                worst_bicarb = b
        components['bicarbonate'] = worst_bicarb_score
        values['bicarbonate'] = worst_bicarb
    else:
        components['bicarbonate'] = 0
        values['bicarbonate'] = None
    
    # 10. BILIRUBIN (mg/dL) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_hosp.labevents
    WHERE subject_id = ? AND hadm_id = ?
      AND itemid = 50885
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, hadm_id, intime, window_end])
    if not df.empty:
        bili = df['valuenum'].values
        worst_bili = float(bili[0])
        worst_bili_score = 0
        for bl in bili:
            bl = float(bl)
            if bl < 4.0:
                s = 0
            elif bl < 6.0:
                s = 4
            else:
                s = 9
            if s > worst_bili_score:
                worst_bili_score = s
                worst_bili = bl
        components['bilirubin'] = worst_bili_score
        values['bilirubin'] = worst_bili
    else:
        components['bilirubin'] = 0
        values['bilirubin'] = None
    
    # 11. BUN (mg/dL) - worst value in 24h
    sql = """
    SELECT valuenum
    FROM mimiciv_hosp.labevents
    WHERE subject_id = ? AND hadm_id = ?
      AND itemid = 51006
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df = query_db(sql, [subject_id, hadm_id, intime, window_end])
    if not df.empty:
        bun = df['valuenum'].values
        worst_bun = float(bun[0])
        worst_bun_score = 0
        for bu in bun:
            bu = float(bu)
            if bu < 28:
                s = 0
            elif bu < 84:
                s = 6
            else:
                s = 10
            if s > worst_bun_score:
                worst_bun_score = s
                worst_bun = bu
        components['bun'] = worst_bun_score
        values['bun'] = worst_bun
    else:
        components['bun'] = 0
        values['bun'] = None
    
    # 12. PaO2/FiO2 ratio - only if ventilated
    sql = """
    SELECT valuenum
    FROM mimiciv_hosp.labevents
    WHERE subject_id = ? AND hadm_id = ?
      AND itemid = 50821
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df_po2 = query_db(sql, [subject_id, hadm_id, intime, window_end])
    
    sql = """
    SELECT valuenum
    FROM mimiciv_icu.chartevents
    WHERE subject_id = ? AND stay_id = ?
      AND itemid = 223835
      AND charttime >= ? AND charttime <= ?
      AND valuenum IS NOT NULL
    """
    df_fio2 = query_db(sql, [subject_id, stay_id, intime, window_end])
    
    pof2_score = 0
    pof2_value = None
    if not df_po2.empty and not df_fio2.empty:
        po2 = df_po2['valuenum'].values
        fio2 = df_fio2['valuenum'].values
        fio2_decimal = fio2 / 100.0 if fio2[0] > 1 else fio2
        ratios = []
        for p, f in zip(po2, fio2_decimal):
            if f > 0:
                ratios.append(float(p) / float(f))
        if ratios:
            worst_ratio = min(ratios)
            pof2_value = worst_ratio
            if worst_ratio >= 200:
                pof2_score = 6
            elif worst_ratio >= 100:
                pof2_score = 9
            else:
                pof2_score = 11
    components['pof2_ratio'] = pof2_score
    values['pof2_ratio'] = pof2_value
    
    # 13. URINARY OUTPUT (L/day) - total in 24h
    # Include all urine output itemids
    sql = """
    SELECT value
    FROM mimiciv_icu.outputevents
    WHERE subject_id = ? AND stay_id = ?
      AND itemid IN (226559, 226560, 226561, 226563, 226566, 226567, 226584, 226627, 226631, 226713, 227489)
      AND charttime >= ? AND charttime <= ?
      AND value IS NOT NULL
    """
    df = query_db(sql, [subject_id, stay_id, intime, window_end])
    urine_score = 0
    urine_value = None
    if not df.empty:
        total_urine_ml = float(df['value'].sum())
        urine_value = total_urine_ml / 1000.0  # Convert to L
        if urine_value >= 1.0:
            urine_score = 0
        elif urine_value >= 0.5:
            urine_score = 4
        else:
            urine_score = 11
    components['urine_output'] = urine_score
    values['urine_output'] = urine_value
    
    # 14. ADMISSION TYPE
    # SAPS II: Scheduled surgical = 0, Medical = 6, Unscheduled surgical = 8
    sql = """
    SELECT COUNT(*) as proc_count
    FROM mimiciv_hosp.procedures_icd
    WHERE hadm_id = ?
    """
    df_proc = query_db(sql, [hadm_id])
    has_surgery = df_proc.iloc[0]['proc_count'] > 0 if not df_proc.empty else False
    
    if admission_type in ['ELECTIVE', 'SURGICAL SAME DAY ADMISSION']:
        admission_score = 0  # Scheduled surgical
    elif has_surgery:
        admission_score = 8  # Unscheduled surgical
    else:
        admission_score = 6  # Medical
    components['admission_type'] = admission_score
    values['admission_type'] = admission_type
    
    # 15. CHRONIC DISEASE - check ICD codes
    chronic_score = 0
    chronic_value = None
    
    sql = """
    SELECT icd_code
    FROM mimiciv_hosp.diagnoses_icd
    WHERE hadm_id = ?
    """
    df_diag = query_db(sql, [hadm_id])
    if not df_diag.empty:
        codes = df_diag['icd_code'].astype(str).tolist()
        has_metastatic = any(c in codes for c in ['196', '197', '198', '199'])
        has_heme = any(c in codes for c in ['200', '201', '202', '203', '204', '205', '206', '207', '208'])
        has_aids = any(c in codes for c in ['042', 'V08'])
        
        if has_aids:
            chronic_score = 17
            chronic_value = 'AIDS'
        elif has_heme:
            chronic_score = 10
            chronic_value = 'Hematologic malignancy'
        elif has_metastatic:
            chronic_score = 9
            chronic_value = 'Metastatic cancer'
    
    components['chronic_disease'] = chronic_score
    values['chronic_disease'] = chronic_value
    
    # Calculate total score
    total_score = sum(components.values())
    
    # Calculate predicted mortality
    if total_score > 0:
        logit = -7.7631 + 0.0737 * total_score + 0.9971 * np.log(total_score + 1)
        predicted_mortality = np.exp(logit) / (1 + np.exp(logit))
    else:
        predicted_mortality = 0.0
    
    return {
        'saps_ii_score': total_score,
        'predicted_mortality': float(predicted_mortality),
        'components': components,
        'values': values,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'stay_id': stay_id
    }

FINAL_FUNCTION = compute_saps_ii