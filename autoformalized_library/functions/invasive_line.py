# Step 16: Create the final self-contained function

import pandas as pd

# Define the line type mappings - item IDs that indicate each line type is present
LINE_TYPE_MAPPINGS = {
    'Arterial Line': [226107, 224289, 224291],
    'Multi Lumen (CVL)': [226113, 224281, 227756, 224283],
    'CCO PAC': [226108, 225225, 227751, 225227],
    'PA Catheter': [226114, 225355, 227757, 225357],
    'PICC Line': [226115, 224188, 227759],
    'Dialysis Catheter': [226118, 225323, 227753],
    'IABP line': [226110, 227754],
    'ICP Catheter': [226124, 226129],
    'Cordis/Introducer': [226109, 224297, 227752],
    'Triple Introducer': [226120, 225395, 227763, 225397]
}

# Get all item IDs for the query
ALL_LINE_ITEM_IDS = []
for item_ids in LINE_TYPE_MAPPINGS.values():
    ALL_LINE_ITEM_IDS.extend(item_ids)

def get_invasive_lines(subject_id, hadm_id=None, stay_id=None):
    """
    Extract invasive line information for a patient.
    
    Parameters:
    - subject_id: Patient identifier (required)
    - hadm_id: Hospital admission identifier (optional)
    - stay_id: ICU stay identifier (optional)
    
    Returns:
    - Dictionary with:
        - subject_id: The patient's subject_id
        - hadm_id: The hadm_id used (or None)
        - stay_id: The stay_id used (or None)
        - lines_present: List of line type names found
        - line_details: Dictionary with details for each line type found
    """
    # Build WHERE clause based on provided identifiers
    where_clauses = [f"ce.subject_id = {subject_id}"]
    if hadm_id is not None:
        where_clauses.append(f"ce.hadm_id = {hadm_id}")
    if stay_id is not None:
        where_clauses.append(f"ce.stay_id = {stay_id}")
    
    where_clause = " AND ".join(where_clauses)
    
    # Query for all invasive line related events
    sql = f"""
    SELECT ce.itemid, di.label, ce.charttime, ce.value, ce.valuenum
    FROM mimiciv_icu.chartevents ce
    JOIN mimiciv_icu.d_items di ON ce.itemid = di.itemid
    WHERE {where_clause}
      AND ce.itemid IN ({','.join(map(str, ALL_LINE_ITEM_IDS))})
    ORDER BY ce.charttime
    """
    df = query_db(sql)
    
    if df.empty:
        return {
            'subject_id': subject_id,
            'hadm_id': hadm_id,
            'stay_id': stay_id,
            'lines_present': [],
            'line_details': {}
        }
    
    # Determine which line types are present
    lines_present = {}
    line_details = {}
    
    for line_type, item_ids in LINE_TYPE_MAPPINGS.items():
        line_events = df[df['itemid'].isin(item_ids)]
        if not line_events.empty:
            lines_present[line_type] = True
            # Get first occurrence time
            first_time = line_events['charttime'].min()
            # Get unique values observed
            values = line_events['value'].dropna().unique().tolist()
            valuenums = line_events['valuenum'].dropna().unique().tolist()
            
            line_details[line_type] = {
                'first_seen': str(first_time),
                'event_count': len(line_events),
                'values_observed': values,
                'valuenum_observed': valuenums
            }
    
    return {
        'subject_id': subject_id,
        'hadm_id': hadm_id,
        'stay_id': stay_id,
        'lines_present': list(lines_present.keys()),
        'line_details': line_details
    }

FINAL_FUNCTION = get_invasive_lines