# Create a new file: datasources/connection_models.py
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from core.utils.encryption import encrypt_credentials, decrypt_credentials

class DatabaseConnection(models.Model):
    """
    Model for reusable database connections
    """
    DATABASE_TYPE_CHOICES = [
        ('postgresql', _('PostgreSQL')),
        ('mysql', _('MySQL')),
        ('oracle', _('Oracle')),
        ('sqlserver', _('SQL Server')),
        ('sqlite', _('SQLite')),
        ('other', _('Other')),
    ]
    
    name = models.CharField(_('Connection Name'), max_length=100)
    description = models.TextField(_('Description'), blank=True)
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
    credentials = models.JSONField(_('Credentials'), default=dict, blank=True, null=True)
    
    # Connection options
    use_ssl = models.BooleanField(_('Use SSL'), default=False)
    ssl_cert_path = models.CharField(_('SSL Certificate Path'), max_length=255, blank=True)
    connection_timeout = models.IntegerField(_('Connection Timeout (s)'), default=30)
    
    # Query execution settings
    query_timeout = models.IntegerField(_('Query Timeout (s)'), default=60)
    max_rows = models.IntegerField(_('Maximum Rows'), default=10000)
    fetch_size = models.IntegerField(_('Fetch Size'), default=1000)
    
    # Audit fields
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='created_connections'
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    modified_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='modified_connections'
    )
    modified_at = models.DateTimeField(_('Modified At'), auto_now=True)
    
    class Meta:
        verbose_name = _('Database Connection')
        verbose_name_plural = _('Database Connections')
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.get_db_type_display()})"
    
    def get_connection_info(self):
        """
        Get the connection information dictionary for this database connection.
        
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
        if self.credentials:
            # Check for encrypted credentials
            if 'encrypted_credentials' in self.credentials:
                encrypted_creds = self.credentials.get('encrypted_credentials')
                decrypted_creds = decrypt_credentials(encrypted_creds)
                if decrypted_creds and 'password' in decrypted_creds:
                    connection_info['password'] = decrypted_creds['password']
            # Fall back to direct password storage (legacy support)
            elif 'password' in self.credentials:
                connection_info['password'] = self.credentials.get('password')
        
        # Add SSL settings if enabled
        if self.use_ssl:
            connection_info['ssl'] = True
            
            if self.ssl_cert_path:
                connection_info['ssl_cert'] = self.ssl_cert_path
        
        return connection_info
    
    def test_connection(self):
        """
        Test the database connection.
        
        Returns:
            Tuple of (success, message)
        """
        from core.database import get_connector
        try:
            connector = get_connector(self.get_connection_info())
            return connector.test_connection()
        except Exception as e:
            return False, str(e)