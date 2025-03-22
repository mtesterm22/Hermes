# workflows/templatetags/workflow_tags.py
from django import template
from django.utils.safestring import mark_safe
import json

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Gets an item from a dictionary safely.
    Used for looking up items by ID in templates.
    """
    if dictionary is None:
        return None
    
    # Try to convert key to int if it's a string representing an integer
    try:
        if isinstance(key, str) and key.isdigit():
            key = int(key)
    except (ValueError, TypeError):
        pass
    
    return dictionary.get(key)

@register.filter
def pretty_json(value):
    """
    Format a JSON object for display.
    """
    if isinstance(value, dict):
        return mark_safe(json.dumps(value, indent=2))
    return value

@register.filter
def status_color(status):
    """
    Return a Tailwind CSS color class based on status.
    """
    status_colors = {
        'success': 'bg-green-100 text-green-800',
        'error': 'bg-red-100 text-red-800',
        'warning': 'bg-yellow-100 text-yellow-800',
        'running': 'bg-blue-100 text-blue-800',
        'pending': 'bg-gray-100 text-gray-800',
        'cancelled': 'bg-gray-100 text-gray-800',
        'skipped': 'bg-gray-100 text-gray-800',
    }
    return status_colors.get(status, 'bg-gray-100 text-gray-800')