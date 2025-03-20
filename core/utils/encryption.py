"""
Encryption utilities for Hermes.

This module provides functions for encrypting and decrypting sensitive data.
"""

import json
import logging
from base64 import urlsafe_b64encode, urlsafe_b64decode
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

def get_encryption_key():
    """
    Get the encryption key from settings.
    
    Returns:
        Fernet key for encryption/decryption
    """
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    if not key:
        logger.warning("ENCRYPTION_KEY not found in settings. Using a fallback method.")
        # This is a fallback for development only and should not be used in production
        # In production, ENCRYPTION_KEY should be set in settings from environment variables
        key = urlsafe_b64encode(b'0123456789abcdef0123456789abcdef')
    
    # Ensure the key is bytes and properly formatted for Fernet
    if isinstance(key, str):
        key = key.encode()
        
    return key

def encrypt_value(value):
    """
    Encrypt a single value.
    
    Args:
        value: Value to encrypt (will be converted to string)
        
    Returns:
        Encrypted value as a string
    """
    if value is None:
        return None
        
    try:
        key = get_encryption_key()
        f = Fernet(key)
        
        # Convert value to string if it's not already
        if not isinstance(value, str):
            value = str(value)
            
        # Encrypt the value
        encrypted = f.encrypt(value.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Error encrypting value: {str(e)}")
        # In case of error, return a placeholder to avoid raising exceptions
        # This is not ideal for security but prevents application errors
        return "ENCRYPTION_ERROR"

def decrypt_value(encrypted_value):
    """
    Decrypt a single value.
    
    Args:
        encrypted_value: Encrypted value as a string
        
    Returns:
        Decrypted value as a string
    """
    if not encrypted_value or encrypted_value == "ENCRYPTION_ERROR":
        return None
        
    try:
        key = get_encryption_key()
        f = Fernet(key)
        
        # Ensure encrypted_value is bytes
        if isinstance(encrypted_value, str):
            encrypted_value = encrypted_value.encode()
            
        # Decrypt the value
        decrypted = f.decrypt(encrypted_value)
        return decrypted.decode()
    except (InvalidToken, Exception) as e:
        logger.error(f"Error decrypting value: {str(e)}")
        return None

def encrypt_credentials(credentials_dict):
    """
    Encrypt credentials using Fernet symmetric encryption.
    
    Args:
        credentials_dict: Dictionary containing credentials to encrypt
        
    Returns:
        Encrypted string
    """
    from cryptography.fernet import Fernet
    from django.conf import settings
    
    key = settings.ENCRYPTION_KEY
    f = Fernet(key)
    
    # Convert dict to string
    credentials_str = json.dumps(credentials_dict)
    
    # Encrypt the string
    encrypted = f.encrypt(credentials_str.encode())
    
    return encrypted.decode()

def decrypt_credentials(encrypted_str):
    """
    Decrypt credentials using Fernet symmetric encryption.
    
    Args:
        encrypted_str: Encrypted string to decrypt
        
    Returns:
        Dictionary containing decrypted credentials
    """
    from cryptography.fernet import Fernet
    from django.conf import settings
    
    try:
        key = settings.ENCRYPTION_KEY
        f = Fernet(key)
        
        # Decrypt the string
        decrypted = f.decrypt(encrypted_str.encode())
        
        # Convert string back to dict
        credentials_dict = json.loads(decrypted.decode())
        
        return credentials_dict
    except Exception as e:
        print(f"Error decrypting value: {str(e)}")
        return {}