# accounts/utils.py
from django.utils import timezone
from datetime import timedelta
from .models import UserSession

def cleanup_expired_sessions(days_threshold=7):
    """
    Clean up user sessions that are inactive or expired
    
    This function:
    1. Marks active sessions as expired if last activity > threshold days ago
    2. Deletes terminated/expired sessions older than threshold days
    
    Parameters:
    - days_threshold: Number of days to keep inactive sessions
    
    Returns:
    - tuple: (marked_expired_count, deleted_count)
    """
    threshold_date = timezone.now() - timedelta(days=days_threshold)
    
    # Mark active sessions as expired if last activity was too long ago
    expired_count = UserSession.objects.filter(
        status='active',
        last_activity__lt=threshold_date
    ).update(
        status='expired',
        logout_time=timezone.now()
    )
    
    # Delete old inactive sessions
    deleted_count = UserSession.objects.filter(
        status__in=['terminated', 'expired'],
        logout_time__lt=threshold_date
    ).delete()[0]
    
    return (expired_count, deleted_count)


def get_suspicious_login_attempts(threshold=5, timespan_hours=24):
    """
    Identify potentially suspicious login activity
    
    Parameters:
    - threshold: Number of failed attempts to consider suspicious
    - timespan_hours: Time window to check for failed attempts
    
    Returns:
    - dict: IP addresses with count of failed attempts
    """
    from .models import AuditLog
    
    timespan = timezone.now() - timedelta(hours=timespan_hours)
    
    # Get failed login attempts grouped by IP
    failed_logins = AuditLog.objects.filter(
        action='login_failed',
        timestamp__gte=timespan
    ).values('ip_address').annotate(
        failed_count=models.Count('id')
    ).filter(
        failed_count__gte=threshold
    ).order_by('-failed_count')
    
    return failed_logins