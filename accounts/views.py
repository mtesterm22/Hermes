# accounts/views.py - complete simplified file
import logging
from django.contrib.auth import login, get_user_model, update_session_auth_hash
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, UpdateView, DetailView, ListView

from .forms import HermesAuthenticationForm, UserRegistrationForm, UserProfileForm, HermesPasswordChangeForm
from .models import User, UserSession, AuditLog

logger = logging.getLogger(__name__)

User = get_user_model()


class HermesLoginView(LoginView):
    """Simple login view with no extra functionality"""
    form_class = HermesAuthenticationForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    
    def form_valid(self, form):
        """Just perform standard login and add message"""
        # Standard login logic
        result = super().form_valid(form)
        
        # Add success message
        messages.success(self.request, _('Login successful'))
        
        return result


class HermesLogoutView(LogoutView):
    """Simple logout view"""
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.info(request, _('You have been logged out.'))
            
        return super().dispatch(request, *args, **kwargs)


class UserRegistrationView(CreateView):
    """View for registering new users"""
    model = User
    form_class = UserRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:login')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _('Account created successfully. You can now log in.'))
        return response


class UserProfileView(LoginRequiredMixin, DetailView):
    """View for displaying user profile"""
    model = User
    template_name = 'accounts/profile.html'
    context_object_name = 'profile_user'
    
    def get_object(self):
        return self.request.user


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    """View for updating user profile"""
    model = User
    form_class = UserProfileForm
    template_name = 'accounts/profile_edit.html'
    success_url = reverse_lazy('accounts:profile')
    
    def get_object(self):
        return self.request.user
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, _('Profile updated successfully.'))
        return response


class HermesPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    """View for changing password"""
    form_class = HermesPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:profile')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, _('Password changed successfully.'))
        return response


class UserSessionListView(LoginRequiredMixin, ListView):
    """View for listing user sessions"""
    model = UserSession
    template_name = 'accounts/sessions.html'
    context_object_name = 'sessions'
    
    def get_queryset(self):
        return UserSession.objects.filter(user=self.request.user).order_by('-login_time')


@login_required
def terminate_session(request, session_id):
    """View for terminating a session"""
    session = get_object_or_404(UserSession, id=session_id, user=request.user)
    
    if session.status == 'active':
        session.status = 'terminated'
        session.logout_time = timezone.now()
        session.save()
        messages.success(request, _('Session terminated successfully.'))
    else:
        messages.info(request, _('This session is already inactive.'))
    
    return redirect('accounts:sessions')


class AdminUserListView(LoginRequiredMixin, ListView):
    """View for listing users (admin only)"""
    model = User
    template_name = 'accounts/admin/user_list.html'
    context_object_name = 'users'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff and not request.user.is_superuser:
            messages.error(request, _('You do not have permission to access this page.'))
            return redirect('dashboard:index')
        return super().dispatch(request, *args, **kwargs)


class AuditLogListView(LoginRequiredMixin, ListView):
    """View for listing audit logs (admin only)"""
    model = AuditLog
    template_name = 'accounts/admin/audit_log.html'
    context_object_name = 'logs'
    paginate_by = 50
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff and not request.user.is_superuser:
            messages.error(request, _('You do not have permission to access this page.'))
            return redirect('dashboard:index')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = AuditLog.objects.all().order_by('-timestamp')
        
        # Filter by user if provided
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by action if provided
        action = self.request.GET.get('action')
        if action:
            queryset = queryset.filter(action=action)
        
        # Filter by date range if provided
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.all()
        context['actions'] = dict(AuditLog.ACTION_CHOICES)
        return context