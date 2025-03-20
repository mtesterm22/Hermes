"""
Core database functionality for Hermes.

This module provides centralized database connection and query execution
capabilities that can be used by both data sources and workflow actions.
"""

from .connectors import DatabaseConnector, get_connector
from .executors import execute_query, execute_script
from .formatters import format_results
from .oracle_connector import OracleConnector

def get_connector(connection_info):
    """
    Factory function to get a database connector based on connection info.
    
    Args:
        connection_info: Dictionary with connection parameters
        
    Returns:
        Database connector instance
    """
    db_type = connection_info.get('type', '').lower()
    
    if db_type == 'oracle':
        return OracleConnector(connection_info)
    # if db_type == 'postgresql':
        # return PostgreSQLConnector(connection_info)
    # elif db_type == 'mysql':
        # return MySQLConnector(connection_info)
    # elif db_type == 'sqlserver':
        # return SQLServerConnector(connection_info)
    # ... other database types ...
    else:
        return None

__all__ = [
    'DatabaseConnector',
    'get_connector',
    'execute_query',
    'execute_script',
    'format_results',
]