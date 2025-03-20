"""
Database connector classes and factory functions.

This module provides connector classes for different database types and
factory functions to create appropriate connectors based on connection info.
"""

import logging
import importlib
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class DatabaseConnector(ABC):
    """Abstract base class for database connectors."""
    
    def __init__(self, connection_info: Dict[str, Any]):
        """
        Initialize the database connector.
        
        Args:
            connection_info: Dictionary containing connection parameters
        """
        self.connection_info = connection_info
        self.connection = None
        
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish a connection to the database.
        
        Returns:
            True if connection was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Close the database connection.
        
        Returns:
            True if disconnection was successful, False otherwise
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test the database connection.
        
        Returns:
            Tuple of (success, message) where success is True if connection
            test was successful, and message contains details
        """
        pass
    
    @abstractmethod
    def execute_query(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[bool, Any, str]:
        """
        Execute a SQL query and return the results.
        
        Args:
            query: SQL query string
            params: Optional parameters for query
            timeout: Optional query timeout in seconds
            
        Returns:
            Tuple of (success, results, error_message)
        """
        pass
    
    @abstractmethod
    def execute_script(
        self, 
        script: str, 
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[bool, Any, str]:
        """
        Execute a SQL script that may contain multiple statements.
        
        Args:
            script: SQL script string
            params: Optional parameters for script
            timeout: Optional script timeout in seconds
            
        Returns:
            Tuple of (success, results, error_message)
        """
        pass
    
    @abstractmethod
    def get_table_names(self) -> List[str]:
        """
        Get a list of table names from the database.
        
        Returns:
            List of table names
        """
        pass
    
    @abstractmethod
    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get schema information for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            List of column definitions
        """
        pass


class PostgreSQLConnector(DatabaseConnector):
    """PostgreSQL database connector."""
    
    def __init__(self, connection_info: Dict[str, Any]):
        """Initialize PostgreSQL connector."""
        super().__init__(connection_info)
        self.db_type = "postgresql"
        # Ensure psycopg2 is installed
        try:
            import psycopg2
            self.psycopg2 = psycopg2
        except ImportError:
            logger.error("psycopg2 module not found. Please install it to use PostgreSQL.")
            raise
    
    def connect(self) -> bool:
        """Establish a connection to PostgreSQL."""
        try:
            # Extract connection parameters
            host = self.connection_info.get('host', 'localhost')
            port = self.connection_info.get('port', 5432)
            database = self.connection_info.get('database', '')
            user = self.connection_info.get('user', '')
            password = self.connection_info.get('password', '')
            
            # Create connection
            self.connection = self.psycopg2.connect(
                host=host,
                port=port,
                dbname=database,
                user=user,
                password=password
            )
            return True
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {str(e)}")
            self.connection = None
            return False
    
    def disconnect(self) -> bool:
        """Close the PostgreSQL connection."""
        if self.connection:
            try:
                self.connection.close()
                self.connection = None
                return True
            except Exception as e:
                logger.error(f"Error disconnecting from PostgreSQL: {str(e)}")
                return False
        return True  # Already disconnected
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test the PostgreSQL connection."""
        if self.connection is None:
            success = self.connect()
            if not success:
                return False, "Failed to establish connection"
        
        try:
            # Try a simple query to test the connection
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                return True, f"Connection successful: {result[0]}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
        finally:
            # Don't disconnect here as the connection might be reused
            pass
    
    def execute_query(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[bool, Any, str]:
        """Execute a SQL query in PostgreSQL."""
        # Ensure connection is established
        if self.connection is None:
            success = self.connect()
            if not success:
                return False, None, "Failed to establish connection"
        
        try:
            # Set statement_timeout if provided
            if timeout is not None:
                with self.connection.cursor() as cursor:
                    cursor.execute(f"SET statement_timeout TO {timeout * 1000}")  # Convert to milliseconds
            
            with self.connection.cursor() as cursor:
                # Execute query with parameters if provided
                if params:
                    # Convert dict params to psycopg2 named parameters
                    # (psycopg2 uses %(name)s format)
                    modified_query = query
                    for key, value in params.items():
                        placeholder = f":{key}"
                        modified_query = modified_query.replace(placeholder, f"%({key})s")
                    
                    cursor.execute(modified_query, params)
                else:
                    cursor.execute(query)
                
                # Fetch results if the query returns data
                if cursor.description is not None:
                    columns = [desc[0] for desc in cursor.description]
                    results = cursor.fetchall()
                    # Convert to list of dictionaries
                    formatted_results = [dict(zip(columns, row)) for row in results]
                    return True, formatted_results, ""
                else:
                    # For non-SELECT queries (e.g., INSERT, UPDATE)
                    self.connection.commit()
                    row_count = cursor.rowcount
                    return True, {"rowcount": row_count}, ""
        
        except Exception as e:
            self.connection.rollback()
            error_message = f"Query execution failed: {str(e)}"
            logger.error(error_message)
            return False, None, error_message
    
    def execute_script(
        self, 
        script: str, 
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[bool, Any, str]:
        """Execute a SQL script in PostgreSQL."""
        # Ensure connection is established
        if self.connection is None:
            success = self.connect()
            if not success:
                return False, None, "Failed to establish connection"
        
        try:
            # Set statement_timeout if provided
            if timeout is not None:
                with self.connection.cursor() as cursor:
                    cursor.execute(f"SET statement_timeout TO {timeout * 1000}")  # Convert to milliseconds
            
            with self.connection.cursor() as cursor:
                # Parameter substitution for scripts is more complex
                # Here we're doing a simple replacement
                if params:
                    processed_script = script
                    for key, value in params.items():
                        placeholder = f":{key}"
                        # Handle different data types for SQL
                        if isinstance(value, str):
                            processed_script = processed_script.replace(placeholder, f"'{value}'")
                        elif value is None:
                            processed_script = processed_script.replace(placeholder, "NULL")
                        else:
                            processed_script = processed_script.replace(placeholder, str(value))
                else:
                    processed_script = script
                
                # Execute the script
                cursor.execute(processed_script)
                
                # Commit the transaction
                self.connection.commit()
                
                # Return success with empty results
                # (scripts may have multiple statements with different results)
                return True, {"executed": True}, ""
        
        except Exception as e:
            self.connection.rollback()
            error_message = f"Script execution failed: {str(e)}"
            logger.error(error_message)
            return False, None, error_message
    
    def get_table_names(self) -> List[str]:
        """Get a list of table names from PostgreSQL."""
        if self.connection is None:
            success = self.connect()
            if not success:
                return []
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name
                """)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting table names: {str(e)}")
            return []
    
    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Get schema information for a PostgreSQL table."""
        if self.connection is None:
            success = self.connect()
            if not success:
                return []
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        column_name, 
                        data_type, 
                        is_nullable, 
                        column_default
                    FROM 
                        information_schema.columns 
                    WHERE 
                        table_schema = 'public' AND 
                        table_name = %s
                    ORDER BY 
                        ordinal_position
                """, (table_name,))
                
                columns = []
                for row in cursor.fetchall():
                    columns.append({
                        "name": row[0],
                        "data_type": row[1],
                        "is_nullable": row[2] == "YES",
                        "default": row[3]
                    })
                return columns
        except Exception as e:
            logger.error(f"Error getting table schema: {str(e)}")
            return []


class MySQLConnector(DatabaseConnector):
    """MySQL database connector."""
    
    def __init__(self, connection_info: Dict[str, Any]):
        """Initialize MySQL connector."""
        super().__init__(connection_info)
        self.db_type = "mysql"
        # Ensure MySQLdb is installed
        try:
            import mysql.connector
            self.mysql = mysql.connector
        except ImportError:
            logger.error("mysql-connector-python module not found. Please install it to use MySQL.")
            raise
    
    def connect(self) -> bool:
        """Establish a connection to MySQL."""
        try:
            # Extract connection parameters
            host = self.connection_info.get('host', 'localhost')
            port = self.connection_info.get('port', 3306)
            database = self.connection_info.get('database', '')
            user = self.connection_info.get('user', '')
            password = self.connection_info.get('password', '')
            
            # Create connection
            self.connection = self.mysql.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password
            )
            return True
        except Exception as e:
            logger.error(f"Error connecting to MySQL: {str(e)}")
            self.connection = None
            return False
    
    def disconnect(self) -> bool:
        """Close the MySQL connection."""
        if self.connection:
            try:
                self.connection.close()
                self.connection = None
                return True
            except Exception as e:
                logger.error(f"Error disconnecting from MySQL: {str(e)}")
                return False
        return True  # Already disconnected
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test the MySQL connection."""
        if self.connection is None:
            success = self.connect()
            if not success:
                return False, "Failed to establish connection"
        
        try:
            # Try a simple query to test the connection
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            return True, f"Connection successful: {result[0]}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
        finally:
            # Don't disconnect here as the connection might be reused
            pass
    
    def execute_query(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[bool, Any, str]:
        """Execute a SQL query in MySQL."""
        # Ensure connection is established
        if self.connection is None:
            success = self.connect()
            if not success:
                return False, None, "Failed to establish connection"
        
        try:
            # MySQL doesn't directly support named parameters in the same way
            # as PostgreSQL, so we'll convert them
            modified_query = query
            param_dict = {}
            
            if params:
                # Replace :param with %(param)s format
                for key in params:
                    placeholder = f":{key}"
                    modified_query = modified_query.replace(placeholder, f"%({key})s")
                param_dict = params
            
            cursor = self.connection.cursor(dictionary=True)
            
            # Set timeout if specified (MySQL uses a different approach)
            if timeout is not None:
                cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {timeout * 1000}")  # milliseconds
            
            # Execute the query
            cursor.execute(modified_query, param_dict)
            
            # Check if the query returns results
            if cursor.description is not None:
                results = cursor.fetchall()
                cursor.close()
                return True, results, ""
            else:
                # For non-SELECT queries
                self.connection.commit()
                row_count = cursor.rowcount
                cursor.close()
                return True, {"rowcount": row_count}, ""
        
        except Exception as e:
            self.connection.rollback()
            error_message = f"Query execution failed: {str(e)}"
            logger.error(error_message)
            return False, None, error_message
    
    def execute_script(
        self, 
        script: str, 
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[bool, Any, str]:
        """Execute a SQL script in MySQL."""
        # MySQL doesn't have a direct equivalent to PostgreSQL's execute_script
        # We'll split the script into statements and execute them individually
        
        # Ensure connection is established
        if self.connection is None:
            success = self.connect()
            if not success:
                return False, None, "Failed to establish connection"
        
        try:
            cursor = self.connection.cursor()
            
            # Set timeout if specified
            if timeout is not None:
                cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {timeout * 1000}")  # milliseconds
            
            # Process parameters if provided
            if params:
                processed_script = script
                for key, value in params.items():
                    placeholder = f":{key}"
                    # Handle different data types for SQL
                    if isinstance(value, str):
                        processed_script = processed_script.replace(placeholder, f"'{value}'")
                    elif value is None:
                        processed_script = processed_script.replace(placeholder, "NULL")
                    else:
                        processed_script = processed_script.replace(placeholder, str(value))
            else:
                processed_script = script
            
            # Split script into statements (simple approach)
            # Note: This doesn't handle all edge cases, like semicolons in string literals
            statements = processed_script.split(';')
            
            # Execute each statement
            for statement in statements:
                if statement.strip():
                    cursor.execute(statement)
            
            # Commit the transaction
            self.connection.commit()
            cursor.close()
            
            return True, {"executed": True}, ""
        
        except Exception as e:
            self.connection.rollback()
            error_message = f"Script execution failed: {str(e)}"
            logger.error(error_message)
            return False, None, error_message
    
    def get_table_names(self) -> List[str]:
        """Get a list of table names from MySQL."""
        if self.connection is None:
            success = self.connect()
            if not success:
                return []
        
        try:
            cursor = self.connection.cursor()
            database = self.connection_info.get('database', '')
            
            cursor.execute(f"""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = '{database}'
                ORDER BY table_name
            """)
            
            result = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return result
        except Exception as e:
            logger.error(f"Error getting table names: {str(e)}")
            return []
    
    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Get schema information for a MySQL table."""
        if self.connection is None:
            success = self.connect()
            if not success:
                return []
        
        try:
            cursor = self.connection.cursor()
            database = self.connection_info.get('database', '')
            
            cursor.execute(f"""
                SELECT 
                    column_name, 
                    data_type, 
                    is_nullable, 
                    column_default
                FROM 
                    information_schema.columns 
                WHERE 
                    table_schema = '{database}' AND 
                    table_name = '{table_name}'
                ORDER BY 
                    ordinal_position
            """)
            
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    "name": row[0],
                    "data_type": row[1],
                    "is_nullable": row[2] == "YES",
                    "default": row[3]
                })
            
            cursor.close()
            return columns
        except Exception as e:
            logger.error(f"Error getting table schema: {str(e)}")
            return []


# Add more database connectors here as needed (Oracle, SQL Server, SQLite, etc.)


def get_connector(connection_info: Dict[str, Any]) -> Optional[DatabaseConnector]:
    """
    Factory function to create an appropriate database connector.
    
    Args:
        connection_info: Dictionary with connection parameters, including 'type'
        
    Returns:
        Database connector instance or None if type is unsupported
    """
    db_type = connection_info.get('type', '').lower()
    
    if db_type == 'postgresql':
        return PostgreSQLConnector(connection_info)
    elif db_type == 'mysql':
        return MySQLConnector(connection_info)
    # Add more database types here
    
    logger.error(f"Unsupported database type: {db_type}")
    return None


def parse_connection_string(connection_string: str) -> Dict[str, Any]:
    """
    Parse a database connection string into a connection info dictionary.
    
    Args:
        connection_string: Database connection string (URI format)
        
    Returns:
        Dictionary with connection parameters
    """
    try:
        # Parse the connection string as a URI
        parsed = urlparse(connection_string)
        
        # Extract the database type from the scheme
        db_type = parsed.scheme.split('+')[0]  # handle cases like 'postgresql+psycopg2'
        
        # Base connection info
        connection_info = {
            'type': db_type,
            'host': parsed.hostname or 'localhost',
            'port': parsed.port,
            'user': parsed.username,
            'password': parsed.password,
        }
        
        # Add database name (path without leading slash)
        if parsed.path:
            connection_info['database'] = parsed.path.lstrip('/')
        
        # Parse query parameters
        if parsed.query:
            import urllib.parse
            query_params = dict(urllib.parse.parse_qsl(parsed.query))
            connection_info.update(query_params)
        
        return connection_info
        
    except Exception as e:
        logger.error(f"Error parsing connection string: {str(e)}")
        return {'type': 'unknown'}