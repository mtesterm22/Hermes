# datasources/csv_models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from .models import DataSource

class CSVDataSource(models.Model):
    """
    Extension model for CSV-specific data source settings.
    """
    datasource = models.OneToOneField(
        DataSource,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='csv_settings'
    )
    
    # File storage options
    FILE_LOCATION_CHOICES = [
        ('local', _('Local File')),
        ('sftp', _('SFTP Server')),
        ('s3', _('S3 Bucket')),
        ('upload', _('Uploaded File')),
    ]
    file_location = models.CharField(
        _('File Location'),
        max_length=20,
        choices=FILE_LOCATION_CHOICES,
        default='upload'
    )
    file_path = models.CharField(_('File Path'), max_length=255, blank=True)
    
    # CSV options
    delimiter = models.CharField(_('Delimiter'), max_length=5, default=',')
    has_header = models.BooleanField(_('Has Header Row'), default=True)
    encoding = models.CharField(_('Character Encoding'), max_length=20, default='utf-8')
    quote_char = models.CharField(_('Quote Character'), max_length=5, default='"')
    
    # Processing options
    skip_rows = models.PositiveIntegerField(_('Skip Rows'), default=0, help_text=_('Number of rows to skip at the beginning'))
    max_rows = models.PositiveIntegerField(_('Max Rows'), null=True, blank=True, help_text=_('Maximum number of rows to process (blank for all)'))
    
    class Meta:
        verbose_name = _('CSV Data Source')
        verbose_name_plural = _('CSV Data Sources')
    
    def __str__(self):
        return f"CSV Settings for {self.datasource.name}"

class CSVFileUpload(models.Model):
    """
    Model to track uploaded CSV files.
    """
    csv_datasource = models.ForeignKey(
        CSVDataSource,
        on_delete=models.CASCADE,
        related_name='uploads'
    )
    file = models.FileField(_('CSV File'), upload_to='csv_files/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(_('Uploaded At'), auto_now_add=True)
    row_count = models.PositiveIntegerField(_('Row Count'), null=True, blank=True)
    file_size = models.PositiveIntegerField(_('File Size (bytes)'), null=True, blank=True)
    
    class Meta:
        verbose_name = _('CSV File Upload')
        verbose_name_plural = _('CSV File Uploads')
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"Upload for {self.csv_datasource.datasource.name} at {self.uploaded_at}"