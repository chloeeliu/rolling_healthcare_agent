import pandas as pd
import numpy as np

def first_day_height(stay_id):
    """
    Extract height measurement for the first day of an ICU stay.
    
    This function retrieves the first height measurement during the first 24 hours
    of an ICU stay (from 24 hours before ICU admission to 24 hours after).
    It prefers centimeter measurements over inch measurements.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict or None
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'height_cm': The first-day height measurement in cm (float or None)
        - 'charttime': The timestamp of the measurement (str or None)
        - 'is_taller_than_175_cm': Boolean indicating if patient is taller than 175 cm
        - 'is_shorter_than_160_cm': Boolean indicating if patient is shorter than 160 cm
        
        Returns None if no matching ICU stay is found or no height data exists.
    
    Notes
    -----
    Height items included:
    - 226707: Height (Inch) - converted to cm using factor 2.54
    - 226730: Height (cm)
    
    The function prefers cm measurements over inch measurements, and returns
    the earliest measurement within the time window.
    
    Examples
    --------
    >>> first_day_height(34146568)
    {'stay_id': 34146568, 'height_cm': 155.0, 'charttime': '2136-03-21 11:41:00',
     'is_taller_than_175_cm': False, 'is_shorter_than_160_cm': True}
    """
    
    sql = """
    WITH height_data AS (
        SELECT ce.stay_id, ce.charttime, ce.itemid, ce.valuenum, ce.valueuom,
               ic.intime,
               EXTRACT(EPOCH FROM (ce.charttime - ic.intime)) / 3600.0 as hours_diff
        FROM mimiciv_icu.chartevents ce
        JOIN mimiciv_icu.icustays ic ON ce.stay_id = ic.stay_id
        WHERE ce.itemid IN (226707, 226730)
          AND ce.stay_id = {stay_id}
          AND ce.charttime >= ic.intime - INTERVAL '24 hours'
          AND ce.charttime <= ic.intime + INTERVAL '24 hours'
    ),
    height_cm AS (
        SELECT stay_id, charttime, valuenum, valueuom, hours_diff,
               CASE WHEN itemid = 226730 THEN valuenum 
                    WHEN itemid = 226707 THEN valuenum * 2.54 
                    ELSE NULL END as height_cm
        FROM height_data
    ),
    ranked_height AS (
        SELECT stay_id, charttime, valuenum, valueuom, hours_diff, height_cm,
               ROW_NUMBER() OVER (PARTITION BY stay_id ORDER BY 
                   CASE WHEN valueuom = 'cm' THEN 0 ELSE 1 END,
                   charttime ASC) as rn
        FROM height_cm
    )
    SELECT stay_id, charttime, height_cm
    FROM ranked_height
    WHERE rn = 1
    """
    
    result = query_db(sql.format(stay_id=stay_id))
    
    if result.empty:
        return None
    
    row = result.iloc[0]
    height_cm = row['height_cm']
    
    return {
        'stay_id': int(row['stay_id']),
        'height_cm': float(height_cm),
        'charttime': str(row['charttime']),
        'is_taller_than_175_cm': bool(height_cm > 175),
        'is_shorter_than_160_cm': bool(height_cm < 160)
    }

FINAL_FUNCTION = first_day_height