"""
Views for handling action-specific forms and logic.

This module extends the generic workflow views with
action-specific handling for different action types.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import CreateView, UpdateView, FormView, TemplateView, DetailView
from django.utils.translation import gettext_lazy as _
from workflows.forms import DataSourceRefreshActionForm, ActionTypeForm, DatabaseQueryActionForm
from django.views import View
from django.utils import timezone
from django.db import transaction
import traceback
import json
from workflows.models import Action, WorkflowExecution, WorkflowAction, ActionExecution, Workflow, DataSource
from workflows.action_executor import ActionExecutor

class ActionTypeSelectView(LoginRequiredMixin, TemplateView):
    """
    View for selecting the type of action to create.
    Changed from FormView to TemplateView to fix 'NoneType' is not callable error.
    """
    template_name = 'workflows/action_type_select.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action_types'] = Action.ACTION_TYPES
        return context

# Updated ActionDetailView in workflows/views.py
class ActionDetailView(LoginRequiredMixin, DetailView):
    model = Action
    template_name = 'workflows/action_detail.html'
    context_object_name = 'action'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflows'] = WorkflowAction.objects.filter(action=self.object).order_by('workflow__name')
        
        # Create a dictionary of data sources for lookup in the template
        from datasources.models import DataSource
        datasources_dict = {}
        
        # If this is a datasource_refresh action, get all the datasources it references
        if self.object.action_type == 'datasource_refresh' and self.object.parameters:
            datasource_ids = []
            
            # Get single datasource if specified
            if 'datasource_id' in self.object.parameters:
                datasource_ids.append(self.object.parameters['datasource_id'])
                
            # Get multiple datasources if specified
            if 'datasource_ids' in self.object.parameters and isinstance(self.object.parameters['datasource_ids'], list):
                datasource_ids.extend(self.object.parameters['datasource_ids'])
                
            # Create a lookup dictionary of datasource objects
            for ds in DataSource.objects.filter(id__in=datasource_ids):
                datasources_dict[ds.id] = ds
                
        context['datasources'] = datasources_dict
        
        # Get recent executions of this action
        from django.db.models import Q
        context['action_executions'] = ActionExecution.objects.filter(
            Q(workflow_action__action=self.object)  # Normal workflow executions
        ).order_by('-start_time')[:10]
        
        return context

class DataSourceRefreshActionCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new Data Source Refresh action.
    """
    model = Action
    form_class = DataSourceRefreshActionForm
    template_name = 'workflows/datasource_refresh_action_form.html'
    
    def get_success_url(self):
        return reverse_lazy('workflows:action_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Data Source Refresh action created successfully.'))
        return super().form_valid(form)

class DataSourceRefreshActionUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating a Data Source Refresh action.
    """
    model = Action
    form_class = DataSourceRefreshActionForm
    template_name = 'workflows/datasource_refresh_action_form.html'
    
    def get_success_url(self):
        return reverse_lazy('workflows:action_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Data Source Refresh action updated successfully.'))
        return super().form_valid(form)


class RunActionView(LoginRequiredMixin, View):
    """
    View for running an action directly from the action detail page.
    This creates a temporary workflow and execution context to run the action.
    """
    def post(self, request, pk):
        action = get_object_or_404(Action, pk=pk)
        
        try:
            with transaction.atomic():
                # Create or get a test workflow for running individual actions
                test_workflow, created = Workflow.objects.get_or_create(
                    name="Test Action Runner",
                    defaults={
                        'description': "Used for testing individual actions",
                        'is_active': True,
                        'created_by': request.user,
                        'modified_by': request.user
                    }
                )
                
                # First check if there's an existing workflow action for this action
                workflow_action = None
                try:
                    # Try to get the existing workflow action for this action
                    workflow_action = WorkflowAction.objects.get(
                        workflow=test_workflow,
                        action=action
                    )
                except WorkflowAction.DoesNotExist:
                    # If it doesn't exist, find the next available sequence number
                    max_sequence = WorkflowAction.objects.filter(
                        workflow=test_workflow
                    ).order_by('-sequence').values_list('sequence', flat=True).first() or 0
                    
                    # Create a new workflow action with the next sequence number
                    workflow_action = WorkflowAction.objects.create(
                        workflow=test_workflow,
                        action=action,
                        sequence=max_sequence + 1,
                        parameters={}
                    )
                
                # Create a workflow execution
                workflow_execution = WorkflowExecution.objects.create(
                    workflow=test_workflow,
                    status='running',
                    triggered_by=request.user,
                    parameters=request.POST.get('parameters', {})
                )
                
                # Create an action execution
                action_execution = ActionExecution.objects.create(
                    workflow_execution=workflow_execution,
                    workflow_action=workflow_action,
                    status='pending'
                )
                
                # Debug output
                print(f"Running action: {action.name} (ID: {action.id}, Type: {action.action_type})")
                print(f"Using workflow action: {workflow_action.id} (Sequence: {workflow_action.sequence})")
                print(f"Created workflow execution: {workflow_execution.id}")
                print(f"Created action execution: {action_execution.id}")
                
                # Use the ActionExecutor to run the action
                success, result = ActionExecutor.execute_action(
                    action_execution,
                    workflow_execution
                )
                
                if success:
                    # Get more details from result if available
                    if isinstance(result, dict):
                        # For DataSourceRefresh action, show more details
                        if action.action_type == 'datasource_refresh':
                            # Format a more detailed success message
                            refresh_details = []
                            if 'datasources_refreshed' in result:
                                refresh_details.append(f"{result['datasources_refreshed']} data sources refreshed")
                            if 'total_datasources' in result:
                                refresh_details.append(f"{result['total_datasources']} total data sources")
                            if 'execution_time' in result:
                                refresh_details.append(f"Execution time: {result['execution_time']}")
                                
                            detail_msg = ", ".join(refresh_details) if refresh_details else ""
                            
                            if detail_msg:
                                messages.success(request, _('Action executed successfully. ') + detail_msg)
                            else:
                                messages.success(request, _('Action executed successfully.'))
                        else:
                            messages.success(request, _('Action executed successfully.'))
                    else:
                        messages.success(request, _('Action executed successfully.'))
                else:
                    # Format a more detailed error message
                    error_msg = action_execution.error_message
                    if not error_msg and isinstance(result, dict) and 'error' in result:
                        error_msg = result['error']
                        
                    # For DataSourceRefresh action, show more details
                    if action.action_type == 'datasource_refresh' and isinstance(result, dict):
                        details = []
                        if 'details' in result and isinstance(result['details'], list):
                            # Extract error messages from details
                            for detail in result['details']:
                                if detail.get('status') == 'error':
                                    ds_name = detail.get('name', f"Data source {detail.get('datasource_id', 'unknown')}")
                                    ds_msg = detail.get('message', 'Unknown error')
                                    details.append(f"{ds_name}: {ds_msg}")
                                    
                        if details:
                            error_details = "\n• " + "\n• ".join(details)
                            messages.error(request, _('Action execution failed: {}{}').format(
                                error_msg or 'Error refreshing data sources', 
                                error_details
                            ))
                        else:
                            messages.error(request, _('Action execution failed: {}').format(
                                error_msg or 'Unknown error'
                            ))
                    else:
                        messages.error(request, _('Action execution failed: {}').format(
                            error_msg or 'Unknown error'
                        ))
                
                # Update the workflow execution status
                workflow_execution.status = 'success' if success else 'error'
                workflow_execution.end_time = timezone.now()
                if not success and action_execution.error_message:
                    workflow_execution.error_message = action_execution.error_message
                workflow_execution.save()
                
                # Update action execution with output data if available
                if isinstance(result, dict) and not action_execution.output_data:
                    action_execution.output_data = result
                    action_execution.save(update_fields=['output_data'])
                
        except Exception as e:
            # Get full traceback for debugging
            error_traceback = traceback.format_exc()
            print(f"Error running action: {str(e)}")
            print(error_traceback)
            
            messages.error(request, _('Error running action: {} (See server logs for details)').format(str(e)))
        
        return redirect('workflows:action_detail', pk=pk)

class DatabaseQueryActionCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new Database Query action.
    """
    model = Action
    form_class = DatabaseQueryActionForm
    template_name = 'workflows/database_query_action_form.html'
    
    def get_success_url(self):
        return reverse_lazy('workflows:action_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Database Query action created successfully.'))
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add available data sources for context
        context['datasources'] = DataSource.objects.filter(type='database').order_by('name')
        
        return context

class DatabaseQueryActionUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating a Database Query action.
    """
    model = Action
    form_class = DatabaseQueryActionForm
    template_name = 'workflows/database_query_action_form.html'
    
    def get_success_url(self):
        return reverse_lazy('workflows:action_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Database Query action updated successfully.'))
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add available data sources for context
        context['datasources'] = DataSource.objects.filter(type='database').order_by('name')
        
        return context