import pandas as pd
from typing import Optional, Dict, Any

def blood_differential(stay_id: Optional[int] = None, 
                       subject_id: Optional[int] = None,
                       hadm_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Extract blood differential information for a patient's ICU stay.
    
    This function retrieves comprehensive blood differential data including WBC count,
    band neutrophils, and other differential components (neutrophils, lymphocytes, 
    monocytes, eosinophils, basophils) during an ICU stay.
    
    Parameters
    ----------
    stay_id : int, optional
        The ICU stay identifier. If provided, data is filtered to this specific stay.
    subject_id : int, optional
        The patient identifier. Can be used alone or with hadm_id.
    hadm_id : int, optional
        The hospital admission identifier. Used with subject_id if stay_id not provided.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'subject_id': patient identifier (int or None)
        - 'hadm_id': hospital admission identifier (int or None)
        - 'stay_id': ICU stay identifier (int or None)
        - 'wbc_count': list of WBC count values during stay (list of float)
        - 'max_wbc_count': maximum WBC count during stay (float or None)
        - 'min_wbc_count': minimum WBC count during stay (float or None)
        - 'has_elevated_wbc': boolean indicating if WBC > 12 K/uL at any point
        - 'band_percent': list of band neutrophil percentages during stay (list of float)
        - 'max_band_percent': maximum band percentage during stay (float or None)
        - 'has_left_shift': boolean indicating if bands > 10% at any point
        - 'neutrophil_percent': list of neutrophil percentages (list of float)
        - 'lymphocyte_percent': list of lymphocyte percentages (list of float)
        - 'monocyte_percent': list of monocyte percentages (list of float)
        - 'eosinophil_percent': list of eosinophil percentages (list of float)
        - 'basophil_percent': list of basophil percentages (list of float)
        - 'absolute_neutrophil_count': list of absolute neutrophil counts (list of float)
        - 'absolute_lymphocyte_count': list of absolute lymphocyte counts (list of float)
        - 'absolute_monocyte_count': list of absolute monocyte counts (list of float)
        - 'absolute_eosinophil_count': list of absolute eosinophil counts (list of float)
        - 'absolute_basophil_count': list of absolute basophil counts (list of float)
    
    Raises
    ------
    ValueError
        If no patient identifier is provided.
    
    Examples
    --------
    >>> blood_differential(stay_id=34477328)
    {'subject_id': 18871238, 'hadm_id': 27601223, 'stay_id': 34477328,
     'wbc_count': [15.4], 'max_wbc_count': 15.4, 'min_wbc_count': 15.4,
     'has_elevated_wbc': True, 'band_percent': [], 'max_band_percent': None,
     'has_left_shift': False, ...}
    """
    
    # Validate input
    if stay_id is None and subject_id is None and hadm_id is None:
        raise ValueError("At least one of stay_id, subject_id, or hadm_id must be provided")
    
    # Define item IDs for blood differential components
    # From d_labitems table
    WBC_COUNT = 51300
    WBC_COUNT_ALT = 51301  # "White Blood Cells" - alternative WBC item
    BANDS = 51144
    NEUTROPHILS = 51256
    LYMPHOCYTES = 51244
    MONOCYTES = 51254
    EOSINOPHILS = 51200
    BASOPHILS = 51146
    ABS_NEUTROPHIL = 52075
    ABS_LYMPHOCYTE = 51133
    ABS_LYMPHOCYTE_ALT = 52769  # Alternative Absolute Lymphocyte Count
    ABS_MONOCYTE = 52074
    ABS_EOSINOPHIL = 52073
    ABS_BASOPHIL = 52069
    
    # Build the base query
    if stay_id is not None:
        # Query with stay_id - join with icustays to get time window
        sql = f"""
        SELECT 
            icu.subject_id,
            icu.hadm_id,
            icu.stay_id,
            le.itemid,
            dl.label,
            le.charttime,
            le.valuenum,
            le.valueuom
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_hosp.d_labitems dl ON le.itemid = dl.itemid
        JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
        WHERE icu.stay_id = {stay_id}
        AND le.itemid IN ({WBC_COUNT}, {WBC_COUNT_ALT}, {BANDS}, {NEUTROPHILS}, {LYMPHOCYTES}, {MONOCYTES}, 
                          {EOSINOPHILS}, {BASOPHILS}, {ABS_NEUTROPHIL}, {ABS_LYMPHOCYTE}, {ABS_LYMPHOCYTE_ALT},
                          {ABS_MONOCYTE}, {ABS_EOSINOPHIL}, {ABS_BASOPHIL})
        AND le.charttime >= icu.intime
        AND le.charttime <= icu.outtime
        ORDER BY le.charttime, le.itemid
        """
    elif subject_id is not None and hadm_id is not None:
        # Query with subject_id and hadm_id - get all ICU stays for this admission
        sql = f"""
        SELECT 
            icu.subject_id,
            icu.hadm_id,
            icu.stay_id,
            le.itemid,
            dl.label,
            le.charttime,
            le.valuenum,
            le.valueuom
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_hosp.d_labitems dl ON le.itemid = dl.itemid
        JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
        WHERE icu.subject_id = {subject_id}
        AND icu.hadm_id = {hadm_id}
        AND le.itemid IN ({WBC_COUNT}, {WBC_COUNT_ALT}, {BANDS}, {NEUTROPHILS}, {LYMPHOCYTES}, {MONOCYTES}, 
                          {EOSINOPHILS}, {BASOPHILS}, {ABS_NEUTROPHIL}, {ABS_LYMPHOCYTE}, {ABS_LYMPHOCYTE_ALT},
                          {ABS_MONOCYTE}, {ABS_EOSINOPHIL}, {ABS_BASOPHIL})
        AND le.charttime >= icu.intime
        AND le.charttime <= icu.outtime
        ORDER BY le.charttime, le.itemid
        """
    elif subject_id is not None:
        # Query with subject_id only - get all ICU stays for this patient
        sql = f"""
        SELECT 
            icu.subject_id,
            icu.hadm_id,
            icu.stay_id,
            le.itemid,
            dl.label,
            le.charttime,
            le.valuenum,
            le.valueuom
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_hosp.d_labitems dl ON le.itemid = dl.itemid
        JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
        WHERE icu.subject_id = {subject_id}
        AND le.itemid IN ({WBC_COUNT}, {WBC_COUNT_ALT}, {BANDS}, {NEUTROPHILS}, {LYMPHOCYTES}, {MONOCYTES}, 
                          {EOSINOPHILS}, {BASOPHILS}, {ABS_NEUTROPHIL}, {ABS_LYMPHOCYTE}, {ABS_LYMPHOCYTE_ALT},
                          {ABS_MONOCYTE}, {ABS_EOSINOPHIL}, {ABS_BASOPHIL})
        AND le.charttime >= icu.intime
        AND le.charttime <= icu.outtime
        ORDER BY le.charttime, le.itemid
        """
    else:
        # Query with hadm_id only
        sql = f"""
        SELECT 
            icu.subject_id,
            icu.hadm_id,
            icu.stay_id,
            le.itemid,
            dl.label,
            le.charttime,
            le.valuenum,
            le.valueuom
        FROM mimiciv_hosp.labevents le
        JOIN mimiciv_hosp.d_labitems dl ON le.itemid = dl.itemid
        JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
        WHERE icu.hadm_id = {hadm_id}
        AND le.itemid IN ({WBC_COUNT}, {WBC_COUNT_ALT}, {BANDS}, {NEUTROPHILS}, {LYMPHOCYTES}, {MONOCYTES}, 
                          {EOSINOPHILS}, {BASOPHILS}, {ABS_NEUTROPHIL}, {ABS_LYMPHOCYTE}, {ABS_LYMPHOCYTE_ALT},
                          {ABS_MONOCYTE}, {ABS_EOSINOPHIL}, {ABS_BASOPHIL})
        AND le.charttime >= icu.intime
        AND le.charttime <= icu.outtime
        ORDER BY le.charttime, le.itemid
        """
    
    # Execute query
    df = query_db(sql)
    
    # Initialize result dictionary
    result = {
        'subject_id': None,
        'hadm_id': None,
        'stay_id': None,
        'wbc_count': [],
        'max_wbc_count': None,
        'min_wbc_count': None,
        'has_elevated_wbc': False,
        'band_percent': [],
        'max_band_percent': None,
        'has_left_shift': False,
        'neutrophil_percent': [],
        'lymphocyte_percent': [],
        'monocyte_percent': [],
        'eosinophil_percent': [],
        'basophil_percent': [],
        'absolute_neutrophil_count': [],
        'absolute_lymphocyte_count': [],
        'absolute_monocyte_count': [],
        'absolute_eosinophil_count': [],
        'absolute_basophil_count': []
    }
    
    if df.empty:
        return result
    
    # Extract identifiers from first row
    result['subject_id'] = int(df['subject_id'].iloc[0])
    result['hadm_id'] = int(df['hadm_id'].iloc[0])
    result['stay_id'] = int(df['stay_id'].iloc[0])
    
    # Extract values by itemid - combine both WBC item IDs
    wbc_data = df[df['itemid'].isin([WBC_COUNT, WBC_COUNT_ALT])]['valuenum'].dropna().tolist()
    band_data = df[df['itemid'] == BANDS]['valuenum'].dropna().tolist()
    neutrophil_data = df[df['itemid'] == NEUTROPHILS]['valuenum'].dropna().tolist()
    lymphocyte_data = df[df['itemid'] == LYMPHOCYTES]['valuenum'].dropna().tolist()
    monocyte_data = df[df['itemid'] == MONOCYTES]['valuenum'].dropna().tolist()
    eosinophil_data = df[df['itemid'] == EOSINOPHILS]['valuenum'].dropna().tolist()
    basophil_data = df[df['itemid'] == BASOPHILS]['valuenum'].dropna().tolist()
    abs_neutrophil_data = df[df['itemid'] == ABS_NEUTROPHIL]['valuenum'].dropna().tolist()
    abs_lymphocyte_data = df[df['itemid'].isin([ABS_LYMPHOCYTE, ABS_LYMPHOCYTE_ALT])]['valuenum'].dropna().tolist()
    abs_monocyte_data = df[df['itemid'] == ABS_MONOCYTE]['valuenum'].dropna().tolist()
    abs_eosinophil_data = df[df['itemid'] == ABS_EOSINOPHIL]['valuenum'].dropna().tolist()
    abs_basophil_data = df[df['itemid'] == ABS_BASOPHIL]['valuenum'].dropna().tolist()
    
    # Populate result
    result['wbc_count'] = wbc_data
    if wbc_data:
        result['max_wbc_count'] = float(max(wbc_data))
        result['min_wbc_count'] = float(min(wbc_data))
        result['has_elevated_wbc'] = any(w > 12.0 for w in wbc_data)
    
    result['band_percent'] = band_data
    if band_data:
        result['max_band_percent'] = float(max(band_data))
        result['has_left_shift'] = any(b > 10.0 for b in band_data)
    
    result['neutrophil_percent'] = neutrophil_data
    result['lymphocyte_percent'] = lymphocyte_data
    result['monocyte_percent'] = monocyte_data
    result['eosinophil_percent'] = eosinophil_data
    result['basophil_percent'] = basophil_data
    result['absolute_neutrophil_count'] = abs_neutrophil_data
    result['absolute_lymphocyte_count'] = abs_lymphocyte_data
    result['absolute_monocyte_count'] = abs_monocyte_data
    result['absolute_eosinophil_count'] = abs_eosinophil_data
    result['absolute_basophil_count'] = abs_basophil_data
    
    return result

FINAL_FUNCTION = blood_differential