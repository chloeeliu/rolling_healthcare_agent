import pandas as pd

def first_day_bg(stay_id=None, subject_id=None, hadm_id=None):
    """
    Extract blood gas information for the first day of an ICU stay.
    
    This function retrieves blood gas measurements (lactate, pH) from both 
    chartevents (ICU) and labevents (hospital) tables for the period from 
    hospital admission to 24 hours after ICU admission.
    
    Parameters
    ----------
    stay_id : int, optional
        The ICU stay ID. If provided, returns data for that specific stay.
    subject_id : int, optional
        The patient's subject_id. If provided with hadm_id, returns data for 
        the first ICU stay during that admission.
    hadm_id : int, optional
        The hospital admission ID. Used with subject_id to identify the admission.
    
    Returns
    -------
    dict
        A dictionary containing first-day blood gas information:
        - 'stay_id': The ICU stay ID (int)
        - 'subject_id': Patient identifier (int)
        - 'hadm_id': Hospital admission ID (int)
        - 'intime': ICU admission time (str)
        - 'first_lactate': First lactate value (mmol/L) during the time window (float or None)
        - 'first_pH': First pH value during the time window (float or None)
        - 'has_elevated_lactate': Boolean indicating if first lactate >= 2 mmol/L
        - 'has_acidosis': Boolean indicating if first pH <= 7.35
        - 'has_severe_acidosis': Boolean indicating if first pH <= 7.20
        - 'lactate_measurements': List of lactate values with timestamps
        - 'ph_measurements': List of pH values with timestamps
    
    Raises
    ------
    ValueError
        If no valid identifier is provided.
    """
    # Determine stay_id from inputs
    if stay_id is not None:
        stay_query = f"WHERE stay_id = {stay_id}"
    elif subject_id is not None and hadm_id is not None:
        # Get the first ICU stay for this admission
        stay_result = query_db(f"""
            SELECT stay_id
            FROM mimiciv_icu.icustays
            WHERE subject_id = {subject_id} AND hadm_id = {hadm_id}
            ORDER BY intime
            LIMIT 1
        """)
        if stay_result.empty:
            raise ValueError(f"No ICU stay found for subject_id={subject_id}, hadm_id={hadm_id}")
        stay_id = stay_result.iloc[0]['stay_id']
        stay_query = f"WHERE stay_id = {stay_id}"
    else:
        raise ValueError("Must provide stay_id or both subject_id and hadm_id")
    
    # Get stay information
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime
        FROM mimiciv_icu.icustays
        {stay_query}
    """)
    
    if stay_info.empty:
        raise ValueError(f"No ICU stay found with stay_id={stay_id}")
    
    stay_id = int(stay_info.iloc[0]['stay_id'])
    subject_id = int(stay_info.iloc[0]['subject_id'])
    hadm_id = int(stay_info.iloc[0]['hadm_id'])
    intime = str(stay_info.iloc[0]['intime'])
    
    # Get hospital admission time
    admission_info = query_db(f"""
        SELECT admittime
        FROM mimiciv_hosp.admissions
        WHERE hadm_id = {hadm_id}
    """)
    admittime = str(admission_info.iloc[0]['admittime'])
    
    # Query lactate from chartevents (ICU) - within time window
    chart_lactate = query_db(f"""
        SELECT 
            c.valuenum as lactate,
            c.charttime
        FROM mimiciv_icu.chartevents c
        WHERE c.stay_id = {stay_id}
            AND c.itemid = 225668  -- Lactic Acid
            AND c.valuenum IS NOT NULL
            AND c.charttime >= CAST('{admittime}' AS TIMESTAMP)
            AND c.charttime < CAST('{intime}' AS TIMESTAMP) + INTERVAL '24 hours'
    """)
    
    # Query lactate from labevents (hospital) - within time window
    lab_lactate = query_db(f"""
        SELECT 
            l.valuenum as lactate,
            l.charttime
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = {subject_id}
            AND l.hadm_id = {hadm_id}
            AND l.itemid IN (50813, 52442, 53154)  -- Lactate
            AND l.valuenum IS NOT NULL
            AND l.charttime >= CAST('{admittime}' AS TIMESTAMP)
            AND l.charttime < CAST('{intime}' AS TIMESTAMP) + INTERVAL '24 hours'
    """)
    
    # Query pH from chartevents (ICU) - within time window
    chart_ph = query_db(f"""
        SELECT 
            c.valuenum as ph,
            c.charttime
        FROM mimiciv_icu.chartevents c
        WHERE c.stay_id = {stay_id}
            AND c.itemid IN (220274, 223830)  -- PH (Venous), PH (Arterial)
            AND c.valuenum IS NOT NULL
            AND c.charttime >= CAST('{admittime}' AS TIMESTAMP)
            AND c.charttime < CAST('{intime}' AS TIMESTAMP) + INTERVAL '24 hours'
    """)
    
    # Query pH from labevents (hospital) - within time window
    lab_ph = query_db(f"""
        SELECT 
            l.valuenum as ph,
            l.charttime
        FROM mimiciv_hosp.labevents l
        WHERE l.subject_id = {subject_id}
            AND l.hadm_id = {hadm_id}
            AND l.itemid IN (50820, 50831, 52041)  -- pH
            AND l.valuenum IS NOT NULL
            AND l.charttime >= CAST('{admittime}' AS TIMESTAMP)
            AND l.charttime < CAST('{intime}' AS TIMESTAMP) + INTERVAL '24 hours'
    """)
    
    # Combine lactate measurements
    all_lactate = pd.concat([
        chart_lactate.assign(source='chartevents'),
        lab_lactate.assign(source='labevents')
    ], ignore_index=True)
    
    # Combine pH measurements
    all_ph = pd.concat([
        chart_ph.assign(source='chartevents'),
        lab_ph.assign(source='labevents')
    ], ignore_index=True)
    
    # Sort by charttime to get first measurement
    if not all_lactate.empty:
        all_lactate = all_lactate.sort_values('charttime')
    if not all_ph.empty:
        all_ph = all_ph.sort_values('charttime')
    
    # Get first measurements
    first_lactate = float(all_lactate['lactate'].iloc[0]) if not all_lactate.empty else None
    first_ph = float(all_ph['ph'].iloc[0]) if not all_ph.empty else None
    
    # Clinical flags based on FIRST measurements
    has_elevated_lactate = first_lactate is not None and first_lactate >= 2.0
    has_acidosis = first_ph is not None and first_ph <= 7.35
    has_severe_acidosis = first_ph is not None and first_ph <= 7.20
    
    # Format measurements for output
    lactate_measurements = []
    if not all_lactate.empty:
        for _, row in all_lactate.iterrows():
            lactate_measurements.append({
                'value': float(row['lactate']),
                'charttime': str(row['charttime']),
                'source': row['source']
            })
    
    ph_measurements = []
    if not all_ph.empty:
        for _, row in all_ph.iterrows():
            ph_measurements.append({
                'value': float(row['ph']),
                'charttime': str(row['charttime']),
                'source': row['source']
            })
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': intime,
        'first_lactate': first_lactate,
        'first_pH': first_ph,
        'has_elevated_lactate': has_elevated_lactate,
        'has_acidosis': has_acidosis,
        'has_severe_acidosis': has_severe_acidosis,
        'lactate_measurements': lactate_measurements,
        'ph_measurements': ph_measurements
    }

FINAL_FUNCTION = first_day_bg