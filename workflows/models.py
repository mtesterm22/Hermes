# workflows/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from datasources.models import DataSource

User = get_user_model()

class Action(models.Model):
    """
    Model for defining workflow actions
    """
    ACTION_TYPES = [
        ('database_query', _('Database Query')),
        ('csv_generate', _('Generate CSV')),
        ('csv_process', _('Process CSV')),
        ('ad_modify', _('Modify Active Directory')),
        ('email_send', _('Send Email')),
        ('user_create', _('Create User')),
        ('user_disable', _('Disable User')),
        ('api_call', _('API Call')),
        ('stored_procedure', _('Stored Procedure')),
        ('custom_script', _('Custom Script')),
    ]
    
    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    action_type = models.CharField(_('Action Type'), max_length=50, choices=ACTION_TYPES)
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='actions'
    )
    parameters = models.JSONField(_('Parameters'), default=dict)
    is_active = models.BooleanField(_('Is Active'), default=True)
    
    # Audit fields
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_actions'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='modified_actions'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Action')
        verbose_name_plural = _('Actions')
        ordering = ['name']
    
    def __str__(self):
        return self.name

class Workflow(models.Model):
    """
    Model for defining workflows composed of actions
    """
    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    is_active = models.BooleanField(_('Is Active'), default=True)
    version = models.PositiveIntegerField(_('Version'), default=1)
    
    # Audit fields
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_workflows'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='modified_workflows'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Workflow')
        verbose_name_plural = _('Workflows')
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} (v{self.version})"
    
    def get_actions(self):
        return self.workflow_actions.all().order_by('sequence')

class WorkflowAction(models.Model):
    """
    Model for connecting actions to workflows with additional configuration
    """
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name='workflow_actions'
    )
    action = models.ForeignKey(
        Action,
        on_delete=models.CASCADE,
        related_name='workflow_actions'
    )
    sequence = models.PositiveIntegerField(_('Sequence'))
    condition = models.TextField(_('Condition'), blank=True)
    error_handling = models.JSONField(_('Error Handling'), default=dict)
    parameters = models.JSONField(_('Parameters'), default=dict)
    
    class Meta:
        verbose_name = _('Workflow Action')
        verbose_name_plural = _('Workflow Actions')
        ordering = ['workflow', 'sequence']
        unique_together = ('workflow', 'sequence')
    
    def __str__(self):
        return f"{self.workflow.name} - {self.action.name} ({self.sequence})"

class Schedule(models.Model):
    """
    Model for scheduling workflow executions
    """
    FREQUENCY_CHOICES = [
        ('once', _('Once')),
        ('hourly', _('Hourly')),
        ('daily', _('Daily')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
        ('custom', _('Custom (Cron)')),
    ]
    
    name = models.CharField(_('Name'), max_length=100)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    frequency = models.CharField(_('Frequency'), max_length=20, choices=FREQUENCY_CHOICES)
    parameters = models.JSONField(_('Parameters'), default=dict)
    cron_expression = models.CharField(_('Cron Expression'), max_length=100, blank=True)
    start_date = models.DateTimeField(_('Start Date'), default=timezone.now)
    end_date = models.DateTimeField(_('End Date'), null=True, blank=True)
    enabled = models.BooleanField(_('Enabled'), default=True)
    last_run = models.DateTimeField(_('Last Run'), null=True, blank=True)
    next_run = models.DateTimeField(_('Next Run'), null=True, blank=True)
    
    # Audit fields
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_schedules'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='modified_schedules'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Schedule')
        verbose_name_plural = _('Schedules')
        ordering = ['next_run']
    
    def __str__(self):
        return self.name

class WorkflowExecution(models.Model):
    """
    Model for tracking workflow executions
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('running', _('Running')),
        ('success', _('Success')),
        ('warning', _('Warning')),
        ('error', _('Error')),
        ('cancelled', _('Cancelled')),
    ]
    
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions'
    )
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='pending')
    parameters = models.JSONField(_('Parameters'), default=dict, blank=True)
    start_time = models.DateTimeField(_('Start Time'), auto_now_add=True)
    end_time = models.DateTimeField(_('End Time'), null=True, blank=True)
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_executions'
    )
    result_data = models.JSONField(_('Result Data'), default=dict, blank=True)
    error_message = models.TextField(_('Error Message'), blank=True)
    
    class Meta:
        verbose_name = _('Workflow Execution')
        verbose_name_plural = _('Workflow Executions')
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.workflow.name} - {self.start_time}"
    
    @property
    def duration(self):
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None
    
    def complete(self, status='success', error_message='', result_data=None):
        self.status = status
        self.end_time = timezone.now()
        self.error_message = error_message
        if result_data:
            self.result_data = result_data
        self.save()
        
        # Update schedule if this was a scheduled execution
        if self.schedule:
            self.schedule.last_run = self.start_time
            self.schedule.save(update_fields=['last_run'])

class ActionExecution(models.Model):
    """
    Model for tracking individual action executions within a workflow
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('running', _('Running')),
        ('success', _('Success')),
        ('warning', _('Warning')),
        ('error', _('Error')),
        ('skipped', _('Skipped')),
    ]
    
    workflow_execution = models.ForeignKey(
        WorkflowExecution,
        on_delete=models.CASCADE,
        related_name='action_executions'
    )
    workflow_action = models.ForeignKey(
        WorkflowAction,
        on_delete=models.CASCADE,
        related_name='executions'
    )
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='pending')
    start_time = models.DateTimeField(_('Start Time'), null=True, blank=True)
    end_time = models.DateTimeField(_('End Time'), null=True, blank=True)
    input_data = models.JSONField(_('Input Data'), default=dict, blank=True)
    output_data = models.JSONField(_('Output Data'), default=dict, blank=True)
    error_message = models.TextField(_('Error Message'), blank=True)
    
    class Meta:
        verbose_name = _('Action Execution')
        verbose_name_plural = _('Action Executions')
        ordering = ['workflow_execution', 'workflow_action__sequence']
    
    def __str__(self):
        return f"{self.workflow_execution} - {self.workflow_action.action.name}"
    
    @property
    def duration(self):
        if self.end_time and self.start_time:
            return self.end_time - self.start_time
        return None
    
    def start(self):
        self.start_time = timezone.now()
        self.status = 'running'
        self.save(update_fields=['start_time', 'status'])
    
    def complete(self, status='success', error_message='', output_data=None):
        self.status = status
        self.end_time = timezone.now()
        self.error_message = error_message
        if output_data:
            self.output_data = output_data
        self.save()

