import pandas as pd
from typing import Optional, Dict, Any, Union

def get_hypoglycemia_info(stay_id: Optional[int] = None, 
                          subject_id: Optional[int] = None, 
                          hadm_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Extract hypoglycemia information for a patient's ICU stay.
    
    This function retrieves glucose measurements from both chartevents (ICU) 
    and labevents (hospital) tables for a specified ICU stay and calculates
    hypoglycemia-related metrics.
    
    Hypoglycemia is defined as glucose < 70 mg/dL.
    Severe hypoglycemia is defined as glucose < 40 mg/dL.
    
    Parameters
    ----------
    stay_id : int, optional
        The ICU stay ID. If provided, returns data for that specific stay.
    subject_id : int, optional
        The patient's subject_id. If provided with hadm_id, returns data for 
        all ICU stays during that admission.
    hadm_id : int, optional
        The hospital admission ID. Used with subject_id to identify the admission.
    
    Returns
    -------
    dict
        A dictionary containing hypoglycemia information:
        - 'stay_id': The ICU stay ID (or list if multiple stays)
        - 'subject_id': Patient identifier
        - 'hadm_id': Hospital admission ID
        - 'min_glucose': Minimum glucose value (mg/dL) during the stay
        - 'max_glucose': Maximum glucose value (mg/dL) during the stay
        - 'mean_glucose': Mean glucose value (mg/dL) during the stay
        - 'num_measurements': Number of glucose measurements
        - 'has_hypoglycemia': Boolean indicating if any glucose < 70 mg/dL
        - 'has_severe_hypoglycemia': Boolean indicating if any glucose < 40 mg/dL
        - 'hypoglycemia_count': Number of hypoglycemic episodes (glucose < 70)
        - 'severe_hypoglycemia_count': Number of severe hypoglycemic episodes (glucose < 40)
        - 'all_glucose_measurements': DataFrame with all glucose measurements
    
    Raises
    ------
    ValueError
        If no valid identifier is provided.
    
    Examples
    --------
    >>> result = get_hypoglycemia_info(stay_id=37054128)
    >>> result['has_hypoglycemia']
    True
    >>> result['min_glucose']
    20.0
    >>> result['has_severe_hypoglycemia']
    True
    """
    
    # Validate input
    if stay_id is None and (subject_id is None or hadm_id is None):
        raise ValueError("Must provide either stay_id, or both subject_id and hadm_id")
    
    # Build the SQL query
    if stay_id is not None:
        # Query for a specific stay_id
        sql = f"""
        WITH glucose_chartevents AS (
            SELECT ce.stay_id, ce.charttime, ce.valuenum as glucose, 'chartevents' as source
            FROM mimiciv_icu.chartevents ce
            WHERE ce.stay_id = {stay_id}
              AND ce.itemid IN (220621, 225664, 226537, 228388)
              AND ce.valuenum IS NOT NULL
              AND ce.valuenum > 0
        ),
        glucose_labevents AS (
            SELECT icu.stay_id, le.charttime, le.valuenum as glucose, 'labevents' as source
            FROM mimiciv_hosp.labevents le
            JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
            WHERE icu.stay_id = {stay_id}
              AND le.itemid IN (50809, 50931, 52027, 52569)
              AND le.valuenum IS NOT NULL
              AND le.valuenum > 0
        ),
        all_glucose AS (
            SELECT * FROM glucose_chartevents
            UNION ALL
            SELECT * FROM glucose_labevents
        )
        SELECT 
            stay_id,
            MIN(glucose) as min_glucose,
            MAX(glucose) as max_glucose,
            AVG(glucose) as mean_glucose,
            COUNT(*) as num_measurements,
            SUM(CASE WHEN glucose < 70 THEN 1 ELSE 0 END) as hypoglycemia_count,
            SUM(CASE WHEN glucose < 40 THEN 1 ELSE 0 END) as severe_hypoglycemia_count
        FROM all_glucose
        GROUP BY stay_id
        """
        
        result = query_db(sql)
        
        if len(result) == 0:
            # No glucose measurements found
            return {
                'stay_id': stay_id,
                'subject_id': None,
                'hadm_id': None,
                'min_glucose': None,
                'max_glucose': None,
                'mean_glucose': None,
                'num_measurements': 0,
                'has_hypoglycemia': False,
                'has_severe_hypoglycemia': False,
                'hypoglycemia_count': 0,
                'severe_hypoglycemia_count': 0,
                'all_glucose_measurements': pd.DataFrame()
            }
        
        row = result.iloc[0]
        
        # Get patient identifiers
        patient_info = query_db(f"""
            SELECT subject_id, hadm_id 
            FROM mimiciv_icu.icustays 
            WHERE stay_id = {stay_id}
        """)
        
        # Get all glucose measurements
        all_measurements = query_db(f"""
        WITH glucose_chartevents AS (
            SELECT ce.stay_id, ce.charttime, ce.valuenum as glucose, 'chartevents' as source
            FROM mimiciv_icu.chartevents ce
            WHERE ce.stay_id = {stay_id}
              AND ce.itemid IN (220621, 225664, 226537, 228388)
              AND ce.valuenum IS NOT NULL
              AND ce.valuenum > 0
        ),
        glucose_labevents AS (
            SELECT icu.stay_id, le.charttime, le.valuenum as glucose, 'labevents' as source
            FROM mimiciv_hosp.labevents le
            JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
            WHERE icu.stay_id = {stay_id}
              AND le.itemid IN (50809, 50931, 52027, 52569)
              AND le.valuenum IS NOT NULL
              AND le.valuenum > 0
        ),
        all_glucose AS (
            SELECT * FROM glucose_chartevents
            UNION ALL
            SELECT * FROM glucose_labevents
        )
        SELECT stay_id, charttime, glucose, source
        FROM all_glucose
        ORDER BY charttime
        """)
        
        return {
            'stay_id': int(row['stay_id']),
            'subject_id': int(patient_info.iloc[0]['subject_id']),
            'hadm_id': int(patient_info.iloc[0]['hadm_id']),
            'min_glucose': float(row['min_glucose']),
            'max_glucose': float(row['max_glucose']),
            'mean_glucose': float(row['mean_glucose']),
            'num_measurements': int(row['num_measurements']),
            'has_hypoglycemia': row['hypoglycemia_count'] > 0,
            'has_severe_hypoglycemia': row['severe_hypoglycemia_count'] > 0,
            'hypoglycemia_count': int(row['hypoglycemia_count']),
            'severe_hypoglycemia_count': int(row['severe_hypoglycemia_count']),
            'all_glucose_measurements': all_measurements
        }
    
    else:
        # Query for subject_id and hadm_id (may have multiple stays)
        sql = f"""
        WITH glucose_chartevents AS (
            SELECT ce.stay_id, ce.charttime, ce.valuenum as glucose, 'chartevents' as source
            FROM mimiciv_icu.chartevents ce
            JOIN mimiciv_icu.icustays icu ON ce.stay_id = icu.stay_id
            WHERE icu.subject_id = {subject_id}
              AND icu.hadm_id = {hadm_id}
              AND ce.itemid IN (220621, 225664, 226537, 228388)
              AND ce.valuenum IS NOT NULL
              AND ce.valuenum > 0
        ),
        glucose_labevents AS (
            SELECT icu.stay_id, le.charttime, le.valuenum as glucose, 'labevents' as source
            FROM mimiciv_hosp.labevents le
            JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
            WHERE icu.subject_id = {subject_id}
              AND icu.hadm_id = {hadm_id}
              AND le.itemid IN (50809, 50931, 52027, 52569)
              AND le.valuenum IS NOT NULL
              AND le.valuenum > 0
        ),
        all_glucose AS (
            SELECT * FROM glucose_chartevents
            UNION ALL
            SELECT * FROM glucose_labevents
        )
        SELECT 
            stay_id,
            MIN(glucose) as min_glucose,
            MAX(glucose) as max_glucose,
            AVG(glucose) as mean_glucose,
            COUNT(*) as num_measurements,
            SUM(CASE WHEN glucose < 70 THEN 1 ELSE 0 END) as hypoglycemia_count,
            SUM(CASE WHEN glucose < 40 THEN 1 ELSE 0 END) as severe_hypoglycemia_count
        FROM all_glucose
        GROUP BY stay_id
        """
        
        result = query_db(sql)
        
        if len(result) == 0:
            return {
                'stay_id': None,
                'subject_id': subject_id,
                'hadm_id': hadm_id,
                'min_glucose': None,
                'max_glucose': None,
                'mean_glucose': None,
                'num_measurements': 0,
                'has_hypoglycemia': False,
                'has_severe_hypoglycemia': False,
                'hypoglycemia_count': 0,
                'severe_hypoglycemia_count': 0,
                'all_glucose_measurements': pd.DataFrame()
            }
        
        # Get all glucose measurements
        all_measurements = query_db(f"""
        WITH glucose_chartevents AS (
            SELECT ce.stay_id, ce.charttime, ce.valuenum as glucose, 'chartevents' as source
            FROM mimiciv_icu.chartevents ce
            JOIN mimiciv_icu.icustays icu ON ce.stay_id = icu.stay_id
            WHERE icu.subject_id = {subject_id}
              AND icu.hadm_id = {hadm_id}
              AND ce.itemid IN (220621, 225664, 226537, 228388)
              AND ce.valuenum IS NOT NULL
              AND ce.valuenum > 0
        ),
        glucose_labevents AS (
            SELECT icu.stay_id, le.charttime, le.valuenum as glucose, 'labevents' as source
            FROM mimiciv_hosp.labevents le
            JOIN mimiciv_icu.icustays icu ON le.hadm_id = icu.hadm_id
            WHERE icu.subject_id = {subject_id}
              AND icu.hadm_id = {hadm_id}
              AND le.itemid IN (50809, 50931, 52027, 52569)
              AND le.valuenum IS NOT NULL
              AND le.valuenum > 0
        ),
        all_glucose AS (
            SELECT * FROM glucose_chartevents
            UNION ALL
            SELECT * FROM glucose_labevents
        )
        SELECT stay_id, charttime, glucose, source
        FROM all_glucose
        ORDER BY charttime
        """)
        
        # Aggregate across all stays
        total_hypoglycemia = result['hypoglycemia_count'].sum()
        total_severe_hypoglycemia = result['severe_hypoglycemia_count'].sum()
        total_measurements = result['num_measurements'].sum()
        
        return {
            'stay_id': result['stay_id'].tolist(),
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'min_glucose': float(result['min_glucose'].min()),
            'max_glucose': float(result['max_glucose'].max()),
            'mean_glucose': float(result['mean_glucose'].mean()),
            'num_measurements': int(total_measurements),
            'has_hypoglycemia': total_hypoglycemia > 0,
            'has_severe_hypoglycemia': total_severe_hypoglycemia > 0,
            'hypoglycemia_count': int(total_hypoglycemia),
            'severe_hypoglycemia_count': int(total_severe_hypoglycemia),
            'all_glucose_measurements': all_measurements
        }

FINAL_FUNCTION = get_hypoglycemia_info