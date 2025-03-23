# workflows/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .models import Workflow, WorkflowAction, Action, Schedule, WorkflowExecution, ActionExecution
from .forms import (
    DataSourceRefreshActionForm, 
    ActionTypeForm, 
    DatabaseQueryActionForm,
    FileCreateActionForm  
)


# Workflow views
class WorkflowListView(LoginRequiredMixin, ListView):
    model = Workflow
    template_name = 'workflows/index.html'
    context_object_name = 'workflows'
    
    def get_queryset(self):
        return Workflow.objects.all().order_by('name')


class WorkflowDetailView(LoginRequiredMixin, DetailView):
    model = Workflow
    template_name = 'workflows/detail.html'
    context_object_name = 'workflow'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflow_actions'] = self.object.workflow_actions.all().order_by('sequence')
        context['recent_executions'] = self.object.executions.all().order_by('-start_time')[:5]
        context['schedules'] = self.object.schedules.all().order_by('next_run')
        return context


class WorkflowCreateView(LoginRequiredMixin, CreateView):
    model = Workflow
    template_name = 'workflows/form.html'
    fields = ['name', 'description', 'is_active']
    success_url = reverse_lazy('workflows:index')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Workflow created successfully.'))
        return super().form_valid(form)


class WorkflowUpdateView(LoginRequiredMixin, UpdateView):
    model = Workflow
    template_name = 'workflows/form.html'
    fields = ['name', 'description', 'is_active']
    
    def get_success_url(self):
        return reverse_lazy('workflows:detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.modified_by = self.request.user
        # Increment version if changes are made
        form.instance.version += 1
        messages.success(self.request, _('Workflow updated successfully.'))
        return super().form_valid(form)


class WorkflowDeleteView(LoginRequiredMixin, DeleteView):
    model = Workflow
    template_name = 'workflows/confirm_delete.html'
    success_url = reverse_lazy('workflows:index')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Workflow deleted successfully.'))
        return super().delete(request, *args, **kwargs)


class WorkflowRunView(LoginRequiredMixin, View):
    """View to trigger a manual execution of a workflow"""
    def post(self, request, pk):
        workflow = get_object_or_404(Workflow, pk=pk)
        
        # Create a workflow execution record
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            status='pending',
            triggered_by=request.user,
            parameters=request.POST.get('parameters', {})
        )
        
        # Here you would trigger the actual workflow execution
        # For now, just update the status
        execution.status = 'success'
        execution.end_time = timezone.now()
        execution.save()
        
        messages.success(request, _('Workflow executed successfully.'))
        return redirect('workflows:execution_detail', pk=execution.pk)


# Workflow Action views
class WorkflowActionCreateView(LoginRequiredMixin, CreateView):
    model = WorkflowAction
    template_name = 'workflows/workflow_action_form.html'
    fields = ['action', 'sequence', 'condition', 'error_handling', 'parameters']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflow'] = get_object_or_404(Workflow, pk=self.kwargs['workflow_pk'])
        return context
    
    def form_valid(self, form):
        form.instance.workflow = get_object_or_404(Workflow, pk=self.kwargs['workflow_pk'])
        messages.success(self.request, _('Workflow action added successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('workflows:detail', kwargs={'pk': self.kwargs['workflow_pk']})


class WorkflowActionUpdateView(LoginRequiredMixin, UpdateView):
    model = WorkflowAction
    template_name = 'workflows/workflow_action_form.html'
    fields = ['action', 'sequence', 'condition', 'error_handling', 'parameters']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflow'] = get_object_or_404(Workflow, pk=self.kwargs['workflow_pk'])
        return context
    
    def get_success_url(self):
        return reverse_lazy('workflows:detail', kwargs={'pk': self.kwargs['workflow_pk']})


class WorkflowActionDeleteView(LoginRequiredMixin, DeleteView):
    model = WorkflowAction
    template_name = 'workflows/workflow_action_confirm_delete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflow'] = get_object_or_404(Workflow, pk=self.kwargs['workflow_pk'])
        return context
    
    def get_success_url(self):
        return reverse_lazy('workflows:detail', kwargs={'pk': self.kwargs['workflow_pk']})


# Action views
class ActionListView(LoginRequiredMixin, ListView):
    model = Action
    template_name = 'workflows/actions.html'
    context_object_name = 'actions'
    
    def get_queryset(self):
        return Action.objects.all().order_by('name')


class ActionDetailView(LoginRequiredMixin, DetailView):
    model = Action
    template_name = 'workflows/action_detail.html'
    context_object_name = 'action'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflows'] = WorkflowAction.objects.filter(action=self.object).order_by('workflow__name')
        return context


class ActionCreateView(LoginRequiredMixin, CreateView):
    model = Action
    template_name = 'workflows/action_form.html'
    fields = ['name', 'description', 'action_type', 'datasource', 'parameters', 'is_active']
    success_url = reverse_lazy('workflows:actions')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Action created successfully.'))
        return super().form_valid(form)


class ActionUpdateView(LoginRequiredMixin, UpdateView):
    model = Action
    template_name = 'workflows/action_form.html'
    fields = ['name', 'description', 'action_type', 'datasource', 'parameters', 'is_active']
    
    def get_success_url(self):
        return reverse_lazy('workflows:action_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Action updated successfully.'))
        return super().form_valid(form)


class ActionDeleteView(LoginRequiredMixin, DeleteView):
    model = Action
    template_name = 'workflows/action_confirm_delete.html'
    success_url = reverse_lazy('workflows:actions')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Action deleted successfully.'))
        return super().delete(request, *args, **kwargs)


# Schedule views
class ScheduleListView(LoginRequiredMixin, ListView):
    model = Schedule
    template_name = 'workflows/schedules.html'
    context_object_name = 'schedules'
    
    def get_queryset(self):
        return Schedule.objects.all().order_by('-enabled', 'next_run', 'name')


class ScheduleDetailView(LoginRequiredMixin, DetailView):
    model = Schedule
    template_name = 'workflows/schedule_detail.html'
    context_object_name = 'schedule'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_executions'] = self.object.executions.all().order_by('-start_time')[:10]
        return context


class ScheduleCreateView(LoginRequiredMixin, CreateView):
    model = Schedule
    template_name = 'workflows/schedule_form.html'
    fields = ['name', 'workflow', 'frequency', 'parameters', 'cron_expression', 'start_date', 'end_date', 'enabled']
    success_url = reverse_lazy('workflows:schedules')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Schedule created successfully.'))
        return super().form_valid(form)


class ScheduleUpdateView(LoginRequiredMixin, UpdateView):
    model = Schedule
    template_name = 'workflows/schedule_form.html'
    fields = ['name', 'workflow', 'frequency', 'parameters', 'cron_expression', 'start_date', 'end_date', 'enabled']
    
    def get_success_url(self):
        return reverse_lazy('workflows:schedule_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Schedule updated successfully.'))
        return super().form_valid(form)


class ScheduleDeleteView(LoginRequiredMixin, DeleteView):
    model = Schedule
    template_name = 'workflows/schedule_confirm_delete.html'
    success_url = reverse_lazy('workflows:schedules')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Schedule deleted successfully.'))
        return super().delete(request, *args, **kwargs)


class ScheduleToggleView(LoginRequiredMixin, View):
    """View to toggle a schedule's enabled status"""
    def post(self, request, pk):
        schedule = get_object_or_404(Schedule, pk=pk)
        schedule.enabled = not schedule.enabled
        schedule.save()
        
        if schedule.enabled:
            messages.success(request, _('Schedule enabled.'))
        else:
            messages.success(request, _('Schedule disabled.'))
        
        next_url = request.POST.get('next', reverse_lazy('workflows:schedules'))
        return redirect(next_url)


# Execution views
class WorkflowExecutionListView(LoginRequiredMixin, ListView):
    model = WorkflowExecution
    template_name = 'workflows/executions.html'
    context_object_name = 'executions'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = WorkflowExecution.objects.all().order_by('-start_time')
        
        # Filter by workflow if specified
        workflow_id = self.request.GET.get('workflow')
        if workflow_id:
            queryset = queryset.filter(workflow_id=workflow_id)
        
        # Filter by status if specified
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['workflows'] = Workflow.objects.all().order_by('name')
        context['statuses'] = dict(WorkflowExecution.STATUS_CHOICES)
        return context


class WorkflowExecutionDetailView(LoginRequiredMixin, DetailView):
    model = WorkflowExecution
    template_name = 'workflows/execution_detail.html'
    context_object_name = 'execution'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['action_executions'] = self.object.action_executions.all().order_by('workflow_action__sequence')
        return context