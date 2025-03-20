"""
Database data source models for Hermes.

This module defines models for database data sources, similar to
the CSV data source models but for database connections.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import logging

from .models import DataSource

from core.utils.encryption import encrypt_credentials, decrypt_credentials

logger = logging.getLogger(__name__)

class DatabaseDataSource(models.Model):
    """
    Extension model for database-specific data source settings.
    """
    DATABASE_TYPE_CHOICES = [
        ('postgresql', _('PostgreSQL')),
        ('mysql', _('MySQL')),
        ('oracle', _('Oracle')),
        ('sqlserver', _('SQL Server')),
        ('sqlite', _('SQLite')),
        ('other', _('Other')),
    ]
    
    datasource = models.OneToOneField(
        DataSource,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='database_settings'
    )
    
    # Database configuration
    db_type = models.CharField(
        _('Database Type'),
        max_length=20,
        choices=DATABASE_TYPE_CHOICES,
        default='postgresql'
    )
    host = models.CharField(_('Host'), max_length=255, blank=True)
    port = models.IntegerField(_('Port'), blank=True, null=True)
    database_name = models.CharField(_('Database Name'), max_length=255, blank=True)
    schema = models.CharField(_('Schema'), max_length=255, blank=True)
    username = models.CharField(_('Username'), max_length=255, blank=True)
    
    # We don't store passwords directly in the model
    # Instead, use the encrypted credentials field on the parent DataSource
    
    # Connection options
    use_ssl = models.BooleanField(_('Use SSL'), default=False)
    ssl_cert_path = models.CharField(_('SSL Certificate Path'), max_length=255, blank=True)
    connection_timeout = models.IntegerField(_('Connection Timeout (s)'), default=30)
    
    # Query execution settings
    query_timeout = models.IntegerField(_('Query Timeout (s)'), default=60)
    max_rows = models.IntegerField(_('Maximum Rows'), default=10000)
    fetch_size = models.IntegerField(_('Fetch Size'), default=1000)
    
    class Meta:
        verbose_name = _('Database Data Source')
        verbose_name_plural = _('Database Data Sources')
    
    def __str__(self):
        return f"Database Settings for {self.datasource.name}"
    
    def get_connection_info(self):
        """
        Get the connection information dictionary for this database source.
        
        Returns:
            Dictionary with connection parameters
        """
        connection_info = {
            'type': self.db_type,
            'host': self.host,
            'port': self.port,
            'database': self.database_name,
            'schema': self.schema,
            'user': self.username,
        }
        
        # Add password from credentials if available
        if self.datasource.credentials:
            # Check for encrypted credentials
            if 'encrypted_credentials' in self.datasource.credentials:
                encrypted_creds = self.datasource.credentials.get('encrypted_credentials')
                decrypted_creds = decrypt_credentials(encrypted_creds)
                if decrypted_creds and 'password' in decrypted_creds:
                    connection_info['password'] = decrypted_creds['password']
            # Fall back to direct password storage (legacy support)
            elif 'password' in self.datasource.credentials:
                connection_info['password'] = self.datasource.credentials.get('password')
        
        # Add SSL settings if enabled
        if self.use_ssl:
            connection_info['ssl'] = True
            
            if self.ssl_cert_path:
                connection_info['ssl_cert'] = self.ssl_cert_path
        
        return connection_info


class DatabaseQuery(models.Model):
    """
    Model for storing predefined queries for a database data source.
    """
    QUERY_TYPE_CHOICES = [
        ('select', _('SELECT')),
        ('insert', _('INSERT')),
        ('update', _('UPDATE')),
        ('delete', _('DELETE')),
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
    
    # Audit fields
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Database Query')
        verbose_name_plural = _('Database Queries')
        ordering = ['name']
    
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