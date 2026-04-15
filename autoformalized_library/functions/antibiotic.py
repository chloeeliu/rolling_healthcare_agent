import pandas as pd
from datetime import timedelta

def get_antibiotic_info(stay_id=None, hadm_id=None, subject_id=None):
    """
    Extract antibiotic administration information for a patient.
    
    This function queries both ICU input events and hospital prescriptions/pharmacy
    records to identify antibiotic administrations. It can answer questions such as:
    - Did this patient receive antibiotics during their hospital admission?
    - How many distinct antibiotics did this patient receive?
    - Did this patient receive antibiotics within the first 48 hours of ICU admission?
    
    Parameters
    ----------
    stay_id : int, optional
        ICU stay identifier. If provided, returns ICU-specific antibiotic data.
    hadm_id : int, optional
        Hospital admission identifier. If provided, returns hospital-wide antibiotic data.
    subject_id : int, optional
        Patient identifier. If provided with hadm_id, filters to that admission.
        If provided alone, returns all antibiotic data for the patient across all admissions.
    
    Returns
    -------
    dict
        A dictionary containing:
        - 'antibiotic_administrations': DataFrame with all antibiotic administrations
          (columns: source, stay_id, hadm_id, subject_id, antibiotic_name, admin_time)
        - 'received_antibiotics': bool indicating if any antibiotics were received
        - 'distinct_antibiotics': list of unique antibiotic names received
        - 'distinct_antibiotic_count': int count of unique antibiotics
        - 'icu_intime': datetime of ICU admission (if stay_id provided)
        - 'within_48hrs_icu': bool indicating if antibiotics received within 48h of ICU admission
        - 'antibiotics_within_48hrs_icu': list of antibiotics received within 48h of ICU admission
    
    Notes
    -----
    - At least one identifier (stay_id, hadm_id, or subject_id) must be provided.
    - Antibiotics are identified from:
      * ICU inputevents table using d_items category = 'Antibiotics'
      * Hospital prescriptions table using drug name pattern matching
    - The function normalizes antibiotic names for consistent counting.
    - Only TRUE antibacterial antibiotics are counted (excludes antifungals, antivirals, etc.)
    """
    
    # TRUE antibacterial antibiotic itemids (36 items)
    # EXCLUDES: antifungals (225838, 225848, 225869, 225885, 225905),
    #           antivirals (225837, 225871, 225873, 225897, 228003, 225903),
    #           antiparasitics (225844, 225857, 225882, 225896),
    #           antituberculars (225868, 225877, 225895, 225898)
    antibacterial_itemids = [
        225840,  # Amikacin
        225842,  # Ampicillin
        225843,  # Ampicillin/Sulbactam (Unasyn)
        225845,  # Azithromycin
        225847,  # Aztreonam
        225899,  # Bactrim (SMX/TMP)
        225850,  # Cefazolin
        225851,  # Cefepime
        229587,  # Ceftaroline
        225853,  # Ceftazidime
        225855,  # Ceftriaxone
        229059,  # Chloramphenicol
        225859,  # Ciprofloxacin
        225860,  # Clindamycin
        225862,  # Colistin
        225900,  # Dalfopristin/Quinupristin (Synercid)
        225863,  # Daptomycin
        225865,  # Doxycycline
        229061,  # Ertapenem sodium (Invanz)
        225866,  # Erythromycin
        225875,  # Gentamicin
        225876,  # Imipenem/Cilastatin
        227691,  # Keflex
        225879,  # Levofloxacin
        225881,  # Linezolid
        225883,  # Meropenem
        225884,  # Metronidazole
        225886,  # Moxifloxacin
        225888,  # Nafcillin
        225889,  # Oxacillin
        225890,  # Penicillin G potassium
        225892,  # Piperacillin
        225893,  # Piperacillin/Tazobactam (Zosyn)
        229064,  # Tigecycline
        225902,  # Tobramycin
        225798,  # Vancomycin
    ]
    
    # If stay_id is provided, look up hadm_id and subject_id from icustays
    stay_valid = False
    if stay_id is not None:
        stay_info = query_db(f"SELECT hadm_id, subject_id FROM mimiciv_icu.icustays WHERE stay_id = {stay_id}")
        if len(stay_info) > 0:
            stay_valid = True
            stay_hadm_id = stay_info['hadm_id'].iloc[0]
            stay_subject_id = stay_info['subject_id'].iloc[0]
            # If hadm_id not provided, use the one from icustays
            if hadm_id is None:
                hadm_id = stay_hadm_id
            # If subject_id not provided, use the one from icustays
            if subject_id is None:
                subject_id = stay_subject_id
        else:
            # stay_id not found - return empty results
            return {
                'antibiotic_administrations': pd.DataFrame(columns=['source', 'stay_id', 'hadm_id', 'subject_id', 'antibiotic_name', 'admin_time']),
                'received_antibiotics': False,
                'distinct_antibiotics': [],
                'distinct_antibiotic_count': 0,
                'icu_intime': None,
                'within_48hrs_icu': False,
                'antibiotics_within_48hrs_icu': []
            }
    
    # Build WHERE clause for ICU inputevents
    icu_clauses = []
    if stay_id is not None:
        icu_clauses.append(f"ie.stay_id = {stay_id}")
    if hadm_id is not None:
        icu_clauses.append(f"ie.hadm_id = {hadm_id}")
    if subject_id is not None:
        icu_clauses.append(f"ie.subject_id = {subject_id}")
    
    icu_where = " AND ".join(icu_clauses) if icu_clauses else "1=1"
    
    # ICU antibiotics query - ONLY antibacterial antibiotics
    icu_query = f"""
    SELECT 
        'ICU' as source,
        ie.stay_id,
        ie.hadm_id,
        ie.subject_id,
        di.label as antibiotic_name,
        ie.starttime as admin_time
    FROM mimiciv_icu.inputevents ie
    JOIN mimiciv_icu.d_items di ON ie.itemid = di.itemid
    WHERE {icu_where}
    AND ie.itemid IN ({','.join(map(str, antibacterial_itemids))})
    """
    
    icu_df = query_db(icu_query)
    
    # Hospital prescriptions antibiotics query - EXCLUDE antifungals, antivirals, etc.
    hosp_clauses = []
    if hadm_id is not None:
        hosp_clauses.append(f"p.hadm_id = {hadm_id}")
    if subject_id is not None:
        hosp_clauses.append(f"p.subject_id = {subject_id}")
    
    hosp_where = " AND ".join(hosp_clauses) if hosp_clauses else "1=1"
    
    # Antibacterial patterns - EXCLUDE antifungals (fluconazole, voriconazole, etc.),
    # antivirals (acyclovir, ganciclovir, etc.), antiparasitics (atovaquone, etc.)
    hosp_query = f"""
    SELECT 
        'Hospital' as source,
        NULL as stay_id,
        p.hadm_id,
        p.subject_id,
        p.drug as antibiotic_name,
        p.starttime as admin_time
    FROM mimiciv_hosp.prescriptions p
    WHERE {hosp_where}
    AND (
        -- Cephalosporins
        p.drug ILIKE '%cefazolin%' 
        OR p.drug ILIKE '%cefepime%' 
        OR p.drug ILIKE '%ceftaroline%' 
        OR p.drug ILIKE '%ceftazidime%' 
        OR p.drug ILIKE '%ceftriaxone%' 
        OR p.drug ILIKE '%cefuroxime%'
        OR p.drug ILIKE '%cefoxitin%'
        OR p.drug ILIKE '%cefadroxil%'
        OR p.drug ILIKE '%keflex%'
        -- Penicillins
        OR p.drug ILIKE '%ampicillin%' 
        OR p.drug ILIKE '%amoxicillin%' 
        OR p.drug ILIKE '%piperacillin%' 
        OR p.drug ILIKE '%nafcillin%' 
        OR p.drug ILIKE '%oxacillin%' 
        OR p.drug ILIKE '%penicillin%'
        -- Carbapenems
        OR p.drug ILIKE '%meropenem%' 
        OR p.drug ILIKE '%imipenem%' 
        OR p.drug ILIKE '%ertapenem%'
        OR p.drug ILIKE '%tigecycline%'
        -- Fluoroquinolones
        OR p.drug ILIKE '%ciprofloxacin%' 
        OR p.drug ILIKE '%levofloxacin%' 
        OR p.drug ILIKE '%moxifloxacin%'
        -- Aminoglycosides
        OR p.drug ILIKE '%gentamicin%' 
        OR p.drug ILIKE '%tobramycin%' 
        OR p.drug ILIKE '%amikacin%'
        -- Others
        OR p.drug ILIKE '%vancomycin%' 
        OR p.drug ILIKE '%metronidazole%' 
        OR p.drug ILIKE '%clindamycin%' 
        OR p.drug ILIKE '%doxycycline%' 
        OR p.drug ILIKE '%linezolid%' 
        OR p.drug ILIKE '%daptomycin%' 
        OR p.drug ILIKE '%colistin%' 
        OR p.drug ILIKE '%aztreonam%' 
        OR p.drug ILIKE '%azithromycin%' 
        OR p.drug ILIKE '%erythromycin%' 
        OR p.drug ILIKE '%bactrim%' 
        OR p.drug ILIKE '%trimethoprim%' 
        OR p.drug ILIKE '%sulfamethoxazole%'
        OR p.drug ILIKE '%chloramphenicol%'
        OR p.drug ILIKE '%synercid%'
        OR p.drug ILIKE '%dalfopristin%'
        OR p.drug ILIKE '%quinupristin%'
        OR p.drug ILIKE '%fosfomycin%'
    )
    AND (
        -- EXCLUDE antifungals
        p.drug NOT ILIKE '%fluconazole%'
        AND p.drug NOT ILIKE '%voriconazole%'
        AND p.drug NOT ILIKE '%amphotericin%'
        AND p.drug NOT ILIKE '%ambisome%'
        AND p.drug NOT ILIKE '%caspofungin%'
        AND p.drug NOT ILIKE '%micafungin%'
        AND p.drug NOT ILIKE '%echinocandin%'
        -- EXCLUDE antivirals
        AND p.drug NOT ILIKE '%acyclovir%'
        AND p.drug NOT ILIKE '%ganciclovir%'
        AND p.drug NOT ILIKE '%valganciclovir%'
        AND p.drug NOT ILIKE '%foscarnet%'
        AND p.drug NOT ILIKE '%ribavirin%'
        AND p.drug NOT ILIKE '%oseltamivir%'
        AND p.drug NOT ILIKE '%tamiflu%'
        -- EXCLUDE antiparasitics
        AND p.drug NOT ILIKE '%atovaquone%'
        AND p.drug NOT ILIKE '%chloroquine%'
        AND p.drug NOT ILIKE '%mefloquine%'
        AND p.drug NOT ILIKE '%quinine%'
        -- EXCLUDE antituberculars
        AND p.drug NOT ILIKE '%isoniazid%'
        AND p.drug NOT ILIKE '%rifampin%'
        AND p.drug NOT ILIKE '%rifampicin%'
        AND p.drug NOT ILIKE '%pyrazinamide%'
        AND p.drug NOT ILIKE '%ethambutol%'
    )
    """
    
    hosp_df = query_db(hosp_query)
    
    # Combine results
    if len(icu_df) > 0 and len(hosp_df) > 0:
        all_abx = pd.concat([icu_df, hosp_df], ignore_index=True)
    elif len(icu_df) > 0:
        all_abx = icu_df
    elif len(hosp_df) > 0:
        all_abx = hosp_df
    else:
        all_abx = pd.DataFrame(columns=['source', 'stay_id', 'hadm_id', 'subject_id', 'antibiotic_name', 'admin_time'])
    
    # Sort by admin_time
    if len(all_abx) > 0:
        all_abx = all_abx.sort_values('admin_time').reset_index(drop=True)
    
    # Get distinct antibiotics (normalize names)
    def normalize_abx_name(name):
        if pd.isna(name):
            return None
        name = str(name).lower().strip()
        # Remove common suffixes/prefixes
        name = name.replace('*nf*', '').replace('*nf ', '').replace(' *nf', '').strip()
        name = name.replace(' sodium', '').replace(' sodium ', '').strip()
        name = name.replace(' oral susp.', '').replace(' oral susp', '').strip()
        name = name.replace(' hcl', '').replace(' hcl ', '').strip()
        name = name.replace(' iv', '').replace(' iv ', '').strip()
        name = name.replace(' injection', '').replace(' injection ', '').strip()
        name = name.replace(' tablet', '').replace(' tablet ', '').strip()
        name = name.replace(' capsule', '').replace(' capsule ', '').strip()
        name = name.replace(' tabs', '').replace(' tabs ', '').strip()
        name = name.replace(' cap', '').replace(' cap ', '').strip()
        name = name.replace(' tabs', '').replace(' tabs ', '').strip()
        name = name.replace(' mg', '').replace(' mg ', '').strip()
        name = name.replace(' g', '').replace(' g ', '').strip()
        name = name.replace(' ml', '').replace(' ml ', '').strip()
        name = name.replace(' -', ' ').replace('-', ' ').strip()
        # Handle common variations - CHECK COMBINATIONS FIRST
        if 'cefepime' in name or 'cefepim' in name:
            return 'Cefepime'
        if 'ceftriaxone' in name or 'ceftriax' in name:
            return 'Ceftriaxone'
        if 'ceftazidime' in name or 'ceftazidim' in name:
            return 'Ceftazidime'
        if 'cefazolin' in name or 'cefazol' in name:
            return 'Cefazolin'
        if 'vancomycin' in name:
            # Distinguish oral from IV
            if 'oral' in name:
                return 'Vancomycin Oral Liquid'
            return 'Vancomycin'
        if 'meropenem' in name:
            return 'Meropenem'
        # CHECK FOR COMBINATIONS FIRST (before individual drugs)
        if 'piperacillin' in name and ('tazobactam' in name or 'zosyn' in name):
            return 'Piperacillin/Tazobactam'
        if 'ampicillin' in name and 'sulbactam' in name:
            return 'Ampicillin/Sulbactam'
        # NOW CHECK INDIVIDUAL DRUGS
        if 'piperacillin' in name:
            return 'Piperacillin'
        if 'zosyn' in name:
            return 'Piperacillin/Tazobactam'
        if 'tazobactam' in name:
            return 'Piperacillin/Tazobactam'
        if 'ampicillin' in name:
            return 'Ampicillin'
        if 'amoxicillin' in name:
            return 'Amoxicillin'
        if 'azithromycin' in name or 'azithro' in name:
            return 'Azithromycin'
        if 'ciprofloxacin' in name or 'cipro' in name:
            return 'Ciprofloxacin'
        if 'levofloxacin' in name or 'levoflox' in name:
            return 'Levofloxacin'
        if 'moxifloxacin' in name or 'moxiflox' in name:
            return 'Moxifloxacin'
        if 'gentamicin' in name:
            return 'Gentamicin'
        if 'tobramycin' in name:
            return 'Tobramycin'
        if 'amikacin' in name:
            return 'Amikacin'
        if 'clindamycin' in name or 'clindamyc' in name:
            return 'Clindamycin'
        if 'metronidazole' in name or 'metronidazol' in name:
            return 'Metronidazole'
        if 'doxycycline' in name or 'doxycycl' in name:
            return 'Doxycycline'
        if 'linezolid' in name:
            return 'Linezolid'
        if 'daptomycin' in name or 'daptomyc' in name:
            return 'Daptomycin'
        if 'tigecycline' in name or 'tigecycl' in name:
            return 'Tigecycline'
        if 'colistin' in name:
            return 'Colistin'
        if 'ertapenem' in name:
            return 'Ertapenem'
        if 'imipenem' in name:
            return 'Imipenem'
        if 'aztreonam' in name:
            return 'Aztreonam'
        if 'cefuroxime' in name or 'cefurox' in name:
            return 'Cefuroxime'
        if 'cefoxitin' in name:
            return 'Cefoxitin'
        if 'ceftaroline' in name:
            return 'Ceftaroline'
        if 'bactrim' in name or 'smx/tmp' in name or 'sulfameth' in name or 'trimethop' in name:
            return 'Bactrim (SMX/TMP)'
        if 'cefadroxil' in name or 'keflex' in name:
            return 'Cefadroxil'
        if 'erythromycin' in name:
            return 'Erythromycin'
        if 'nafcillin' in name:
            return 'Nafcillin'
        if 'oxacillin' in name:
            return 'Oxacillin'
        if 'penicillin' in name:
            return 'Penicillin'
        if 'synercid' in name or 'dalfopristin' in name or 'quinupristin' in name:
            return 'Dalfopristin/Quinupristin'
        if 'chloramphenicol' in name:
            return 'Chloramphenicol'
        if 'fosfomycin' in name:
            return 'Fosfomycin'
        return name.title()
    
    # Get distinct antibiotics
    if len(all_abx) > 0:
        all_abx['normalized_name'] = all_abx['antibiotic_name'].apply(normalize_abx_name)
        distinct_abx = all_abx['normalized_name'].dropna().unique().tolist()
    else:
        distinct_abx = []
    
    # Get ICU intime if stay_id provided
    icu_intime = None
    within_48hrs_icu = False
    antibiotics_within_48hrs_icu = []
    
    if stay_id is not None and len(all_abx) > 0:
        icu_info = query_db(f"""
            SELECT intime FROM mimiciv_icu.icustays WHERE stay_id = {stay_id}
        """)
        if len(icu_info) > 0:
            icu_intime = icu_info['intime'].iloc[0]
            
            # Check for antibiotics within 48 hours of ICU admission
            cutoff_time = icu_intime + timedelta(hours=48)
            abx_within_48h = all_abx[
                (all_abx['admin_time'] >= icu_intime) & 
                (all_abx['admin_time'] <= cutoff_time)
            ]
            
            if len(abx_within_48h) > 0:
                within_48hrs_icu = True
                antibiotics_within_48hrs_icu = abx_within_48h['normalized_name'].dropna().unique().tolist()
    
    # Build result dictionary
    result = {
        'antibiotic_administrations': all_abx[['source', 'stay_id', 'hadm_id', 'subject_id', 'antibiotic_name', 'admin_time']],
        'received_antibiotics': len(all_abx) > 0,
        'distinct_antibiotics': distinct_abx,
        'distinct_antibiotic_count': len(distinct_abx),
        'icu_intime': icu_intime,
        'within_48hrs_icu': within_48hrs_icu,
        'antibiotics_within_48hrs_icu': antibiotics_within_48hrs_icu
    }
    
    return result

FINAL_FUNCTION = get_antibiotic_info