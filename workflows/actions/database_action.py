"""
Database query action for workflows.

This module implements a database query action for the workflow engine,
leveraging the core database functionality.
"""

import logging
import json
import time
import traceback
from typing import Dict, Any, Optional, Tuple, List

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.database import get_connector
from core.database.executors import execute_query
from core.database.formatters import format_results
from core.database.utils import validate_query, extract_query_type, extract_query_params, limit_results

from workflows.models import Action, ActionExecution, WorkflowExecution

logger = logging.getLogger(__name__)

class DatabaseQueryAction:
    """
    Implementation of database query action for workflows.
    """
    
    def __init__(self, action: Action):
        """
        Initialize the database query action.
        
        Args:
            action: Action model instance
        """
        self.action = action
        self.parameters = action.parameters or {}
    
    def run(
        self, 
        action_execution: ActionExecution, 
        execution_params: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Execute the database query action.
        
        Args:
            action_execution: ActionExecution model instance
            execution_params: Parameters for this execution
            
        Returns:
            Tuple of (success, result_data)
        """
        start_time = time.time()
        
        try:
            # Update execution status
            action_execution.start()
            
            # Merge default parameters with execution parameters
            params = {**self.parameters, **execution_params}
            
            # Extract required parameters
            query = params.get('query', '')
            timeout = params.get('timeout', 30)
            result_format = params.get('result_format', 'json')
            max_rows = params.get('max_rows', 1000)
            
            # Validate query
            is_valid, error_message = validate_query(query)
            if not is_valid:
                action_execution.complete('error', error_message=error_message)
                return False, {"error": error_message}
            
            # Get database connection from ID
            connection_id = params.get('connection_id')
            if not connection_id:
                error = "No database connection specified for database query action"
                action_execution.complete('error', error_message=error)
                return False, {"error": error}

            try:
                from datasources.connection_models import DatabaseConnection
                connection = DatabaseConnection.objects.get(id=connection_id)
                
                # Log the database type for debugging
                db_type = connection.db_type.lower() if hasattr(connection, 'db_type') else 'unknown'
                logger.info(f"Using database connection of type: {db_type}")
                
            except DatabaseConnection.DoesNotExist:
                error = f"Database connection with ID {connection_id} not found"
                action_execution.complete('error', error_message=error)
                return False, {"error": error}
            
            # Get connection info from the database connection
            connection_info = connection.get_connection_info()
            
            # Ensure the type is set correctly
            if 'type' not in connection_info or not connection_info['type']:
                if hasattr(connection, 'db_type') and connection.db_type:
                    connection_info['type'] = connection.db_type.lower()
                else:
                    error = "Database type not specified in the connection"
                    action_execution.complete('error', error_message=error)
                    return False, {"error": error}
                    
            # Debug connection info
            logger.debug(f"Connection info: {connection_info}")
            print(f"Connection type: {connection_info.get('type')}")
            print(f"Password included: {'password' in connection_info}")
            
            # Log execution
            query_type = extract_query_type(query)
            logger.info(f"Executing {query_type} query for action {self.action.name}")
            
            # Apply row limit based on database type
            original_query = query
            if max_rows > 0 and connection_info.get('type') != 'oracle':
                query = limit_results(query, max_rows)
            
            # Extract query parameters from execution context
            query_params = {}
            
            # Include any static parameters defined in the action
            if params.get('query_params') and isinstance(params.get('query_params'), dict):
                query_params.update(params.get('query_params'))
            
            # Process any parameter substitutions from workflow context
            for key, value in execution_params.items():
                if key.startswith('param_'):
                    param_name = key[6:]  # Remove 'param_' prefix
                    query_params[param_name] = value
            
            # Use type-specific connector if needed
            if connection_info.get('type') == 'oracle':
                try:
                    # Import the Oracle connector directly
                    from core.database.oracle_connector import OracleConnector
                    
                    # Create the connector
                    connector = OracleConnector(connection_info)
                    
                    # Test the connection
                    test_success, test_message = connector.test_connection()
                    if not test_success:
                        error = f"Oracle connection test failed: {test_message}"
                        logger.error(error)
                        action_execution.complete('error', error_message=error)
                        return False, {"error": error}
                    
                    # Prepare the query for Oracle
                    oracle_query = original_query.strip()
                    
                    # Remove trailing semicolon if it exists
                    if oracle_query.endswith(';'):
                        oracle_query = oracle_query[:-1].strip()
                    
                    # Apply Oracle-specific row limit if needed
                    if max_rows > 0:
                        # Check if query already has ROWNUM or FETCH FIRST
                        if 'rownum' not in oracle_query.lower() and 'fetch first' not in oracle_query.lower():
                            # Use appropriate limit syntax based on query structure
                            if 'where' in oracle_query.lower():
                                oracle_query = f"{oracle_query} AND ROWNUM <= {max_rows}"
                            else:
                                oracle_query = f"{oracle_query} WHERE ROWNUM <= {max_rows}"
                    
                    # Execute query using the Oracle connector
                    logger.info(f"Executing Oracle query: {oracle_query[:100]}...")
                    success, results, error = connector.execute_query(
                        oracle_query,
                        query_params,
                        timeout
                    )
                except Exception as e:
                    error_message = f"Error with Oracle connector: {str(e)}\n{traceback.format_exc()}"
                    logger.error(error_message)
                    action_execution.complete('error', error_message=str(e))
                    return False, {"error": str(e)}
            else:
                # Use the standard execute_query function for other database types
                try:
                    logger.info(f"Executing query using connection {connection.name}")
                    success, results, error = execute_query(
                        connection_info,
                        query,
                        query_params,
                        timeout
                    )
                except Exception as e:
                    error_message = f"Error executing query: {str(e)}"
                    logger.error(error_message)
                    action_execution.complete('error', error_message=error_message)
                    return False, {"error": error_message}
            
            if not success:
                action_execution.complete('error', error_message=error)
                return False, {"error": error}
            
            # Format the results
            format_options = params.get('format_options', {})
            formatted_results = format_results(results, result_format, format_options)
            
            # Prepare result data
            execution_time = time.time() - start_time
            result_data = {
                "success": True,
                "execution_time": f"{execution_time:.2f}s",
                "query_type": query_type,
                "connection_name": connection.name,
                "rows_affected": results.get("rowcount", 0) if isinstance(results, dict) else len(results),
                "result": formatted_results if result_format == 'dict' else str(formatted_results)
            }
            
            # Complete the execution
            action_execution.complete('success', output_data=result_data)
            
            return True, result_data
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"Error executing database query action: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_message)
            
            # Complete the execution with error
            action_execution.complete('error', error_message=str(e))
            
            return False, {
                "success": False,
                "execution_time": f"{execution_time:.2f}s",
                "error": str(e)
            }


def create_database_action_handler(action_type):
    """
    Factory function to create database action handlers based on type.
    
    Args:
        action_type: Type of database action
        
    Returns:
        Action handler instance
    """
    # For now, we only have one database action type, but this function
    # allows for future expansion to different types of database actions
    if action_type == 'database_query':
        return DatabaseQueryAction
    else:
        raise ValueError(f"Unsupported database action type: {action_type}")