# Now let me create the final self-contained code block
import pandas as pd
from datetime import datetime

def urine_output(stay_id):
    """
    Extract urine output information for a patient's ICU stay.
    
    This function retrieves urine output data from the ICU output events table
    and calculates daily totals, average daily output, and determines if the
    patient has oliguria or severe oliguria.
    
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
    - 226627: OR Urine
    - 226631: PACU Urine
    - 227489: GU Irrigant/Urine Volume Out
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict
        A dictionary containing the following keys:
        - 'subject_id': patient identifier (int)
        - 'hadm_id': hospital admission identifier (int)
        - 'stay_id': ICU stay identifier (int)
        - 'total_urine_output_ml': total urine output in mL (float)
        - 'num_days_with_output': number of days with urine output recorded (int)
        - 'average_daily_output_ml': average daily urine output in mL/day (float)
        - 'daily_outputs': list of dicts with date and daily output (list)
        - 'has_oliguria': boolean indicating if average output < 500 mL/day (bool)
        - 'has_severe_oliguria': boolean indicating if average output < 200 mL/day (bool)
        - 'min_daily_output_ml': minimum daily output in mL (float or None)
        - 'max_daily_output_ml': maximum daily output in mL (float or None)
    
    Raises
    ------
    ValueError
        If stay_id is not provided.
    
    Examples
    --------
    >>> urine_output(37081114)
    {'subject_id': 10000690, 'hadm_id': 25860671, 'stay_id': 37081114,
     'total_urine_output_ml': 6717.0, 'num_days_with_output': 5,
     'average_daily_output_ml': 1343.4, 'daily_outputs': [...],
     'has_oliguria': False, 'has_severe_oliguria': False,
     'min_daily_output_ml': 170.0, 'max_daily_output_ml': 2685.0}
    """
    
    if stay_id is None:
        raise ValueError("stay_id must be provided")
    
    # Define urine output itemids
    urine_itemids = (226557, 226558, 226559, 226560, 226561, 226563, 226564, 226565, 
                     226566, 226567, 226627, 226631, 227489)
    
    # Query urine output data
    sql = f"""
    WITH urine_data AS (
        SELECT 
            oe.subject_id, 
            oe.hadm_id, 
            oe.stay_id,
            DATE(oe.charttime) as chart_date,
            SUM(oe.value) as daily_output
        FROM mimiciv_icu.outputevents oe
        WHERE oe.stay_id = {stay_id}
          AND oe.itemid IN {urine_itemids}
        GROUP BY oe.subject_id, oe.hadm_id, oe.stay_id, DATE(oe.charttime)
        ORDER BY chart_date
    )
    SELECT * FROM urine_data
    """
    
    df = query_db(sql)
    
    # Handle case where no urine output data exists
    if df.empty:
        return {
            'subject_id': None,
            'hadm_id': None,
            'stay_id': stay_id,
            'total_urine_output_ml': 0.0,
            'num_days_with_output': 0,
            'average_daily_output_ml': 0.0,
            'daily_outputs': [],
            'has_oliguria': True,  # No output = oliguria
            'has_severe_oliguria': True,  # No output = severe oliguria
            'min_daily_output_ml': None,
            'max_daily_output_ml': None
        }
    
    # Extract patient identifiers
    subject_id = df['subject_id'].iloc[0]
    hadm_id = df['hadm_id'].iloc[0]
    
    # Calculate totals
    total_output = df['daily_output'].sum()
    num_days = len(df)
    avg_daily = total_output / num_days if num_days > 0 else 0.0
    min_daily = df['daily_output'].min()
    max_daily = df['daily_output'].max()
    
    # Determine oliguria status
    has_oliguria = avg_daily < 500
    has_severe_oliguria = avg_daily < 200
    
    # Create daily outputs list
    daily_outputs = df.to_dict('records')
    
    return {
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'stay_id': stay_id,
        'total_urine_output_ml': round(total_output, 2),
        'num_days_with_output': num_days,
        'average_daily_output_ml': round(avg_daily, 2),
        'daily_outputs': daily_outputs,
        'has_oliguria': has_oliguria,
        'has_severe_oliguria': has_severe_oliguria,
        'min_daily_output_ml': round(min_daily, 2) if min_daily is not None else None,
        'max_daily_output_ml': round(max_daily, 2) if max_daily is not None else None
    }

FINAL_FUNCTION = urine_output