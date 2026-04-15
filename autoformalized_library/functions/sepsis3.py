import pandas as pd
import numpy as np
from typing import Optional, Dict, Any

def compute_sepsis3(stay_id: int, hadm_id: Optional[int] = None, subject_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Compute Sepsis-3 classification for an ICU stay.
    
    Sepsis-3 criteria:
    - Sepsis: Suspected infection + SOFA increase >= 2 points from baseline
    - Septic Shock: Sepsis + vasopressors for MAP >= 65 mm Hg + lactate > 2 mmol/L
    
    Parameters
    ----------
    stay_id : int
        ICU stay identifier
    hadm_id : int, optional
        Hospital admission identifier (will be looked up if not provided)
    subject_id : int, optional
        Patient identifier (will be looked up if not provided)
    
    Returns
    -------
    dict
        Dictionary containing sepsis-3 classification results:
        - stay_id: ICU stay identifier
        - subject_id: Patient identifier
        - hadm_id: Hospital admission identifier
        - has_suspicion_of_infection: Boolean indicating if infection suspected
        - baseline_sofa: SOFA score on first day of ICU stay
        - worst_sofa: Worst SOFA score during ICU stay
        - sofa_delta: Difference between worst and baseline SOFA
        - has_sepsis: Boolean indicating if sepsis criteria met
        - has_vasopressors: Boolean indicating if vasopressors administered
        - max_lactate: Maximum lactate value (mmol/L) during admission
        - has_septic_shock: Boolean indicating if septic shock criteria met
    """
    # Get stay info if hadm_id or subject_id not provided
    if hadm_id is None or subject_id is None:
        stay_info = query_db("""
            SELECT subject_id, hadm_id, intime, outtime
            FROM mimiciv_icu.icustays
            WHERE stay_id = {}
        """.format(stay_id))
        if len(stay_info) == 0:
            raise ValueError(f"No ICU stay found for stay_id={stay_id}")
        subject_id = int(stay_info['subject_id'].iloc[0])
        hadm_id = int(stay_info['hadm_id'].iloc[0])
    
    # Get suspicion of infection
    infection_info = get_suspicion_of_infection(stay_id=stay_id, hadm_id=hadm_id, subject_id=subject_id)
    has_suspicion = infection_info['has_suspicion_of_infection']
    
    # Get first day SOFA (baseline)
    first_day = first_day_sofa(stay_id)
    baseline_sofa = first_day['total_sofa_score']
    
    # Get worst SOFA during stay
    worst_sofa = compute_sofa_score(stay_id)
    worst_sofa_score = worst_sofa['total_score']
    
    # Calculate SOFA delta
    sofa_delta = worst_sofa_score - baseline_sofa
    
    # Determine sepsis status
    has_sepsis = has_suspicion and sofa_delta >= 2
    
    # Check for septic shock criteria
    has_septic_shock = False
    has_vasopressors = False
    max_lactate = None
    
    if has_sepsis:
        # Check for vasopressors
        vasopressor_query = """
            SELECT DISTINCT i.itemid, d.label
            FROM mimiciv_icu.inputevents i
            JOIN mimiciv_icu.d_items d ON i.itemid = d.itemid
            WHERE i.stay_id = {}
              AND d.label IN ('Norepinephrine', 'Epinephrine', 'Vasopressin', 'Dopamine', 'Phenylephrine')
        """.format(stay_id)
        vasopressors = query_db(vasopressor_query)
        has_vasopressors = len(vasopressors) > 0
        
        # Check for lactate > 2 mmol/L
        lactate_query = """
            SELECT MAX(valuenum) as max_lactate
            FROM mimiciv_hosp.labevents
            WHERE subject_id = {} AND hadm_id = {}
              AND itemid IN (52442, 53154, 50813)
              AND valuenum IS NOT NULL
        """.format(subject_id, hadm_id)
        lactate_result = query_db(lactate_query)
        if len(lactate_result) > 0 and lactate_result['max_lactate'].iloc[0] is not None:
            max_lactate = float(lactate_result['max_lactate'].iloc[0])
        
        # Septic shock: vasopressors + lactate > 2
        has_septic_shock = has_vasopressors and (max_lactate is not None and max_lactate > 2)
    
    return {
        'stay_id': stay_id,
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'has_suspicion_of_infection': has_suspicion,
        'baseline_sofa': baseline_sofa,
        'worst_sofa': worst_sofa_score,
        'sofa_delta': sofa_delta,
        'has_sepsis': has_sepsis,
        'has_vasopressors': has_vasopressors,
        'max_lactate': max_lactate,
        'has_septic_shock': has_septic_shock
    }

FINAL_FUNCTION = compute_sepsis3