import pandas as pd

def first_day_weight(stay_id):
    """
    Extract weight measurement for the first day of an ICU stay.
    
    This function retrieves weight measurements during the first 24 hours
    of an ICU stay (from 24 hours before ICU admission to 24 hours after).
    It handles both kg and lbs measurements, converting lbs to kg.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict or None
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'weight_kg': The first-day weight measurement in kg (float or None)
        - 'charttime': The timestamp of the measurement (str or None)
        - 'is_80kg_or_more': Boolean indicating if patient weighs 80 kg or more
        - 'is_100kg_or_more': Boolean indicating if patient weighs 100 kg or more (obesity)
        - 'is_obese': Boolean indicating if patient is obese (>=100 kg)
        
        Returns None if no matching ICU stay is found or no weight data exists.
    
    Notes
    -----
    Weight items included:
    - 224639: Daily Weight (kg)
    - 226512: Admission Weight (Kg)
    - 226531: Admission Weight (lbs.) - converted to kg using factor 0.453592
    
    The function returns the earliest measurement within the time window.
    
    Examples
    --------
    >>> first_day_weight(39553978)
    {'stay_id': 39553978, 'weight_kg': 39.4, 'charttime': '2180-07-23 12:36:00',
     'is_80kg_or_more': False, 'is_100kg_or_more': False, 'is_obese': False}
    """
    
    sql = """
    WITH stay_info AS (
        SELECT stay_id, intime 
        FROM mimiciv_icu.icustays 
        WHERE stay_id = {stay_id}
    ),
    weight_data AS (
        SELECT 
            ce.stay_id,
            CASE 
                WHEN ce.itemid = 226531 THEN ce.valuenum * 0.453592  -- Convert lbs to kg
                ELSE ce.valuenum
            END AS weight_kg,
            ce.charttime,
            si.intime
        FROM mimiciv_icu.chartevents ce
        JOIN stay_info si ON ce.stay_id = si.stay_id
        WHERE ce.itemid IN (224639, 226512, 226531)
          AND ce.charttime >= si.intime - INTERVAL '24' HOUR
          AND ce.charttime <= si.intime + INTERVAL '24' HOUR
          AND ce.valuenum IS NOT NULL
          AND ce.valuenum > 0
        ORDER BY ce.charttime
        LIMIT 1
    )
    SELECT stay_id, weight_kg, charttime FROM weight_data
    """
    
    result = query_db(sql.format(stay_id=stay_id))
    
    if result.empty:
        return None
    
    row = result.iloc[0]
    weight_kg = float(row['weight_kg'])
    
    return {
        'stay_id': int(row['stay_id']),
        'weight_kg': round(weight_kg, 2),
        'charttime': str(row['charttime']),
        'is_80kg_or_more': bool(weight_kg >= 80),
        'is_100kg_or_more': bool(weight_kg >= 100),
        'is_obese': bool(weight_kg >= 100)
    }

FINAL_FUNCTION = first_day_weight