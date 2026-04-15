import pandas as pd

def weight_durations(stay_id):
    """
    Extract weight-related clinical information for an ICU stay.
    
    This function retrieves all weight measurements during a specific ICU stay
    that are recorded in kilograms, and provides summary statistics and 
    clinical thresholds.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    dict or None
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'weight_count': Number of weight measurements (int)
        - 'all_weights_kg': List of all weight measurements in kg (list of floats)
        - 'min_weight_kg': Minimum weight in kg (float or None)
        - 'max_weight_kg': Maximum weight in kg (float or None)
        - 'avg_weight_kg': Average weight in kg (float or None)
        - 'has_weight_80_or_more': Boolean indicating if patient weighed 80+ kg at any point
        - 'has_weight_100_or_more': Boolean indicating if patient weighed 100+ kg (obese) at any point
        
        Returns None if no matching ICU stay is found or no weight data exists.
    
    Notes
    -----
    Weight items included (only those with unitname = 'kg'):
    - 224639: Daily Weight (kg)
    - 226512: Admission Weight (Kg)
    - 226846: Feeding Weight (kg)
    
    Examples
    --------
    >>> weight_durations(37081114)
    {'stay_id': 37081114, 'weight_count': 1, 'all_weights_kg': [55.3],
     'min_weight_kg': 55.3, 'max_weight_kg': 55.3, 'avg_weight_kg': 55.3,
     'has_weight_80_or_more': False, 'has_weight_100_or_more': False}
    """
    
    # SQL query to get all weight measurements for the stay (only kg units)
    sql = """
    SELECT 
        ce.stay_id,
        ce.itemid,
        di.label,
        di.unitname,
        ce.charttime,
        ce.valuenum AS weight_kg
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
    WHERE ce.stay_id = {stay_id}
      AND ce.itemid IN (224639, 226512, 226531, 226846)
      AND di.unitname = 'kg'
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum > 0
    ORDER BY ce.charttime
    """.format(stay_id=stay_id)
    
    df = query_db(sql)
    
    # If no weight data found, return None
    if df.empty:
        return None
    
    # Extract weight values in kg
    weights_kg = df['weight_kg'].tolist()
    weight_count = len(weights_kg)
    
    # Calculate statistics
    min_weight = min(weights_kg)
    max_weight = max(weights_kg)
    avg_weight = sum(weights_kg) / weight_count
    
    # Clinical thresholds
    has_weight_80_or_more = any(w >= 80 for w in weights_kg)
    has_weight_100_or_more = any(w >= 100 for w in weights_kg)
    
    return {
        'stay_id': stay_id,
        'weight_count': weight_count,
        'all_weights_kg': weights_kg,
        'min_weight_kg': round(min_weight, 2),
        'max_weight_kg': round(max_weight, 2),
        'avg_weight_kg': round(avg_weight, 2),
        'has_weight_80_or_more': has_weight_80_or_more,
        'has_weight_100_or_more': has_weight_100_or_more
    }

FINAL_FUNCTION = weight_durations