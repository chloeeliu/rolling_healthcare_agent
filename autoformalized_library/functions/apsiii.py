# Write the complete function in one block
def apache_iii_heart_rate(hr):
    """Calculate APACHE III points for heart rate"""
    if hr is None:
        return 0
    if hr <= 39:
        return 8
    elif hr <= 49:
        return 5
    elif hr <= 99:
        return 0
    elif hr <= 109:
        return 1
    elif hr <= 119:
        return 5
    elif hr <= 139:
        return 7
    elif hr <= 154:
        return 13
    else:
        return 17

def apache_iii_map(map_val):
    """Calculate APACHE III points for mean arterial pressure"""
    if map_val is None:
        return 0
    if map_val <= 39:
        return 23
    elif map_val <= 59:
        return 15
    elif map_val <= 69:
        return 7
    elif map_val <= 79:
        return 6
    elif map_val <= 99:
        return 0
    elif map_val <= 119:
        return 4
    elif map_val <= 129:
        return 7
    elif map_val <= 139:
        return 9
    else:
        return 10

def apache_iii_temperature(temp):
    """Calculate APACHE III points for temperature (Celsius)"""
    if temp is None:
        return 0
    if temp <= 32.9:
        return 20
    elif temp <= 33.4:
        return 16
    elif temp <= 33.9:
        return 13
    elif temp <= 34.9:
        return 8
    elif temp <= 35.9:
        return 2
    elif temp <= 39.9:
        return 0
    else:
        return 4

def apache_iii_respiratory_rate(rr):
    """Calculate APACHE III points for respiratory rate"""
    if rr is None:
        return 0
    if rr <= 5:
        return 17
    elif rr <= 11:
        return 8
    elif rr <= 13:
        return 7
    elif rr <= 24:
        return 0
    elif rr <= 34:
        return 6
    elif rr <= 39:
        return 9
    elif rr <= 49:
        return 11
    else:
        return 18

def apache_iii_pao2(pao2):
    """Calculate APACHE III points for PaO2 (when FiO2 < 0.5)"""
    if pao2 is None:
        return 0
    if pao2 >= 80:
        return 0
    elif pao2 >= 70:
        return 2
    elif pao2 >= 60:
        return 7
    elif pao2 >= 50:
        return 11
    else:
        return 15

def apache_iii_aado2(aado2):
    """Calculate APACHE III points for A-aDO2 (when FiO2 >= 0.5)"""
    if aado2 is None:
        return 0
    if aado2 < 100:
        return 0
    elif aado2 <= 249:
        return 7
    elif aado2 <= 349:
        return 9
    elif aado2 <= 499:
        return 11
    else:
        return 14

def apache_iii_hematocrit(hct):
    """Calculate APACHE III points for hematocrit"""
    if hct is None:
        return 0
    if hct < 41:
        return 3
    elif hct <= 49:
        return 0
    else:
        return 3

def apache_iii_wbc(wbc):
    """Calculate APACHE III points for WBC"""
    if wbc is None:
        return 0
    if wbc < 1.0:
        return 19
    elif wbc <= 2.9:
        return 5
    elif wbc <= 19.9:
        return 0
    elif wbc <= 24.9:
        return 1
    else:
        return 5

def apache_iii_creatinine(creat, has_arf=False):
    """Calculate APACHE III points for creatinine"""
    if creat is None:
        return 0
    if creat <= 0.4:
        return 3
    elif creat <= 1.4:
        return 0
    elif creat <= 1.94:
        points = 4
    else:
        points = 7
    if has_arf and points > 0:
        return points * 2
    return points

def apache_iii_urine_output(urine):
    """Calculate APACHE III points for urine output (mL/24h)"""
    if urine is None:
        return 0
    if urine < 400:
        return 15
    elif urine <= 599:
        return 8
    elif urine <= 899:
        return 7
    elif urine <= 1499:
        return 5
    elif urine <= 1999:
        return 4
    elif urine <= 3999:
        return 0
    else:
        return 1

def apache_iii_bun(bun):
    """Calculate APACHE III points for BUN"""
    if bun is None:
        return 0
    if bun <= 16.9:
        return 0
    elif bun <= 19:
        return 2
    elif bun <= 39:
        return 7
    elif bun <= 79:
        return 11
    else:
        return 12

def apache_iii_sodium(na):
    """Calculate APACHE III points for sodium"""
    if na is None:
        return 0
    if na <= 119:
        return 3
    elif na <= 134:
        return 2
    elif na <= 145:
        return 0
    elif na <= 154:
        return 1
    else:
        return 4

def apache_iii_albumin(albumin):
    """Calculate APACHE III points for albumin"""
    if albumin is None:
        return 0
    if albumin < 2.0:
        return 11
    elif albumin <= 2.4:
        return 6
    else:
        return 0

def apache_iii_bilirubin(bili):
    """Calculate APACHE III points for bilirubin"""
    if bili is None:
        return 0
    if bili < 2.0:
        return 0
    elif bili <= 2.9:
        return 5
    elif bili <= 4.9:
        return 6
    elif bili <= 7.9:
        return 8
    else:
        return 16

def apache_iii_glucose(glucose):
    """Calculate APACHE III points for glucose"""
    if glucose is None:
        return 0
    if glucose <= 39:
        return 8
    elif glucose <= 59:
        return 9
    elif glucose <= 199:
        return 0
    elif glucose <= 349:
        return 3
    else:
        return 5

def apache_iii_acid_base(ph, paco2):
    """Calculate APACHE III points for acid-base status (pH x PaCO2 matrix)"""
    if ph is None or paco2 is None:
        return 0
    if ph < 7.15:
        ph_row = 0
    elif ph <= 7.19:
        ph_row = 1
    elif ph <= 7.24:
        ph_row = 2
    elif ph <= 7.29:
        ph_row = 3
    elif ph <= 7.34:
        ph_row = 4
    elif ph <= 7.39:
        ph_row = 5
    elif ph <= 7.44:
        ph_row = 6
    elif ph <= 7.49:
        ph_row = 7
    elif ph <= 7.54:
        ph_row = 8
    elif ph <= 7.59:
        ph_row = 9
    elif ph <= 7.64:
        ph_row = 10
    else:
        ph_row = 11
    if paco2 < 25:
        paco2_col = 0
    elif paco2 <= 29:
        paco2_col = 1
    elif paco2 <= 34:
        paco2_col = 2
    elif paco2 <= 39:
        paco2_col = 3
    elif paco2 <= 44:
        paco2_col = 4
    elif paco2 <= 49:
        paco2_col = 5
    elif paco2 <= 54:
        paco2_col = 6
    elif paco2 <= 59:
        paco2_col = 7
    elif paco2 <= 64:
        paco2_col = 8
    else:
        paco2_col = 9
    acid_base_matrix = [
        [12, 4, 6, 7, 7, 0, 0, 0, 0, 0],
        [12, 4, 3, 3, 2, 0, 0, 0, 0, 0],
        [12, 2, 1, 1, 0, 0, 0, 0, 0, 0],
        [9, 2, 1, 0, 0, 0, 0, 0, 0, 0],
        [7, 2, 0, 0, 0, 1, 1, 0, 0, 0],
        [7, 0, 0, 0, 0, 0, 1, 3, 0, 0],
        [6, 0, 0, 0, 0, 0, 1, 3, 5, 0],
        [3, 0, 0, 0, 0, 0, 2, 5, 7, 9],
        [3, 2, 2, 2, 0, 0, 3, 7, 9, 11],
        [0, 3, 3, 3, 2, 3, 5, 9, 11, 12],
        [0, 3, 5, 5, 3, 5, 7, 11, 12, 12],
        [0, 3, 12, 12, 12, 12, 12, 12, 12, 12]
    ]
    return acid_base_matrix[ph_row][paco2_col]

def apache_iii_gcs(gcs_total):
    """Calculate APACHE III points for GCS"""
    if gcs_total is None:
        return 0
    gcs_points = {15: 0, 14: 3, 13: 5, 12: 7, 11: 10, 10: 13, 9: 15, 8: 18, 7: 22, 6: 26, 5: 33, 4: 39, 3: 48}
    return gcs_points.get(gcs_total, 0)

def apache_iii_age(age):
    """Calculate APACHE III points for age"""
    if age is None:
        return 0
    if age < 45:
        return 0
    elif age <= 59:
        return 5
    elif age <= 64:
        return 11
    elif age <= 69:
        return 13
    elif age <= 74:
        return 16
    elif age <= 84:
        return 17
    else:
        return 24

def has_chronic_condition(icd_codes, condition_type):
    """Check if patient has a specific chronic condition based on ICD-9 codes."""
    icd_strs = [str(code) for code in icd_codes if pd.notna(code)]
    if condition_type == 'aids':
        for code in icd_strs:
            if code == '042' or code.startswith('043') or code == 'V08':
                return True
        return False
    elif condition_type == 'hepatic_failure':
        for code in icd_strs:
            if code in ['5712', '5715', '5716', '5718', '5719', '5714', '4560', '4561', '4562', '5722', '5723', '5724', '5732', '5733']:
                return True
        return False
    elif condition_type == 'lymphoma':
        for code in icd_strs:
            if code.startswith('200') or code.startswith('202') or code.startswith('203'):
                return True
        return False
    elif condition_type == 'metastatic_cancer':
        for code in icd_strs:
            if code.startswith('196') or code.startswith('197') or code.startswith('198') or code.startswith('199'):
                return True
        return False
    elif condition_type == 'leukemia_myeloma':
        for code in icd_strs:
            if code.startswith('204') or code.startswith('205') or code.startswith('206') or code.startswith('207') or code.startswith('208'):
                return True
            if code.startswith('2030') or code.startswith('2031') or code.startswith('2032') or code.startswith('2033') or code.startswith('2034') or code.startswith('2035') or code.startswith('2036') or code.startswith('2037') or code.startswith('2038') or code.startswith('2039'):
                return True
        return False
    elif condition_type == 'immunosuppression':
        for code in icd_strs:
            if code.startswith('V581') or code.startswith('V586'):
                return True
        return False
    return False

def get_chronic_health_points(icd_codes, admission_type_str):
    """Calculate chronic health points for APACHE III. Returns MAXIMUM, not sum."""
    admission_type_upper = str(admission_type_str).upper() if admission_type_str else ""
    is_elective_postop = 'ELECTIVE' in admission_type_upper
    is_emergency_postop = 'SURGICAL SAME DAY' in admission_type_upper or ('URGENT' in admission_type_upper and 'OBSERVATION' not in admission_type_upper)
    is_non_operative = not is_elective_postop and not is_emergency_postop
    if is_elective_postop:
        return 0
    points_list = []
    if has_chronic_condition(icd_codes, 'aids'):
        points_list.append(11)
    if has_chronic_condition(icd_codes, 'hepatic_failure'):
        points_list.append(4)
    if has_chronic_condition(icd_codes, 'lymphoma'):
        points_list.append(13)
    if has_chronic_condition(icd_codes, 'metastatic_cancer'):
        points_list.append(14)
    if has_chronic_condition(icd_codes, 'leukemia_myeloma'):
        points_list.append(10)
    if has_chronic_condition(icd_codes, 'immunosuppression'):
        points_list.append(10)
    return max(points_list) if points_list else 0

def compute_apache_iii(stay_id):
    """Compute APACHE III score for a given ICU stay."""
    from datetime import datetime, timedelta
    sql = "SELECT subject_id, hadm_id, intime FROM mimiciv_icu.icustays WHERE stay_id = ?"
    stay_info = query_db(sql, params=[stay_id])
    if len(stay_info) == 0:
        raise ValueError(f"Stay ID {stay_id} not found")
    subject_id = int(stay_info.iloc[0]['subject_id'])
    hadm_id = int(stay_info.iloc[0]['hadm_id'])
    intime = stay_info.iloc[0]['intime']
    intime_dt = datetime.strptime(str(intime), '%Y-%m-%d %H:%M:%S')
    first_day_end = intime_dt + timedelta(hours=24)
    first_day_end_str = first_day_end.strftime('%Y-%m-%d %H:%M:%S')
    sql = "SELECT anchor_age FROM mimiciv_hosp.patients WHERE subject_id = ?"
    patient_info = query_db(sql, params=[subject_id])
    age = int(patient_info.iloc[0]['anchor_age']) if len(patient_info) > 0 else None
    sql = "SELECT admission_type FROM mimiciv_hosp.admissions WHERE hadm_id = ?"
    admission_info = query_db(sql, params=[hadm_id])
    admission_type = admission_info.iloc[0]['admission_type'] if len(admission_info) > 0 else None
    sql = "SELECT icd_code FROM mimiciv_hosp.diagnoses_icd WHERE hadm_id = ?"
    icd_info = query_db(sql, params=[hadm_id])
    icd_codes = icd_info['icd_code'].tolist() if len(icd_info) > 0 else []
    sql = "SELECT itemid, valuenum, charttime FROM mimiciv_icu.chartevents WHERE stay_id = ? AND charttime >= ? AND charttime <= ? AND valuenum IS NOT NULL"
    chartevents = query_db(sql, params=[stay_id, intime, first_day_end_str])
    def get_values(itemids):
        if isinstance(itemids, int):
            itemids = [itemids]
        return chartevents[chartevents['itemid'].isin(itemids)]
    hr_df = get_values(220045)
    map_df = get_values([220052, 220181])
    rr_df = get_values(220210)
    temp_df = get_values(223762)
    hct_df = get_values(220545)
    wbc_df = get_values(220546)
    creat_df = get_values(220615)
    bun_df = get_values(225624)
    na_df = get_values(220645)
    glucose_df = get_values(220621)
    albumin_df = get_values(227456)
    bili_df = get_values(225690)
    ph_df = get_values(223830)
    paco2_df = get_values(220235)
    pao2_df = get_values(220224)
    fio2_df = get_values(223835)
    gcs_eye_df = get_values(220739)
    gcs_verbal_df = get_values(223900)
    gcs_motor_df = get_values(223901)
    hr_values = hr_df['valuenum'].tolist() if len(hr_df) > 0 else []
    hr_points = [apache_iii_heart_rate(hr) for hr in hr_values] if hr_values else [0]
    hr_score = max(hr_points)
    map_values = map_df['valuenum'].tolist() if len(map_df) > 0 else []
    map_points = [apache_iii_map(m) for m in map_values] if map_values else [0]
    map_score = max(map_points)
    temp_values = temp_df['valuenum'].tolist() if len(temp_df) > 0 else []
    temp_points = [apache_iii_temperature(t) for t in temp_values] if temp_values else [0]
    temp_score = max(temp_points)
    rr_values = rr_df['valuenum'].tolist() if len(rr_df) > 0 else []
    rr_points = [apache_iii_respiratory_rate(r) for r in rr_values] if rr_values else [0]
    rr_score = max(rr_points)
    fio2_values = fio2_df['valuenum'].tolist() if len(fio2_df) > 0 else []
    pao2_values = pao2_df['valuenum'].tolist() if len(pao2_df) > 0 else []
    paco2_values = paco2_df['valuenum'].tolist() if len(paco2_df) > 0 else []
    oxygenation_score = 0
    if pao2_values:
        if fio2_values:
            max_fio2 = max(fio2_values)
            if max_fio2 > 1:
                max_fio2 = max_fio2 / 100.0
            min_pao2 = min(pao2_values)
            avg_paco2 = sum(paco2_values) / len(paco2_values) if paco2_values else 40
            if max_fio2 < 0.5:
                oxygenation_score = apache_iii_pao2(min_pao2)
            else:
                aado2 = (max_fio2 * 713) - (avg_paco2 / 0.8) - min_pao2
                oxygenation_score = apache_iii_aado2(aado2)
        else:
            oxygenation_score = apache_iii_pao2(min(pao2_values))
    hct_values = hct_df['valuenum'].tolist() if len(hct_df) > 0 else []
    hct_points = [apache_iii_hematocrit(h) for h in hct_values] if hct_values else [0]
    hct_score = max(hct_points)
    wbc_values = wbc_df['valuenum'].tolist() if len(wbc_df) > 0 else []
    wbc_points = [apache_iii_wbc(w) for w in wbc_values] if wbc_values else [0]
    wbc_score = max(wbc_points)
    creat_values = creat_df['valuenum'].tolist() if len(creat_df) > 0 else []
    max_creat = max(creat_values) if creat_values else None
    sql = "SELECT value FROM mimiciv_icu.outputevents WHERE stay_id = ? AND itemid IN (226566, 226627, 226631, 227489) AND charttime >= ? AND charttime <= ? AND value IS NOT NULL"
    urine_df = query_db(sql, params=[stay_id, intime, first_day_end_str])
    urine_values = urine_df['value'].astype(float).tolist() if len(urine_df) > 0 else []
    total_urine = sum(urine_values) if urine_values else None
    has_arf = False
    if max_creat is not None and max_creat >= 1.7:
        if total_urine is not None and total_urine < 500:
            has_arf = True
    creat_points = [apache_iii_creatinine(c, has_arf) for c in creat_values] if creat_values else [0]
    creat_score = max(creat_points)
    urine_score = apache_iii_urine_output(total_urine)
    bun_values = bun_df['valuenum'].tolist() if len(bun_df) > 0 else []
    bun_points = [apache_iii_bun(b) for b in bun_values] if bun_values else [0]
    bun_score = max(bun_points)
    na_values = na_df['valuenum'].tolist() if len(na_df) > 0 else []
    na_points = [apache_iii_sodium(n) for n in na_values] if na_values else [0]
    na_score = max(na_points)
    albumin_values = albumin_df['valuenum'].tolist() if len(albumin_df) > 0 else []
    albumin_points = [apache_iii_albumin(a) for a in albumin_values] if albumin_values else [0]
    albumin_score = max(albumin_points)
    bili_values = bili_df['valuenum'].tolist() if len(bili_df) > 0 else []
    bili_points = [apache_iii_bilirubin(b) for b in bili_values] if bili_values else [0]
    bili_score = max(bili_points)
    glucose_values = glucose_df['valuenum'].tolist() if len(glucose_df) > 0 else []
    glucose_points = [apache_iii_glucose(g) for g in glucose_values] if glucose_values else [0]
    glucose_score = max(glucose_points)
    ph_values = ph_df['valuenum'].tolist() if len(ph_df) > 0 else []
    paco2_values = paco2_df['valuenum'].tolist() if len(paco2_df) > 0 else []
    acid_base_score = 0
    if ph_values and paco2_values:
        max_ab_points = 0
        for ph in ph_values:
            for paco2 in paco2_values:
                ab_points = apache_iii_acid_base(ph, paco2)
                if ab_points > max_ab_points:
                    max_ab_points = ab_points
        acid_base_score = max_ab_points
    gcs_eye_values = gcs_eye_df['valuenum'].tolist() if len(gcs_eye_df) > 0 else []
    gcs_verbal_values = gcs_verbal_df['valuenum'].tolist() if len(gcs_verbal_df) > 0 else []
    gcs_motor_values = gcs_motor_df['valuenum'].tolist() if len(gcs_motor_df) > 0 else []
    gcs_score = 0
    if gcs_eye_values and gcs_verbal_values and gcs_motor_values:
        min_gcs = min(gcs_eye_values) + min(gcs_verbal_values) + min(gcs_motor_values)
        gcs_score = apache_iii_gcs(min_gcs)
    aps_score = hr_score + map_score + temp_score + rr_score + oxygenation_score + hct_score + wbc_score + creat_score + urine_score + bun_score + na_score + albumin_score + bili_score + glucose_score + acid_base_score + gcs_score
    age_points = apache_iii_age(age)
    chronic_health_points = get_chronic_health_points(icd_codes, admission_type)
    total_score = aps_score + age_points + chronic_health_points
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': str(intime),
        'aps_score': aps_score,
        'age_points': age_points,
        'chronic_health_points': chronic_health_points,
        'total_score': total_score,
        'component_scores': {
            'heart_rate': hr_score,
            'map': map_score,
            'temperature': temp_score,
            'respiratory_rate': rr_score,
            'oxygenation': oxygenation_score,
            'hematocrit': hct_score,
            'wbc': wbc_score,
            'creatinine': creat_score,
            'urine_output': urine_score,
            'bun': bun_score,
            'sodium': na_score,
            'albumin': albumin_score,
            'bilirubin': bili_score,
            'glucose': glucose_score,
            'acid_base': acid_base_score,
            'gcs': gcs_score
        }
    }

FINAL_FUNCTION = compute_apache_iii