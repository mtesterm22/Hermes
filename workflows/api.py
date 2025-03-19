# workflows/api.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Workflow, WorkflowAction, Action, Schedule, WorkflowExecution

class WorkflowViewSet(viewsets.ModelViewSet):
    """
    API endpoint for workflows
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Workflow.objects.all().order_by('name')
    
    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """
        Run a workflow
        """
        workflow = self.get_object()
        
        # Create execution record
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            status='pending',
            triggered_by=request.user,
            parameters=request.data.get('parameters', {})
        )
        
        # Here you would actually run the workflow
        
        return Response({'execution_id': execution.id})
    
    @action(detail=True)
    def actions(self, request, pk=None):
        """
        Get actions for a workflow
        """
        workflow = self.get_object()
        actions = workflow.workflow_actions.all().order_by('sequence')
        
        # Here you would serialize and return the actions
        return Response({'count': actions.count()})
    
    @action(detail=True)
    def executions(self, request, pk=None):
        """
        Get execution history for a workflow
        """
        workflow = self.get_object()
        executions = workflow.executions.all().order_by('-start_time')
        
        # Here you would serialize and return the executions
        return Response({'count': executions.count()})


class ActionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for actions
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Action.objects.all().order_by('name')


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    API endpoint for schedules
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Schedule.objects.all().order_by('-enabled', 'next_run')
    
    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """
        Toggle a schedule's enabled status
        """
        schedule = self.get_object()
        schedule.enabled = not schedule.enabled
        schedule.save()
        
        return Response({'enabled': schedule.enabled})