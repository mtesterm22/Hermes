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
        Get a database connector instance.
        
        Returns:
            Database connector instance
        """
        if self._connector is None:
            connection_info = self.db_settings.get_connection_info()
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
            # Get saved queries
            queries = DatabaseQuery.objects.filter(
                database_datasource=self.db_settings,
                is_enabled=True
            )
            
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