import pandas as pd

def get_vasoactive_agent_info(stay_id):
    """
    Extract vasoactive agent infusion information for a patient's ICU stay.

    This function queries the MIMIC-IV database to retrieve vasoactive medication
    administration data for a specific ICU stay. Vasoactive agents include:
    - Vasopressors: Norepinephrine, Epinephrine, Dopamine, Phenylephrine, Vasopressin
    - Inotropes: Dobutamine, Milrinone

    Parameters:
    -----------
    stay_id : int
        The ICU stay identifier for the patient.

    Returns:
    --------
    dict
        A dictionary containing the following keys:
        - 'received_vasoactive': bool - Whether the patient received any vasoactive agent
        - 'agents_received': list - List of vasoactive agent names received
        - 'agent_details': dict - Detailed info for each agent (min/max/avg rate, timing)
        - 'max_combined_rate': float - Maximum rate across all agents (for comparison)
        - 'num_total_records': int - Total number of vasoactive infusion records
        - 'first_time': datetime or None - First vasoactive administration time
        - 'last_time': datetime or None - Last vasoactive administration time
        - 'subject_id': int or None - Patient subject ID
        - 'hadm_id': int or None - Hospital admission ID
    """
    # Define vasoactive medication itemids
    # Vasopressors: Norepinephrine (221906), Epinephrine (221289, 229617), 
    #               Dopamine (221662), Phenylephrine (221749, 229632, 229631, 229630),
    #               Vasopressin (222315)
    # Inotropes: Dobutamine (221653), Milrinone (221986)
    vasoactive_itemids = [221289, 229617, 221653, 221662, 221986, 221906, 221749, 229632, 229631, 229630, 222315]
    
    # Query for vasoactive agent data
    sql = f"""
    WITH vasoactive_items AS (
        SELECT itemid, label
        FROM mimiciv_icu.d_items
        WHERE itemid IN ({','.join(map(str, vasoactive_itemids))})
    ),
    vasoactive_events AS (
        SELECT 
            ie.subject_id,
            ie.hadm_id,
            ie.stay_id,
            ie.itemid,
            vi.label,
            ie.rate,
            ie.rateuom,
            ie.starttime,
            ie.endtime
        FROM mimiciv_icu.inputevents ie
        JOIN vasoactive_items vi ON ie.itemid = vi.itemid
        WHERE ie.stay_id = {stay_id}
    )
    SELECT 
        subject_id,
        hadm_id,
        label,
        COUNT(*) as num_records,
        MIN(rate) as min_rate,
        MAX(rate) as max_rate,
        AVG(rate) as avg_rate,
        MIN(starttime) as first_time,
        MAX(endtime) as last_time,
        rateuom
    FROM vasoactive_events
    GROUP BY subject_id, hadm_id, label, rateuom
    """
    
    result = query_db(sql)
    
    # Initialize return dictionary
    output = {
        'received_vasoactive': False,
        'agents_received': [],
        'agent_details': {},
        'max_combined_rate': 0.0,
        'num_total_records': 0,
        'first_time': None,
        'last_time': None,
        'subject_id': None,
        'hadm_id': None
    }
    
    if result.empty:
        return output
    
    # Extract patient identifiers
    output['subject_id'] = int(result['subject_id'].iloc[0])
    output['hadm_id'] = int(result['hadm_id'].iloc[0])
    output['received_vasoactive'] = True
    
    # Process each agent
    for _, row in result.iterrows():
        agent_name = row['label']
        output['agents_received'].append(agent_name)
        
        output['agent_details'][agent_name] = {
            'num_records': int(row['num_records']),
            'min_rate': round(float(row['min_rate']), 2),
            'max_rate': round(float(row['max_rate']), 2),
            'avg_rate': round(float(row['avg_rate']), 2),
            'first_time': row['first_time'],
            'last_time': row['last_time'],
            'rateuom': row['rateuom']
        }
    
    # Calculate aggregate statistics
    output['num_total_records'] = int(result['num_records'].sum())
    output['first_time'] = result['first_time'].min()
    output['last_time'] = result['last_time'].max()
    
    # Find maximum rate across all agents
    max_rates = result['max_rate'].max()
    output['max_combined_rate'] = round(float(max_rates), 2)
    
    return output

FINAL_FUNCTION = get_vasoactive_agent_info