# users/utils.py

def coalesce_identifiers(raw_identifiers):
    """
    Restructures raw identifiers from {source -> {attr -> value}} 
    to {attr -> [{value, source_names}]}
    
    Args:
        raw_identifiers: Dictionary with format {source_name: {attr_name: value}}
        
    Returns:
        Dictionary with format {attr_name: [{value, source_names}]}
    """
    if not raw_identifiers:
        return {}
        
    # First, collect all values for each attribute across all sources
    attr_values = {}
    for source, attributes in raw_identifiers.items():
        for attr_name, value in attributes.items():
            if attr_name not in attr_values:
                attr_values[attr_name] = {}
            
            # Use the value as a key to group by unique values
            if value not in attr_values[attr_name]:
                attr_values[attr_name][value] = []
            
            # Add this source to the list of sources for this value
            attr_values[attr_name][value].append(source)
    
    # Convert the nested dict to the final format expected by the template
    coalesced = {}
    for attr_name in attr_values:
        # Convert dict of value->sources to list of {value, source_names} objects
        entries = []
        for value, sources in attr_values[attr_name].items():
            entries.append({
                'value': value,
                'source_names': sources
            })
        coalesced[attr_name] = entries
    
    return coalesced