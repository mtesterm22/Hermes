"""
Action executor for workflow engine.

This module provides functionality for executing actions within workflows,
including handling different action types and processing their results.
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple

from django.utils import timezone

from .models import Action, ActionExecution, WorkflowExecution
from .actions.database_action import DatabaseQueryAction
from .actions.datasource_refresh_action import DataSourceRefreshAction
from .actions.file_create_action import FileCreateAction
from .actions.profile_check_action import ProfileCheckAction
from .actions.iterator_action import IteratorAction
from .actions.profile_query_action import ProfileQueryAction

logger = logging.getLogger(__name__)

class ActionExecutor:
    """
    Executor for workflow actions.
    """
    
    # Registry of action handlers by action type
    ACTION_HANDLERS = {
        'database_query': DatabaseQueryAction,
        'datasource_refresh': DataSourceRefreshAction,
        'file_create': FileCreateAction,
        'profile_check': ProfileCheckAction,
        'profile_query': ProfileQueryAction,
        'iterator' : IteratorAction
        # Add more action handlers here as they are implemented
    }
    
    @classmethod
    def execute_action(
        cls,
        action_execution: ActionExecution,
        workflow_execution: WorkflowExecution,
        params: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Execute an action within a workflow.
        
        Args:
            action_execution: ActionExecution model instance
            workflow_execution: WorkflowExecution model instance
            params: Additional parameters for the action
            
        Returns:
            Tuple of (success, result_data)
        """
        # Get the action and workflow action
        action = action_execution.workflow_action.action
        workflow_action = action_execution.workflow_action
        
        # Check if action is active
        if not action.is_active:
            action_execution.status = 'skipped'
            action_execution.error_message = 'Action is disabled'
            action_execution.save(update_fields=['status', 'error_message'])
            return False, {"error": "Action is disabled"}
        
        # Merge parameters from different sources
        execution_params = {}
        
        # 1. Base parameters from action definition
        execution_params.update(action.parameters or {})
        
        # 2. Parameters from workflow action configuration
        execution_params.update(workflow_action.parameters or {})
        
        # 3. Parameters from workflow execution
        if workflow_execution.parameters:
            execution_params.update(workflow_execution.parameters)
        
        # 4. Parameters passed directly to this execution
        if params:
            execution_params.update(params)
        
        # Check for action handler
        action_type = action.action_type
        handler_class = cls.ACTION_HANDLERS.get(action_type)
        
        if not handler_class:
            error_message = f"No handler registered for action type: {action_type}"
            logger.error(error_message)
            
            action_execution.start()
            action_execution.complete('error', error_message=error_message)
            
            return False, {"error": error_message}
        
        try:
            # Instantiate the action handler
            handler = handler_class(action)
            
            # Execute the action
            logger.info(f"Executing action: {action.name} (type: {action_type})")
            success, result = handler.run(action_execution, execution_params)
            
            return success, result
            
        except Exception as e:
            error_message = f"Error executing action {action.name}: {str(e)}"
            logger.error(error_message)
            
            # Update execution status
            action_execution.start()
            action_execution.complete('error', error_message=error_message)
            
            return False, {"error": error_message}