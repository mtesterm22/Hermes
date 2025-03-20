# core/database/oracle_connector.py
import logging
import cx_Oracle
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

class OracleConnector:
    """
    Connector for Oracle databases.
    """
    
    def __init__(self, connection_info):
        """
        Initialize with connection info.
        
        Args:
            connection_info: Dictionary with Oracle connection parameters
        """
        self.connection_info = connection_info
        self.connection = None
    
    def get_connection(self):
        """
        Get or create a connection to the Oracle database.
        
        Returns:
            Connection object
        """
        if self.connection is None or self.connection.closed:
            # Build DSN string for Oracle
            host = self.connection_info.get('host', 'localhost')
            port = self.connection_info.get('port', 1521)
            service_name = self.connection_info.get('service_name')
            sid = self.connection_info.get('sid')
            
            # Choose between service_name and SID
            if service_name:
                dsn = cx_Oracle.makedsn(host, port, service_name=service_name)
            elif sid:
                dsn = cx_Oracle.makedsn(host, port, sid=sid)
            else:
                # If neither is provided, use the database name as the service name
                database = self.connection_info.get('database', '')
                dsn = cx_Oracle.makedsn(host, port, service_name=database)
            
            username = self.connection_info.get('user', '')
            password = self.connection_info.get('password', '')
            
            # Additional connection options
            encoding = self.connection_info.get('encoding', 'UTF-8')
            
            # Create the connection
            self.connection = cx_Oracle.connect(
                user=username,
                password=password,
                dsn=dsn,
                encoding=encoding
            )
            
            # Configure session
            cursor = self.connection.cursor()
            cursor.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'")
            cursor.close()
        
        return self.connection
    
    def close_connection(self):
        """
        Close the connection if it exists.
        """
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the database connection.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            result = cursor.fetchone()
            cursor.close()
            
            if result and result[0] == 1:
                # Get Oracle version
                cursor = conn.cursor()
                cursor.execute("SELECT BANNER FROM V$VERSION WHERE BANNER LIKE 'Oracle%'")
                version = cursor.fetchone()
                cursor.close()
                
                version_str = version[0] if version else "Unknown"
                return True, f"Connected successfully to Oracle: {version_str}"
            else:
                return False, "Connection test query returned unexpected result"
        except Exception as e:
            return False, f"Error connecting to Oracle: {str(e)}"
    
    def get_table_names(self) -> List[str]:
        """
        Get a list of table names in the database schema.
        
        Returns:
            List of table names
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Get the schema to use (if provided)
            schema = self.connection_info.get('schema', '').upper()
            if not schema:
                # Use the user's schema by default
                schema = self.connection_info.get('user', '').upper()
            
            # Query for tables in the schema
            query = """
            SELECT TABLE_NAME 
            FROM ALL_TABLES 
            WHERE OWNER = :schema
            ORDER BY TABLE_NAME
            """
            
            cursor.execute(query, schema=schema)
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            
            return tables
        except Exception as e:
            logger.error(f"Error getting table names: {str(e)}")
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
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Get the schema to use (if provided)
            schema = self.connection_info.get('schema', '').upper()
            if not schema:
                # Use the user's schema by default
                schema = self.connection_info.get('user', '').upper()
            
            # Query for column information
            query = """
            SELECT 
                COLUMN_NAME, 
                DATA_TYPE,
                DATA_LENGTH,
                NULLABLE,
                DATA_DEFAULT
            FROM ALL_TAB_COLUMNS
            WHERE OWNER = :schema
            AND TABLE_NAME = :table_name
            ORDER BY COLUMN_ID
            """
            
            cursor.execute(query, schema=schema, table_name=table_name.upper())
            
            columns = []
            for row in cursor.fetchall():
                column = {
                    'name': row[0],
                    'data_type': row[1],
                    'data_length': row[2],
                    'is_nullable': row[3] == 'Y',
                    'default': row[4] if row[4] else None
                }
                columns.append(column)
            
            cursor.close()
            return columns
        except Exception as e:
            logger.error(f"Error getting table schema: {str(e)}")
            return []
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None, 
                     timeout: int = 60) -> Tuple[bool, Any, Optional[str]]:
        """
        Execute a SQL query with optional parameters.
        
        Args:
            query: SQL query to execute
            params: Optional parameters for the query
            timeout: Query timeout in seconds
            
        Returns:
            Tuple of (success, results, error_message)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Set array size for better performance with large result sets
            cursor.arraysize = 1000
            
            # Convert dict params to bind variables
            bind_params = {}
            if params:
                for key, value in params.items():
                    # Oracle uses :param format
                    bind_params[key] = value
            
            # Execute the query
            if bind_params:
                cursor.execute(query, bind_params)
            else:
                cursor.execute(query)
            
            # Determine query type from the first word
            query_type = query.strip().split(' ')[0].upper()
            
            # Handle based on query type
            if query_type in ['SELECT']:
                # For SELECT, return the rows as a list of dicts
                columns = [col[0] for col in cursor.description]
                rows = []
                
                for row in cursor:
                    rows.append(dict(zip(columns, row)))
                
                cursor.close()
                return True, rows, None
            else:
                # For other queries, return row count
                affected = cursor.rowcount
                conn.commit()
                cursor.close()
                return True, {'rowcount': affected}, None
        
        except Exception as e:
            # Log the error for debugging
            logger.error(f"Error executing Oracle query: {str(e)}")
            
            # Attempt to get specific Oracle error information
            error_message = str(e)
            
            # If a cursor was created, close it
            if 'cursor' in locals() and cursor:
                cursor.close()
            
            return False, None, error_message