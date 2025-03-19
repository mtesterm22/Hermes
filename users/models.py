# users/models.py
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from datasources.models import DataSource

User = get_user_model()

class Person(models.Model):
    """
    Core model for reconciled user identities across multiple systems
    """
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('inactive', _('Inactive')),
        ('pending', _('Pending')),
    ]
    
    # Core identifying information
    unique_id = models.CharField(_('Unique ID'), max_length=100, unique=True)
    first_name = models.CharField(_('First Name'), max_length=100, blank=True)
    last_name = models.CharField(_('Last Name'), max_length=100, blank=True)
    display_name = models.CharField(_('Display Name'), max_length=200, blank=True)
    
    # Contact information
    email = models.EmailField(_('Email'), blank=True)
    secondary_email = models.EmailField(_('Secondary Email'), blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)
    
    # Status and metadata
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='active')
    attributes = models.JSONField(_('Attributes'), default=dict, blank=True)
    
    # Audit fields
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Person')
        verbose_name_plural = _('People')
        ordering = ['last_name', 'first_name']
    
    def __str__(self):
        if self.display_name:
            return self.display_name
        elif self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        else:
            return self.unique_id
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_external_ids(self):
        return self.external_ids.all()

class ExternalIdentity(models.Model):
    """
    Model for tracking identities in external systems
    """
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='external_ids'
    )
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='identities'
    )
    external_id = models.CharField(_('External ID'), max_length=100)
    username = models.CharField(_('Username'), max_length=100, blank=True)
    email = models.EmailField(_('Email'), blank=True)
    attributes = models.JSONField(_('Attributes'), default=dict, blank=True)
    last_synced = models.DateTimeField(_('Last Synced'), default=timezone.now)
    is_active = models.BooleanField(_('Is Active'), default=True)
    
    class Meta:
        verbose_name = _('External Identity')
        verbose_name_plural = _('External Identities')
        unique_together = ('datasource', 'external_id')
        ordering = ['datasource', 'external_id']
    
    def __str__(self):
        return f"{self.person} - {self.datasource.name} ({self.external_id})"

class AttributeChange(models.Model):
    """
    Model for tracking changes to person attributes over time
    """
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='attribute_changes'
    )
    external_identity = models.ForeignKey(
        ExternalIdentity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attribute_changes'
    )
    attribute_name = models.CharField(_('Attribute Name'), max_length=100)
    old_value = models.TextField(_('Old Value'), blank=True, null=True)
    new_value = models.TextField(_('New Value'), blank=True, null=True)
    changed_at = models.DateTimeField(_('Changed At'), auto_now_add=True)
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attribute_changes'
    )
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attribute_changes'
    )
    
    class Meta:
        verbose_name = _('Attribute Change')
        verbose_name_plural = _('Attribute Changes')
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.person} - {self.attribute_name} - {self.changed_at}"

class MappingRule(models.Model):
    """
    Model for configuring attribute mapping and transformation rules
    """
    RULE_TYPES = [
        ('direct', _('Direct Mapping')),
        ('transform', _('Transformation')),
        ('combine', _('Combine Fields')),
        ('split', _('Split Field')),
        ('conditional', _('Conditional')),
    ]
    
    name = models.CharField(_('Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    source_datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='source_rules'
    )
    source_field = models.CharField(_('Source Field'), max_length=100)
    target_field = models.CharField(_('Target Field'), max_length=100)
    rule_type = models.CharField(_('Rule Type'), max_length=20, choices=RULE_TYPES)
    rule_definition = models.JSONField(_('Rule Definition'), default=dict)
    is_active = models.BooleanField(_('Is Active'), default=True)
    
    # Audit fields
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='created_rules'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='modified_rules'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Mapping Rule')
        verbose_name_plural = _('Mapping Rules')
        ordering = ['source_datasource', 'source_field']
    
    def __str__(self):
        return f"{self.name} ({self.source_datasource.name}.{self.source_field} → {self.target_field})"

def get_identifiers(person):
    """
    Get all key field identifiers for a person from all data sources.
    Returns a dictionary of data source name to identifier value.
    """
    from users.profile_integration import AttributeSource, ProfileFieldMapping
    
    # Find all attributes that came from key field mappings
    identifiers = {}
    
    # Get all key field mappings
    key_mappings = ProfileFieldMapping.objects.filter(is_key_field=True)
    key_attributes = {mapping.profile_attribute for mapping in key_mappings}
    
    # Get all attribute sources for this person that match key attributes
    key_sources = AttributeSource.objects.filter(
        person=person,
        attribute_name__in=key_attributes,
        is_current=True
    ).select_related('datasource', 'mapping')
    
    # Group by data source
    for source in key_sources:
        if source.datasource.name not in identifiers:
            identifiers[source.datasource.name] = {}
        
        # Add the identifier with its attribute name
        identifiers[source.datasource.name][source.attribute_name] = source.attribute_value
    
    return identifiers