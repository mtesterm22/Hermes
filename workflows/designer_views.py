# workflows/designer_views.py
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import View
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse

from .models import Workflow, WorkflowAction, Action

class WorkflowDesignerView(LoginRequiredMixin, View):
    """
    Visual workflow designer view.
    """
    template_name = 'workflows/workflow_designer.html'
    
    def get(self, request, pk=None):
        workflow = None
        workflow_data = {}
        
        # If pk is provided, load existing workflow
        if pk:
            workflow = get_object_or_404(Workflow, pk=pk)
            if hasattr(workflow, 'workflow_data') and workflow.workflow_data:
                try:
                    workflow_data = workflow.workflow_data
                except:
                    # If workflow_data is not valid JSON, start fresh
                    pass
        
        # Get all available actions for the sidebar
        actions = Action.objects.filter(is_active=True)
        
        # Categorize actions by type
        database_actions = actions.filter(action_type__in=['database_query'])
        datasource_actions = actions.filter(action_type__in=['datasource_refresh'])
        file_actions = actions.filter(action_type__in=['file_create', 'csv_generate', 'csv_process'])
        other_actions = actions.exclude(
            action_type__in=[
                'database_query', 'datasource_refresh', 
                'file_create', 'csv_generate', 'csv_process'
            ]
        )
        
        context = {
            'workflow': workflow,
            'workflow_data': json.dumps(workflow_data),
            'database_actions': database_actions,
            'datasource_actions': datasource_actions,
            'file_actions': file_actions,
            'other_actions': other_actions,
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, pk=None):
        """
        Handle saving workflow from the designer.
        """
        try:
            # Get workflow data from form
            name = request.POST.get('name')
            description = request.POST.get('description', '')
            is_active = request.POST.get('is_active', 'true') == 'true'
            workflow_data = request.POST.get('workflow_data', '{}')
            
            if not name:
                return JsonResponse({
                    'success': False,
                    'error': 'Workflow name is required'
                })
            
            # Validate workflow data
            try:
                workflow_json = json.loads(workflow_data)
            except json.JSONDecodeError as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid workflow data format: {str(e)}'
                })
            
            # Create or update workflow
            if pk:
                # Update existing workflow
                try:
                    workflow = Workflow.objects.get(pk=pk)
                    workflow.name = name
                    workflow.description = description
                    workflow.is_active = is_active
                    workflow.workflow_data = workflow_json
                    workflow.modified_by = request.user
                    workflow.save()
                except Workflow.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': f'Workflow with ID {pk} not found'
                    })
            else:
                # Create new workflow
                workflow = Workflow.objects.create(
                    name=name,
                    description=description,
                    is_active=is_active,
                    workflow_data=workflow_json,
                    created_by=request.user,
                    modified_by=request.user
                )
            
            # Create workflow actions from workflow data
            try:
                # First delete existing workflow actions if any
                if pk:
                    workflow.workflow_actions.all().delete()
                
                sequence = 1
                for node_id, node_data in workflow_json.items():
                    if node_data.get('type') == 'action':
                        action_id = node_data.get('actionId')
                        if action_id:
                            try:
                                action = Action.objects.get(id=action_id)
                                
                                # Create workflow action
                                WorkflowAction.objects.create(
                                    workflow=workflow,
                                    action=action,
                                    sequence=sequence,
                                    condition=self._get_condition_for_node(node_id, workflow_json),
                                    parameters=node_data.get('parameters', {})
                                )
                                
                                sequence += 1
                            except Action.DoesNotExist:
                                # Skip actions that don't exist
                                continue
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Error creating workflow actions: {str(e)}'
                })
            
            return JsonResponse({
                'success': True,
                'workflow_id': workflow.id,
                'redirect_url': reverse('workflows:detail', kwargs={'pk': workflow.id})
            })
        
        except Exception as e:
            # Log the exception for debugging
            import traceback
            logger.error(f"Error saving workflow: {str(e)}")
            logger.error(traceback.format_exc())
            
            return JsonResponse({
                'success': False,
                'error': f'Error saving workflow: {str(e)}'
            })
    
    def _get_condition_for_node(self, node_id, workflow_data):
        """
        Find if this node has a condition by looking for incoming connections
        from conditional nodes.
        """
        for src_id, src_data in workflow_data.items():
            if src_data.get('type') == 'conditional' and src_data.get('connections'):
                for conn in src_data.get('connections', []):
                    if conn.get('target') == node_id:
                        condition_path = conn.get('conditionPath')
                        condition = src_data.get('condition', '')
                        
                        if condition and condition_path:
                            if condition_path == 'true':
                                return condition
                            else:
                                return f"not ({condition})"
        
        return ""