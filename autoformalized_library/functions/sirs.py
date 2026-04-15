import pandas as pd
import numpy as np

def compute_sirs(stay_id):
    """
    Calculate SIRS (Systemic Inflammatory Response Syndrome) score for a patient's ICU stay.
    
    SIRS is defined by the presence of 2 or more of 4 criteria:
    1. Temperature: > 38.0°C (100.4°F) OR < 36.0°C (96.8°F)
    2. Heart Rate: > 90 bpm
    3. Respiratory Rate: > 20 breaths/min OR PaCO2 < 32 mmHg
    4. WBC: > 12,000 cells/μL OR < 4,000 cells/μL OR > 10% bands
    
    The function evaluates the worst values within the first 24 hours of ICU admission.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'stay_id': the ICU stay identifier (int)
        - 'subject_id': patient identifier (int)
        - 'hadm_id': hospital admission identifier (int)
        - 'sirs_score': total SIRS score (0-4) (int)
        - 'sirs_positive': boolean indicating if SIRS criteria met (score >= 2)
        - 'criteria': dict with individual criterion results (bool for each)
        - 'temperature_celsius': temperature in Celsius (float or None)
        - 'heart_rate': heart rate in bpm (float or None)
        - 'respiratory_rate': respiratory rate in breaths/min (float or None)
        - 'wbc_count': WBC count in K/uL (float or None)
        - 'band_percent': band percentage (float or None)
        - 'paco2': PaCO2 in mmHg (float or None)
    """
    # Get stay information
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        return {'error': 'Stay ID not found'}
    
    stay_id_val = int(stay_info.iloc[0]['stay_id'])
    subject_id = int(stay_info.iloc[0]['subject_id'])
    hadm_id = int(stay_info.iloc[0]['hadm_id'])
    
    # Get vital signs within first 24 hours
    vitals = query_db(f"""
        SELECT ce.charttime, ce.itemid, ce.valuenum, ce.valueuom
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.icustays s ON ce.stay_id = s.stay_id
        WHERE ce.stay_id = {stay_id}
          AND ce.charttime >= s.intime 
          AND ce.charttime < s.intime + INTERVAL '24 hours'
          AND ce.itemid IN (223761, 223762, 220045, 220210)
          AND ce.valuenum IS NOT NULL
    """)
    
    # Get WBC from labevents within first 24 hours
    wbc_data = query_db(f"""
        SELECT le.charttime, le.valuenum, le.valueuom
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_icu.icustays s ON le.hadm_id = s.hadm_id AND le.subject_id = s.subject_id
        WHERE s.stay_id = {stay_id}
          AND le.charttime >= s.intime 
          AND le.charttime < s.intime + INTERVAL '24 hours'
          AND le.itemid IN (51300, 51301, 51755, 51756)
          AND le.valuenum IS NOT NULL
    """)
    
    # Get bands from labevents
    bands_data = query_db(f"""
        SELECT le.charttime, le.valuenum
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_icu.icustays s ON le.hadm_id = s.hadm_id AND le.subject_id = s.subject_id
        WHERE s.stay_id = {stay_id}
          AND le.charttime >= s.intime 
          AND le.charttime < s.intime + INTERVAL '24 hours'
          AND le.itemid = 51144
          AND le.valuenum IS NOT NULL
    """)
    
    # Get PaCO2 from labevents
    paco2_data = query_db(f"""
        SELECT le.charttime, le.valuenum
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_icu.icustays s ON le.hadm_id = s.hadm_id AND le.subject_id = s.subject_id
        WHERE s.stay_id = {stay_id}
          AND le.charttime >= s.intime 
          AND le.charttime < s.intime + INTERVAL '24 hours'
          AND le.itemid = 50818
          AND le.valuenum IS NOT NULL
    """)
    
    # Process temperature (convert Fahrenheit to Celsius if needed)
    temp_f = vitals[vitals['itemid'] == 223761]['valuenum'].tolist()
    temp_c = vitals[vitals['itemid'] == 223762]['valuenum'].tolist()
    
    # Convert F to C
    all_temps_c = temp_c + [(f - 32) * 5/9 for f in temp_f]
    
    # Process heart rate
    heart_rates = vitals[vitals['itemid'] == 220045]['valuenum'].tolist()
    
    # Process respiratory rate
    resp_rates = vitals[vitals['itemid'] == 220210]['valuenum'].tolist()
    
    # Process WBC
    wbc_counts = wbc_data['valuenum'].tolist()
    
    # Process bands
    band_percents = bands_data['valuenum'].tolist()
    
    # Process PaCO2
    paco2_values = paco2_data['valuenum'].tolist()
    
    # Calculate criteria using worst values
    # Temperature criterion: > 38.0°C OR < 36.0°C
    temp_criterion = False
    temp_value = None
    if all_temps_c:
        max_temp = max(all_temps_c)
        min_temp = min(all_temps_c)
        temp_criterion = max_temp > 38.0 or min_temp < 36.0
        temp_value = max_temp if max_temp > 38.0 else min_temp if min_temp < 36.0 else all_temps_c[0]
    
    # Heart rate criterion: > 90 bpm
    hr_criterion = False
    hr_value = None
    if heart_rates:
        max_hr = max(heart_rates)
        hr_value = max_hr
        hr_criterion = max_hr > 90
    
    # Respiratory rate criterion: > 20 breaths/min OR PaCO2 < 32 mmHg
    rr_criterion = False
    rr_value = None
    paco2_value = None
    if resp_rates:
        max_rr = max(resp_rates)
        rr_value = max_rr
        rr_criterion = max_rr > 20
    if paco2_values:
        min_paco2 = min(paco2_values)
        paco2_value = min_paco2
        rr_criterion = rr_criterion or (min_paco2 < 32)
    
    # WBC criterion: > 12 OR < 4 OR bands > 10%
    wbc_criterion = False
    wbc_value = None
    band_value = None
    if wbc_counts:
        max_wbc = max(wbc_counts)
        min_wbc = min(wbc_counts)
        wbc_value = max_wbc if max_wbc > 12 else min_wbc if min_wbc < 4 else wbc_counts[0]
        wbc_criterion = max_wbc > 12 or min_wbc < 4
    if band_percents:
        max_bands = max(band_percents)
        band_value = max_bands
        wbc_criterion = wbc_criterion or (max_bands > 10)
    
    # Calculate SIRS score
    sirs_score = sum([temp_criterion, hr_criterion, rr_criterion, wbc_criterion])
    sirs_positive = sirs_score >= 2
    
    # Convert values to native Python types
    def to_native(val):
        if val is None:
            return None
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return float(val)
        return val
    
    return {
        'stay_id': to_native(stay_id_val),
        'subject_id': to_native(subject_id),
        'hadm_id': to_native(hadm_id),
        'sirs_score': int(sirs_score),
        'sirs_positive': bool(sirs_positive),
        'criteria': {
            'temperature': bool(temp_criterion),
            'heart_rate': bool(hr_criterion),
            'respiratory_rate': bool(rr_criterion),
            'wbc': bool(wbc_criterion)
        },
        'temperature_celsius': to_native(temp_value),
        'heart_rate': to_native(hr_value),
        'respiratory_rate': to_native(rr_value),
        'wbc_count': to_native(wbc_value),
        'band_percent': to_native(band_value),
        'paco2': to_native(paco2_value)
    }

FINAL_FUNCTION = compute_sirs