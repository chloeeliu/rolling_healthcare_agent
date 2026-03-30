import pandas as pd

def gcs(stay_id):
    """
    Extract Glasgow Coma Scale (GCS) information for a patient's ICU stay.
    
    This function retrieves all GCS component scores (Eye Opening, Verbal Response,
    Motor Response) recorded during an ICU stay and calculates the total GCS score.
    
    The primary numerical output is the minimum GCS score when the patient was
    not intubated (verbal response > 1), as intubation artificially lowers GCS.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'subject_id': Patient identifier (int or None)
        - 'hadm_id': Hospital admission identifier (int or None)
        - 'gcs_records': DataFrame with all GCS recordings during the stay
        - 'min_gcs': Minimum total GCS score when verbal > 1 (float or None)
        - 'min_gcs_all': Minimum total GCS score including intubated periods (float or None)
        - 'max_gcs': Maximum total GCS score during the stay (float or None)
        - 'has_severe_impairment': Boolean indicating if GCS ≤ 8 at any point (bool)
        - 'has_verbal_unresponsive': Boolean indicating if verbal response = 1 at any point (bool)
        - 'first_gcs_time': Timestamp of first GCS recording (datetime or None)
        - 'last_gcs_time': Timestamp of last GCS recording (datetime or None)
        - 'total_gcs_assessments': Number of GCS assessments during the stay (int)
    
    Notes
    -----
    GCS Components:
    - Eye Opening (E): 1=None, 2=To pain, 3=To speech, 4=Spontaneous
    - Verbal Response (V): 1=None, 2=Incomprehensible sounds, 3=Inappropriate words, 
                          4=Confused, 5=Oriented
    - Motor Response (M): 1=None, 2=Abnormal extension, 3=Abnormal flexion, 
                         4=Withdrawal, 5=Localizing, 6=Obeys commands
    
    Clinical Thresholds:
    - Severe impairment: GCS ≤ 8 (indicates coma, may require intubation)
    - Moderate impairment: GCS 9-12
    - Mild impairment: GCS 13-14
    - Normal: GCS 15
    
    The min_gcs value excludes periods when verbal=1 (intubated) to reflect
    the patient's true neurological status.
    """
    
    # SQL query to get all GCS components for the stay
    sql = """
    WITH gcs_components AS (
        SELECT stay_id, subject_id, hadm_id, charttime, itemid, valuenum
        FROM mimiciv_icu.chartevents
        WHERE stay_id = {stay_id}
          AND itemid IN (220739, 223900, 223901)
    ),
    gcs_pivot AS (
        SELECT stay_id, subject_id, hadm_id, charttime,
               MAX(CASE WHEN itemid = 220739 THEN valuenum END) as eye,
               MAX(CASE WHEN itemid = 223900 THEN valuenum END) as verbal,
               MAX(CASE WHEN itemid = 223901 THEN valuenum END) as motor
        FROM gcs_components
        GROUP BY stay_id, subject_id, hadm_id, charttime
    )
    SELECT stay_id, subject_id, hadm_id, charttime, eye, verbal, motor,
           (eye + verbal + motor) as gcs_total
    FROM gcs_pivot
    ORDER BY charttime
    """
    
    # Execute query
    df = query_db(sql.format(stay_id=stay_id))
    
    # If no GCS records found, return appropriate response
    if df.empty:
        return {
            'stay_id': stay_id,
            'subject_id': None,
            'hadm_id': None,
            'gcs_records': pd.DataFrame(columns=['charttime', 'eye', 'verbal', 'motor', 'gcs_total']),
            'min_gcs': None,
            'min_gcs_all': None,
            'max_gcs': None,
            'has_severe_impairment': False,
            'has_verbal_unresponsive': False,
            'first_gcs_time': None,
            'last_gcs_time': None,
            'total_gcs_assessments': 0
        }
    
    # Extract patient identifiers
    subject_id = df['subject_id'].iloc[0]
    hadm_id = df['hadm_id'].iloc[0]
    
    # Calculate summary statistics
    # min_gcs: minimum GCS when verbal > 1 (excluding intubated periods)
    non_intubated = df[df['verbal'] > 1]
    if not non_intubated.empty:
        min_gcs = non_intubated['gcs_total'].min()
    else:
        min_gcs = None
    
    # min_gcs_all: minimum GCS including all periods
    min_gcs_all = df['gcs_total'].min()
    
    # max_gcs: maximum GCS during the stay
    max_gcs = df['gcs_total'].max()
    
    # has_severe_impairment: GCS ≤ 8 at any point (using min_gcs_all)
    has_severe_impairment = min_gcs_all <= 8
    
    # has_verbal_unresponsive: verbal = 1 at any point (intubated)
    has_verbal_unresponsive = df['verbal'].min() == 1
    
    # Create gcs_records DataFrame
    gcs_records = df[['charttime', 'eye', 'verbal', 'motor', 'gcs_total']].copy()
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'gcs_records': gcs_records,
        'min_gcs': min_gcs,
        'min_gcs_all': min_gcs_all,
        'max_gcs': max_gcs,
        'has_severe_impairment': has_severe_impairment,
        'has_verbal_unresponsive': has_verbal_unresponsive,
        'first_gcs_time': df['charttime'].min(),
        'last_gcs_time': df['charttime'].max(),
        'total_gcs_assessments': len(df)
    }

FINAL_FUNCTION = gcs