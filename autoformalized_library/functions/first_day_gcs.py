import pandas as pd

def first_day_gcs(stay_id):
    """
    Extract Glasgow Coma Scale (GCS) information for the first day of an ICU stay.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        Dictionary with GCS information including:
        - 'stay_id', 'subject_id', 'hadm_id', 'intime', 'first_day_end'
        - 'first_day_gcs_records': DataFrame with all GCS recordings
        - 'min_gcs_first_day': Min GCS from non-intubated periods (verbal > 1)
        - 'min_gcs_first_day_all': Min GCS including all periods
        - 'max_gcs_first_day': Max GCS
        - 'has_severe_impairment_first_day': True if GCS ≤ 8 (non-intubated) or motor=1 majority (all intubated)
        - 'has_mild_or_normal_first_day': True if GCS ≥ 13 (non-intubated) or motor=6 (all intubated)
        - 'first_gcs_time_first_day', 'last_gcs_time_first_day'
        - 'total_gcs_assessments_first_day'
        - 'has_verbal_unresponsive_first_day'
    """
    
    # Get ICU stay information
    stay_info = query_db("""
        SELECT stay_id, subject_id, hadm_id, intime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {}
    """.format(stay_id))
    
    if stay_info.empty:
        return {
            'stay_id': stay_id,
            'subject_id': None,
            'hadm_id': None,
            'intime': None,
            'first_day_end': None,
            'first_day_gcs_records': pd.DataFrame(),
            'min_gcs_first_day': None,
            'min_gcs_first_day_all': None,
            'max_gcs_first_day': None,
            'has_severe_impairment_first_day': False,
            'has_mild_or_normal_first_day': False,
            'first_gcs_time_first_day': None,
            'last_gcs_time_first_day': None,
            'total_gcs_assessments_first_day': 0,
            'has_verbal_unresponsive_first_day': False
        }
    
    subject_id = stay_info['subject_id'].iloc[0]
    hadm_id = stay_info['hadm_id'].iloc[0]
    intime = stay_info['intime'].iloc[0]
    
    # Query GCS components for the first day (24 hours from ICU admission)
    gcs_query = """
        WITH gcs_components AS (
            SELECT 
                ce.stay_id,
                ce.charttime,
                MAX(CASE WHEN ce.itemid = 220739 THEN ce.valuenum END) as eye,
                MAX(CASE WHEN ce.itemid = 223900 THEN ce.valuenum END) as verbal,
                MAX(CASE WHEN ce.itemid = 223901 THEN ce.valuenum END) as motor
            FROM mimiciv_icu.chartevents ce
            WHERE ce.itemid IN (220739, 223900, 223901)
            AND ce.stay_id = {}
            GROUP BY ce.stay_id, ce.charttime
        ),
        gcs_with_total AS (
            SELECT 
                stay_id,
                charttime,
                eye, verbal, motor,
                (eye + verbal + motor) as gcs_total
            FROM gcs_components
            WHERE eye IS NOT NULL AND verbal IS NOT NULL AND motor IS NOT NULL
        ),
        first_day_gcs AS (
            SELECT 
                g.stay_id,
                g.charttime,
                g.eye,
                g.verbal,
                g.motor,
                g.gcs_total,
                i.intime,
                i.intime + INTERVAL '24 hours' as first_day_end
            FROM gcs_with_total g
            JOIN mimiciv_icu.icustays i ON g.stay_id = i.stay_id
            WHERE g.charttime >= i.intime 
            AND g.charttime < i.intime + INTERVAL '24 hours'
        )
        SELECT 
            stay_id,
            charttime,
            eye,
            verbal,
            motor,
            gcs_total,
            intime,
            first_day_end
        FROM first_day_gcs
        ORDER BY charttime
    """.format(stay_id)
    
    gcs_records = query_db(gcs_query)
    
    if gcs_records.empty:
        return {
            'stay_id': stay_id,
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'intime': str(intime),
            'first_day_end': None,
            'first_day_gcs_records': pd.DataFrame(),
            'min_gcs_first_day': None,
            'min_gcs_first_day_all': None,
            'max_gcs_first_day': None,
            'has_severe_impairment_first_day': False,
            'has_mild_or_normal_first_day': False,
            'first_gcs_time_first_day': None,
            'last_gcs_time_first_day': None,
            'total_gcs_assessments_first_day': 0,
            'has_verbal_unresponsive_first_day': False
        }
    
    # Calculate statistics
    min_gcs_all = gcs_records['gcs_total'].min()
    max_gcs = gcs_records['gcs_total'].max()
    
    # Separate intubated (verbal=1) and non-intubated (verbal>1) readings
    non_intubated = gcs_records[gcs_records['verbal'] > 1]
    intubated = gcs_records[gcs_records['verbal'] == 1]
    
    # min_gcs_first_day: minimum GCS from non-intubated periods only
    if len(non_intubated) > 0:
        min_gcs = non_intubated['gcs_total'].min()
    else:
        min_gcs = None
    
    # has_severe_impairment_first_day:
    # - If non-intubated readings exist: use min GCS from non-intubated (≤8 = severe)
    # - If all intubated: check if motor=1 is majority (>50% = severe)
    if len(non_intubated) > 0:
        has_severe = min_gcs <= 8
    else:
        # All intubated - check if motor=1 is the majority (>50%)
        motor_scores = intubated['motor'].tolist()
        motor_1_count = sum(1 for m in motor_scores if m == 1)
        motor_1_ratio = motor_1_count / len(motor_scores)
        has_severe = motor_1_ratio > 0.5
    
    # has_mild_or_normal_first_day:
    # - If non-intubated readings exist: check if any GCS ≥ 13
    # - If all intubated: check if any motor=6 (obeys commands)
    if len(non_intubated) > 0:
        has_mild_or_normal = (non_intubated['gcs_total'] >= 13).any()
    else:
        has_mild_or_normal = (intubated['motor'] == 6).any()
    
    # Check for verbal unresponsive (verbal = 1)
    has_verbal_unresponsive = (gcs_records['verbal'] == 1).any()
    
    # Get timestamps
    first_gcs_time = gcs_records['charttime'].min()
    last_gcs_time = gcs_records['charttime'].max()
    
    # Get first_day_end
    first_day_end = gcs_records['first_day_end'].iloc[0]
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'intime': str(intime),
        'first_day_end': str(first_day_end),
        'first_day_gcs_records': gcs_records[['charttime', 'eye', 'verbal', 'motor', 'gcs_total']],
        'min_gcs_first_day': float(min_gcs) if min_gcs is not None else None,
        'min_gcs_first_day_all': float(min_gcs_all),
        'max_gcs_first_day': float(max_gcs),
        'has_severe_impairment_first_day': bool(has_severe),
        'has_mild_or_normal_first_day': bool(has_mild_or_normal),
        'first_gcs_time_first_day': first_gcs_time,
        'last_gcs_time_first_day': last_gcs_time,
        'total_gcs_assessments_first_day': len(gcs_records),
        'has_verbal_unresponsive_first_day': bool(has_verbal_unresponsive)
    }

FINAL_FUNCTION = first_day_gcs