# datasources/active_directory_models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.conf import settings

from .models import DataSource
from core.utils.encryption import encrypt_credentials, decrypt_credentials

class ActiveDirectoryConnection(models.Model):
    """
    Model for reusable Active Directory connections via LDAP
    """
    LDAP_VERSION_CHOICES = [
        (2, 'LDAP v2'),
        (3, 'LDAP v3'),
    ]
    
    SEARCH_SCOPE_CHOICES = [
        ('base', _('Base')),
        ('level', _('One Level')),
        ('subtree', _('Subtree')),
    ]
    
    name = models.CharField(_('Connection Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
    
    # Connection Settings
    server = models.CharField(_('Server'), max_length=255)
    port = models.IntegerField(_('Port'), default=389)
    use_ssl = models.BooleanField(_('Use SSL/TLS'), default=False)
    use_start_tls = models.BooleanField(_('Use StartTLS'), default=False)
    ldap_version = models.IntegerField(_('LDAP Version'), choices=LDAP_VERSION_CHOICES, default=3)
    
    # Authentication Settings
    bind_dn = models.CharField(_('Bind DN'), max_length=255, blank=True,
                              help_text=_('Distinguished Name for binding to LDAP server'))
    credentials = models.JSONField(_('Credentials'), default=dict, blank=True, null=True)
    
    # Search Settings
    base_dn = models.CharField(_('Base DN'), max_length=255,
                              help_text=_('Base Distinguished Name for LDAP searches'))
    search_scope = models.CharField(_('Search Scope'), max_length=20,
                                   choices=SEARCH_SCOPE_CHOICES, default='subtree')
    user_search_filter = models.CharField(_('User Search Filter'), max_length=255, 
                                        default='(objectClass=user)',
                                        help_text=_('LDAP filter to identify user objects'))
    group_search_filter = models.CharField(_('Group Search Filter'), max_length=255, 
                                         default='(objectClass=group)',
                                         help_text=_('LDAP filter to identify group objects'))
    
    # Connection options
    connect_timeout = models.IntegerField(_('Connection Timeout (s)'), default=30)
    
    # Audit fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_ad_connections'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='modified_ad_connections'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Active Directory Connection')
        verbose_name_plural = _('Active Directory Connections')
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.server})"
    
    def get_connection_info(self):
        """
        Get the connection information dictionary for this AD connection.
        
        Returns:
            Dictionary with connection parameters
        """
        connection_info = {
            'server': self.server,
            'port': self.port,
            'use_ssl': self.use_ssl,
            'use_start_tls': self.use_start_tls,
            'ldap_version': self.ldap_version,
            'bind_dn': self.bind_dn,
            'base_dn': self.base_dn,
            'search_scope': self.search_scope,
            'user_search_filter': self.user_search_filter,
            'group_search_filter': self.group_search_filter,
            'connect_timeout': self.connect_timeout,
        }
        
        # Add password from credentials if available
        if self.credentials and isinstance(self.credentials, dict):
            # Check for encrypted credentials
            if 'encrypted_credentials' in self.credentials:
                encrypted_creds = self.credentials.get('encrypted_credentials')
                try:
                    decrypted_creds = decrypt_credentials(encrypted_creds)
                    if decrypted_creds and isinstance(decrypted_creds, dict) and 'password' in decrypted_creds:
                        connection_info['password'] = decrypted_creds['password']
                except Exception as e:
                    print(f"Error decrypting credentials: {str(e)}")
            
            # Fall back to direct password storage (legacy support)
            elif 'password' in self.credentials:
                connection_info['password'] = self.credentials.get('password')
        
        return connection_info
    
    def test_connection(self):
        """
        Test the Active Directory connection.
        
        Returns:
            Tuple of (success, message)
        """
        from .connectors.active_directory_connector import ADConnector
        try:
            connector = ADConnector(self.get_connection_info())
            return connector.test_connection()
        except Exception as e:
            return False, str(e)


class ActiveDirectoryDataSource(models.Model):
    """
    Extension model for Active Directory specific data source settings.
    """
    datasource = models.OneToOneField(
        DataSource,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='active_directory_settings'
    )
    
    # AD connection (reusable)
    connection = models.ForeignKey(
        ActiveDirectoryConnection,
        on_delete=models.PROTECT,  # Don't allow deletion if referenced
        related_name='data_sources'
    )
    
    # User query settings
    user_filter = models.CharField(_('User Filter'), max_length=255, 
                                default='(&(objectClass=user)(objectCategory=person))',
                                help_text=_('LDAP filter for users to include'))
    user_attributes = models.JSONField(_('User Attributes'), default=list,
                                     help_text=_('List of LDAP attributes to retrieve for users'))
    include_groups = models.BooleanField(_('Include Group Membership'), default=True)
    
    # Group query settings
    include_nested_groups = models.BooleanField(_('Include Nested Groups'), default=True)
    group_filter = models.CharField(_('Group Filter'), max_length=255, 
                                  default='(objectClass=group)',
                                  help_text=_('LDAP filter for groups to include'))
    group_attributes = models.JSONField(_('Group Attributes'), default=list,
                                      help_text=_('List of LDAP attributes to retrieve for groups'))
    
    # Sync settings
    page_size = models.IntegerField(_('Page Size'), default=1000,
                                  help_text=_('Number of entries to retrieve per page'))
    sync_deleted = models.BooleanField(_('Sync Deleted Objects'), default=False,
                                     help_text=_('Check for deleted objects during sync'))
    
    class Meta:
        verbose_name = _('Active Directory Data Source')
        verbose_name_plural = _('Active Directory Data Sources')
    
    def __str__(self):
        return f"AD Settings for {self.datasource.name}"
    
    def get_settings(self):
        """
        Get a dictionary of settings for the connector.
        
        Returns:
            Dictionary of settings
        """
        base_settings = self.connection.get_connection_info()
        
        # Add query settings
        settings = {
            **base_settings,
            'user_filter': self.user_filter,
            'user_attributes': self.user_attributes,
            'include_groups': self.include_groups,
            'include_nested_groups': self.include_nested_groups,
            'group_filter': self.group_filter,
            'group_attributes': self.group_attributes,
            'page_size': self.page_size,
            'sync_deleted': self.sync_deleted,
        }
        
        return settings


class ADSync(models.Model):
    """
    Model for tracking Active Directory synchronization operations
    """
    active_directory_datasource = models.ForeignKey(
        ActiveDirectoryDataSource,
        on_delete=models.CASCADE,
        related_name='syncs'
    )
    sync_record = models.OneToOneField(
        'DataSourceSync',
        on_delete=models.CASCADE,
        related_name='ad_sync'
    )
    
    users_processed = models.IntegerField(_('Users Processed'), default=0)
    users_created = models.IntegerField(_('Users Created'), default=0)
    users_updated = models.IntegerField(_('Users Updated'), default=0)
    users_deleted = models.IntegerField(_('Users Deleted'), default=0)
    
    groups_processed = models.IntegerField(_('Groups Processed'), default=0)
    groups_created = models.IntegerField(_('Groups Created'), default=0)
    groups_updated = models.IntegerField(_('Groups Updated'), default=0)
    groups_deleted = models.IntegerField(_('Groups Deleted'), default=0)
    
    class Meta:
        verbose_name = _('Active Directory Sync')
        verbose_name_plural = _('Active Directory Syncs')
    
    def __str__(self):
        return f"AD Sync for {self.active_directory_datasource.datasource.name} - {self.sync_record.start_time}"