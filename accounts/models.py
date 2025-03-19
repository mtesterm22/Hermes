# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """
    Extended user model with additional fields for Hermes administrators
    """
    # Additional fields
    job_title = models.CharField(_('Job Title'), max_length=100, blank=True)
    department = models.CharField(_('Department'), max_length=100, blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)
    
    # User settings
    email_notifications = models.BooleanField(_('Email Notifications'), default=True)
    dark_mode = models.BooleanField(_('Dark Mode'), default=False)
    
    # Security & Audit
    last_password_change = models.DateTimeField(_('Last Password Change'), auto_now_add=True)
    last_login_ip = models.GenericIPAddressField(_('Last Login IP'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
    
    def __str__(self):
        return self.get_full_name() or self.username
    
    @property
    def is_admin(self):
        return self.is_staff or self.is_superuser
    
    def get_permissions(self):
        """Get all permissions for the user"""
        return self.user_permissions.all() | self.groups.values_list('permissions', flat=True)


class UserSession(models.Model):
    """
    Model to track user sessions for security auditing
    """
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('expired', _('Expired')),
        ('terminated', _('Terminated')),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    session_key = models.CharField(_('Session Key'), max_length=40)
    ip_address = models.GenericIPAddressField(_('IP Address'), blank=True, null=True)
    user_agent = models.TextField(_('User Agent'), blank=True)
    login_time = models.DateTimeField(_('Login Time'), auto_now_add=True)
    last_activity = models.DateTimeField(_('Last Activity'), auto_now=True)
    logout_time = models.DateTimeField(_('Logout Time'), blank=True, null=True)
    status = models.CharField(_('Status'), max_length=20, choices=STATUS_CHOICES, default='active')
    
    class Meta:
        verbose_name = _('User Session')
        verbose_name_plural = _('User Sessions')
        ordering = ['-login_time']
    
    def __str__(self):
        return f"{self.user.username} - {self.login_time}"


class AuditLog(models.Model):
    """
    Model to track user actions for security auditing
    """
    ACTION_CHOICES = [
        ('login', _('Login')),
        ('logout', _('Logout')),
        ('password_change', _('Password Change')),
        ('create', _('Create')),
        ('update', _('Update')),
        ('delete', _('Delete')),
        ('view', _('View')),
        ('export', _('Export')),
        ('run', _('Run Workflow')),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    action = models.CharField(_('Action'), max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(_('Timestamp'), auto_now_add=True)
    ip_address = models.GenericIPAddressField(_('IP Address'), blank=True, null=True)
    content_type = models.CharField(_('Content Type'), max_length=100, blank=True)
    object_id = models.CharField(_('Object ID'), max_length=100, blank=True)
    object_repr = models.CharField(_('Object Representation'), max_length=200, blank=True)
    additional_data = models.JSONField(_('Additional Data'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username if self.user else 'System'} - {self.get_action_display()} - {self.timestamp}"