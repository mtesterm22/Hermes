"""
Data source refresh action for workflows.

This module implements a data source refresh action for the workflow engine,
allowing workflows to trigger synchronizations of data sources.
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple, List, Union

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from datasources.models import DataSource, DataSourceSync
from datasources.tasks import sync_datasource
from workflows.models import Action, ActionExecution

logger = logging.getLogger(__name__)

class DataSourceRefreshAction:
    """
    Implementation of data source refresh action for workflows.
    
    This action triggers a synchronization of a specified data source or sources.
    It can be configured to run synchronously (wait for completion) or asynchronously,
    and supports refreshing multiple data sources in sequence.
    """
    
    def __init__(self, action: Action):
        """
        Initialize the data source refresh action.
        
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
        Execute the data source refresh action.
        
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
            datasource_ids = params.get('datasource_ids', [])
            wait_for_completion = params.get('wait_for_completion', False)
            timeout = params.get('timeout', 600)  # default 10 minutes timeout
            
            # Allow single datasource_id for convenience
            single_datasource_id = params.get('datasource_id')
            if single_datasource_id and not datasource_ids:
                datasource_ids = [single_datasource_id]
            
            # Validate parameters
            if not datasource_ids:
                error_message = "No data sources specified for refresh action"
                action_execution.complete('error', error_message=error_message)
                return False, {"error": error_message}
            
            # Initialize results
            results = {
                "datasources_refreshed": 0,
                "datasources_failed": 0,
                "sync_ids": [],
                "details": []
            }
            
            # Debug log
            print(f"Data Source Refresh Action: Processing {len(datasource_ids)} data sources")
            print(f"Wait for completion: {wait_for_completion}")
            print(f"Timeout: {timeout} seconds")
            
            # Process each data source
            for datasource_id in datasource_ids:
                try:
                    # Get the data source
                    try:
                        datasource = DataSource.objects.get(id=datasource_id)
                        print(f"Processing data source: {datasource.name} (ID: {datasource_id}, Type: {datasource.type})")
                    except DataSource.DoesNotExist:
                        error = f"Data source with ID {datasource_id} not found"
                        print(f"Error: {error}")
                        results["details"].append({
                            "datasource_id": datasource_id,
                            "status": "error",
                            "message": error
                        })
                        results["datasources_failed"] += 1
                        continue
                    
                    # Check if data source is already syncing
                    if datasource.is_syncing():
                        message = f"Data source '{datasource.name}' is already being synchronized"
                        print(f"Warning: {message}")
                        results["details"].append({
                            "datasource_id": datasource_id,
                            "name": datasource.name,
                            "status": "warning",
                            "message": message
                        })
                        continue
                    
                    # Create sync record
                    sync = DataSourceSync.objects.create(
                        datasource=datasource,
                        status='running',
                        triggered_by=self.action.created_by  # Use action creator as trigger user
                    )
                    
                    # Store sync ID
                    results["sync_ids"].append(sync.id)
                    
                    # Get a user ID for the task
                    user_id = None
                    if self.action.created_by:
                        user_id = self.action.created_by.id
                    
                    # Run synchronously or asynchronously based on parameter
                    if wait_for_completion:
                        print(f"Running synchronous refresh for '{datasource.name}'")
                        # Get the appropriate connector based on data source type
                        if datasource.type == 'csv':
                            from datasources.connectors.csv_connector import CSVConnector
                            connector = CSVConnector(datasource)
                        elif datasource.type == 'database':
                            from datasources.connectors.database_connector import DatabaseConnector
                            connector = DatabaseConnector(datasource)
                        else:
                            error = f"Unsupported data source type: {datasource.type}"
                            print(f"Error: {error}")
                            sync.complete(status='error', error_message=error)
                            results["details"].append({
                                "datasource_id": datasource_id,
                                "name": datasource.name,
                                "status": "error",
                                "message": error,
                                "sync_id": sync.id
                            })
                            results["datasources_failed"] += 1
                            continue
                        
                        # Run the sync directly
                        try:
                            sync_result = connector.sync_data(triggered_by=self.action.created_by)
                            
                            # Update results
                            if sync_result.status == 'success':
                                print(f"Sync successful for '{datasource.name}'")
                                results["datasources_refreshed"] += 1
                                results["details"].append({
                                    "datasource_id": datasource_id,
                                    "name": datasource.name,
                                    "status": "success",
                                    "message": f"Successfully refreshed data source '{datasource.name}'",
                                    "sync_id": sync.id,
                                    "records_processed": sync_result.records_processed,
                                    "records_created": sync_result.records_created,
                                    "records_updated": sync_result.records_updated
                                })
                            else:
                                print(f"Sync failed for '{datasource.name}': {sync_result.error_message}")
                                results["datasources_failed"] += 1
                                results["details"].append({
                                    "datasource_id": datasource_id,
                                    "name": datasource.name,
                                    "status": "error",
                                    "message": sync_result.error_message or f"Failed to refresh data source '{datasource.name}'",
                                    "sync_id": sync.id
                                })
                        except Exception as sync_error:
                            error_message = f"Error syncing data source '{datasource.name}': {str(sync_error)}"
                            print(f"Exception during sync: {error_message}")
                            import traceback
                            print(traceback.format_exc())
                            
                            # Make sure the sync is marked as failed
                            sync.complete(status='error', error_message=error_message)
                            
                            results["datasources_failed"] += 1
                            results["details"].append({
                                "datasource_id": datasource_id,
                                "name": datasource.name,
                                "status": "error",
                                "message": error_message,
                                "sync_id": sync.id
                            })
                    else:
                        # Run the sync asynchronously via task
                        print(f"Initiating asynchronous refresh for '{datasource.name}'")
                        from datasources.tasks import sync_datasource as sync_task
                        sync_task.delay(datasource.id, user_id)
                        
                        results["datasources_refreshed"] += 1
                        results["details"].append({
                            "datasource_id": datasource_id,
                            "name": datasource.name,
                            "status": "initiated",
                            "message": f"Refresh initiated for data source '{datasource.name}'",
                            "sync_id": sync.id
                        })
                
                except Exception as e:
                    # Handle errors for individual data sources
                    error_message = f"Error processing data source (ID: {datasource_id}): {str(e)}"
                    print(f"Exception: {error_message}")
                    import traceback
                    print(traceback.format_exc())
                    
                    results["datasources_failed"] += 1
                    results["details"].append({
                        "datasource_id": datasource_id,
                        "status": "error",
                        "message": error_message
                    })
            
            # Determine overall success
            execution_time = time.time() - start_time
            if results["datasources_failed"] == 0 and results["datasources_refreshed"] > 0:
                final_status = 'success'
            elif results["datasources_refreshed"] > 0:
                final_status = 'warning'  # Some succeeded, some failed
            else:
                final_status = 'error'  # All failed
            
            # Prepare result data
            result_data = {
                "success": final_status != 'error',
                "execution_time": f"{execution_time:.2f}s",
                "total_datasources": len(datasource_ids),
                "datasources_refreshed": results["datasources_refreshed"],
                "datasources_failed": results["datasources_failed"],
                "sync_ids": results["sync_ids"],
                "details": results["details"]
            }
            
            # Complete the execution
            print(f"Completing action execution with status: {final_status}")
            action_execution.complete(final_status, output_data=result_data)
            
            return final_status != 'error', result_data
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"Error executing data source refresh action: {str(e)}"
            print(f"Exception in data source refresh action: {error_message}")
            import traceback
            print(traceback.format_exc())
            
            # Complete the execution with error
            action_execution.complete('error', error_message=error_message)
            
            return False, {
                "success": False,
                "execution_time": f"{execution_time:.2f}s",
                "error": error_message
            }