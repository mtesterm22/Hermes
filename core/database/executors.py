"""
Query execution utilities for database operations.

This module provides functions for executing database queries with
proper error handling, logging, and result processing.
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple, Union, List

from .connectors import DatabaseConnector, get_connector

logger = logging.getLogger(__name__)

def execute_query(
    connector: Union[DatabaseConnector, Dict[str, Any]], 
    query: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    max_retries: int = 0,
    retry_delay: int = 1
) -> Tuple[bool, Any, str]:
    """
    Execute a SQL query with the provided connector and parameters.
    
    Args:
        connector: Either a DatabaseConnector instance or connection info dict
        query: SQL query to execute
        params: Optional parameters for the query
        timeout: Optional timeout in seconds
        max_retries: Maximum number of retries on failure
        retry_delay: Delay between retries in seconds
        
    Returns:
        Tuple of (success, results, error_message)
    """
    # Get a connector instance if connection_info was provided
    if isinstance(connector, dict):
        connector_instance = get_connector(connector)
        if connector_instance is None:
            return False, None, "Unable to create database connector"
    else:
        connector_instance = connector
    
    # Execute the query with retry logic
    retries = 0
    last_error = ""
    
    while retries <= max_retries:
        try:
            # Ensure connection is established
            if not connector_instance.connection:
                connector_instance.connect()
            
            # Execute the query
            start_time = time.time()
            success, results, error = connector_instance.execute_query(query, params, timeout)
            execution_time = time.time() - start_time
            
            # Log query execution
            if success:
                logger.info(f"Query executed successfully in {execution_time:.2f}s")
                return success, results, error
            else:
                last_error = error
                logger.warning(f"Query execution failed: {error}")
                
                # Retry if we haven't exceeded max_retries
                if retries < max_retries:
                    retries += 1
                    logger.info(f"Retrying query (attempt {retries}/{max_retries})...")
                    time.sleep(retry_delay)
                else:
                    return False, None, f"Query failed after {retries} retries: {last_error}"
        
        except Exception as e:
            last_error = str(e)
            logger.error(f"Error executing query: {last_error}")
            
            # Retry if we haven't exceeded max_retries
            if retries < max_retries:
                retries += 1
                logger.info(f"Retrying query (attempt {retries}/{max_retries})...")
                time.sleep(retry_delay)
            else:
                return False, None, f"Query failed after {retries} retries: {last_error}"
    
    # Should not reach here, but just in case
    return False, None, f"Query execution failed: {last_error}"


def execute_script(
    connector: Union[DatabaseConnector, Dict[str, Any]], 
    script: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    max_retries: int = 0,
    retry_delay: int = 1
) -> Tuple[bool, Any, str]:
    """
    Execute a SQL script with the provided connector and parameters.
    
    Args:
        connector: Either a DatabaseConnector instance or connection info dict
        script: SQL script to execute (may contain multiple statements)
        params: Optional parameters for the script
        timeout: Optional timeout in seconds
        max_retries: Maximum number of retries on failure
        retry_delay: Delay between retries in seconds
        
    Returns:
        Tuple of (success, results, error_message)
    """
    # Get a connector instance if connection_info was provided
    if isinstance(connector, dict):
        connector_instance = get_connector(connector)
        if connector_instance is None:
            return False, None, "Unable to create database connector"
    else:
        connector_instance = connector
    
    # Execute the script with retry logic
    retries = 0
    last_error = ""
    
    while retries <= max_retries:
        try:
            # Ensure connection is established
            if not connector_instance.connection:
                connector_instance.connect()
            
            # Execute the script
            start_time = time.time()
            success, results, error = connector_instance.execute_script(script, params, timeout)
            execution_time = time.time() - start_time
            
            # Log script execution
            if success:
                logger.info(f"Script executed successfully in {execution_time:.2f}s")
                return success, results, error
            else:
                last_error = error
                logger.warning(f"Script execution failed: {error}")
                
                # Retry if we haven't exceeded max_retries
                if retries < max_retries:
                    retries += 1
                    logger.info(f"Retrying script (attempt {retries}/{max_retries})...")
                    time.sleep(retry_delay)
                else:
                    return False, None, f"Script failed after {retries} retries: {last_error}"
        
        except Exception as e:
            last_error = str(e)
            logger.error(f"Error executing script: {last_error}")
            
            # Retry if we haven't exceeded max_retries
            if retries < max_retries:
                retries += 1
                logger.info(f"Retrying script (attempt {retries}/{max_retries})...")
                time.sleep(retry_delay)
            else:
                return False, None, f"Script failed after {retries} retries: {last_error}"
    
    # Should not reach here, but just in case
    return False, None, f"Script execution failed: {last_error}"