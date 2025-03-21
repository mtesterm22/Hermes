"""
Encryption utilities for Hermes.

This module provides functions for encrypting and decrypting sensitive data.
"""

import json
import logging
import base64
from base64 import urlsafe_b64encode, urlsafe_b64decode
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
import traceback

logger = logging.getLogger(__name__)

def get_encryption_key():
    """
    Get the encryption key from settings.
    
    Returns:
        Fernet key for encryption/decryption
    """
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    
    # Debug output
    print("Encryption key type:", type(key))
    print("Encryption key present:", "Yes" if key else "No")
    
    if not key:
        logger.warning("ENCRYPTION_KEY not found in settings. Using a fallback method.")
        # This is a fallback for development only and should not be used in production
        # In production, ENCRYPTION_KEY should be set in settings from environment variables
        key = 'OF1TeEJXaVplY0VkSnFMdERYY01JYWpTVUt4OFlDTExSV29HUkxmbGRzRT0='
    
    # Ensure the key is bytes and properly formatted for Fernet
    if isinstance(key, str):
        key = key.encode()
    
    # Ensure the key is a valid Fernet key (32 url-safe base64-encoded bytes)
    try:
        # If key is not a valid Fernet key, try to pad or hash it
        Fernet(key)
    except Exception:
        # Fall back to a method that ensures we get a valid key
        # First try base64 decoding if it looks like base64
        try:
            if len(key) % 4 == 0 and all(c in b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in key):
                decoded = base64.b64decode(key)
                # If decoded is 32 bytes, use it directly, otherwise hash it
                if len(decoded) == 32:
                    key = base64.urlsafe_b64encode(decoded)
                else:
                    from hashlib import sha256
                    hashed = sha256(key).digest()
                    key = base64.urlsafe_b64encode(hashed)
            else:
                # Hash the key to get exactly 32 bytes
                from hashlib import sha256
                hashed = sha256(key).digest()
                key = base64.urlsafe_b64encode(hashed)
        except Exception as e:
            logger.error(f"Error processing encryption key: {str(e)}")
            # Fallback to a hardcoded key (NOT for production use)
            key = base64.urlsafe_b64encode(b'0123456789abcdef0123456789abcdef')
    
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
    try:
        key = get_encryption_key()
        f = Fernet(key)
        
        # Convert dict to string
        credentials_str = json.dumps(credentials_dict)
        
        # Encrypt the string
        encrypted = f.encrypt(credentials_str.encode())
        
        # Return as string for JSON serialization
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Error encrypting credentials: {str(e)}")
        print(f"Error encrypting credentials: {str(e)}")
        print(traceback.format_exc())
        return "ENCRYPTION_ERROR"

def decrypt_credentials(encrypted_str):
    """
    Decrypt credentials using Fernet symmetric encryption.
    
    Args:
        encrypted_str: Encrypted string to decrypt
        
    Returns:
        Dictionary containing decrypted credentials
    """
    try:
        key = get_encryption_key()
        f = Fernet(key)
        
        # Make sure encrypted_str is bytes
        if isinstance(encrypted_str, str):
            encrypted_str = encrypted_str.encode()
        
        # Debug output
        print("Attempting to decrypt credentials")
        print("Encrypted string type:", type(encrypted_str))
        print("Encrypted string length:", len(encrypted_str))
        
        # Decrypt the string
        decrypted = f.decrypt(encrypted_str)
        
        # Convert string back to dict
        credentials_dict = json.loads(decrypted.decode())
        
        # Debug output
        print("Successfully decrypted credentials")
        print("Decrypted keys:", credentials_dict.keys())
        
        return credentials_dict
    except Exception as e:
        print(f"Error decrypting credentials: {str(e)}")
        print(traceback.format_exc())
        logger.error(f"Error decrypting credentials: {str(e)}")
        return {}