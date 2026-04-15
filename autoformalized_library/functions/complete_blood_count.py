import pandas as pd
from typing import Optional, Dict, Any

def complete_blood_count(stay_id: Optional[int] = None, 
                         subject_id: Optional[int] = None,
                         hadm_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Extract complete blood count (CBC) information for a patient's ICU stay.

    This function retrieves comprehensive CBC data including hemoglobin, hematocrit,
    platelet count, and white blood cell count during an ICU stay. It provides
    summary statistics and clinical flags for common CBC abnormalities.

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
        - 'hemoglobin': dict with hemoglobin statistics (g/dL)
            - 'values': list of all hemoglobin values
            - 'max': Maximum hemoglobin value (float or None)
            - 'min': Minimum hemoglobin value (float or None)
            - 'mean': Mean hemoglobin value (float or None)
            - 'count': Number of hemoglobin measurements (int)
            - 'has_anemia': Boolean indicating if hemoglobin < 10 g/dL at any point
        - 'hematocrit': dict with hematocrit statistics (%)
            - 'values': list of all hematocrit values
            - 'max': Maximum hematocrit value (float or None)
            - 'min': Minimum hematocrit value (float or None)
            - 'mean': Mean hematocrit value (float or None)
            - 'count': Number of hematocrit measurements (int)
        - 'platelet_count': dict with platelet count statistics (K/uL)
            - 'values': list of all platelet count values
            - 'max': Maximum platelet count value (float or None)
            - 'min': Minimum platelet count value (float or None)
            - 'mean': Mean platelet count value (float or None)
            - 'count': Number of platelet count measurements (int)
            - 'has_thrombocytopenia': Boolean indicating if platelet < 150 K/uL at any point
        - 'wbc_count': dict with WBC count statistics (K/uL)
            - 'values': list of all WBC count values
            - 'max': Maximum WBC count value (float or None)
            - 'min': Minimum WBC count value (float or None)
            - 'mean': Mean WBC count value (float or None)
            - 'count': Number of WBC count measurements (int)
            - 'has_leukocytosis': Boolean indicating if WBC > 12 K/uL at any point
            - 'has_leukopenia': Boolean indicating if WBC < 4 K/uL at any point
        - 'all_values': DataFrame with all CBC values during the stay

    Raises
    ------
    ValueError
        If no patient identifier is provided.

    Examples
    --------
    >>> complete_blood_count(stay_id=34477328)
    {'subject_id': 18871238, 'hadm_id': 27601223, 'stay_id': 34477328,
     'hemoglobin': {'values': [10.4], 'max': 10.4, 'min': 10.4, 'mean': 10.4, 
                    'count': 1, 'has_anemia': False},
     'platelet_count': {'values': [330.0], 'max': 330.0, 'min': 330.0, 
                        'mean': 330.0, 'count': 1, 'has_thrombocytopenia': False},
     ...}

    Notes
    -----
    This function uses the following item IDs from the MIMIC-IV database:
    - Hemoglobin: 220228 (g/dL)
    - Platelet Count: 227457 (K/uL)
    - Hematocrit (serum): 220545 (%)
    - WBC: 220546 (K/uL)

    Clinical thresholds used:
    - Anemia: hemoglobin < 10 g/dL
    - Thrombocytopenia: platelet count < 150 K/uL
    - Leukocytosis: WBC > 12 K/uL
    - Leukopenia: WBC < 4 K/uL
    """
    
    if stay_id is None and subject_id is None:
        raise ValueError("At least one patient identifier (stay_id or subject_id) must be provided.")
    
    # Build the WHERE clause based on provided identifiers
    where_clauses = []
    if stay_id is not None:
        where_clauses.append(f"ce.stay_id = {stay_id}")
    if subject_id is not None:
        where_clauses.append(f"ce.subject_id = {subject_id}")
    if hadm_id is not None:
        where_clauses.append(f"ce.hadm_id = {hadm_id}")
    
    where_clause = " AND ".join(where_clauses)
    
    # Query for CBC data from chartevents
    # Item IDs: 220228 (Hemoglobin), 227457 (Platelet Count), 220545 (Hematocrit), 220546 (WBC)
    sql = f"""
    SELECT 
        ce.subject_id,
        ce.hadm_id,
        ce.stay_id,
        ce.charttime,
        ce.valuenum,
        d.label,
        ce.valueuom
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.d_items d ON ce.itemid = d.itemid
    WHERE {where_clause}
    AND ce.itemid IN (220228, 227457, 220545, 220546)
    AND ce.valuenum IS NOT NULL
    ORDER BY ce.charttime
    """
    
    df = query_db(sql)
    
    if df.empty:
        # Return empty structure if no data found
        return {
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'stay_id': stay_id,
            'hemoglobin': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0, 'has_anemia': False},
            'hematocrit': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0},
            'platelet_count': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0, 'has_thrombocytopenia': False},
            'wbc_count': {'values': [], 'max': None, 'min': None, 'mean': None, 'count': 0, 'has_leukocytosis': False, 'has_leukopenia': False},
            'all_values': pd.DataFrame()
        }
    
    # Extract patient identifiers
    subject_id_result = df['subject_id'].iloc[0] if 'subject_id' in df.columns else None
    hadm_id_result = df['hadm_id'].iloc[0] if 'hadm_id' in df.columns else None
    stay_id_result = df['stay_id'].iloc[0] if 'stay_id' in df.columns else None
    
    # Filter by component
    hemoglobin_df = df[df['label'] == 'Hemoglobin'][['charttime', 'valuenum']].copy()
    hemoglobin_df['parameter'] = 'hemoglobin'
    hemoglobin_df['unit'] = 'g/dL'
    
    hematocrit_df = df[df['label'] == 'Hematocrit (serum)'][['charttime', 'valuenum']].copy()
    hematocrit_df['parameter'] = 'hematocrit'
    hematocrit_df['unit'] = '%'
    
    platelet_df = df[df['label'] == 'Platelet Count'][['charttime', 'valuenum']].copy()
    platelet_df['parameter'] = 'platelet_count'
    platelet_df['unit'] = 'K/uL'
    
    wbc_df = df[df['label'] == 'WBC'][['charttime', 'valuenum']].copy()
    wbc_df['parameter'] = 'wbc_count'
    wbc_df['unit'] = 'K/uL'
    
    # Combine all values for the all_values DataFrame
    all_values = pd.concat([hemoglobin_df, hematocrit_df, platelet_df, wbc_df], ignore_index=True)
    all_values = all_values[['charttime', 'valuenum', 'parameter', 'unit']]
    
    # Calculate hemoglobin statistics
    hgb_values = hemoglobin_df['valuenum'].tolist() if not hemoglobin_df.empty else []
    hgb_stats = {
        'values': hgb_values,
        'max': float(hemoglobin_df['valuenum'].max()) if not hemoglobin_df.empty else None,
        'min': float(hemoglobin_df['valuenum'].min()) if not hemoglobin_df.empty else None,
        'mean': float(hemoglobin_df['valuenum'].mean()) if not hemoglobin_df.empty else None,
        'count': len(hgb_values),
        'has_anemia': bool((hemoglobin_df['valuenum'] < 10).any()) if not hemoglobin_df.empty else False
    }
    
    # Calculate hematocrit statistics
    hct_values = hematocrit_df['valuenum'].tolist() if not hematocrit_df.empty else []
    hct_stats = {
        'values': hct_values,
        'max': float(hematocrit_df['valuenum'].max()) if not hematocrit_df.empty else None,
        'min': float(hematocrit_df['valuenum'].min()) if not hematocrit_df.empty else None,
        'mean': float(hematocrit_df['valuenum'].mean()) if not hematocrit_df.empty else None,
        'count': len(hct_values)
    }
    
    # Calculate platelet statistics
    plt_values = platelet_df['valuenum'].tolist() if not platelet_df.empty else []
    plt_stats = {
        'values': plt_values,
        'max': float(platelet_df['valuenum'].max()) if not platelet_df.empty else None,
        'min': float(platelet_df['valuenum'].min()) if not platelet_df.empty else None,
        'mean': float(platelet_df['valuenum'].mean()) if not platelet_df.empty else None,
        'count': len(plt_values),
        'has_thrombocytopenia': bool((platelet_df['valuenum'] < 150).any()) if not platelet_df.empty else False
    }
    
    # Calculate WBC statistics
    wbc_values = wbc_df['valuenum'].tolist() if not wbc_df.empty else []
    wbc_stats = {
        'values': wbc_values,
        'max': float(wbc_df['valuenum'].max()) if not wbc_df.empty else None,
        'min': float(wbc_df['valuenum'].min()) if not wbc_df.empty else None,
        'mean': float(wbc_df['valuenum'].mean()) if not wbc_df.empty else None,
        'count': len(wbc_values),
        'has_leukocytosis': bool((wbc_df['valuenum'] > 12).any()) if not wbc_df.empty else False,
        'has_leukopenia': bool((wbc_df['valuenum'] < 4).any()) if not wbc_df.empty else False
    }
    
    return {
        'subject_id': subject_id_result,
        'hadm_id': hadm_id_result,
        'stay_id': stay_id_result,
        'hemoglobin': hgb_stats,
        'hematocrit': hct_stats,
        'platelet_count': plt_stats,
        'wbc_count': wbc_stats,
        'all_values': all_values
    }

FINAL_FUNCTION = complete_blood_count