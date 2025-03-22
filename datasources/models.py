# datasources/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

User = get_user_model()

class DataSource(models.Model):
    """
    Model for managing different types of data sources.
    """
    TYPE_CHOICES = [
        ('database', _('Database')),
        ('csv', _('CSV File')),
        ('api', _('API')),
        ('active_directory', _('Active Directory')),
        ('graph_api', _('Microsoft Graph API')),
    ]
    
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('warning', _('Warning')),
        ('error', _('Error')),
        ('disabled', _('Disabled')),
    ]
    
    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    type = models.CharField(_('Type'), max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='active')
    connection_string = models.TextField(_('Connection String'), blank=True)
    credentials = models.JSONField(_('Credentials'), blank=True, null=True)
    
    # Audit fields
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_datasources'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='modified_datasources'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    # Tracking fields
    last_sync = models.DateTimeField(_('Last Sync'), null=True, blank=True)
    sync_count = models.IntegerField(_('Sync Count'), default=0)
    
    class Meta:
        verbose_name = _('Data Source')
        verbose_name_plural = _('Data Sources')
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def update_last_sync(self):
        self.last_sync = timezone.now()
        self.sync_count += 1
        self.save(update_fields=['last_sync', 'sync_count'])

    def is_syncing(self):
        """Check if this data source is currently syncing."""
        return self.syncs.filter(status='running').exists()

    def lock_for_sync(self):
        """Attempt to lock this data source for syncing."""
        if self.is_syncing():
            return False
        return True

class DataSourceField(models.Model):
    """
    Model for tracking fields/columns in data sources
    """
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='fields'
    )
    name = models.CharField(_('Field Name'), max_length=100)
    display_name = models.CharField(_('Display Name'), max_length=100, blank=True)
    field_type = models.CharField(_('Field Type'), max_length=50)
    is_key = models.BooleanField(_('Is Key Field'), default=False)
    is_nullable = models.BooleanField(_('Is Nullable'), default=True)
    sample_data = models.TextField(_('Sample Data'), blank=True)
    
    class Meta:
        verbose_name = _('Data Source Field')
        verbose_name_plural = _('Data Source Fields')
        unique_together = ('datasource', 'name')
        ordering = ['datasource', 'name']
    
    def __str__(self):
        return f"{self.datasource.name}: {self.name}"

class DataSourceSync(models.Model):
    """
    Model for tracking data source synchronization events
    """
    STATUS_CHOICES = [
        ('running', _('Running')),
        ('success', _('Success')),
        ('error', _('Error')),
        ('warning', _('Warning')),
    ]
    
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='syncs'
    )
    start_time = models.DateTimeField(_('Start Time'), auto_now_add=True)
    end_time = models.DateTimeField(_('End Time'), null=True, blank=True)
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='running')
    records_processed = models.IntegerField(_('Records Processed'), default=0)
    records_created = models.IntegerField(_('Records Created'), default=0)
    records_updated = models.IntegerField(_('Records Updated'), default=0)
    records_deleted = models.IntegerField(_('Records Deleted'), default=0)
    error_message = models.TextField(_('Error Message'), blank=True)
    triggered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='triggered_syncs'
    )
    
    class Meta:
        verbose_name = _('Data Source Sync')
        verbose_name_plural = _('Data Source Syncs')
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.datasource.name} - {self.start_time}"
    
    def complete(self, status='success', error_message=''):
        self.status = status
        self.end_time = timezone.now()
        self.error_message = error_message
        self.save()
        
        # Update parent data source
        if status == 'success':
            self.datasource.status = 'active'
        elif status == 'warning':
            self.datasource.status = 'warning'
        elif status == 'error':
            self.datasource.status = 'error'
        
        self.datasource.update_last_sync()