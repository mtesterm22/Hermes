# Update datasources/database_models.py
"""
Database data source models for Hermes.

This module defines models for database data sources, with a focus
on queries that can use shared database connections.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import logging

from .models import DataSource
from .connection_models import DatabaseConnection

logger = logging.getLogger(__name__)

class DatabaseDataSource(models.Model):
    """
    Extension model for database-specific data source settings.
    """
    datasource = models.OneToOneField(
        DataSource,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='database_settings'
    )
    
    # Database connection (reusable)
    connection = models.ForeignKey(
        DatabaseConnection,
        on_delete=models.PROTECT,  # Don't allow deletion if referenced
        related_name='data_sources'
    )
    
    # Query execution settings (can override connection defaults)
    query_timeout = models.IntegerField(_('Query Timeout (s)'), default=60)
    max_rows = models.IntegerField(_('Maximum Rows'), default=10000)
    
    class Meta:
        verbose_name = _('Database Data Source')
        verbose_name_plural = _('Database Data Sources')
    
    def __str__(self):
        return f"Database Settings for {self.datasource.name}"
    
    def get_connection_info(self):
        """
        Get the connection information from the linked connection.
        
        Returns:
            Dictionary with connection parameters
        """
        return self.connection.get_connection_info()


class DatabaseQuery(models.Model):
    """
    Model for storing predefined queries for a database data source.
    """
    QUERY_TYPE_CHOICES = [
        ('select', _('SELECT')),
        ('insert', _('INSERT')),
        ('update', _('UPDATE')),
        ('delete', _('DELETE')),
        ('proc', _('Stored Procedure')),
        ('other', _('Other')),
    ]
    
    database_datasource = models.ForeignKey(
        DatabaseDataSource,
        on_delete=models.CASCADE,
        related_name='queries'
    )
    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    query_text = models.TextField(_('Query Text'))
    query_type = models.CharField(
        _('Query Type'),
        max_length=20,
        choices=QUERY_TYPE_CHOICES,
        default='select'
    )
    parameters = models.JSONField(_('Parameters'), default=dict, blank=True)
    is_enabled = models.BooleanField(_('Enabled'), default=True)
    is_default = models.BooleanField(_('Default Query'), default=False, 
                                    help_text=_('This query will be used as the default for syncing'))
    
    # Audit fields
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='created_queries'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='modified_queries'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Database Query')
        verbose_name_plural = _('Database Queries')
        ordering = ['-is_default', 'name']
        unique_together = [('database_datasource', 'name')]
    
    def __str__(self):
        return f"{self.name} ({self.database_datasource.datasource.name})"


class DatabaseQueryExecution(models.Model):
    """
    Model for tracking database query executions.
    """
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('running', _('Running')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('cancelled', _('Cancelled')),
    ]
    
    query = models.ForeignKey(
        DatabaseQuery,
        on_delete=models.CASCADE,
        related_name='executions',
        null=True,
        blank=True
    )
    database_datasource = models.ForeignKey(
        DatabaseDataSource,
        on_delete=models.CASCADE,
        related_name='query_executions'
    )
    query_text = models.TextField(_('Query Text'))
    parameters = models.JSONField(_('Parameters'), default=dict, blank=True)
    status = models.CharField(
        _('Status'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    start_time = models.DateTimeField(_('Start Time'), auto_now_add=True)
    end_time = models.DateTimeField(_('End Time'), null=True, blank=True)
    duration_ms = models.IntegerField(_('Duration (ms)'), null=True, blank=True)
    rows_affected = models.IntegerField(_('Rows Affected'), null=True, blank=True)
    error_message = models.TextField(_('Error Message'), blank=True)
    
    # Add reference to workflow execution if part of one
    workflow_execution = models.ForeignKey(
        'workflows.WorkflowExecution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='database_executions'
    )
    
    class Meta:
        verbose_name = _('Database Query Execution')
        verbose_name_plural = _('Database Query Executions')
        ordering = ['-start_time']
    
    def __str__(self):
        return f"Execution at {self.start_time} ({self.database_datasource.datasource.name})"
    
    def complete(self, status='completed', rows_affected=None, error_message=''):
        """
        Complete the query execution with the provided status and data.
        
        Args:
            status: Final status of the execution
            rows_affected: Number of rows affected by the query
            error_message: Error message if the execution failed
        """
        self.status = status
        self.end_time = timezone.now()
        
        # Calculate duration in milliseconds
        if self.start_time:
            delta = (self.end_time - self.start_time)
            self.duration_ms = int(delta.total_seconds() * 1000)
        
        if rows_affected is not None:
            self.rows_affected = rows_affected
            
        if error_message:
            self.error_message = error_message
            
        self.save()