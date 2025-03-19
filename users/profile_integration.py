# users/profile_integration.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from datasources.models import DataSource, DataSourceField

class ProfileFieldMapping(models.Model):
    """
    Maps fields from a data source to user profile attributes.
    """
    MAPPING_TYPES = [
        ('direct', _('Direct Mapping')),
        ('transform', _('Transformation')),
        ('multi', _('Multiple Values')),
    ]
    
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='profile_mappings'
    )
    source_field = models.ForeignKey(
        DataSourceField,
        on_delete=models.CASCADE,
        related_name='profile_mappings'
    )
    profile_attribute = models.CharField(_('Profile Attribute'), max_length=100)
    mapping_type = models.CharField(_('Mapping Type'), max_length=20, choices=MAPPING_TYPES, default='direct')
    is_key_field = models.BooleanField(_('Is Identity Key'), default=False, 
                                      help_text=_('Used to match records to user profiles'))
    transformation_logic = models.TextField(_('Transformation Logic'), blank=True, 
                                          help_text=_('For transformation mappings, e.g. Python expression'))
    priority = models.PositiveIntegerField(_('Priority'), default=100, 
                                         help_text=_('Higher priority values override lower ones when conflicts occur'))
    is_multivalued = models.BooleanField(_('Allows Multiple Values'), default=False)
    is_enabled = models.BooleanField(_('Enabled'), default=True)
    
    class Meta:
        verbose_name = _('Profile Field Mapping')
        verbose_name_plural = _('Profile Field Mappings')
        unique_together = ('datasource', 'source_field', 'profile_attribute')
        ordering = ['-priority', 'profile_attribute']
    
    def __str__(self):
        return f"{self.datasource.name}: {self.source_field.name} → {self.profile_attribute}"


class AttributeSource(models.Model):
    """
    Tracks where each user profile attribute value came from.
    """
    person = models.ForeignKey(
        'users.Person',  # Assuming Person model exists in users app
        on_delete=models.CASCADE,
        related_name='attribute_sources'
    )
    attribute_name = models.CharField(_('Attribute Name'), max_length=100)
    attribute_value = models.TextField(_('Attribute Value'))
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='provided_attributes'
    )
    mapping = models.ForeignKey(
        ProfileFieldMapping,
        on_delete=models.SET_NULL,
        null=True,
        related_name='attribute_instances'
    )
    source_record_id = models.CharField(_('Source Record ID'), max_length=255, blank=True,
                                      help_text=_('ID of the record in the source system'))
    first_seen = models.DateTimeField(_('First Seen'), auto_now_add=True)
    last_updated = models.DateTimeField(_('Last Updated'), auto_now=True)
    is_current = models.BooleanField(_('Is Current Value'), default=True)
    
    class Meta:
        verbose_name = _('Attribute Source')
        verbose_name_plural = _('Attribute Sources')
        unique_together = ('person', 'attribute_name', 'attribute_value', 'datasource')
        ordering = ['-last_updated']
    
    def __str__(self):
        return f"{self.person}: {self.attribute_name} from {self.datasource.name}"


class ProfileAttributeChange(models.Model):
    """
    Records changes to user profile attributes over time.
    """
    CHANGE_TYPES = [
        ('add', _('Added')),
        ('modify', _('Modified')),
        ('remove', _('Removed')),
    ]
    
    person = models.ForeignKey(
        'users.Person',
        on_delete=models.CASCADE,
        related_name='profile_attribute_changes'  # Updated related_name
    )
    attribute_name = models.CharField(_('Attribute Name'), max_length=100)
    old_value = models.TextField(_('Old Value'), blank=True)
    new_value = models.TextField(_('New Value'), blank=True)
    change_type = models.CharField(_('Change Type'), max_length=10, choices=CHANGE_TYPES)
    changed_at = models.DateTimeField(_('Changed At'), default=timezone.now)
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.SET_NULL,
        null=True,
        related_name='caused_profile_changes'  # Updated related_name
    )
    sync = models.ForeignKey(
        'datasources.DataSourceSync',
        on_delete=models.SET_NULL,
        null=True,
        related_name='profile_attribute_changes'  # Updated related_name
    )
    
    class Meta:
        verbose_name = _('Profile Attribute Change')
        verbose_name_plural = _('Profile Attribute Changes')
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.person}: {self.attribute_name} {self.change_type} at {self.changed_at}"


class IdentityResolutionConfig(models.Model):
    """
    Configuration for how user identities are resolved from data sources.
    """
    MATCHING_METHODS = [
        ('exact', _('Exact Match')),
        ('case_insensitive', _('Case Insensitive')),
        ('fuzzy', _('Fuzzy Match')),
        ('custom', _('Custom Logic')),
    ]
    
    datasource = models.OneToOneField(
        DataSource,
        on_delete=models.CASCADE,
        related_name='identity_resolution'
    )
    is_enabled = models.BooleanField(_('Identity Resolution Enabled'), default=True)
    create_missing_profiles = models.BooleanField(_('Create Missing Profiles'), default=False,
                                                help_text=_('Create new user profiles when no match is found'))
    matching_method = models.CharField(_('Matching Method'), max_length=20, choices=MATCHING_METHODS, default='exact')
    custom_matcher = models.TextField(_('Custom Matcher Code'), blank=True,
                                    help_text=_('Python code for custom matching logic'))
    match_confidence_threshold = models.FloatField(_('Match Confidence Threshold'), default=0.9,
                                                 help_text=_('For fuzzy matching (0.0 to 1.0)'))
    
    class Meta:
        verbose_name = _('Identity Resolution Configuration')
        verbose_name_plural = _('Identity Resolution Configurations')
    
    def __str__(self):
        return f"Identity Resolution for {self.datasource.name}"


# Enhanced handle_datasource_deletion in users/profile_integration.py

def handle_datasource_deletion(sender, instance, **kwargs):
    """
    Signal handler for data source deletion to clean up related user profile data.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Cleaning up data for deleted data source: {instance.name} (ID: {instance.id})")
    
    try:
        # Get counts for logging
        attribute_count = AttributeSource.objects.filter(datasource=instance).count()
        
        # Remove all attribute sources from this data source
        AttributeSource.objects.filter(datasource=instance).delete()
        logger.info(f"Deleted {attribute_count} attributes from data source {instance.name}")
        
        # Mark changes as orphaned by setting datasource to null
        # (we keep the change history but note the source is gone)
        change_count = ProfileAttributeChange.objects.filter(datasource=instance).count()
        ProfileAttributeChange.objects.filter(datasource=instance).update(datasource=None)
        logger.info(f"Orphaned {change_count} attribute changes from data source {instance.name}")
        
        # Delete field mappings
        mapping_count = ProfileFieldMapping.objects.filter(datasource=instance).count()
        ProfileFieldMapping.objects.filter(datasource=instance).delete()
        logger.info(f"Deleted {mapping_count} field mappings from data source {instance.name}")
        
        # Delete identity resolution config if it exists
        try:
            identity_config = IdentityResolutionConfig.objects.get(datasource=instance)
            identity_config.delete()
            logger.info(f"Deleted identity resolution config for data source {instance.name}")
        except IdentityResolutionConfig.DoesNotExist:
            pass
        
        # Handle CSV-specific cleanup
        if instance.type == 'csv':
            try:
                from datasources.csv_models import CSVDataSource, CSVFileUpload
                
                # Get CSV settings
                try:
                    csv_settings = CSVDataSource.objects.get(datasource=instance)
                    
                    # Get all uploads
                    uploads = CSVFileUpload.objects.filter(csv_datasource=csv_settings)
                    
                    # Delete the actual files
                    for upload in uploads:
                        try:
                            # Delete the file from storage
                            if upload.file:
                                upload.file.delete(save=False)
                        except Exception as file_error:
                            logger.error(f"Error deleting file {upload.file}: {str(file_error)}")
                    
                    # Delete the upload records
                    upload_count = uploads.count()
                    uploads.delete()
                    logger.info(f"Deleted {upload_count} CSV file uploads from data source {instance.name}")
                    
                    # Delete the CSV settings
                    csv_settings.delete()
                    logger.info(f"Deleted CSV settings for data source {instance.name}")
                    
                except CSVDataSource.DoesNotExist:
                    pass
                
            except ImportError:
                logger.warning(f"Could not import CSV models for cleanup")
        
        logger.info(f"Successfully cleaned up all data for data source: {instance.name}")
        
    except Exception as e:
        logger.error(f"Error during data source deletion cleanup: {str(e)}")
        # Don't re-raise the exception - we want the data source to be deleted
        # even if some cleanup fails

class AttributeDisplayConfig(models.Model):
    """
    Configuration for how attributes from a data source should be displayed in user profiles.
    """
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='attribute_display_configs'
    )
    attribute_name = models.CharField(_('Attribute Name'), max_length=100)
    display_name = models.CharField(_('Display Name'), max_length=100, blank=True,
                                  help_text=_('Custom label to show in the UI'))
    category = models.CharField(_('Category'), max_length=50, default='general',
                              help_text=_('Grouping for related attributes'))
    display_order = models.PositiveIntegerField(_('Display Order'), default=999,
                                              help_text=_('Lower numbers appear first'))
    is_primary = models.BooleanField(_('Primary Attribute'), default=False,
                                   help_text=_('Show in profile summary'))
    is_visible = models.BooleanField(_('Visible'), default=True,
                                   help_text=_('Show in profile view'))
    
    class Meta:
        verbose_name = _('Attribute Display Configuration')
        verbose_name_plural = _('Attribute Display Configurations')
        unique_together = ('datasource', 'attribute_name')
        ordering = ['datasource', 'category', 'display_order', 'attribute_name']
    
    def __str__(self):
        return f"{self.datasource.name}: {self.attribute_name}"

    def get_formatted_display_name(self):
        """Return the display name or a formatted version of the attribute name"""
        if self.display_name:
            return self.display_name
        return self.attribute_name.replace('_', ' ').title()



