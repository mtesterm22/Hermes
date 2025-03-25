"""
Workflow execution engine.

This module handles the execution of workflows, including conditional logic
and appropriate error handling.
"""

import logging
import time
import json
import re
from typing import Dict, Any, Optional, List, Tuple
import traceback

from django.utils import timezone

from .models import Workflow, WorkflowAction, WorkflowExecution, ActionExecution
from .action_executor import ActionExecutor

logger = logging.getLogger(__name__)

class WorkflowEngine:
    """
    Engine for executing workflows.
    
    This class handles the execution of workflows, including conditional branching
    and appropriate error handling. It tracks the execution state and manages the
    flow between different actions in the workflow.
    """
    
    def __init__(self, workflow_execution: WorkflowExecution):
        """
        Initialize the workflow engine.
        
        Args:
            workflow_execution: WorkflowExecution instance
        """
        self.workflow_execution = workflow_execution
        self.workflow = workflow_execution.workflow
        self.workflow_data = workflow_execution.workflow.workflow_data or {}
        
        # Execution context for sharing data between actions
        self.execution_context = {
            'parameters': workflow_execution.parameters or {},
            'results': {},
            'variables': {},
            'errors': []
        }
        
        # Execution tracking
        self.executed_actions = set()
        self.current_action = None
        self.execution_path = []
    
    def execute(self) -> bool:
        """
        Execute the workflow.
        
        Returns:
            True if workflow executed successfully, False otherwise
        """
        try:
            # Start execution
            self.workflow_execution.status = 'running'
            self.workflow_execution.save(update_fields=['status'])
            
            logger.info(f"Starting workflow execution: {self.workflow.name} (ID: {self.workflow.id})")
            
            # If workflow has designer data, use that for execution
            if self.workflow.has_designer_data() and self.workflow_data:
                success = self._execute_from_designer_data()
            else:
                # Otherwise, fall back to legacy sequential execution
                success = self._execute_sequential()
            
            # Complete execution
            end_status = 'success' if success else 'error'
            self.workflow_execution.status = end_status
            self.workflow_execution.end_time = timezone.now()
            
            # Store result data from execution context
            result_data = {
                'execution_path': self.execution_path,
                'results': self.execution_context['results'],
                'errors': self.execution_context['errors']
            }
            self.workflow_execution.result_data = result_data
            
            self.workflow_execution.save(update_fields=['status', 'end_time', 'result_data'])
            
            logger.info(f"Workflow execution completed: {self.workflow.name} (ID: {self.workflow.id}) - Status: {end_status}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error executing workflow {self.workflow.name} (ID: {self.workflow.id}): {str(e)}")
            logger.error(traceback.format_exc())
            
            # Mark execution as failed
            self.workflow_execution.status = 'error'
            self.workflow_execution.end_time = timezone.now()
            self.workflow_execution.error_message = str(e)
            self.workflow_execution.save(update_fields=['status', 'end_time', 'error_message'])
            
            return False
    
    def _execute_sequential(self) -> bool:
        """
        Execute workflow actions sequentially.
        
        This is the legacy execution method that simply runs actions in sequence
        based on their sequence numbers.
        
        Returns:
            True if all actions executed successfully, False otherwise
        """
        # Get all workflow actions in sequence order
        workflow_actions = self.workflow.get_actions()
        
        if not workflow_actions:
            logger.warning(f"No actions found for workflow {self.workflow.name} (ID: {self.workflow.id})")
            return True  # Return True for empty workflows
        
        # Execute each action in sequence
        for workflow_action in workflow_actions:
            # Check if action is active
            if not workflow_action.action.is_active:
                logger.info(f"Skipping inactive action: {workflow_action.action.name} (ID: {workflow_action.action.id})")
                continue
            
            # Create action execution record
            action_execution = ActionExecution.objects.create(
                workflow_execution=self.workflow_execution,
                workflow_action=workflow_action,
                status='pending'
            )
            
            # Check condition if present
            if workflow_action.condition:
                condition_result = self._evaluate_condition(workflow_action.condition)
                if not condition_result:
                    logger.info(f"Skipping action due to condition: {workflow_action.action.name} (ID: {workflow_action.action.id})")
                    action_execution.status = 'skipped'
                    action_execution.save(update_fields=['status'])
                    continue
            
            # Track current action
            self.current_action = workflow_action
            self.execution_path.append({
                'action_id': workflow_action.action.id,
                'action_name': workflow_action.action.name,
                'sequence': workflow_action.sequence
            })
            
            logger.info(f"Executing action: {workflow_action.action.name} (ID: {workflow_action.action.id})")
            
            # Execute the action
            success, result = ActionExecutor.execute_action(
                action_execution,
                self.workflow_execution,
                self.execution_context['parameters']
            )
            
            # Update execution context with action results
            self._update_execution_context(action_execution)
            
            # Store result in execution context
            result_key = f"action_{workflow_action.action.id}"
            self.execution_context['results'][result_key] = result
            
            if not success:
                logger.error(f"Action execution failed: {workflow_action.action.name} (ID: {workflow_action.action.id})")
                
                # Add error to execution context
                self.execution_context['errors'].append({
                    'action_id': workflow_action.action.id,
                    'action_name': workflow_action.action.name,
                    'error': result.get('error', 'Unknown error')
                })
                
                # Check if we should continue despite the error
                if not workflow_action.error_handling.get('continue_on_error', False):
                    return False
            
            # Add action to executed set
            self.executed_actions.add(workflow_action.id)
        
        return True
    
    def _execute_from_designer_data(self) -> bool:
        """
        Execute workflow based on designer data.
        
        This method uses the workflow_data JSON to determine the execution flow,
        including handling conditionals and branches.
        
        Returns:
            True if workflow executed successfully, False otherwise
        """
        # Find the start node
        start_node_id = None
        for node_id, node_data in self.workflow_data.items():
            if node_data.get('type') == 'start':
                start_node_id = node_id
                break
        
        if not start_node_id:
            logger.error(f"No start node found in workflow {self.workflow.name} (ID: {self.workflow.id})")
            return False
        
        # Execute starting from the start node
        return self._execute_node(start_node_id)
    
    def _execute_node(self, node_id: str) -> bool:
        """
        Execute a specific node in the workflow.
        
        This recursively follows connections to execute the entire workflow.
        
        Args:
            node_id: ID of the node to execute
            
        Returns:
            True if execution was successful, False otherwise
        """
        # Check if this node exists
        if node_id not in self.workflow_data:
            logger.error(f"Node {node_id} not found in workflow data")
            return False
        
        node_data = self.workflow_data[node_id]
        node_type = node_data.get('type')
        
        logger.debug(f"Executing node: {node_id} (Type: {node_type})")
        
        # Handle different node types
        if node_type == 'start':
            # Start node, just follow connections
            return self._follow_connections(node_id)
            
        elif node_type == 'end':
            # End node, execution is successful
            return True
            
        elif node_type == 'action':
            # Execute action and follow connections if successful
            success = self._execute_action_node(node_id, node_data)
            
            if success:
                return self._follow_connections(node_id)
            else:
                # Check if we should continue despite the error
                action_id = node_data.get('actionId')
                try:
                    workflow_action = WorkflowAction.objects.get(
                        workflow=self.workflow,
                        action_id=action_id
                    )
                    
                    if workflow_action.error_handling.get('continue_on_error', False):
                        return self._follow_connections(node_id)
                except WorkflowAction.DoesNotExist:
                    pass
                
                return False
                
        elif node_type == 'conditional':
            # Evaluate condition and follow appropriate path
            return self._execute_conditional_node(node_id, node_data)
            
        else:
            logger.error(f"Unknown node type: {node_type}")
            return False
    
    def _execute_action_node(self, node_id: str, node_data: Dict[str, Any]) -> bool:
        """
        Execute an action node.
        
        Args:
            node_id: ID of the node
            node_data: Node data from workflow_data
            
        Returns:
            True if action executed successfully, False otherwise
        """
        action_id = node_data.get('actionId')
        if not action_id:
            logger.error(f"No action ID for node {node_id}")
            return False
        
        try:
            # Get the action
            from .models import Action
            action = Action.objects.get(id=action_id)
            
            # Check if action is active
            if not action.is_active:
                logger.info(f"Skipping inactive action: {action.name} (ID: {action.id})")
                return True
            
            # Find or create the workflow action
            workflow_action, created = WorkflowAction.objects.get_or_create(
                workflow=self.workflow,
                action=action,
                defaults={
                    'sequence': len(self.executed_actions) + 1,
                    'parameters': node_data.get('parameters', {})
                }
            )
            
            # If not created, update parameters from node data
            if not created:
                workflow_action.parameters = node_data.get('parameters', {})
                workflow_action.save(update_fields=['parameters'])
            
            # Create action execution record
            action_execution = ActionExecution.objects.create(
                workflow_execution=self.workflow_execution,
                workflow_action=workflow_action,
                status='pending'
            )
            
            # Track current action
            self.current_action = workflow_action
            self.execution_path.append({
                'node_id': node_id,
                'action_id': action.id,
                'action_name': action.name
            })
            
            logger.info(f"Executing action: {action.name} (ID: {action.id})")
            
            # Execute the action
            success, result = ActionExecutor.execute_action(
                action_execution,
                self.workflow_execution,
                self.execution_context['parameters']
            )
            
            # Update execution context with the results
            self._update_execution_context(action_execution)
            
            # Store result in execution context
            result_key = f"action_{action.id}"
            self.execution_context['results'][result_key] = result
            
            # Also store result by node ID for easier reference in conditions
            self.execution_context['results'][node_id] = result
            
            if not success:
                logger.error(f"Action execution failed: {action.name} (ID: {action.id})")
                
                # Add error to execution context
                self.execution_context['errors'].append({
                    'node_id': node_id,
                    'action_id': action.id,
                    'action_name': action.name,
                    'error': result.get('error', 'Unknown error')
                })
                
                return False
            
            # Add action to executed set
            self.executed_actions.add(workflow_action.id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error executing action node {node_id}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Add error to execution context
            self.execution_context['errors'].append({
                'node_id': node_id,
                'error': str(e)
            })
            
            return False
    
    def _execute_conditional_node(self, node_id: str, node_data: Dict[str, Any]) -> bool:
        """
        Execute a conditional node.
        
        Args:
            node_id: ID of the node
            node_data: Node data from workflow_data
            
        Returns:
            True if execution along the chosen path was successful, False otherwise
        """
        condition = node_data.get('condition', '')
        
        # Track in execution path
        self.execution_path.append({
            'node_id': node_id,
            'type': 'conditional',
            'condition': condition
        })
        
        # Evaluate condition
        condition_result = self._evaluate_condition(condition)
        
        logger.info(f"Evaluated condition '{condition}': {condition_result}")
        
        # Update execution path with result
        self.execution_path[-1]['result'] = condition_result
        
        # Follow the appropriate connection based on condition result
        connections = node_data.get('connections', [])
        target_node_id = None
        
        for conn in connections:
            if conn.get('conditionPath') == 'true' and condition_result:
                target_node_id = conn.get('target')
                break
            elif conn.get('conditionPath') == 'false' and not condition_result:
                target_node_id = conn.get('target')
                break
        
        if target_node_id:
            return self._execute_node(target_node_id)
        else:
            logger.warning(f"No connection found for condition result: {condition_result}")
            return True  # No connection to follow is not an error
    
    def _follow_connections(self, node_id: str) -> bool:
        """
        Follow connections from a node to execute next nodes.
        
        Args:
            node_id: ID of the node to get connections from
            
        Returns:
            True if all connected nodes executed successfully, False otherwise
        """
        node_data = self.workflow_data[node_id]
        connections = node_data.get('connections', [])
        
        if not connections:
            # No connections to follow
            return True
        
        # For non-conditional nodes, just follow all connections sequentially
        if node_data.get('type') != 'conditional':
            for conn in connections:
                target_node_id = conn.get('target')
                if target_node_id:
                    if not self._execute_node(target_node_id):
                        return False
            
            return True
        
        # For conditional nodes, connections are handled in _execute_conditional_node
        return True
    
    def _evaluate_condition(self, condition: str) -> bool:
        """
        Evaluate a condition expression.
        
        The condition is a Python expression that has access to the execution context
        via the variables: data, result, and params.
        
        Args:
            condition: Condition expression to evaluate
            
        Returns:
            True if condition evaluates to a truthy value, False otherwise
        """
        if not condition:
            return True
        
        try:
            # Create a safe evaluation environment with limited variables
            eval_globals = {
                'data': self.execution_context['results'],
                'result': self.execution_context['results'],
                'params': self.execution_context['parameters'],
                'vars': self.execution_context['variables'],
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict
            }
            
            # Evaluate the condition
            result = eval(condition, eval_globals, {})
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {str(e)}")
            return False
    
    def _update_execution_context(self, action_execution):
        """
        Update the execution context with output from an action execution.
        
        This merges any context variables created by the action into the
        workflow execution context, making them available to subsequent actions.
        
        Args:
            action_execution: ActionExecution that was just completed
        """
        # Skip if no output data
        if not action_execution.output_data:
            return
            
        # Check if this is an iterator action
        workflow_action = action_execution.workflow_action
        if workflow_action.action.action_type == 'iterator':
            # Iterator actions already update the workflow execution parameters directly
            # We just need to ensure the updated parameters are in our execution context
            if self.workflow_execution.parameters:
                self.execution_context['parameters'].update(self.workflow_execution.parameters)
        
        # Store result in execution context under a key specific to this action
        action_id = workflow_action.action.id
        result_key = f"action_{action_id}"
        self.execution_context['results'][result_key] = action_execution.output_data
        
        # Also store by the action's name for easier reference in expressions
        action_name = workflow_action.action.name
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', action_name)
        self.execution_context['results'][safe_name] = action_execution.output_data


def execute_workflow(workflow_id: int, parameters: Optional[Dict[str, Any]] = None, user=None) -> WorkflowExecution:
    """
    Execute a workflow.
    
    Args:
        workflow_id: ID of the workflow to execute
        parameters: Additional parameters for the workflow execution
        user: User who triggered the execution
        
    Returns:
        WorkflowExecution instance
    """
    try:
        # Get the workflow
        workflow = Workflow.objects.get(id=workflow_id)
        
        # Create workflow execution record
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            status='pending',
            parameters=parameters or {},
            triggered_by=user
        )
        
        # Execute the workflow
        engine = WorkflowEngine(execution)
        engine.execute()
        
        return execution
        
    except Workflow.DoesNotExist:
        logger.error(f"Workflow with ID {workflow_id} not found")
        raise ValueError(f"Workflow with ID {workflow_id} not found")
        
    except Exception as e:
        logger.error(f"Error executing workflow: {str(e)}")
        logger.error(traceback.format_exc())
        raise