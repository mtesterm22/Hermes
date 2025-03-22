"""
Database query action for workflows.

This module implements a database query action for the workflow engine,
leveraging the core database functionality.
"""

import logging
import json
import time
from typing import Dict, Any, Optional, Tuple, List

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.database import (
    get_connector, 
    execute_query, 
    execute_script, 
    format_results
)
from core.database.utils import (
    validate_query,
    extract_query_type,
    extract_query_params,
    limit_results
)
from datasources.models import DataSource
from workflows.models import Action, ActionExecution

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
            timeout = params.get('timeout', 30)  # default 30s timeout
            result_format = params.get('result_format', 'json')
            max_rows = params.get('max_rows', 1000)
            
            # Validate query
            is_valid, error_message = validate_query(query)
            if not is_valid:
                action_execution.complete('error', error_message=error_message)
                return False, {"error": error_message}
            
            # Apply row limit if specified
            if max_rows > 0:
                query = limit_results(query, max_rows)
            
            # Log execution
            query_type = extract_query_type(query)
            logger.info(f"Executing {query_type} query for action {self.action.name}")
            
            # Get data source
            data_source = None
            if self.action.datasource:
                # Use the action's data source
                data_source = self.action.datasource
            else:
                # Check if data source is specified in parameters
                data_source_id = params.get('data_source_id')
                if data_source_id:
                    try:
                        data_source = DataSource.objects.get(id=data_source_id)
                    except DataSource.DoesNotExist:
                        error = f"Data source with ID {data_source_id} not found"
                        action_execution.complete('error', error_message=error)
                        return False, {"error": error}
            
            if not data_source:
                error = "No data source specified for database query action"
                action_execution.complete('error', error_message=error)
                return False, {"error": error}
            
            # Get connection parameters from the data source
            connection_info = {
                'type': data_source.type if hasattr(data_source, 'type') else 'postgresql',
                'host': data_source.host if hasattr(data_source, 'host') else 'localhost',
                'port': data_source.port if hasattr(data_source, 'port') else 5432,
                'database': data_source.database if hasattr(data_source, 'database') else '',
                'user': data_source.username if hasattr(data_source, 'username') else '',
                'password': data_source.password if hasattr(data_source, 'password') else '',
            }
            
            # Add any database-specific options
            if hasattr(data_source, 'options') and data_source.options:
                if isinstance(data_source.options, dict):
                    connection_info.update(data_source.options)
                    
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
            
            # Get database connector and execute the query
            connector = get_connector(connection_info)
            if not connector:
                error = f"Failed to create database connector for {data_source.name}"
                action_execution.complete('error', error_message=error)
                return False, {"error": error}
            
            # Execute the query
            success, results, error = execute_query(
                connector,
                query,
                query_params,
                timeout
            )
            
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
                "rows_affected": results.get("rowcount", 0) if isinstance(results, dict) else len(results),
                "result": formatted_results if result_format == 'dict' else str(formatted_results)
            }
            
            # Complete the execution
            action_execution.complete('success', output_data=result_data)
            
            return True, result_data
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"Error executing database query action: {str(e)}"
            logger.error(error_message)
            
            # Complete the execution with error
            action_execution.complete('error', error_message=error_message)
            
            return False, {
                "success": False,
                "execution_time": f"{execution_time:.2f}s",
                "error": error_message
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