import pandas as pd
import numpy as np

def first_day_urine_output(stay_id):
    """
    Extract urine output information for a patient's first ICU day.
    
    This function retrieves urine output data from the ICU output events table
    and calculates the total urine output during the first 24 hours of the ICU stay.
    It also determines if the patient has oliguria or severe oliguria on that day.
    
    Urine output is captured from the following itemids in the outputevents table:
    - 226557: R Ureteral Stent
    - 226558: L Ureteral Stent
    - 226559: Foley
    - 226560: Void
    - 226561: Condom Cath
    - 226563: Suprapubic
    - 226564: R Nephrostomy
    - 226565: L Nephrostomy
    - 226566: Urine and GU Irrigant Out
    - 226567: Straight Cath
    - 227489: GU Irrigant/Urine Volume Out
    
    Note: OR Urine (226627) and PACU Urine (226631) are excluded as they represent
    pre-ICU outputs from the operating room and post-anesthesia care unit.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'subject_id': patient identifier (int or None)
        - 'hadm_id': hospital admission identifier (int or None)
        - 'stay_id': ICU stay identifier (int)
        - 'first_day_start': start time of the first ICU day (str in ISO format or None)
        - 'first_day_end': end time of the first ICU day (str in ISO format or None)
        - 'total_urine_output_ml': total urine output in first 24 hours in mL (float or None)
        - 'num_records': number of urine output records in first 24 hours (int)
        - 'has_oliguria': boolean indicating if total output < 500 mL (bool or None)
        - 'has_severe_oliguria': boolean indicating if total output < 200 mL (bool or None)
    
    Raises
    ------
    ValueError
        If stay_id is not provided.
    
    Examples
    --------
    >>> first_day_urine_output(37081114)
    {'subject_id': 10000690, 'hadm_id': 25860671, 'stay_id': 37081114,
     'first_day_start': '2150-11-02 19:37:00', 'first_day_end': '2150-11-03 19:37:00',
     'total_urine_output_ml': 695.0, 'num_records': 17,
     'has_oliguria': False, 'has_severe_oliguria': False}
    
    Notes
    -----
    Clinical thresholds:
    - Oliguria: total urine output < 500 mL in first 24 hours of ICU stay
    - Severe oliguria: total urine output < 200 mL in first 24 hours of ICU stay
    """
    
    if stay_id is None:
        raise ValueError("stay_id must be provided")
    
    # SQL query to get first 24 hours urine output
    # Excluding OR Urine (226627) and PACU Urine (226631)
    sql = """
    WITH first_day AS (
        SELECT stay_id, subject_id, hadm_id, intime, intime + INTERVAL '24 hours' as end_time
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    )
    SELECT 
        fd.subject_id,
        fd.hadm_id,
        fd.stay_id,
        CAST(fd.intime AS VARCHAR) as first_day_start,
        CAST(fd.end_time AS VARCHAR) as first_day_end,
        SUM(oe.value) as total_urine_output_ml,
        COUNT(oe.value) as num_records
    FROM first_day fd
    LEFT JOIN mimiciv_icu.outputevents oe 
        ON fd.stay_id = oe.stay_id
        AND oe.charttime >= fd.intime
        AND oe.charttime < fd.end_time
        AND oe.itemid IN (226557, 226558, 226559, 226560, 226561, 226563, 226564, 226565, 226566, 226567, 227489)
    GROUP BY fd.subject_id, fd.hadm_id, fd.stay_id, fd.intime, fd.end_time
    """.format(stay_id=stay_id)
    
    result = query_db(sql)
    
    if result.empty:
        return {
            'subject_id': None,
            'hadm_id': None,
            'stay_id': stay_id,
            'first_day_start': None,
            'first_day_end': None,
            'total_urine_output_ml': None,
            'num_records': 0,
            'has_oliguria': None,
            'has_severe_oliguria': None
        }
    
    row = result.iloc[0]
    total_output = row['total_urine_output_ml']
    
    # Handle case where there's no urine output data (total_output could be NaN)
    if pd.isna(total_output):
        total_output = None
    
    return {
        'subject_id': int(row['subject_id']),
        'hadm_id': int(row['hadm_id']),
        'stay_id': int(row['stay_id']),
        'first_day_start': str(row['first_day_start']),
        'first_day_end': str(row['first_day_end']),
        'total_urine_output_ml': float(total_output) if total_output is not None else None,
        'num_records': int(row['num_records']),
        'has_oliguria': total_output is not None and total_output < 500,
        'has_severe_oliguria': total_output is not None and total_output < 200
    }

FINAL_FUNCTION = first_day_urine_output