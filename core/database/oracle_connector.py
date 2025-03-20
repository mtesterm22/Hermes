# core/database/oracle_connector.py
import logging
import traceback

logger = logging.getLogger(__name__)

class OracleConnector:
    def __init__(self, connection_info):
        self.connection_info = connection_info
        self.connection = None
        
        # Log the connection info without sensitive data
        safe_info = connection_info.copy()
        if 'password' in safe_info:
            safe_info['password'] = '******'
        logger.debug(f"Initializing Oracle connector with: {safe_info}")
    
    def connect(self):
        """
        Establish a connection to the Oracle database.
        """
        logger.debug("Connecting to Oracle database...")
        import cx_Oracle
        
        # Get connection parameters
        host = self.connection_info.get('host')
        port = self.connection_info.get('port', 1521)
        service_name = self.connection_info.get('service_name')
        sid = self.connection_info.get('sid')
        username = self.connection_info.get('user')
        password = self.connection_info.get('password')
        
        if not password:
            logger.error("No password provided for Oracle connection")
            raise ValueError("Password is required for Oracle connections")
        
        # Create DSN
        if service_name:
            logger.debug(f"Using service_name: {service_name}")
            dsn = cx_Oracle.makedsn(host, port, service_name=service_name)
        elif sid:
            logger.debug(f"Using SID: {sid}")
            dsn = cx_Oracle.makedsn(host, port, sid=sid)
        else:
            logger.error("No service_name or sid provided")
            raise ValueError("Either service_name or sid must be provided for Oracle connections")
        
        logger.debug(f"DSN: {dsn}")
        
        # Connect to the database
        try:
            self.connection = cx_Oracle.connect(username, password, dsn)
            logger.debug("Oracle connection established successfully")
            return self.connection
        except Exception as e:
            logger.error(f"Oracle connection failed: {str(e)}")
            raise
    
    def is_connection_closed(self, connection):
        """Check if an Oracle connection is closed or invalid."""
        try:
            # Execute a simple query to test the connection
            cursor = connection.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.close()
            return False  # Connection is open
        except Exception:
            return True  # Connection is closed or has an error
    
    def execute_query(self, query, params=None, timeout=None):
        """
        Execute a SQL query against the Oracle database.
        
        Args:
            query: SQL query to execute
            params: Optional parameters for the query
            timeout: Optional timeout in seconds
            
        Returns:
            Tuple of (success, results, error_message)
        """
        try:
            logger.debug(f"Executing Oracle query: {query}")
            
            # Make sure we have a connection
            if not hasattr(self, 'connection') or self.connection is None or self.is_connection_closed(self.connection):
                logger.debug("No active connection, creating new connection")
                self.connect()
            
            cursor = self.connection.cursor()
            
            # Set timeout if specified
            if timeout:
                cursor.callTimeout = timeout * 1000  # Convert to milliseconds
            
            # Execute the query
            if params:
                logger.debug(f"With parameters: {params}")
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # For SELECT queries, fetch results
            if query.strip().upper().startswith('SELECT'):
                columns = [col[0] for col in cursor.description]
                results = []
                
                for row in cursor:
                    results.append(dict(zip(columns, row)))
                
                logger.debug(f"Query returned {len(results)} rows")
                cursor.close()
                return True, results, None
            else:
                # For non-SELECT queries, return row count
                rowcount = cursor.rowcount
                self.connection.commit()
                logger.debug(f"Query affected {rowcount} rows")
                cursor.close()
                return True, {'rowcount': rowcount}, None
                
        except Exception as e:
            error_message = f"Error executing Oracle query: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_message)
            return False, None, error_message
    
    def get_table_names(self):
        """
        Get a list of table names in the database.
        
        Returns:
            List of table names
        """
        try:
            logger.debug("Getting Oracle table names")
            
            schema = self.connection_info.get('schema')
            if not schema:
                schema = self.connection_info.get('user').upper()
            
            query = """
                SELECT TABLE_NAME 
                FROM ALL_TABLES 
                WHERE OWNER = :schema
                ORDER BY TABLE_NAME
            """
            
            success, results, error = self.execute_query(query, {'schema': schema})
            
            if success and results:
                table_names = [row['TABLE_NAME'] for row in results]
                logger.debug(f"Found {len(table_names)} tables")
                return table_names
            else:
                logger.error(f"Failed to get table names: {error}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting table names: {str(e)}")
            return []
    
    def get_table_schema(self, table_name):
        """
        Get schema information for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column definitions
        """
        try:
            logger.debug(f"Getting schema for table: {table_name}")
            
            schema = self.connection_info.get('schema')
            if not schema:
                schema = self.connection_info.get('user').upper()
            
            query = """
                SELECT 
                    COLUMN_NAME as name, 
                    DATA_TYPE as data_type,
                    DATA_LENGTH as length,
                    DATA_PRECISION as precision,
                    DATA_SCALE as scale,
                    NULLABLE as is_nullable,
                    DATA_DEFAULT as default
                FROM ALL_TAB_COLUMNS
                WHERE OWNER = :schema
                AND TABLE_NAME = :table_name
                ORDER BY COLUMN_ID
            """
            
            success, results, error = self.execute_query(
                query, 
                {'schema': schema, 'table_name': table_name}
            )
            
            if success and results:
                # Convert is_nullable from 'Y'/'N' to boolean
                for col in results:
                    col['is_nullable'] = (col['IS_NULLABLE'] == 'Y')
                
                logger.debug(f"Found {len(results)} columns for table {table_name}")
                return results
            else:
                logger.error(f"Failed to get table schema: {error}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting table schema: {str(e)}")
            return []
    
    def test_connection(self):
        """
        Test the connection to the Oracle database.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            logger.debug("Testing Oracle connection")
            
            # First ensure we have a connection
            if not hasattr(self, 'connection') or self.connection is None or self.is_connection_closed(self.connection):
                self.connect()
            
            # Execute a simple query
            success, results, error = self.execute_query("SELECT 1 FROM DUAL")
            
            if success:
                return True, "Connection successful"
            else:
                return False, f"Connection test failed: {error}"
                
        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            return False, str(e)
    
    def close(self):
        """
        Close the database connection.
        """
        try:
            if hasattr(self, 'connection') and self.connection is not None:
                self.connection.close()
                self.connection = None
                logger.debug("Oracle connection closed")
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")