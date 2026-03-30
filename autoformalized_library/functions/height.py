import pandas as pd

def get_height(stay_id):
    """
    Extract height-related clinical information for an ICU stay.
    
    This function retrieves the most recent height measurement during a specific ICU stay,
    preferring centimeter measurements over inch measurements.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict or None
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'height_cm': The most recent height measurement in cm (float)
        - 'is_taller_than_180_cm': Boolean indicating if patient is taller than 180 cm
        - 'is_shorter_than_160_cm': Boolean indicating if patient is shorter than 160 cm
        
        Returns None if no matching ICU stay is found or no height data exists.
    
    Notes
    -----
    Height items included:
    - 226707: Height (Inch) - converted to cm using factor 2.54
    - 226730: Height (cm)
    
    The function prefers cm measurements over inch measurements, and returns
    the most recent measurement by charttime.
    
    Examples
    --------
    >>> get_height(35597217)
    {'stay_id': 35597217, 'height_cm': 178.0,
     'is_taller_than_180_cm': False, 'is_shorter_than_160_cm': False}
    """
    # Query for height data - prefer cm, then get most recent
    sql = f"""
    WITH height_data AS (
        SELECT 
            ce.subject_id, 
            ce.hadm_id, 
            ce.stay_id, 
            ce.charttime,
            CASE 
                WHEN ce.valueuom = 'cm' THEN CAST(ce.value AS DOUBLE)
                WHEN ce.valueuom = 'Inch' THEN CAST(ce.value AS DOUBLE) * 2.54
                ELSE NULL
            END as height_cm,
            CASE WHEN ce.valueuom = 'cm' THEN 1 ELSE 0 END as is_cm
        FROM mimiciv_icu.chartevents ce
        WHERE ce.itemid IN (226707, 226730)
        AND ce.value IS NOT NULL
        AND ce.stay_id = {stay_id}
    )
    SELECT height_cm
    FROM height_data
    ORDER BY charttime DESC, is_cm DESC
    LIMIT 1
    """
    
    result = query_db(sql)
    
    if result.empty:
        return None
    
    height_cm = float(result.iloc[0]['height_cm'])
    
    return {
        'stay_id': int(stay_id),
        'height_cm': height_cm,
        'is_taller_than_180_cm': bool(height_cm > 180),
        'is_shorter_than_160_cm': bool(height_cm < 160)
    }

FINAL_FUNCTION = get_height