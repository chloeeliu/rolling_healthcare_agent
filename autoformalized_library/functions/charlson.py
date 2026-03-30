import pandas as pd

def compute_charlson(subject_id, hadm_id=None):
    """
    Calculate the Charlson Comorbidity Index (CCI) for a patient.
    
    The Charlson Comorbidity Index is a scoring system that predicts 10-year 
    mortality based on the presence of comorbid conditions. Each condition 
    is assigned a weight from 1 to 6 points.
    
    Parameters:
    -----------
    subject_id : int
        The unique patient identifier in the database.
    hadm_id : int, optional
        The hospital admission identifier. If provided, only diagnoses from 
        this admission are considered. If None, all diagnoses for the patient 
        across all admissions are considered.
    
    Returns:
    --------
    dict
        A dictionary containing:
        - 'cci_score': The total Charlson Comorbidity Index score
        - 'conditions': A dictionary of conditions found and their weights
        - 'has_cohort': Boolean indicating if CCI >= 3
    """
    
    # Define ICD-9 and ICD-10 codes for each Charlson condition
    # ICD-9 codes are stored WITHOUT decimal points in the database
    # ICD-10 codes are stored WITH decimal points
    
    # Myocardial infarction (1 point)
    mi_codes = {
        'icd9': ['410'],
        'icd10': ['I21', 'I22']
    }
    
    # Congestive heart failure (1 point)
    chf_codes = {
        'icd9': ['428'],
        'icd10': ['I50']
    }
    
    # Peripheral vascular disease (1 point)
    pvd_codes = {
        'icd9': ['443', '447', '557', '558'],
        'icd10': ['I73', 'I70', 'I71', 'I72', 'I74', 'I77', 'I79.2', 'K65.2', 'K55', 'K51.5', 'K55.0', 'K55.1', 'K55.2', 'K55.8', 'K55.9', 'K66.1']
    }
    
    # Cerebrovascular disease (1 point)
    cbd_codes = {
        'icd9': ['430', '431', '432', '433', '434', '435', '436', '437', '438'],
        'icd10': ['I60', 'I61', 'I62', 'I63', 'I64', 'I65', 'I66', 'I67', 'I69']
    }
    
    # Dementia (1 point)
    dementia_codes = {
        'icd9': ['290', '331'],
        'icd10': ['F00', 'F01', 'F02', 'F03', 'G30']
    }
    
    # Chronic pulmonary disease (1 point)
    cpd_codes = {
        'icd9': ['490', '491', '492', '493', '494', '495', '496'],
        'icd10': ['J40', 'J41', 'J42', 'J43', 'J44', 'J45', 'J46', 'J60', 'J61', 'J62', 'J63', 'J64', 'J65', 'J66', 'J67', 'J68', 'J69', 'J70']
    }
    
    # Connective tissue disease (1 point)
    ctd_codes = {
        'icd9': ['710', '714', '725', '728', '729'],
        'icd10': ['M05', 'M06', 'M08', 'M30', 'M31', 'M32', 'M33', 'M34', 'M35', 'M36']
    }
    
    # Peptic ulcer disease (1 point)
    pud_codes = {
        'icd9': ['531', '532'],
        'icd10': ['K25', 'K26', 'K27', 'K28']
    }
    
    # Mild liver disease (1 point) - ICD-9 without decimals
    mild_liver_codes = {
        'icd9': ['571', '572', '573'],
        'icd10': ['B18', 'B19', 'B23', 'B42', 'B43', 'B44', 'B45', 'B46', 'B47', 'B48', 'B49', 'K70', 'K71', 'K72', 'K73', 'K74', 'K75', 'K76', 'K77']
    }
    
    # Diabetes without end-organ damage (1 point)
    diabetes_no_comp_codes = {
        'icd9': ['249', '250'],
        'icd10': ['E10', 'E11', 'E12', 'E13', 'E14']
    }
    
    # Diabetes with end-organ damage (2 points) - ICD-9 without decimals
    diabetes_comp_codes = {
        'icd9': ['2504', '2505', '2506', '2507', '2508', '2509'],
        'icd10': ['E10.1', 'E10.2', 'E10.3', 'E10.4', 'E10.5', 'E10.6', 'E10.7', 'E10.8', 'E10.9',
                  'E11.1', 'E11.2', 'E11.3', 'E11.4', 'E11.5', 'E11.6', 'E11.7', 'E11.8', 'E11.9',
                  'E12.1', 'E12.2', 'E12.3', 'E12.4', 'E12.5', 'E12.6', 'E12.7', 'E12.8', 'E12.9',
                  'E13.1', 'E13.2', 'E13.3', 'E13.4', 'E13.5', 'E13.6', 'E13.7', 'E13.8', 'E13.9',
                  'E14.1', 'E14.2', 'E14.3', 'E14.4', 'E14.5', 'E14.6', 'E14.7', 'E14.8', 'E14.9']
    }
    
    # Hemiplegia (2 points) - ICD-9 without decimals
    hemiplegia_codes = {
        'icd9': ['342', '343', '4382'],
        'icd10': ['G80', 'G81', 'G82', 'I69.3']
    }
    
    # Moderate to severe renal disease (2 points)
    renal_codes = {
        'icd9': ['585', '586', '587', '588'],
        'icd10': ['N18', 'N19', 'N25', 'N26', 'N27', 'N28', 'N29']
    }
    
    # Any tumor (2 points) - solid tumors
    tumor_codes = {
        'icd9': ['140', '141', '142', '143', '144', '145', '146', '147', '148', '149',
                 '150', '151', '152', '153', '154', '155', '156', '157', '158', '159',
                 '160', '161', '162', '163', '164', '165', '166', '167', '168', '169',
                 '170', '171', '172', '173', '174', '175', '176', '177', '178', '179',
                 '180', '181', '182', '183', '184', '185', '186', '187', '188', '189',
                 '190', '191', '192', '193', '194', '195'],
        'icd10': ['C00', 'C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09',
                  'C10', 'C11', 'C12', 'C13', 'C14', 'C15', 'C16', 'C17', 'C18', 'C19',
                  'C20', 'C21', 'C22', 'C23', 'C24', 'C25', 'C26', 'C27', 'C28', 'C29',
                  'C30', 'C31', 'C32', 'C33', 'C34', 'C35', 'C36', 'C37', 'C38', 'C39',
                  'C40', 'C41', 'C42', 'C43', 'C44', 'C45', 'C46', 'C47', 'C48', 'C49',
                  'C50', 'C51', 'C52', 'C53', 'C54', 'C55', 'C56', 'C57', 'C58', 'C59',
                  'C60', 'C61', 'C62', 'C63', 'C64', 'C65', 'C66', 'C67', 'C68', 'C69',
                  'C70', 'C71', 'C72', 'C73', 'C74', 'C75', 'C76', 'C77', 'C78', 'C79',
                  'C80']
    }
    
    # Leukemia (2 points)
    leukemia_codes = {
        'icd9': ['204', '205', '206', '207', '208'],
        'icd10': ['C91', 'C92', 'C93', 'C94', 'C95']
    }
    
    # Lymphoma (2 points)
    lymphoma_codes = {
        'icd9': ['200', '201', '202', '203'],
        'icd10': ['C81', 'C82', 'C83', 'C84', 'C85', 'C86', 'C87', 'C88', 'C96']
    }
    
    # Moderate to severe liver disease (3 points) - ICD-9 without decimals
    # These are specific severe liver codes: 571.2, 571.5, 571.6, 571.8, 571.9
    severe_liver_codes = {
        'icd9': ['5712', '5715', '5716', '5718', '5719'],
        'icd10': ['K70.3', 'K70.4', 'K71.7', 'K72.0', 'K72.1', 'K72.9', 'K73.0', 'K73.1', 'K73.2', 'K73.9',
                  'K74.0', 'K74.1', 'K74.2', 'K74.3', 'K74.4', 'K74.5', 'K74.6', 'K75.4', 'K76.0', 'K76.1', 'K76.2', 'K76.3', 'K76.4', 'K76.5', 'K76.6', 'K76.7', 'K76.8', 'K76.9']
    }
    
    # Metastatic solid tumor (6 points)
    metastatic_codes = {
        'icd9': ['196', '197', '198', '199'],
        'icd10': ['C77', 'C78', 'C79']
    }
    
    # AIDS (6 points)
    aids_codes = {
        'icd9': ['042'],
        'icd10': ['B20']
    }
    
    # Build the SQL query to get all diagnoses for the patient
    if hadm_id is not None:
        query = """
        SELECT icd_code, icd_version
        FROM mimiciv_hosp.diagnoses_icd
        WHERE subject_id = ? AND hadm_id = ?
        """
        params = (subject_id, hadm_id)
    else:
        query = """
        SELECT icd_code, icd_version
        FROM mimiciv_hosp.diagnoses_icd
        WHERE subject_id = ?
        """
        params = (subject_id,)
    
    # Execute the query
    df = query_db(query, params)
    
    # Track which conditions have been found (use sets to avoid duplicates)
    # Conditions with 1 point
    found_1pt = set()
    # Conditions with 2 points
    found_2pt = set()
    # Conditions with 3 points
    found_3pt = set()
    # Conditions with 6 points
    found_6pt = set()
    
    # Track special conditions that need priority handling
    has_diabetes_no_comp = False
    has_diabetes_comp = False
    has_mild_liver = False
    has_severe_liver = False
    has_any_tumor = False
    has_metastatic = False
    
    for _, row in df.iterrows():
        icd_code = str(row['icd_code'])
        icd_version = str(row['icd_version'])
        
        if icd_version == '9':
            # Myocardial infarction (1 point)
            if any(icd_code.startswith(code) for code in mi_codes['icd9']):
                found_1pt.add('myocardial_infarction')
            
            # Congestive heart failure (1 point)
            if any(icd_code.startswith(code) for code in chf_codes['icd9']):
                found_1pt.add('congestive_heart_failure')
            
            # Peripheral vascular disease (1 point)
            if any(icd_code.startswith(code) for code in pvd_codes['icd9']):
                found_1pt.add('peripheral_vascular_disease')
            
            # Cerebrovascular disease (1 point)
            if any(icd_code.startswith(code) for code in cbd_codes['icd9']):
                found_1pt.add('cerebrovascular_disease')
            
            # Dementia (1 point)
            if any(icd_code.startswith(code) for code in dementia_codes['icd9']):
                found_1pt.add('dementia')
            
            # Chronic pulmonary disease (1 point)
            if any(icd_code.startswith(code) for code in cpd_codes['icd9']):
                found_1pt.add('chronic_pulmonary_disease')
            
            # Connective tissue disease (1 point)
            if any(icd_code.startswith(code) for code in ctd_codes['icd9']):
                found_1pt.add('connective_tissue_disease')
            
            # Peptic ulcer disease (1 point)
            if any(icd_code.startswith(code) for code in pud_codes['icd9']):
                found_1pt.add('peptic_ulcer_disease')
            
            # Mild liver disease (1 point)
            if any(icd_code.startswith(code) for code in mild_liver_codes['icd9']):
                has_mild_liver = True
            
            # Diabetes without end-organ damage (1 point)
            if any(icd_code.startswith(code) for code in diabetes_no_comp_codes['icd9']):
                # Check if it's not a complication code
                if not any(icd_code.startswith(code) for code in diabetes_comp_codes['icd9']):
                    has_diabetes_no_comp = True
            
            # Diabetes with end-organ damage (2 points)
            if any(icd_code.startswith(code) for code in diabetes_comp_codes['icd9']):
                has_diabetes_comp = True
            
            # Hemiplegia (2 points)
            if any(icd_code.startswith(code) for code in hemiplegia_codes['icd9']):
                found_2pt.add('hemiplegia')
            
            # Moderate to severe renal disease (2 points)
            if any(icd_code.startswith(code) for code in renal_codes['icd9']):
                found_2pt.add('moderate_severe_renal_disease')
            
            # Any tumor (2 points)
            if any(icd_code.startswith(code) for code in tumor_codes['icd9']):
                has_any_tumor = True
            
            # Leukemia (2 points)
            if any(icd_code.startswith(code) for code in leukemia_codes['icd9']):
                found_2pt.add('leukemia')
            
            # Lymphoma (2 points)
            if any(icd_code.startswith(code) for code in lymphoma_codes['icd9']):
                found_2pt.add('lymphoma')
            
            # Moderate to severe liver disease (3 points)
            if any(icd_code.startswith(code) for code in severe_liver_codes['icd9']):
                has_severe_liver = True
            
            # Metastatic solid tumor (6 points)
            if any(icd_code.startswith(code) for code in metastatic_codes['icd9']):
                has_metastatic = True
            
            # AIDS (6 points)
            if any(icd_code.startswith(code) for code in aids_codes['icd9']):
                found_6pt.add('aids')
        
        elif icd_version == '10':
            # Myocardial infarction (1 point)
            if any(icd_code.startswith(code) for code in mi_codes['icd10']):
                found_1pt.add('myocardial_infarction')
            
            # Congestive heart failure (1 point)
            if any(icd_code.startswith(code) for code in chf_codes['icd10']):
                found_1pt.add('congestive_heart_failure')
            
            # Peripheral vascular disease (1 point)
            if any(icd_code.startswith(code) for code in pvd_codes['icd10']):
                found_1pt.add('peripheral_vascular_disease')
            
            # Cerebrovascular disease (1 point)
            if any(icd_code.startswith(code) for code in cbd_codes['icd10']):
                found_1pt.add('cerebrovascular_disease')
            
            # Dementia (1 point)
            if any(icd_code.startswith(code) for code in dementia_codes['icd10']):
                found_1pt.add('dementia')
            
            # Chronic pulmonary disease (1 point)
            if any(icd_code.startswith(code) for code in cpd_codes['icd10']):
                found_1pt.add('chronic_pulmonary_disease')
            
            # Connective tissue disease (1 point)
            if any(icd_code.startswith(code) for code in ctd_codes['icd10']):
                found_1pt.add('connective_tissue_disease')
            
            # Peptic ulcer disease (1 point)
            if any(icd_code.startswith(code) for code in pud_codes['icd10']):
                found_1pt.add('peptic_ulcer_disease')
            
            # Mild liver disease (1 point)
            if any(icd_code.startswith(code) for code in mild_liver_codes['icd10']):
                has_mild_liver = True
            
            # Diabetes without end-organ damage (1 point)
            if any(icd_code.startswith(code) for code in diabetes_no_comp_codes['icd10']):
                # Check if it's not a complication code
                if not any(icd_code.startswith(code) for code in diabetes_comp_codes['icd10']):
                    has_diabetes_no_comp = True
            
            # Diabetes with end-organ damage (2 points)
            if any(icd_code.startswith(code) for code in diabetes_comp_codes['icd10']):
                has_diabetes_comp = True
            
            # Hemiplegia (2 points)
            if any(icd_code.startswith(code) for code in hemiplegia_codes['icd10']):
                found_2pt.add('hemiplegia')
            
            # Moderate to severe renal disease (2 points)
            if any(icd_code.startswith(code) for code in renal_codes['icd10']):
                found_2pt.add('moderate_severe_renal_disease')
            
            # Any tumor (2 points)
            if any(icd_code.startswith(code) for code in tumor_codes['icd10']):
                has_any_tumor = True
            
            # Leukemia (2 points)
            if any(icd_code.startswith(code) for code in leukemia_codes['icd10']):
                found_2pt.add('leukemia')
            
            # Lymphoma (2 points)
            if any(icd_code.startswith(code) for code in lymphoma_codes['icd10']):
                found_2pt.add('lymphoma')
            
            # Moderate to severe liver disease (3 points)
            if any(icd_code.startswith(code) for code in severe_liver_codes['icd10']):
                has_severe_liver = True
            
            # Metastatic solid tumor (6 points)
            if any(icd_code.startswith(code) for code in metastatic_codes['icd10']):
                has_metastatic = True
            
            # AIDS (6 points)
            if any(icd_code.startswith(code) for code in aids_codes['icd10']):
                found_6pt.add('aids')
    
    # Calculate the CCI score
    cci_score = 0
    conditions = {}
    
    # Add points for each found condition (1 point each)
    for condition in found_1pt:
        conditions[condition] = 1
        cci_score += 1
    
    # Add points for each found condition (2 points each)
    for condition in found_2pt:
        conditions[condition] = 2
        cci_score += 2
    
    # Add points for each found condition (3 points each)
    for condition in found_3pt:
        conditions[condition] = 3
        cci_score += 3
    
    # Add points for each found condition (6 points each)
    for condition in found_6pt:
        conditions[condition] = 6
        cci_score += 6
    
    # Handle special cases
    
    # Diabetes: if both no-comp and comp are found, only count comp (2 points)
    if has_diabetes_comp:
        conditions['diabetes_with_end_organ_damage'] = 2
        cci_score += 2
    elif has_diabetes_no_comp:
        conditions['diabetes_without_end_organ_damage'] = 1
        cci_score += 1
    
    # Liver disease: if both mild and severe are found, only count severe (3 points)
    if has_severe_liver:
        conditions['moderate_severe_liver_disease'] = 3
        cci_score += 3
    elif has_mild_liver:
        conditions['mild_liver_disease'] = 1
        cci_score += 1
    
    # Tumor: if metastatic is found, count 6 points; otherwise if any tumor, count 2 points
    if has_metastatic:
        conditions['metastatic_solid_tumor'] = 6
        cci_score += 6
    elif has_any_tumor:
        conditions['any_tumor'] = 2
        cci_score += 2
    
    return {
        'cci_score': cci_score,
        'conditions': conditions,
        'has_cohort': cci_score >= 3
    }

FINAL_FUNCTION = compute_charlson