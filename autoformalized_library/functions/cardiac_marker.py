import pandas as pd
import numpy as np

def cardiac_marker(stay_id):
    """
    Extract cardiac marker information for a specific ICU stay.
    
    This function retrieves troponin and NT-proBNP/BNP lab values for a patient
    during their ICU stay from both labevents (hospital) and chartevents (ICU)
    sources, and returns the maximum value if any marker is elevated.
    
    Parameters
    ----------
    stay_id : int
        The ICU stay identifier.
    
    Returns
    -------
    float or np.nan
        The maximum cardiac marker value if any marker is elevated, otherwise np.nan.
        Returns np.nan if no matching ICU stay is found.
    
    Notes
    -----
    Clinical thresholds used:
    - Troponin T elevated: > 0.1 ng/mL (indicative of myocardial injury)
    - NT-proBNP/BNP elevated: > 1000 pg/mL (suggestive of heart failure)
    
    Cardiac marker item IDs:
    labevents: 50963 (NTproBNP), 51002 (Troponin I), 51003 (Troponin T), 52642 (Troponin I)
    chartevents: 227429 (Troponin-T), 227446 (BNP), 225622 (BNP)
    """
    
    # Check if ICU stay exists
    stay_info = query_db(f"""
        SELECT stay_id, subject_id, hadm_id, intime, outtime 
        FROM mimiciv_icu.icustays 
        WHERE stay_id = {stay_id}
    """)
    
    if stay_info.empty:
        return np.nan
    
    stay_info = stay_info.iloc[0]
    
    # Query for cardiac markers from labevents during the ICU stay
    sql_lab = """
    SELECT le.itemid, le.valuenum
    FROM mimiciv_hosp.labevents le
    JOIN mimiciv_icu.icustays i ON le.hadm_id = i.hadm_id
    WHERE i.stay_id = {stay_id}
        AND le.charttime >= i.intime 
        AND le.charttime <= i.outtime
        AND le.itemid IN (50963, 51002, 51003, 52642)
        AND le.valuenum IS NOT NULL
    """.format(stay_id=stay_id)
    
    df_lab = query_db(sql_lab)
    
    # Query for cardiac markers from chartevents during the ICU stay
    sql_chart = """
    SELECT c.itemid, c.valuenum
    FROM mimiciv_icu.chartevents c
    JOIN mimiciv_icu.icustays i ON c.stay_id = i.stay_id
    WHERE i.stay_id = {stay_id}
        AND c.charttime >= i.intime 
        AND c.charttime <= i.outtime
        AND c.itemid IN (227429, 227446, 225622)
        AND c.valuenum IS NOT NULL
    """.format(stay_id=stay_id)
    
    df_chart = query_db(sql_chart)
    
    # Combine both sources
    df = pd.concat([df_lab, df_chart], ignore_index=True)
    
    if df.empty:
        return np.nan
    
    # Troponin T (51003, 227429) elevated if > 0.1
    troponin_t = df[df['itemid'].isin([51003, 227429])]
    troponin_t_elevated = not troponin_t.empty and troponin_t['valuenum'].max() > 0.1
    
    # NT-proBNP/BNP (50963, 227446, 225622) elevated if > 1000
    ntprobnp = df[df['itemid'].isin([50963, 227446, 225622])]
    ntprobnp_elevated = not ntprobnp.empty and ntprobnp['valuenum'].max() > 1000
    
    if troponin_t_elevated or ntprobnp_elevated:
        return float(df['valuenum'].max())
    else:
        return np.nan

FINAL_FUNCTION = cardiac_marker