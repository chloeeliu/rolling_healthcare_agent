import pandas as pd
from typing import Dict, Any

def icp(stay_id: int) -> Dict[str, Any]:
    """
    Extract Intracranial Pressure (ICP) information for a patient's ICU stay.
    
    This function retrieves all ICP measurements recorded during an ICU stay
    and provides clinical assessments based on established thresholds.
    
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
        - 'icp_records': DataFrame with all ICP recordings during the stay
        - 'max_icp': Maximum ICP value (mmHg) during the stay (float or None)
        - 'min_icp': Minimum ICP value (mmHg) during the stay (float or None)
        - 'mean_icp': Mean ICP value (mmHg) during the stay (float or None)
        - 'has_elevated_icp': Boolean indicating if ICP > 20 mmHg at any point (bool)
        - 'has_refractory_hypertension': Boolean indicating if ICP > 25 mmHg at any point (bool)
        - 'elevated_icp_count': Number of measurements with ICP > 20 mmHg (int)
        - 'refractory_icp_count': Number of measurements with ICP > 25 mmHg (int)
        - 'total_icp_measurements': Total number of ICP measurements (int)
        - 'first_icp_time': Timestamp of first ICP recording (datetime or None)
        - 'last_icp_time': Timestamp of last ICP recording (datetime or None)
    
    Notes
    -----
    Clinical Thresholds for Intracranial Pressure:
    - Normal ICP: 5-15 mmHg
    - Elevated ICP: > 20 mmHg (requires intervention)
    - Refractory Intracranial Hypertension: > 25 mmHg (severe, resistant to treatment)
    
    The function filters ICP values to a clinically reasonable range (0-100 mmHg)
    to exclude data entry errors or outliers.
    
    Examples
    --------
    >>> icp(39937494)
    {'stay_id': 39937494, 'subject_id': 17346220, 'hadm_id': 21459373,
     'max_icp': 58.0, 'min_icp': 0.0, 'mean_icp': 6.49,
     'has_elevated_icp': True, 'has_refractory_hypertension': True, ...}
    """
    
    # Query ICP data for the given stay_id
    # ICP itemid is 220765 (Intra Cranial Pressure)
    sql = f"""
    SELECT 
        ce.subject_id,
        ce.hadm_id,
        ce.stay_id,
        ce.charttime,
        ce.valuenum as icp_value
    FROM mimiciv_icu.chartevents ce
    WHERE ce.stay_id = {stay_id}
      AND ce.itemid = 220765
      AND ce.valuenum IS NOT NULL
      AND ce.valuenum BETWEEN 0 AND 100
    ORDER BY ce.charttime
    """
    
    df = query_db(sql)
    
    # Handle case where no ICP data found
    if df.empty:
        return {
            'stay_id': stay_id,
            'subject_id': None,
            'hadm_id': None,
            'icp_records': pd.DataFrame(),
            'max_icp': None,
            'min_icp': None,
            'mean_icp': None,
            'has_elevated_icp': False,
            'has_refractory_hypertension': False,
            'elevated_icp_count': 0,
            'refractory_icp_count': 0,
            'total_icp_measurements': 0,
            'first_icp_time': None,
            'last_icp_time': None
        }
    
    # Calculate statistics
    max_icp = df['icp_value'].max()
    min_icp = df['icp_value'].min()
    mean_icp = df['icp_value'].mean()
    
    # Count elevated and refractory measurements
    elevated_count = (df['icp_value'] > 20).sum()
    refractory_count = (df['icp_value'] > 25).sum()
    
    # Get timestamps
    first_icp_time = df['charttime'].min()
    last_icp_time = df['charttime'].max()
    
    return {
        'stay_id': stay_id,
        'subject_id': df['subject_id'].iloc[0],
        'hadm_id': df['hadm_id'].iloc[0],
        'icp_records': df,
        'max_icp': float(max_icp),
        'min_icp': float(min_icp),
        'mean_icp': float(mean_icp),
        'has_elevated_icp': bool(elevated_count > 0),
        'has_refractory_hypertension': bool(refractory_count > 0),
        'elevated_icp_count': int(elevated_count),
        'refractory_icp_count': int(refractory_count),
        'total_icp_measurements': len(df),
        'first_icp_time': first_icp_time,
        'last_icp_time': last_icp_time
    }

FINAL_FUNCTION = icp