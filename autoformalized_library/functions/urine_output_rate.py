import pandas as pd
import numpy as np

def get_urine_output_rate(stay_id):
    """
    Extract urine output rate information for a patient's ICU stay.
    
    This function queries the MIMIC-IV database to calculate urine output rates
    and identify periods of oliguria during an ICU stay.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier for the patient.
    
    Returns
    -------
    dict or None
        A dictionary containing the following keys:
        - 'stay_id': The ICU stay identifier (int)
        - 'weight_kg': Patient weight in kg (float or None)
        - 'total_urine_output_mL': Total urine output during ICU stay (float or None)
        - 'urine_output_records': Number of urine output records (int)
        - 'min_hourly_rate_mL_kg_hr': Minimum hourly urine output rate (float or None)
        - 'max_hourly_rate_mL_kg_hr': Maximum hourly urine output rate (float or None)
        - 'mean_hourly_rate_mL_kg_hr': Mean hourly urine output rate (float or None)
        - 'min_6hr_rate_mL_kg_hr': Minimum 6-hour rolling urine output rate (float or None)
        - 'has_oliguria': Boolean indicating if patient had oliguria (< 0.5 mL/kg/hr) at any point
        - 'has_severe_oliguria': Boolean indicating if patient had severe oliguria (< 0.3 mL/kg/hr) at any point
        - 'oliguria_periods': Number of hourly periods with oliguria (int)
        - 'severe_oliguria_periods': Number of hourly periods with severe oliguria (int)
        
        Returns None if no matching ICU stay is found or no urine output data exists.
    
    Notes
    -----
    Urine output items included:
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
    - 226582: Ostomy (output)
    - 226627: OR Urine
    - 226631: PACU Urine
    - 227489: GU Irrigant/Urine Volume Out
    
    Weight items included:
    - 224639: Daily Weight (kg)
    - 226512: Admission Weight (Kg)
    - 226846: Feeding Weight (kg)
    
    Clinical thresholds:
    - Oliguria: urine output rate < 0.5 mL/kg/hr
    - Severe oliguria: urine output rate < 0.3 mL/kg/hr
    """
    
    # Define urine output item IDs
    urine_item_ids = [226557, 226558, 226559, 226560, 226561, 226563, 226564, 226565, 
                      226566, 226567, 226582, 226627, 226631, 227489]
    
    # Define weight item IDs
    weight_item_ids = [224639, 226512, 226846]
    
    # SQL query to get urine output, weight, and ICU stay data
    urine_items_str = ','.join([str(id) for id in urine_item_ids])
    weight_items_str = ','.join([str(id) for id in weight_item_ids])
    
    sql = f"""
    WITH urine_output AS (
        SELECT oe.charttime, oe.value, oe.stay_id
        FROM mimiciv_icu.outputevents oe
        WHERE oe.stay_id = {stay_id}
        AND oe.itemid IN ({urine_items_str})
        AND oe.value > 0
    ),
    weight_data AS (
        SELECT ce.valuenum as weight_kg
        FROM mimiciv_icu.chartevents ce
        WHERE ce.stay_id = {stay_id}
        AND ce.itemid IN ({weight_items_str})
        AND ce.valueuom = 'kg'
        ORDER BY ce.charttime
        LIMIT 1
    ),
    stay_info AS (
        SELECT intime, outtime
        FROM mimiciv_icu.icustays
        WHERE stay_id = {stay_id}
    )
    SELECT u.charttime, u.value, w.weight_kg, s.intime, s.outtime
    FROM urine_output u
    CROSS JOIN weight_data w
    CROSS JOIN stay_info s
    ORDER BY u.charttime
    """
    
    try:
        df = query_db(sql)
    except Exception as e:
        return None
    
    # Check if we have any data
    if df.empty:
        return None
    
    # Convert timestamps
    df['charttime'] = pd.to_datetime(df['charttime'])
    df['intime'] = pd.to_datetime(df['intime'])
    df['outtime'] = pd.to_datetime(df['outtime'])
    
    weight_kg = df['weight_kg'].iloc[0]
    intime = df['intime'].iloc[0]
    outtime = df['outtime'].iloc[0]
    
    # Filter to ICU stay period
    df = df[(df['charttime'] >= intime) & (df['charttime'] <= outtime)]
    
    # Check if we have any data after filtering
    if df.empty:
        return None
    
    # Calculate total urine output
    total_urine_output = df['value'].sum()
    
    # Calculate hourly urine output rate based on time since previous record
    df = df.sort_values('charttime').reset_index(drop=True)
    df['time_diff_hours'] = df['charttime'].diff().dt.total_seconds() / 3600
    df['hourly_rate_mL_kg_hr'] = (df['value'] / df['time_diff_hours'].replace(0, np.nan)) / weight_kg
    
    # Get valid hourly rates
    valid_rates = df['hourly_rate_mL_kg_hr'].dropna()
    
    # Calculate 6-hour rolling urine output rates
    df_indexed = df.set_index('charttime')
    df_hourly = df_indexed['value'].resample('h').sum().fillna(0)
    df_hourly_6hr = df_hourly.rolling('6h').sum()
    df_hourly_6hr_rate = (df_hourly_6hr / 6) / weight_kg
    
    # Build result dictionary with native Python types
    result = {
        'stay_id': int(stay_id),
        'weight_kg': round(float(weight_kg), 2) if weight_kg is not None else None,
        'total_urine_output_mL': round(float(total_urine_output), 2) if total_urine_output is not None else None,
        'urine_output_records': int(len(df)),
        'min_hourly_rate_mL_kg_hr': round(float(valid_rates.min()), 4) if len(valid_rates) > 0 else None,
        'max_hourly_rate_mL_kg_hr': round(float(valid_rates.max()), 4) if len(valid_rates) > 0 else None,
        'mean_hourly_rate_mL_kg_hr': round(float(valid_rates.mean()), 4) if len(valid_rates) > 0 else None,
        'min_6hr_rate_mL_kg_hr': round(float(df_hourly_6hr_rate.min()), 4) if len(df_hourly_6hr_rate.dropna()) > 0 else None,
        'has_oliguria': bool((valid_rates < 0.5).any()) if len(valid_rates) > 0 else False,
        'has_severe_oliguria': bool((valid_rates < 0.3).any()) if len(valid_rates) > 0 else False,
        'oliguria_periods': int((valid_rates < 0.5).sum()) if len(valid_rates) > 0 else 0,
        'severe_oliguria_periods': int((valid_rates < 0.3).sum()) if len(valid_rates) > 0 else 0
    }
    
    return result

FINAL_FUNCTION = get_urine_output_rate