# core/database/oracle_connector.py
import logging
import traceback
from .connectors import DatabaseConnector

logger = logging.getLogger(__name__)

class OracleConnector(DatabaseConnector):
    """Oracle database connector implementation."""
    
    def __init__(self, connection_info):
        super().__init__(connection_info)
        self.db_type = "oracle"
        
        # Log the connection info without sensitive data
        safe_info = connection_info.copy() if connection_info else {}
        if 'password' in safe_info:
            safe_info['password'] = '******'
        logger.debug(f"Initializing Oracle connector with: {safe_info}")
        
        # More detailed debugging
        print("Oracle connection info keys:", self.connection_info.keys())
        print("Connection contains password:", 'password' in self.connection_info)
        print("Connection contains username:", 'user' in self.connection_info)
        print("Service name provided:", self.connection_info.get('service_name') is not None)
        print("SID provided:", self.connection_info.get('sid') is not None)
    
    def connect(self):
        """
        Establish a connection to the Oracle database.
        """
        logger.debug("Connecting to Oracle database...")
        try:
            import cx_Oracle
        except ImportError:
            logger.error("cx_Oracle module not found. Please install it to use Oracle.")
            raise ImportError("cx_Oracle module not found. Please install it to use Oracle.")
            
        # Get connection parameters
        host = self.connection_info.get('host')
        port = self.connection_info.get('port', 1521)
        service_name = self.connection_info.get('service_name')
        sid = self.connection_info.get('sid')
        username = self.connection_info.get('user')
        password = self.connection_info.get('password')
        
        # More detailed debugging
        print("Oracle connection details:")
        print(f"Host: {host}")
        print(f"Port: {port}")
        print(f"Service Name: {service_name}")
        print(f"SID: {sid}")
        print(f"Username: {username}")
        print(f"Password exists: {'Yes' if password else 'No'}")
        
        # Check for credentials in other formats
        if not password and 'credentials' in self.connection_info:
            creds = self.connection_info['credentials']
            if isinstance(creds, dict):
                if 'password' in creds:
                    password = creds['password']
                    print("Found password in credentials dictionary")
                if 'encrypted_credentials' in creds:
                    try:
                        from core.utils.encryption import decrypt_credentials
                        decrypted = decrypt_credentials(creds['encrypted_credentials'])
                        if decrypted and 'password' in decrypted:
                            password = decrypted['password']
                            print("Found password in encrypted credentials")
                    except Exception as e:
                        print(f"Error decrypting credentials: {str(e)}")
        
        # Password check with detailed error
        if not password:
            error_msg = (
                "No password provided for Oracle connection. "
                "Make sure the password is properly stored and retrieved. "
                "Check the database connection configuration."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if not host:
            raise ValueError("Host is required for Oracle connections")
            
        if not username:
            raise ValueError("Username is required for Oracle connections")
        
        # Create DSN - try both service_name and sid
        dsn = None
        try:
            if service_name:
                logger.debug(f"Using service_name: {service_name}")
                dsn = cx_Oracle.makedsn(host, port, service_name=service_name)
            elif sid:
                logger.debug(f"Using SID: {sid}")
                dsn = cx_Oracle.makedsn(host, port, sid=sid)
            else:
                # Try with just host/port if no service_name or SID provided
                logger.warning("No service_name or sid provided. Attempting connection with just host/port.")
                dsn = f"{host}:{port}"
        except Exception as e:
            logger.error(f"Error creating DSN: {str(e)}")
            raise
            
        if not dsn:
            error_msg = "Unable to create DSN for Oracle connection"
            logger.error(error_msg)
            raise ValueError(error_msg)
            
        logger.debug(f"DSN: {dsn}")
        
        # Connect to the database with detailed error handling
        try:
            self.connection = cx_Oracle.connect(username, password, dsn)
            logger.info("Oracle connection established successfully")
            print("Oracle connection established successfully")
            return True
        except cx_Oracle.DatabaseError as e:
            error_obj, = e.args
            error_msg = f"Oracle connection failed: {error_obj.message}"
            logger.error(error_msg)
            print(error_msg)
            self.connection = None
            return False
        except Exception as e:
            error_msg = f"Oracle connection failed with an unexpected error: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            print(error_msg)
            print(traceback.format_exc())
            self.connection = None
            return False
    
    def disconnect(self):
        """Close the database connection."""
        try:
            if self.connection:
                self.connection.close()
                self.connection = None
                logger.debug("Oracle connection closed")
                return True
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")
            return False
        return True  # Already disconnected
    
    def is_connection_closed(self):
        """Check if the Oracle connection is closed or invalid."""
        if not self.connection:
            return True
            
        try:
            # Execute a simple query to test the connection
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.close()
            return False  # Connection is open
        except Exception:
            return True  # Connection is closed or has an error
    
    def test_connection(self):
        """
        Test the connection to the Oracle database.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            logger.debug("Testing Oracle connection")
            
            # First ensure we have a connection
            if self.is_connection_closed():
                success = self.connect()
                if not success:
                    return False, "Failed to establish connection"
            
            # Execute a simple query
            success, results, error = self.execute_query("SELECT 1 FROM DUAL")
            
            if success:
                return True, "Connection successful"
            else:
                return False, f"Connection test failed: {error}"
                
        except Exception as e:
            logger.error(f"Error testing connection: {str(e)}")
            return False, str(e)
    
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
            if self.is_connection_closed():
                logger.debug("No active connection, creating new connection")
                success = self.connect()
                if not success:
                    return False, None, "Failed to establish connection"
            
            cursor = self.connection.cursor()
            
            # Note: Setting timeout on cursor is skipped since callTimeout is not available
            # Log a warning instead
            if timeout:
                logger.warning(f"Timeout specified ({timeout}s) but timeout setting not supported in this version of cx_Oracle")
                print(f"Timeout specified ({timeout}s) but not supported in this version of cx_Oracle")
            
            # Execute the query
            if params:
                logger.debug(f"With parameters: {params}")
                # Convert dict params to bind variables
                bind_params = {}
                
                # Oracle uses :param instead of %(param)s
                for key, value in params.items():
                    bind_params[key] = value
                
                cursor.execute(query, bind_params)
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
                return True, results, ""
            else:
                # For non-SELECT queries, return row count
                rowcount = cursor.rowcount
                self.connection.commit()
                logger.debug(f"Query affected {rowcount} rows")
                cursor.close()
                return True, {'rowcount': rowcount}, ""
                
        except Exception as e:
            error_message = f"Error executing Oracle query: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_message)
            print(error_message)
            if self.connection:
                try:
                    self.connection.rollback()
                except:
                    pass
            return False, None, error_message
    
    def execute_script(self, script, params=None, timeout=None):
        """
        Execute a SQL script with multiple statements.
        
        Args:
            script: SQL script with multiple statements
            params: Optional parameters
            timeout: Optional timeout in seconds
            
        Returns:
            Tuple of (success, results, error_message)
        """
        # Oracle doesn't have a direct way to execute multiple statements at once
        # We'll split the script and execute each statement
        
        statements = [stmt.strip() for stmt in script.split(';') if stmt.strip()]
        if not statements:
            return True, {"executed": True}, ""
            
        try:
            # Make sure we have a connection
            if self.is_connection_closed():
                success = self.connect()
                if not success:
                    return False, None, "Failed to establish connection"
            
            cursor = self.connection.cursor()
            
            # Set timeout if specified
            if timeout:
                cursor.callTimeout = timeout * 1000  # Convert to milliseconds
            
            # Execute each statement
            for statement in statements:
                if params:
                    # Simple parameter substitution
                    processed_statement = statement
                    for key, value in params.items():
                        placeholder = f":{key}"
                        if isinstance(value, str):
                            processed_statement = processed_statement.replace(placeholder, f"'{value}'")
                        elif value is None:
                            processed_statement = processed_statement.replace(placeholder, "NULL")
                        else:
                            processed_statement = processed_statement.replace(placeholder, str(value))
                    cursor.execute(processed_statement)
                else:
                    cursor.execute(statement)
            
            # Commit changes
            self.connection.commit()
            cursor.close()
            return True, {"executed": True}, ""
            
        except Exception as e:
            error_message = f"Error executing Oracle script: {str(e)}"
            logger.error(error_message)
            if self.connection:
                try:
                    self.connection.rollback()
                except:
                    pass
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
                schema = self.connection_info.get('user', '').upper()
            
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
                schema = self.connection_info.get('user', '').upper()
            
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
                    col['is_nullable'] = (col.get('IS_NULLABLE', 'N') == 'Y')
                
                logger.debug(f"Found {len(results)} columns for table {table_name}")
                return results
            else:
                logger.error(f"Failed to get table schema: {error}")
                return []
                
        except Exception as e:
            logger.error(f"Error getting table schema: {str(e)}")
            return []