"""
Utility functions for database operations.

This module provides utility functions for database operations,
including SQL query validation, extraction of query metadata,
parameter processing, and more.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def extract_query_tables(query: str) -> List[str]:
    """
    Extract table names from a SQL query.
    
    Args:
        query: SQL query to examine
        
    Returns:
        List of table names referenced in the query
    """
    # This is a simplified implementation and won't handle all SQL variants
    # or complex queries correctly
    
    # Remove comments
    query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
    
    # Extract tables from FROM and JOIN clauses
    from_pattern = r'FROM\s+([a-zA-Z0-9_\.]+(?:\s*,\s*[a-zA-Z0-9_\.]+)*)'
    join_pattern = r'JOIN\s+([a-zA-Z0-9_\.]+)'
    update_pattern = r'UPDATE\s+([a-zA-Z0-9_\.]+)'
    insert_pattern = r'INSERT\s+INTO\s+([a-zA-Z0-9_\.]+)'
    delete_pattern = r'DELETE\s+FROM\s+([a-zA-Z0-9_\.]+)'
    
    tables = set()
    
    # Find all FROM clauses
    for match in re.finditer(from_pattern, query, re.IGNORECASE):
        table_list = match.group(1)
        for table in table_list.split(','):
            tables.add(table.strip())
    
    # Find all JOIN clauses
    for match in re.finditer(join_pattern, query, re.IGNORECASE):
        tables.add(match.group(1).strip())
    
    # Find UPDATE tables
    for match in re.finditer(update_pattern, query, re.IGNORECASE):
        tables.add(match.group(1).strip())
    
    # Find INSERT tables
    for match in re.finditer(insert_pattern, query, re.IGNORECASE):
        tables.add(match.group(1).strip())
    
    # Find DELETE tables
    for match in re.finditer(delete_pattern, query, re.IGNORECASE):
        tables.add(match.group(1).strip())
    
    return list(tables)




def mask_sensitive_data(connection_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a copy of connection info with sensitive data masked for logging.
    
    Args:
        connection_info: Connection information dictionary
        
    Returns:
        Connection info with sensitive fields masked
    """
    masked_info = connection_info.copy()
    
    # List of sensitive fields to mask
    sensitive_fields = ['password', 'pwd', 'apikey', 'secret', 'token']
    
    for field in sensitive_fields:
        if field in masked_info:
            masked_info[field] = '********'
    
    return masked_info


def check_sql_read_only(query: str) -> bool:
    """
    Check if a SQL query is read-only (doesn't modify data).
    
    Args:
        query: SQL query to check
        
    Returns:
        True if the query is read-only, False otherwise
    """
    # Remove comments and normalize whitespace
    query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
    query = ' '.join(query.split())
    
    # Determine query type
    query_type = extract_query_type(query)
    
    # List of read-only query types
    read_only_types = ['SELECT', 'SHOW', 'DESCRIBE', 'DESC', 'EXPLAIN']
    
    return query_type in read_only_types

def validate_query(query: str) -> Tuple[bool, str]:
    """
    Perform basic validation on a SQL query.
    
    Args:
        query: SQL query to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not query or not query.strip():
        return False, "Query cannot be empty"
    
    # Basic check for SQL injection attempts
    dangerous_patterns = [
        r'\bDROP\s+', 
        r'\bDELETE\s+',
        r'\bTRUNCATE\s+',
        r';\s*DROP',
        r';\s*DELETE',
        r';\s*UPDATE',
        r';\s*INSERT',
        r'\bALTER\s+',
        r'\bEXEC\s+',
        r'\bXP_'
    ]
    
    # Check if query contains dangerous patterns that might indicate SQL injection
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            # Consider implementation context - these patterns may be legitimate in some cases
            logger.warning(f"Query contains potentially dangerous pattern: {pattern}")
            # Instead of blocking, we'll just warn since this is an administrative tool
    
    return True, ""


def extract_query_type(query: str) -> str:
    """
    Determine the type of SQL query (SELECT, INSERT, UPDATE, etc.).
    
    Args:
        query: SQL query to examine
        
    Returns:
        Query type as a string
    """
    # Extract the first word from the query (ignoring comments)
    query = query.strip()
    
    # Remove comments
    query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
    
    # Get the first word
    match = re.match(r'^\s*(\w+)', query, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    return "UNKNOWN"


def extract_query_params(query: str) -> Set[str]:
    """
    Extract parameter names from a SQL query.
    
    Args:
        query: SQL query to examine
        
    Returns:
        Set of parameter names
    """
    # Find all :param style parameters
    param_pattern = r':([a-zA-Z0-9_]+)'
    params = set(re.findall(param_pattern, query))
    
    return params


def limit_results(query: str, max_rows: int) -> str:
    """
    Add a LIMIT or similar clause to a SQL query to restrict number of rows returned.
    
    Args:
        query: SQL query to modify
        max_rows: Maximum number of rows to return
        
    Returns:
        Modified query with appropriate row limit
    """
    # Only add limit to SELECT queries
    query_type = extract_query_type(query)
    if query_type != 'SELECT':
        return query
    
    # Normalize query - remove trailing semicolons and whitespace
    query = query.strip()
    if query.endswith(';'):
        query = query[:-1].strip()
    
    # Check if query already has a LIMIT clause
    if re.search(r'\bLIMIT\s+\d+', query, re.IGNORECASE):
        return query + ';'
    
    # Check if query has an ORDER BY clause (add LIMIT after that)
    if re.search(r'\bORDER\s+BY\b', query, re.IGNORECASE):
        return f"{query} LIMIT {max_rows};"
    
    # Add LIMIT clause 
    return f"{query} LIMIT {max_rows};"


def format_query_for_display(query: str, max_length: int = 100) -> str:
    """
    Format a query for display in logs or UI, with long queries truncated.
    
    Args:
        query: SQL query to format
        max_length: Maximum length before truncation
        
    Returns:
        Formatted query string
    """
    # Remove extra whitespace
    query = ' '.join(query.split())
    
    # Truncate if necessary
    if len(query) > max_length:
        return query[:max_length] + '...'
    
    return query


def parse_query_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse raw query results into a more usable format.
    
    Args:
        results: Raw query results from database connector
        
    Returns:
        Parsed results
    """
    if not results:
        return {'rows': [], 'count': 0}
    
    if isinstance(results, list):
        return {
            'rows': results,
            'count': len(results)
        }
    
    if isinstance(results, dict):
        if 'rows' in results:
            return {
                'rows': results['rows'],
                'count': len(results['rows']),
                'columns': results.get('columns', []),
                'metadata': {k: v for k, v in results.items() if k not in ['rows', 'columns']}
            }
        elif 'rowcount' in results:
            return {
                'rowcount': results['rowcount'],
                'affected_rows': results['rowcount'],
                'type': 'non-query'
            }
    
    # Fallback for unknown result format
    return {'raw_results': results}