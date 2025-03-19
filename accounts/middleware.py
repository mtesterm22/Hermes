# accounts/middleware.py
from django.utils import timezone
from ipware import get_client_ip
from .models import UserSession

class SessionTrackingMiddleware:
    """
    Middleware to track user sessions and activity
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process request
        if request.user.is_authenticated and request.session.session_key:
            # Check if we have an active session record
            session = UserSession.objects.filter(
                user=request.user,
                session_key=request.session.session_key,
                status='active'
            ).first()
            
            if session:
                # Update last activity time
                session.last_activity = timezone.now()
                session.save(update_fields=['last_activity'])
            else:
                # Create a new session record if none exists
                client_ip, _ = get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                
                UserSession.objects.create(
                    user=request.user,
                    session_key=request.session.session_key,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    status='active'
                )
                
                # Update user's last login IP
                request.user.last_login_ip = client_ip
                request.user.save(update_fields=['last_login_ip'])

        response = self.get_response(request)
        return response