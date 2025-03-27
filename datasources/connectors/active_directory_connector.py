# datasources/connectors/active_directory_connector.py
import logging
from typing import Dict, Any, List, Tuple, Optional, Set, Union
import datetime
import time

from django.utils import timezone
from django.db import transaction

from ldap3 import Server, Connection, Tls, SUBTREE, LEVEL, BASE, ALL_ATTRIBUTES
from ldap3.core.exceptions import LDAPException, LDAPBindError, LDAPSocketOpenError
import ssl

from ..models import DataSource, DataSourceField, DataSourceSync
from ..active_directory_models import ActiveDirectoryDataSource, ADSync

logger = logging.getLogger(__name__)

class ADConnector:
    """
    Connector for Active Directory data sources via LDAP.
    """
    
    def __init__(self, config=None, datasource=None):
        """
        Initialize with either a config dictionary or a DataSource instance.
        
        Args:
            config: Dictionary with connection parameters
            datasource: DataSource instance
        """
        self.config = config
        self.datasource = datasource
        self._connection = None
        self._server = None
        self.sync = None
        
        # If datasource is provided, get config from it
        if datasource and not config:
            try:
                self.ad_settings = datasource.active_directory_settings
                self.config = self.ad_settings.get_settings()
            except ActiveDirectoryDataSource.DoesNotExist:
                raise ValueError("Active Directory settings not found for this data source")
    
    def _get_connection(self):
        """
        Get a connection to the Active Directory server.
        
        Returns:
            ldap3.Connection object
        """
        if self._connection is None:
            # Create TLS configuration if needed
            tls = None
            if self.config.get('use_ssl') or self.config.get('use_start_tls'):
                tls = Tls(validate=ssl.CERT_NONE)  # Can be configured for certificate validation
            
            # Create server object
            self._server = Server(
                self.config['server'],
                port=self.config.get('port', 389),
                use_ssl=self.config.get('use_ssl', False),
                tls=tls,
                get_info='ALL'
            )
            
            # Create connection
            self._connection = Connection(
                self._server,
                user=self.config.get('bind_dn', ''),
                password=self.config.get('password', ''),
                auto_bind=False,
                version=self.config.get('ldap_version', 3),
                receive_timeout=self.config.get('connect_timeout', 30),
                read_only=True  # Use read-only by default for safety
            )
        
        return self._connection
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the connection to the Active Directory server.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            conn = self._get_connection()
            
            # Try to bind
            if not conn.bind():
                return False, f"Failed to bind: {conn.result}"
            
            # If bound successfully, try a simple search
            base_dn = self.config.get('base_dn', '')
            if not base_dn:
                return True, "Connected successfully but base DN is not set for testing search"
            
            search_filter = '(objectClass=*)'
            search_scope = {
                'base': BASE,
                'level': LEVEL,
                'subtree': SUBTREE
            }.get(self.config.get('search_scope', 'subtree'), SUBTREE)
            
            if not conn.search(
                base_dn,
                search_filter,
                search_scope=search_scope,
                attributes=['cn'],
                size_limit=1
            ):
                return True, f"Connected successfully but search failed: {conn.result}"
            
            entry_count = len(conn.entries)
            return True, f"Connected and searched successfully. Found {entry_count} entries."
            
        except LDAPBindError as e:
            return False, f"Authentication failed: {str(e)}"
        except LDAPSocketOpenError as e:
            return False, f"Connection failed: {str(e)}"
        except LDAPException as e:
            return False, f"LDAP error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
        finally:
            # Ensure connection is closed
            if self._connection and self._connection.bound:
                self._connection.unbind()
                self._connection = None
    
    def detect_fields(self) -> List[Dict[str, Any]]:

        """
        Auto-detect fields from the Active Directory schema.
        
        Returns:
            List of DataSourceField dictionaries
        """
        fields = []
        try:
            # Ensure we have a valid configuration
            if not self.config or not isinstance(self.config, dict):
                if self.datasource:
                    # Try to get config from datasource
                    try:
                        self.ad_settings = self.datasource.active_directory_settings
                        self.config = self.ad_settings.get_settings()
                    except Exception as e:
                        raise ValueError(f"Could not get Active Directory settings from datasource: {str(e)}")
                else:
                    raise ValueError("No configuration or datasource provided for field detection")
            
            conn = self._get_connection()
            
            # Try to bind
            if not conn.bind():
                raise Exception(f"Failed to bind: {conn.result}")
            
            # Get base_dn and search filter from config
            base_dn = self.config.get('base_dn', '')
            user_filter = self.config.get('user_filter', '(objectClass=user)')
            
            # Search for one user to get attribute schema
            search_scope = {
                'base': BASE,
                'level': LEVEL,
                'subtree': SUBTREE
            }.get(self.config.get('search_scope', 'subtree'), SUBTREE)
            
            # Search for a user to get attributes
            if not conn.search(
                base_dn,
                user_filter,
                search_scope=search_scope,
                attributes=ALL_ATTRIBUTES,
                size_limit=1
            ):
                raise Exception(f"Search failed: {conn.result}")
            
            if not conn.entries:
                raise Exception("No users found to detect attributes")
            
            # Get the first user entry
            user = conn.entries[0]
            
            # Common AD attributes to prioritize
            common_attributes = [
                'objectGUID', 'sAMAccountName', 'userPrincipalName', 'cn', 'givenName', 
                'sn', 'displayName', 'mail', 'telephoneNumber', 'mobile', 'title',
                'department', 'company', 'manager', 'memberOf', 'whenCreated', 
                'whenChanged', 'userAccountControl', 'distinguishedName'
            ]
            
            # Sort to put common attributes first
            attributes = list(user.entry_attributes)
            attributes = [attr for attr in common_attributes if attr in attributes] + \
                         [attr for attr in attributes if attr not in common_attributes]
            
            # Create field entries
            for attr_name in attributes:
                attr_value = getattr(user, attr_name, None)
                sample_data = ""
                
                if attr_value is not None:
                    if isinstance(attr_value, list):
                        sample_data = str(attr_value[0]) if attr_value else ""
                    else:
                        sample_data = str(attr_value)
                
                # Determine field type
                field_type = self._guess_field_type(attr_value)
                is_key = attr_name in ['objectGUID', 'sAMAccountName', 'userPrincipalName', 'distinguishedName']
                
                fields.append({
                    'name': attr_name,
                    'display_name': attr_name,
                    'field_type': field_type,
                    'is_key': is_key,
                    'is_nullable': True,
                    'sample_data': sample_data[:100]  # Limit sample data length
                })
            
            return fields
                
        except Exception as e:
            logger.error(f"Error detecting fields: {str(e)}")
            raise
        finally:
            # Ensure connection is closed
            if self._connection and self._connection.bound:
                self._connection.unbind()
                self._connection = None
    
    def _guess_field_type(self, value):
        """
        Determine the field type based on the value.
        
        Args:
            value: Sample value to analyze
            
        Returns:
            Field type string
        """
        if value is None:
            return 'text'
        
        # Handle list values (common in LDAP)
        if isinstance(value, list):
            if not value:
                return 'text'
            # Use the first item to determine type
            value = value[0]
        
        # Check value type
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, datetime.datetime) or isinstance(value, datetime.date):
            return 'datetime'
        elif isinstance(value, bytes):
            return 'binary'
        
        # Default to text
        return 'text'
    
    def sync_data(self, triggered_by=None):
        """
        Synchronize data from Active Directory.
        
        Args:
            triggered_by: User who triggered the sync
            
        Returns:
            Sync record
        """
        # Create sync record
        if self.datasource:
            datasource_sync = DataSourceSync.objects.create(
                datasource=self.datasource,
                triggered_by=triggered_by,
                status='running'
            )
            
            # Create AD-specific sync record
            self.sync = ADSync.objects.create(
                active_directory_datasource=self.datasource.active_directory_settings,
                sync_record=datasource_sync
            )
        else:
            raise ValueError("DataSource instance required for sync_data")
        
        try:
            # Log important information for debugging
            logger.info(f"Starting sync for AD data source: {self.datasource.name}")
            logger.info(f"Using base DN: {self.config.get('base_dn', 'Not set')}")
            logger.info(f"Using user filter: {self.config.get('user_filter', 'Not set')}")
            
            conn = self._get_connection()
            
            # Try to bind
            if not conn.bind():
                error_msg = f"Failed to bind: {conn.result}"
                logger.error(error_msg)
                raise Exception(error_msg)
            
            # Get settings from config
            base_dn = self.config.get('base_dn', '')
            user_filter = self.config.get('user_filter', '(&(objectClass=user)(objectCategory=person))')
            user_attributes = self.config.get('user_attributes', [])
            include_groups = self.config.get('include_groups', True)
            include_nested_groups = self.config.get('include_nested_groups', True)
            group_filter = self.config.get('group_filter', '(objectClass=group)')
            group_attributes = self.config.get('group_attributes', [])
            page_size = self.config.get('page_size', 1000)
            sync_deleted = self.config.get('sync_deleted', False)
            
            # If no attributes specified, get all
            if not user_attributes:
                user_attributes = ALL_ATTRIBUTES
            
            if not group_attributes and include_groups:
                group_attributes = ALL_ATTRIBUTES
            
            # Get search scope
            search_scope = {
                'base': BASE,
                'level': LEVEL,
                'subtree': SUBTREE
            }.get(self.config.get('search_scope', 'subtree'), SUBTREE)
            
            # Set up profile integration service with improved error handling
            profile_service = None
            try:
                from users.services.profile_integration import ProfileIntegrationService
                logger.info("Attempting to initialize profile integration service")
                profile_service = ProfileIntegrationService(self.datasource, datasource_sync)
                logger.info("Profile integration service initialized successfully")
                
                # Check for existing field mappings
                from users.profile_integration import ProfileFieldMapping
                mapping_count = ProfileFieldMapping.objects.filter(datasource=self.datasource).count()
                logger.info(f"Found {mapping_count} profile field mappings for this data source")
            except ImportError:
                logger.warning("Profile integration service not available - module not found")
            except Exception as profile_error:
                logger.error(f"Error initializing profile service: {str(profile_error)}")
                # Continue without profile service - mark as warning
                datasource_sync.error_message = f"Profile integration error: {str(profile_error)}"
                datasource_sync.save(update_fields=['error_message'])
            
            # Search for users
            total_users = 0
            created_users = 0
            updated_users = 0
            deleted_users = 0
            
            # Track object IDs for later deletion detection
            synced_object_ids = []
            
            # Search for users with paged results to handle large directories
            try:
                logger.info(f"Executing LDAP search with filter: {user_filter}")
                entry_generator = conn.extend.standard.paged_search(
                    search_base=base_dn,
                    search_filter=user_filter,
                    search_scope=search_scope,
                    attributes=user_attributes,
                    paged_size=page_size,
                    generator=True
                )
                logger.info("LDAP search initiated successfully")
            except Exception as search_error:
                logger.error(f"Error executing LDAP search: {str(search_error)}")
                raise Exception(f"LDAP search failed: {str(search_error)}")
            
            # Process each user
            for entry in entry_generator:
                if 'attributes' not in entry:
                    continue
                
                try:
                    # Extract user data
                    user_data = entry['attributes']
                    
                    # Add DN
                    user_data['distinguishedName'] = entry['dn']
                    
                    # Generate a record ID for tracking
                    object_id = user_data.get('objectGUID', None)
                    if object_id:
                        # Convert binary GUID to string if needed
                        if isinstance(object_id, bytes):
                            import uuid
                            object_id = str(uuid.UUID(bytes_le=object_id))
                        elif isinstance(object_id, list) and object_id and isinstance(object_id[0], bytes):
                            import uuid
                            object_id = str(uuid.UUID(bytes_le=object_id[0]))
                    
                    # Use sAMAccountName as fallback
                    if not object_id:
                        object_id = user_data.get('sAMAccountName', '')
                        if isinstance(object_id, list) and object_id:
                            object_id = object_id[0]
                    
                    if object_id:
                        synced_object_ids.append(str(object_id))
                    
                    # Normalize data
                    normalized_data = self._normalize_ldap_data(user_data)
                    
                    # Find group memberships if requested
                    if include_groups and 'memberOf' in normalized_data:
                        group_dns = normalized_data['memberOf']
                        if isinstance(group_dns, str):
                            group_dns = [group_dns]
                        
                        # Get group names
                        normalized_data['groupNames'] = []
                        for group_dn in group_dns:
                            # Extract CN from DN
                            if group_dn.startswith('CN='):
                                group_name = group_dn.split(',')[0][3:]
                                normalized_data['groupNames'].append(group_name)
                        
                        # If nested groups are enabled, we could expand them here
                        if include_nested_groups and group_dns:
                            logger.debug(f"Processing nested groups for user with ID {object_id}")
                            # This would require additional LDAP queries to find parent groups
                            # Implementation would depend on your specific needs
                    
                    # Process the record through profile integration if available
                    if profile_service:
                        try:
                            logger.debug(f"Processing user with ID {object_id} through profile integration")
                            person, created, changes = profile_service.process_record(normalized_data, str(object_id))
                            
                            if created:
                                created_users += 1
                                logger.debug(f"Created new profile for user with ID {object_id}")
                            elif changes > 0:
                                updated_users += 1
                                logger.debug(f"Updated profile for user with ID {object_id} with {changes} changes")
                        except Exception as profile_error:
                            logger.error(f"Error processing user with ID {object_id} through profile integration: {str(profile_error)}")
                            # Continue with next user
                    else:
                        # Just count the record if no profile integration
                        logger.debug(f"Counted user with ID {object_id} (no profile integration)")
                        total_users += 1
                    
                    # Update sync status periodically
                    if (created_users + updated_users) % 100 == 0:
                        self.sync.users_processed = total_users
                        self.sync.users_created = created_users
                        self.sync.users_updated = updated_users
                        self.sync.save(update_fields=['users_processed', 'users_created', 'users_updated'])
                        logger.info(f"Processed {total_users} users so far ({created_users} created, {updated_users} updated)")
                
                except Exception as e:
                    logger.error(f"Error processing user entry: {str(e)}")
                    # Continue with next entry to make sync as robust as possible
            
            # Handle deleted objects if requested
            if sync_deleted and profile_service and synced_object_ids:
                try:
                    logger.info(f"Removing attributes from profiles not in current dataset ({len(synced_object_ids)} objects processed)")
                    deleted_count = profile_service.remove_missing_attributes(synced_object_ids)
                    deleted_users = deleted_count
                    logger.info(f"Removed {deleted_count} attributes from profiles not in current dataset")
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up missing attributes: {str(cleanup_error)}")
            
            # Get final count if we haven't been tracking through profile service
            if profile_service is None:
                total_users = created_users + updated_users
            
            # Update sync stats
            self.sync.users_processed = total_users or created_users + updated_users
            self.sync.users_created = created_users
            self.sync.users_updated = updated_users
            self.sync.users_deleted = deleted_users
            self.sync.save()
            
            # Update main sync record
            datasource_sync.records_processed = total_users or created_users + updated_users + deleted_users
            datasource_sync.records_created = created_users
            datasource_sync.records_updated = updated_users
            datasource_sync.records_deleted = deleted_users
            datasource_sync.complete(status='success')
            
            # Update datasource
            self.datasource.status = 'active'
            self.datasource.last_sync = timezone.now()
            self.datasource.sync_count += 1
            self.datasource.save(update_fields=['status', 'last_sync', 'sync_count'])
            
            logger.info(f"Sync completed successfully: {created_users} created, {updated_users} updated, {deleted_users} deleted")
            return datasource_sync
            
        except Exception as e:
            import traceback
            error_message = f"Error syncing Active Directory data: {str(e)}"
            stack_trace = traceback.format_exc()
            logger.error(error_message)
            logger.error(f"Stack trace: {stack_trace}")
            
            if datasource_sync:
                datasource_sync.complete(status='error', error_message=error_message)
            
            # Update datasource status
            self.datasource.status = 'error'
            self.datasource.save(update_fields=['status'])
            
            raise
        finally:
            # Ensure connection is closed
            if self._connection and self._connection.bound:
                try:
                    self._connection.unbind()
                    logger.debug("LDAP connection closed successfully")
                except Exception as conn_error:
                    logger.warning(f"Error closing LDAP connection: {str(conn_error)}")
                finally:
                    self._connection = None
    
    def _normalize_ldap_data(self, data):
        """
        Normalize LDAP data for integration.
        
        Args:
            data: Dictionary of LDAP attributes
            
        Returns:
            Normalized data dictionary
        """
        normalized = {}
        
        for key, value in data.items():
            # Skip operational attributes
            if key.startswith('@'):
                continue
                
            # Handle binary data
            if isinstance(value, bytes):
                # For binary data like GUID, we convert to string representation
                try:
                    if key.lower() == 'objectguid':
                        import uuid
                        normalized[key] = str(uuid.UUID(bytes_le=value))
                    else:
                        # For other binary attributes, convert to hex
                        normalized[key] = value.hex()
                except Exception:
                    # If conversion fails, store as base64
                    import base64
                    normalized[key] = base64.b64encode(value).decode('ascii')
                    
            # Handle lists with one item
            elif isinstance(value, list) and len(value) == 1:
                # For single-item lists, unwrap the value
                normalized[key] = self._normalize_single_value(value[0])
                
            # Handle multi-valued attributes
            elif isinstance(value, list):
                # Convert items in the list
                normalized[key] = [self._normalize_single_value(item) for item in value]
                
            # Handle datetimes (LDAP returns these as strings, but we check just in case)
            elif isinstance(value, datetime.datetime):
                normalized[key] = value.isoformat()
                
            # Pass through other values
            else:
                normalized[key] = value
                
        return normalized
    
    def _normalize_single_value(self, value):
        """
        Normalize a single LDAP value.
        
        Args:
            value: Value to normalize
            
        Returns:
            Normalized value
        """
        # Handle binary data
        if isinstance(value, bytes):
            # For binary data, convert to hex
            return value.hex()
            
        # Handle datetime (LDAP returns these as strings, but we check just in case)
        elif isinstance(value, datetime.datetime):
            return value.isoformat()
            
        # Pass through other values
        else:
            return value