"""
Iterator action for workflows.

This module implements an iterator action that processes collections of items,
allowing workflows to iterate over data collections and process each item.
"""

import logging
import time
import traceback
from typing import Dict, Any, Optional, Tuple, List

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from workflows.models import Action, ActionExecution, WorkflowExecution

logger = logging.getLogger(__name__)

class IteratorAction:
    """
    Implementation of iterator action for workflows.
    
    This action processes a collection of items, creating variables for each item
    that can be used by subsequent actions in a workflow.
    """
    
    def __init__(self, action: Action):
        """
        Initialize the iterator action.
        
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
        Execute the iterator action.
        
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
            
            # Extract parameters
            collection_source = params.get('collection_source', 'previous_action')
            source_action_id = params.get('source_action_id')
            collection_key = params.get('collection_key', 'result')
            variable_name = params.get('variable_name', 'current_item')
            index_variable = params.get('index_variable', 'index')
            custom_collection = params.get('custom_collection', [])
            max_iterations = params.get('max_iterations', 0)  # 0 = no limit

            # Get the workflow execution
            workflow_execution = action_execution.workflow_execution
            
            # Get the collection to iterate over
            collection = self._get_collection(
                collection_source, 
                source_action_id, 
                collection_key, 
                custom_collection,
                workflow_execution
            )
            
            if not collection:
                message = "No items to iterate over or collection not found"
                logger.warning(message)
                action_execution.complete('warning', error_message=message)
                return True, {
                    "success": True,
                    "warning": message,
                    "items_processed": 0,
                    "total_items": 0
                }
            
            # Apply max iterations limit if specified
            if max_iterations > 0 and len(collection) > max_iterations:
                collection = collection[:max_iterations]
                logger.info(f"Limited iteration to {max_iterations} items out of {len(collection)}")
            
            # Process each item in the collection
            results = []
            for index, item in enumerate(collection):
                # Create a variable context for this iteration
                iteration_context = {
                    variable_name: item,
                    index_variable: index,
                    'total_items': len(collection)
                }
                
                # Add the context to the workflow execution parameters
                # This makes these variables available to subsequent actions
                if not workflow_execution.parameters:
                    workflow_execution.parameters = {}
                
                # Store iteration variables in the workflow execution parameters
                workflow_execution.parameters.update(iteration_context)
                workflow_execution.save(update_fields=['parameters'])
                
                # Store this item's result
                results.append({
                    'index': index,
                    'item': item
                })
                
                # Log progress for long-running iterations
                if index > 0 and index % 100 == 0:
                    logger.info(f"Iterator progress: processed {index}/{len(collection)} items")
            
            # Prepare result data
            execution_time = time.time() - start_time
            result_data = {
                "success": True,
                "execution_time": f"{execution_time:.2f}s",
                "items_processed": len(collection),
                "total_items": len(collection),
                "variable_name": variable_name,
                "index_variable": index_variable,
                "results": results
            }
            
            # Complete the execution
            action_execution.complete('success', output_data=result_data)
            
            return True, result_data
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"Error executing iterator action: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_message)
            
            # Complete the execution with error
            action_execution.complete('error', error_message=str(e))
            
            return False, {
                "success": False,
                "execution_time": f"{execution_time:.2f}s",
                "error": str(e)
            }
    
    def _get_collection(
        self,
        collection_source: str,
        source_action_id: Optional[int],
        collection_key: str,
        custom_collection: List[Any],
        workflow_execution: WorkflowExecution
    ) -> List[Any]:
        """
        Get the collection to iterate over from the specified source.
        
        Args:
            collection_source: Source of the collection (previous_action, custom, parameter)
            source_action_id: ID of the source action (for previous_action source)
            collection_key: Key to use to extract the collection from the source
            custom_collection: Custom collection to use (for custom source)
            workflow_execution: Current workflow execution
            
        Returns:
            Collection to iterate over (list)
        """
        if collection_source == 'custom':
            # Use the custom collection directly
            return custom_collection
            
        elif collection_source == 'parameter':
            # Get collection from workflow parameters
            params = workflow_execution.parameters or {}
            collection = params.get(collection_key, [])
            
            # Convert to list if it's a dict
            if isinstance(collection, dict):
                return list(collection.items())
            elif not isinstance(collection, list):
                # Try to convert to list if possible
                try:
                    return list(collection)
                except:
                    return [collection]
            return collection
            
        elif collection_source == 'previous_action':
            # Get collection from previous action result
            if not source_action_id:
                # Try to get most recent action execution
                prev_execution = workflow_execution.action_executions.filter(
                    status='success'
                ).exclude(
                    id=workflow_execution.pk
                ).order_by('-end_time').first()
                
                if prev_execution:
                    output_data = prev_execution.output_data or {}
                    
                    # Try to get collection from result
                    collection = output_data.get(collection_key)
                    if collection is None:
                        # If not found with the key, try using the entire output
                        collection = output_data
                    
                    # Convert to list if necessary
                    if isinstance(collection, dict):
                        return list(collection.items())
                    elif not isinstance(collection, list):
                        try:
                            return list(collection)
                        except:
                            return [collection]
                    return collection
            else:
                # Get specific action execution
                try:
                    action_execution = workflow_execution.action_executions.get(
                        workflow_action__action_id=source_action_id,
                        status='success'
                    )
                    
                    output_data = action_execution.output_data or {}
                    
                    # Try to get collection from result
                    collection = output_data.get(collection_key)
                    if collection is None:
                        # If not found with the key, try using the entire output
                        collection = output_data
                    
                    # Convert to list if necessary
                    if isinstance(collection, dict):
                        return list(collection.items())
                    elif not isinstance(collection, list):
                        try:
                            return list(collection)
                        except:
                            return [collection]
                    return collection
                    
                except ActionExecution.DoesNotExist:
                    logger.error(f"Action execution for action ID {source_action_id} not found")
                    return []
        
        # Default
        return []