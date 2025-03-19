# accounts/decorators.py
import functools
from django.utils.translation import gettext_lazy as _
from ipware import get_client_ip
from .models import AuditLog

def audit_log(action, get_object_id=None, get_object_repr=None, content_type=None):
    """
    Decorator to log user actions for auditing purposes
    
    Parameters:
    - action: The action being performed (create, update, delete, etc.)
    - get_object_id: Function to extract object ID from function arguments
    - get_object_repr: Function to extract object representation from function arguments
    - content_type: Type of content being modified
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            # Call the view function first
            response = view_func(request, *args, **kwargs)
            
            # Only log if user is authenticated
            if request.user.is_authenticated:
                # Get client IP
                client_ip, _ = get_client_ip(request)
                
                # Extract object info
                object_id = get_object_id(args, kwargs) if get_object_id else ''
                if not object_id and 'pk' in kwargs:
                    object_id = str(kwargs['pk'])
                    
                object_repr = get_object_repr(args, kwargs, response) if get_object_repr else ''
                content_type_str = content_type or request.resolver_match.app_name
                
                # Create audit log
                AuditLog.objects.create(
                    user=request.user,
                    action=action,
                    ip_address=client_ip,
                    content_type=content_type_str,
                    object_id=object_id,
                    object_repr=object_repr
                )
            
            return response
        return wrapped_view
    return decorator


# Example usage:
"""
@audit_log(
    action='update',
    content_type='DataSource',
    get_object_id=lambda args, kwargs: str(kwargs.get('pk')),
    get_object_repr=lambda args, kwargs, response: f"DataSource: {kwargs.get('pk')}"
)
def some_view(request, pk):
    # View logic here
    pass
"""