# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User, UserSession, AuditLog


@admin.register(User)
class HermesUserAdmin(UserAdmin):
    """Custom admin for User model"""
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email', 'department', 'job_title', 'phone')}),
        (_('Preferences'), {'fields': ('email_notifications', 'dark_mode')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        (_('Security'), {'fields': ('last_login', 'last_password_change', 'last_login_ip')}),
        (_('Important dates'), {'fields': ('date_joined',)}),
    )
    readonly_fields = ('last_login', 'date_joined', 'last_password_change', 'last_login_ip')
    list_display = ('username', 'email', 'first_name', 'last_name', 'department', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'department')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'department')


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    """Admin for UserSession model"""
    list_display = ('user', 'login_time', 'last_activity', 'ip_address', 'status')
    list_filter = ('status', 'login_time')
    search_fields = ('user__username', 'ip_address', 'user_agent')
    readonly_fields = ('user', 'session_key', 'ip_address', 'user_agent', 'login_time', 'last_activity', 'logout_time')
    actions = ['terminate_sessions']
    
    def terminate_sessions(self, request, queryset):
        """Admin action to terminate selected active sessions"""
        from django.utils import timezone
        updated = queryset.filter(status='active').update(status='terminated', logout_time=timezone.now())
        self.message_user(request, _(f"{updated} sessions were successfully terminated."))
    terminate_sessions.short_description = _("Terminate selected active sessions")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for AuditLog model"""
    list_display = ('user', 'action', 'timestamp', 'ip_address', 'content_type', 'object_repr')
    list_filter = ('action', 'timestamp')
    search_fields = ('user__username', 'ip_address', 'content_type', 'object_repr')
    readonly_fields = ('user', 'action', 'timestamp', 'ip_address', 'content_type', 'object_id', 'object_repr', 'additional_data')
    date_hierarchy = 'timestamp'