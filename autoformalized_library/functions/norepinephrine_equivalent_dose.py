import pandas as pd

def compute_norepinephrine_equivalent_dose(stay_id):
    """
    Calculate the norepinephrine equivalent dose for a patient's ICU stay.
    
    Conversion factors:
    - Norepinephrine, Epinephrine, Dopamine: 1:1 mcg/kg/min
    - Phenylephrine: 0.1 mcg/kg/min NE equivalent per mcg/kg/min
    - Vasopressin: 0.04 units/hour ≈ 1 mcg/kg/min norepinephrine equivalent
      (i.e., 1 units/hour vasopressin = 25 mcg/kg/min NE equivalent)
    
    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.
    
    Returns:
    --------
    dict
        A dictionary containing:
        - 'max_ne_equivalent': float - Maximum norepinephrine equivalent dose (mcg/kg/min)
        - 'min_ne_equivalent': float - Minimum norepinephrine equivalent dose (mcg/kg/min)
        - 'avg_ne_equivalent': float - Average norepinephrine equivalent dose (mcg/kg/min)
        - 'received_vasopressors': bool - Whether any vasopressors were received
        - 'agents_used': list - List of vasopressor agents used
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID
    """
    
    # Vasopressor item IDs and their conversion factors
    # Format: itemid: (label, conversion_factor)
    vasopressors = {
        221906: ('Norepinephrine', 1.0),      # 1:1
        221289: ('Epinephrine', 1.0),         # 1:1
        221662: ('Dopamine', 1.0),            # 1:1
        221749: ('Phenylephrine', 0.1),       # 0.1 conversion
        222315: ('Vasopressin', 25.0),        # 0.04 units/hr = 1 mcg/kg/min NE
    }
    
    # Query all vasopressor infusions for this stay
    itemids = list(vasopressors.keys())
    itemid_str = ','.join(map(str, itemids))
    
    sql = f"""
    SELECT ie.itemid, ie.starttime, ie.rate, ie.rateuom
    FROM mimiciv_icu.inputevents ie
    WHERE ie.stay_id = {stay_id}
      AND ie.itemid IN ({itemid_str})
      AND ie.rate IS NOT NULL
    ORDER BY ie.starttime
    """
    
    df = query_db(sql)
    
    if df.empty:
        return {
            'max_ne_equivalent': 0.0,
            'min_ne_equivalent': 0.0,
            'avg_ne_equivalent': 0.0,
            'received_vasopressors': False,
            'agents_used': [],
            'subject_id': None,
            'hadm_id': None
        }
    
    # Get patient info
    patient_info_sql = f"""
    SELECT subject_id, hadm_id
    FROM mimiciv_icu.icustays
    WHERE stay_id = {stay_id}
    LIMIT 1
    """
    patient_info = query_db(patient_info_sql)
    subject_id = int(patient_info['subject_id'].iloc[0]) if not patient_info.empty else None
    hadm_id = int(patient_info['hadm_id'].iloc[0]) if not patient_info.empty else None
    
    # Convert rates to norepinephrine equivalents
    df['label'] = df['itemid'].map(lambda x: vasopressors[x][0])
    df['ne_equivalent'] = df.apply(
        lambda row: row['rate'] * vasopressors[row['itemid']][1], 
        axis=1
    )
    
    # Track which agents were used
    agents_used = df['label'].unique().tolist()
    
    # Calculate summary statistics
    max_ne = float(df['ne_equivalent'].max())
    min_ne = float(df['ne_equivalent'].min())
    avg_ne = float(df['ne_equivalent'].mean())
    
    return {
        'max_ne_equivalent': round(max_ne, 2),
        'min_ne_equivalent': round(min_ne, 2),
        'avg_ne_equivalent': round(avg_ne, 2),
        'received_vasopressors': True,
        'agents_used': agents_used,
        'subject_id': subject_id,
        'hadm_id': hadm_id
    }

FINAL_FUNCTION = compute_norepinephrine_equivalent_dose