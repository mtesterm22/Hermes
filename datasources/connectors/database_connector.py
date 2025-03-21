"""
Database connector for data sources.

This module implements a database connector for the data source system,
leveraging the core database functionality.
"""

import logging
import time
from typing import Dict, Any, Optional, Tuple, List, Union
from datetime import datetime

from django.utils import timezone

from core.database import get_connector, execute_query, execute_script
from core.database.utils import validate_query, extract_query_type, extract_query_params

from ..models import DataSource, DataSourceField, DataSourceSync
from ..database_models import DatabaseDataSource, DatabaseQuery, DatabaseQueryExecution

logger = logging.getLogger(__name__)

class DatabaseConnector:
    """
    Connector for database data sources.
    """
    
    def __init__(self, datasource):
        """
        Initialize with a DataSource instance.
        
        Args:
            datasource: DataSource instance
        """
        self.datasource = datasource
        try:
            self.db_settings = datasource.database_settings
        except DatabaseDataSource.DoesNotExist:
            raise ValueError("Database settings not found for this data source")
        
        self.sync = None
        self._connection = None
        self._connector = None
    
    def _get_connector(self):
        """
        Get the appropriate database connector.
        """
        if self._connector is None:
            # Get connection info
            connection_info = self.db_settings.get_connection_info()
            
            # Debug output
            print("Connection info for query (excluding password):", 
                {k:v for k,v in connection_info.items() if k != 'password'})
            print("Password present:", 'password' in connection_info)
            
            # Get connector
            from core.database import get_connector
            self._connector = get_connector(connection_info)
            
            if self._connector is None:
                raise ValueError(f"Unsupported database type: {connection_info.get('type')}")
        
        return self._connector
        
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the database connection.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            connector = self._get_connector()
            success, message = connector.test_connection()
            return success, message
        except Exception as e:
            error_message = f"Error testing database connection: {str(e)}"
            logger.error(error_message)
            return False, error_message
    
    def detect_fields(self, table_name: str = None, query: str = None) -> List[Dict[str, Any]]:
        """
        Auto-detect fields from a database table or query.
        
        Args:
            table_name: Name of the table to detect fields from
            query: SQL query to detect fields from
            
        Returns:
            List of DataSourceField dictionaries
        """
        connector = self._get_connector()
        fields = []
        
        try:
            if query:
                # Extract fields from query results
                is_valid, error = validate_query(query)
                if not is_valid:
                    raise ValueError(error)
                
                success, results, error = execute_query(
                    connector, 
                    query,
                    timeout=self.db_settings.query_timeout,
                )
                
                if not success or not results:
                    raise ValueError(f"Failed to execute query: {error}")
                
                # If results is a dictionary (e.g., for non-SELECT queries)
                if isinstance(results, dict):
                    raise ValueError("Query did not return tabular results")
                
                # Get field names from the first row
                if results:
                    first_row = results[0]
                    for field_name, value in first_row.items():
                        field_type = self._guess_field_type(value)
                        fields.append({
                            'name': field_name,
                            'display_name': field_name.replace('_', ' ').title(),
                            'field_type': field_type,
                            'is_key': False,
                            'is_nullable': True,
                            'sample_data': str(value) if value is not None else ''
                        })
            
            elif table_name:
                # Extract fields from table schema
                table_schema = connector.get_table_schema(table_name)
                
                for column in table_schema:
                    field_type = self._map_db_type_to_field_type(column.get('data_type', ''))
                    fields.append({
                        'name': column.get('name', ''),
                        'display_name': column.get('name', '').replace('_', ' ').title(),
                        'field_type': field_type,
                        'is_key': False,  # We might want to detect primary keys in the future
                        'is_nullable': column.get('is_nullable', True),
                        'sample_data': column.get('default', '')
                    })
            
            else:
                raise ValueError("Either table_name or query must be provided")
            
            return fields
            
        except Exception as e:
            logger.error(f"Error detecting fields: {str(e)}")
            raise
    
    def _guess_field_type(self, value: Any) -> str:
        """
        Guess the field type from a sample value.
        
        Args:
            value: Sample value
            
        Returns:
            Field type string
        """
        if value is None:
            return 'text'
        
        if isinstance(value, bool):
            return 'boolean'
        
        if isinstance(value, int):
            return 'integer'
        
        if isinstance(value, float):
            return 'float'
        
        if isinstance(value, (datetime, timezone)):
            return 'datetime'
        
        # Check if string might be a date/time
        if isinstance(value, str):
            # Try to detect if it's a date or datetime
            from datetime import datetime
            date_formats = [
                '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', 
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'
            ]
            
            for fmt in date_formats:
                try:
                    datetime.strptime(value, fmt)
                    return 'datetime' if '%H' in fmt else 'date'
                except ValueError:
                    pass
        
        # Default to text
        return 'text'
    
    def _map_db_type_to_field_type(self, db_type: str) -> str:
        """
        Map database column type to field type.
        
        Args:
            db_type: Database column type
            
        Returns:
            Field type string
        """
        db_type = db_type.lower()
        
        # Integer types
        if any(t in db_type for t in ['int', 'serial', 'smallint', 'bigint', 'tinyint']):
            return 'integer'
        
        # Float/decimal types
        if any(t in db_type for t in ['float', 'double', 'decimal', 'numeric', 'real']):
            return 'float'
        
        # Boolean types
        if any(t in db_type for t in ['bool', 'boolean']):
            return 'boolean'
        
        # Date types
        if any(t in db_type for t in ['date']):
            return 'date'
        
        # DateTime types
        if any(t in db_type for t in ['timestamp', 'datetime']):
            return 'datetime'
        
        # Text types
        if any(t in db_type for t in ['char', 'text', 'varchar', 'string']):
            return 'text'
        
        # Default to text
        return 'text'
    
    def execute_query(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None,
        create_execution_record: bool = True
    ) -> Tuple[bool, Any, Optional[DatabaseQueryExecution]]:
        """
        Execute a database query.
        
        Args:
            query: SQL query to execute
            params: Optional parameters for the query
            create_execution_record: Whether to create an execution record
            
        Returns:
            Tuple of (success, results, execution_record)
        """
        connector = self._get_connector()
        execution_record = None
        
        # Create execution record if requested
        if create_execution_record:
            execution_record = DatabaseQueryExecution.objects.create(
                database_datasource=self.db_settings,
                query_text=query,
                parameters=params or {},
                status='running'
            )
        
        try:
            # Validate query
            is_valid, error = validate_query(query)
            if not is_valid:
                if execution_record:
                    execution_record.complete(
                        status='failed',
                        error_message=error
                    )
                return False, None, execution_record
            
            # Execute the query
            start_time = time.time()
            success, results, error = execute_query(
                connector, 
                query, 
                params,
                timeout=self.db_settings.query_timeout
            )
            execution_time = time.time() - start_time
            
            # Update execution record
            if execution_record:
                if success:
                    # Determine rows affected
                    if isinstance(results, dict) and 'rowcount' in results:
                        rows_affected = results['rowcount']
                    elif isinstance(results, list):
                        rows_affected = len(results)
                    else:
                        rows_affected = 0
                    
                    execution_record.complete(
                        status='completed',
                        rows_affected=rows_affected
                    )
                else:
                    execution_record.complete(
                        status='failed',
                        error_message=error
                    )
            
            return success, results, execution_record
        
        except Exception as e:
            error_message = f"Error executing query: {str(e)}"
            logger.error(error_message)
            
            if execution_record:
                execution_record.complete(
                    status='failed',
                    error_message=error_message
                )
            
            return False, None, execution_record
    
    def execute_oracle_query(self, query_text, params=None):
        """
        Execute an Oracle-specific query with special handling for certain operations.
        
        Args:
            query_text: SQL query to execute
            params: Optional parameters for the query
            
        Returns:
            Tuple of (success, results, execution_record)
        """
        # Create an execution record
        execution_record = DatabaseQueryExecution.objects.create(
            database_datasource=self.db_settings,
            query_text=query_text,
            parameters=params or {},
            status='running'
        )
        
        try:
            # Get connection info
            connection_info = self.db_settings.get_connection_info()
            
            # Debug connection info
            print("Oracle connection info keys:", connection_info.keys())
            
            # Ensure Oracle type is set
            connection_info['type'] = 'oracle'
            
            # If no password, try to get it from credentials directly
            if 'password' not in connection_info and hasattr(self.db_settings.connection, 'credentials'):
                print("Trying to retrieve password directly from credentials")
                try:
                    creds = self.db_settings.connection.credentials
                    if isinstance(creds, dict):
                        # Try direct password
                        if 'password' in creds:
                            connection_info['password'] = creds['password']
                            print("Found password in direct credentials")
                            
                        # Try encrypted credentials
                        elif 'encrypted_credentials' in creds:
                            from core.utils.encryption import decrypt_credentials
                            decrypted = decrypt_credentials(creds['encrypted_credentials'])
                            if isinstance(decrypted, dict) and 'password' in decrypted:
                                connection_info['password'] = decrypted['password']
                                print("Found password in encrypted credentials")
                except Exception as e:
                    print(f"Error retrieving password: {str(e)}")
            
            # Create Oracle connector directly
            from core.database.oracle_connector import OracleConnector
            connector = OracleConnector(connection_info)
            
            # Execute the query
            success, results, error = connector.execute_query(
                query_text, 
                params,
                timeout=self.db_settings.query_timeout
            )
            
            # Update execution record
            if success:
                # Determine rows affected
                if isinstance(results, dict) and 'rowcount' in results:
                    rows_affected = results['rowcount']
                elif isinstance(results, list):
                    rows_affected = len(results)
                else:
                    rows_affected = 0
                
                execution_record.complete(
                    status='completed',
                    rows_affected=rows_affected
                )
            else:
                execution_record.complete(
                    status='failed',
                    error_message=error
                )
            
            return success, results, execution_record
        
        except Exception as e:
            import traceback
            error_message = f"Error executing Oracle query: {str(e)}\n{traceback.format_exc()}"
            print(error_message)
            
            execution_record.complete(
                status='failed',
                error_message=error_message
            )
            
            return False, None, execution_record

    def get_tables(self) -> List[str]:
        """
        Get a list of tables available in the database.
        
        Returns:
            List of table names
        """
        try:
            connector = self._get_connector()
            return connector.get_table_names()
        except Exception as e:
            logger.error(f"Error getting tables: {str(e)}")
            return []
    
    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get schema information for a database table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column definitions
        """
        try:
            connector = self._get_connector()
            return connector.get_table_schema(table_name)
        except Exception as e:
            logger.error(f"Error getting table schema: {str(e)}")
            return []
    
    def sync_data(self, triggered_by=None):
        """
        Synchronize data from the database.
        
        Args:
            triggered_by: User who triggered the sync
            
        Returns:
            Sync record
        """
        # Create sync record
        self.sync = DataSourceSync.objects.create(
            datasource=self.datasource,
            triggered_by=triggered_by,
            status='running'
        )
        
        try:
            # Get saved queries with preference for default query
            queries = DatabaseQuery.objects.filter(
                database_datasource=self.db_settings,
                is_enabled=True
            ).order_by('-is_default', 'name')
            
            if not queries.exists():
                self.sync.complete(
                    status='warning',
                    error_message='No enabled queries found for this data source'
                )
                return self.sync
            
            total_records = 0
            processed_queries = 0
            
            # Execute each query
            for query in queries:
                if query.query_type.lower() == 'select':
                    # For SELECT queries, get the results
                    success, results, execution = self.execute_query(
                        query.query_text,
                        query.parameters,
                        create_execution_record=True
                    )
                    
                    if success and results:
                        if isinstance(results, list):
                            total_records += len(results)
                        processed_queries += 1
                else:
                    # For non-SELECT queries, just execute them
                    success, results, execution = self.execute_query(
                        query.query_text,
                        query.parameters,
                        create_execution_record=True
                    )
                    
                    if success:
                        processed_queries += 1
                        
                        # If we have rowcount, add it to total records
                        if isinstance(results, dict) and 'rowcount' in results:
                            total_records += results['rowcount']
            
            # Update sync record
            self.sync.records_processed = total_records
            self.sync.complete(status='success')
            
            # Update datasource
            self.datasource.status = 'active'
            self.datasource.last_sync = timezone.now()
            self.datasource.sync_count += 1
            self.datasource.save(update_fields=['status', 'last_sync', 'sync_count'])
            
            return self.sync
            
        except Exception as e:
            error_message = f"Error syncing database data: {str(e)}"
            logger.error(error_message)
            
            if self.sync:
                self.sync.complete(status='error', error_message=error_message)
            
            # Update datasource status
            self.datasource.status = 'error'
            self.datasource.save(update_fields=['status'])
            
            raise
    """
    Enhanced database field detection functionality.

    This extension to the database connector allows detecting fields from queries
    and storing them for attribute management similar to CSV data sources.
    """

    def detect_fields_from_query(self, query, params=None):
        """
        Detect fields from a database query by executing it and examining the result set.
        
        Args:
            query: SQL query to execute
            params: Optional parameters for the query
            
        Returns:
            List of DataSourceField dictionaries
        """
        try:
            print(f"Detecting fields from query: {query[:100]}...")
            
            # Check database type for specialized handling
            is_oracle = False
            try:
                is_oracle = (self.db_settings.connection.db_type.lower() == 'oracle')
            except Exception as e:
                print(f"Error detecting database type: {str(e)}")
            
            # Execute the query to get sample data
            # Limit the number of rows to improve performance
            limited_query = self._limit_query_for_detection(query)
            
            if is_oracle:
                success, results, execution = self.execute_oracle_query(limited_query, params)
            else:
                success, results, execution = self.execute_query(limited_query, params)
            
            if not success or not results:
                if execution and execution.error_message:
                    raise ValueError(f"Query execution failed: {execution.error_message}")
                raise ValueError("Query execution failed or returned no results")
            
            # Process results to extract field information
            if isinstance(results, list) and results:
                # Get the first row for sample data
                sample_row = results[0]
                fields = []
                
                for field_name, value in sample_row.items():
                    # Create field definition
                    field = {
                        'name': field_name,
                        'display_name': field_name.replace('_', ' ').title(),
                        'field_type': self._guess_field_type(value),
                        'is_key': False,  # Default to False, user can modify later
                        'is_nullable': True,  # Default to True, user can modify later
                        'sample_data': str(value) if value is not None else ''
                    }
                    fields.append(field)
                
                return fields
            else:
                raise ValueError("Unexpected result format")
        
        except Exception as e:
            import traceback
            print(f"Error detecting fields: {str(e)}")
            print(traceback.format_exc())
            raise

    def _limit_query_for_detection(self, query):
        """
        Add LIMIT/ROWNUM clause to query for field detection to improve performance.
        Handles different database syntaxes.
        
        Args:
            query: Original SQL query
            
        Returns:
            Modified query with row limit
        """
        # Determine database type
        db_type = self.db_settings.connection.db_type.lower()
        
        # Strip ending semicolon if present
        query = query.strip()
        if query.endswith(';'):
            query = query[:-1].strip()
        
        # Different limits for different database types
        if db_type == 'oracle':
            # Check if query already has a ROWNUM condition
            if 'rownum' in query.lower():
                return query
                
            # Oracle uses ROWNUM
            if 'where' in query.lower():
                return f"{query} AND ROWNUM <= 5"
            else:
                return f"{query} WHERE ROWNUM <= 5"
                
        elif db_type in ['postgresql', 'mysql', 'sqlite']:
            # Check if query already has a LIMIT clause
            if 'limit' in query.lower():
                return query
                
            # Most SQL databases use LIMIT
            return f"{query} LIMIT 5"
            
        elif db_type == 'sqlserver':
            # SQL Server uses TOP
            if 'top' in query.lower():
                return query
                
            # Insert TOP after the first SELECT
            select_pos = query.lower().find('select')
            if select_pos >= 0:
                return f"{query[:select_pos+6]} TOP 5 {query[select_pos+6:]}"
        
        # Default - return query unchanged
        return query

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
        
        # Use type to determine field type
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, (datetime.date, datetime.datetime)):
            if isinstance(value, datetime.datetime):
                return 'datetime'
            else:
                return 'date'
        
        # If it's a string, try to detect if it might be a formatted date/datetime
        if isinstance(value, str):
            # Try various date formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    datetime.datetime.strptime(value, fmt)
                    return 'date'
                except ValueError:
                    pass
            
            # Try datetime formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y %H:%M:%S']:
                try:
                    datetime.datetime.strptime(value, fmt)
                    return 'datetime'
                except ValueError:
                    pass
        
        # Default to text for anything else
        return 'text'

    def create_fields_from_query(self, datasource, query, params=None):
        """
        Create field definitions in the database based on query results.
        
        Args:
            datasource: DataSource instance to add fields to
            query: SQL query to execute
            params: Optional parameters for the query
            
        Returns:
            List of created DataSourceField instances
        """
        from ..models import DataSourceField
        
        # First, detect fields from the query
        field_defs = self.detect_fields_from_query(query, params)
        
        # Create field objects in the database
        created_fields = []
        
        with transaction.atomic():
            # Optionally clear existing fields first
            # datasource.fields.all().delete()
            
            # Create new fields
            for field_def in field_defs:
                field = DataSourceField(
                    datasource=datasource,
                    **field_def
                )
                field.save()
                created_fields.append(field)
        
        return created_fields

def execute_oracle_query(self, query_text, params=None):
    """
    Execute an Oracle-specific query with dedicated handling.
    
    Args:
        query_text: SQL query to execute
        params: Optional parameters for the query
        
    Returns:
        Tuple of (success, results, execution_record)
    """
    from core.database.oracle_connector import OracleConnector
    
    # Create an execution record
    execution_record = DatabaseQueryExecution.objects.create(
        database_datasource=self.db_settings,
        query_text=query_text,
        parameters=params or {},
        status='running'
    )
    
    try:
        # Get connection info
        connection_info = self.db_settings.get_connection_info()
        
        # Ensure connection info has the type set to 'oracle'
        connection_info['type'] = 'oracle'
        
        # Create Oracle connector directly
        connector = OracleConnector(connection_info)
        
        # Test connection first to ensure it's valid
        success, message = connector.test_connection()
        if not success:
            execution_record.complete(
                status='failed',
                error_message=f"Failed to connect: {message}"
            )
            return False, None, execution_record
        
        # Execute the query with detailed logging
        print(f"Executing Oracle query: {query_text}")
        print(f"With parameters: {params}")
        
        # Execute the query
        success, results, error = connector.execute_query(
            query_text, 
            params,
            timeout=self.db_settings.query_timeout
        )
        
        # Update execution record
        if success:
            # Determine rows affected
            if isinstance(results, dict) and 'rowcount' in results:
                rows_affected = results['rowcount']
            elif isinstance(results, list):
                rows_affected = len(results)
            else:
                rows_affected = 0
            
            execution_record.complete(
                status='completed',
                rows_affected=rows_affected
            )
        else:
            execution_record.complete(
                status='failed',
                error_message=error
            )
        
        return success, results, execution_record
    
    except Exception as e:
        import traceback
        error_message = f"Error executing Oracle query: {str(e)}\n{traceback.format_exc()}"
        print(error_message)
        
        execution_record.complete(
            status='failed',
            error_message=error_message
        )
        
        return False, None, execution_record

