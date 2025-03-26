# datasources/active_directory_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.db import transaction

from .models import DataSource, DataSourceField, DataSourceSync
from .active_directory_models import ActiveDirectoryConnection, ActiveDirectoryDataSource
from .active_directory_forms import ActiveDirectoryConnectionForm, ActiveDirectoryDataSourceForm
from .connectors.active_directory_connector import ADConnector

import logging
logger = logging.getLogger(__name__)

# Active Directory Connection Views
class ADConnectionListView(LoginRequiredMixin, ListView):
    """
    View for listing Active Directory connections
    """
    model = ActiveDirectoryConnection
    template_name = 'datasources/active_directory/connections/index.html'
    context_object_name = 'connections'
    
    def get_queryset(self):
        return ActiveDirectoryConnection.objects.all().order_by('name')

class ADConnectionDetailView(LoginRequiredMixin, DetailView):
    """
    View for connection details
    """
    model = ActiveDirectoryConnection
    template_name = 'datasources/active_directory/connections/detail.html'
    context_object_name = 'connection'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get data sources using this connection
        context['data_sources'] = self.object.data_sources.all()
        
        return context

class ADConnectionCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new Active Directory connection
    """
    model = ActiveDirectoryConnection
    form_class = ActiveDirectoryConnectionForm
    template_name = 'datasources/active_directory/connections/form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check if we're returning to a data source
        context['return_to_datasource'] = self.request.GET.get('return_to') == 'datasource'
        context['datasource_id'] = self.request.GET.get('datasource_id')
        return context
    
    def form_valid(self, form):
        with transaction.atomic():
            # Save the connection
            connection = form.save(commit=False)
            connection.created_by = self.request.user
            connection.modified_by = self.request.user
            connection.save()
            
            messages.success(self.request, _('Active Directory connection created successfully.'))
            
            # Check if we need to return to a data source
            if self.request.GET.get('return_to') == 'datasource':
                datasource_id = self.request.GET.get('datasource_id')
                if datasource_id:
                    try:
                        datasource = DataSource.objects.get(id=datasource_id)
                        # Create AD settings for the datasource
                        ad_settings = ActiveDirectoryDataSource(
                            datasource=datasource,
                            connection=connection
                        )
                        ad_settings.save()
                        
                        return redirect('datasources:ad_detail', pk=datasource_id)
                    except DataSource.DoesNotExist:
                        pass
            
            # Otherwise go to connection detail
            return redirect('datasources:ad_connection_detail', pk=connection.pk)

class ADConnectionUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating an Active Directory connection
    """
    model = ActiveDirectoryConnection
    form_class = ActiveDirectoryConnectionForm
    template_name = 'datasources/active_directory/connections/form.html'
    
    def form_valid(self, form):
        with transaction.atomic():
            # Save the connection
            connection = form.save(commit=False)
            connection.modified_by = self.request.user
            connection.save()
            
            messages.success(self.request, _('Active Directory connection updated successfully.'))
            
            # Test connection if requested
            if 'test_connection' in self.request.POST:
                return redirect('datasources:ad_connection_test', pk=connection.pk)
            
            return redirect('datasources:ad_connection_detail', pk=connection.pk)

class ADConnectionDeleteView(LoginRequiredMixin, DeleteView):
    """
    View for deleting an Active Directory connection
    """
    model = ActiveDirectoryConnection
    template_name = 'datasources/active_directory/connections/confirm_delete.html'
    success_url = reverse_lazy('datasources:ad_connections')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Check if connection is in use
        context['used_by_count'] = self.object.data_sources.count()
        
        return context
    
    def delete(self, request, *args, **kwargs):
        connection = self.get_object()
        
        # Check if connection is in use
        if connection.data_sources.exists():
            messages.error(request, _(
                'Cannot delete connection that is in use by data sources. '
                'Please update those data sources to use a different connection first.'
            ))
            return redirect('datasources:ad_connection_detail', pk=connection.pk)
        
        messages.success(request, _('Active Directory connection deleted successfully.'))
        return super().delete(request, *args, **kwargs)

class ADConnectionTestView(LoginRequiredMixin, View):
    """
    View for testing an Active Directory connection
    """
    def get(self, request, pk):
        connection = get_object_or_404(ActiveDirectoryConnection, pk=pk)
        
        try:
            # Test the connection
            connector = ADConnector(connection.get_connection_info())
            success, message = connector.test_connection()
            
            if success:
                messages.success(request, _('Connection test successful: {}').format(message))
            else:
                messages.error(request, _('Connection test failed: {}').format(message))
        
        except Exception as e:
            messages.error(request, _('Error testing connection: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:ad_connection_detail', pk=pk)

# Active Directory Data Source Views
class ADDataSourceCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new Active Directory data source
    """
    template_name = 'datasources/active_directory/create.html'
    form_class = ActiveDirectoryDataSourceForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get available connections
        context['connections'] = ActiveDirectoryConnection.objects.all().order_by('name')
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        
        with transaction.atomic():
            # Create the base DataSource
            datasource = DataSource(
                name=form.cleaned_data['name'],
                description=form.cleaned_data['description'],
                type='active_directory',
                status=form.cleaned_data.get('status', 'active'),
                created_by=self.request.user,
                modified_by=self.request.user
            )
            datasource.save()
            
            # Create the Active Directory settings with selected connection
            ad_settings = ActiveDirectoryDataSource(
                datasource=datasource,
                connection=form.cleaned_data['connection'],
                user_filter=form.cleaned_data['user_filter'],
                user_attributes=form.cleaned_data['user_attributes'],
                include_groups=form.cleaned_data['include_groups'],
                include_nested_groups=form.cleaned_data['include_nested_groups'],
                group_filter=form.cleaned_data['group_filter'],
                group_attributes=form.cleaned_data['group_attributes'],
                page_size=form.cleaned_data['page_size'],
                sync_deleted=form.cleaned_data['sync_deleted']
            )
            ad_settings.save()
            
            messages.success(self.request, _('Active Directory data source created successfully.'))
            return redirect('datasources:ad_detail', pk=datasource.pk)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)

class ADDataSourceUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating an Active Directory data source
    """
    model = DataSource
    template_name = 'datasources/active_directory/update.html'
    form_class = ActiveDirectoryDataSourceForm
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.type != 'active_directory':
            messages.error(self.request, _('This is not an Active Directory data source.'))
            return redirect('datasources:index')
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['settings_form'] = ActiveDirectoryDataSourceForm(
                self.request.POST, 
                instance=self.object.active_directory_settings
            )
        else:
            try:
                context['settings_form'] = ActiveDirectoryDataSourceForm(instance=self.object.active_directory_settings)
            except ActiveDirectoryDataSource.DoesNotExist:
                # Create settings if they don't exist
                context['settings_form'] = ActiveDirectoryDataSourceForm(initial={'datasource': self.object})
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        settings_form = context['settings_form']
        
        if settings_form.is_valid():
            with transaction.atomic():
                # Update the base data source
                datasource = form.save(commit=False)
                datasource.modified_by = self.request.user
                datasource.save()
                
                # Update or create the AD settings
                ad_settings = settings_form.save(commit=False)
                ad_settings.datasource = datasource
                ad_settings.save()
                
                messages.success(self.request, _('Active Directory data source updated successfully.'))
                
                # Test connection if requested
                if 'test_connection' in self.request.POST:
                    return redirect('datasources:ad_test_connection', pk=datasource.pk)
                
                return redirect('datasources:ad_detail', pk=datasource.pk)
        else:
            return self.form_invalid(form)

class ADDataSourceDetailView(LoginRequiredMixin, DetailView):
    """
    View for Active Directory data source details
    """
    model = DataSource
    template_name = 'datasources/active_directory/detail.html'
    context_object_name = 'datasource'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.type != 'active_directory':
            messages.error(self.request, _('This is not an Active Directory data source.'))
            return redirect('datasources:index')
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get AD settings
        try:
            context['ad_settings'] = self.object.active_directory_settings
        except ActiveDirectoryDataSource.DoesNotExist:
            context['ad_settings'] = None
        
        # Get field information
        context['fields'] = self.object.fields.all().order_by('name')
        
        # Get recent syncs
        context['recent_syncs'] = self.object.syncs.all().order_by('-start_time')[:5]
        
        return context

class ADTestConnectionView(LoginRequiredMixin, View):
    """
    View for testing AD connection
    """
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'active_directory':
            messages.error(request, _('This is not an Active Directory data source.'))
            return redirect('datasources:index')
        
        self._test_connection(request, datasource)
        return redirect('datasources:ad_detail', pk=pk)
    
    def post(self, request, pk):
        # Add this method to handle POST requests
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'active_directory':
            messages.error(request, _('This is not an Active Directory data source.'))
            return redirect('datasources:index')
        
        self._test_connection(request, datasource)
        return redirect('datasources:ad_detail', pk=pk)
    
    def _test_connection(self, request, datasource):
        try:
            # Get or create AD settings
            try:
                ad_settings = datasource.active_directory_settings
            except ActiveDirectoryDataSource.DoesNotExist:
                messages.error(request, _('Active Directory settings not found for this data source.'))
                return
            
            # Create connector and test connection
            connector = ADConnector(datasource)
            success, message = connector.test_connection()
            
            if success:
                messages.success(request, _('Connection test successful: {}').format(message))
            else:
                messages.error(request, _('Connection test failed: {}').format(message))
            
        except Exception as e:
            messages.error(request, _('Error testing connection: {}').format(str(e)))

class ADDataSourceSyncView(LoginRequiredMixin, View):
    """
    View to trigger a manual sync of an Active Directory data source
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'active_directory':
            messages.error(request, _('This is not an Active Directory data source.'))
            return redirect('datasources:index')
        
        # Check if already syncing
        if datasource.is_syncing():
            messages.warning(request, _('This data source is already being synchronized.'))
            return redirect('datasources:ad_detail', pk=pk)
        
        try:
            # Create connector with the datasource instance
            connector = ADConnector(datasource=datasource)  # Make sure datasource is passed here
            sync = connector.sync_data(triggered_by=request.user)
            
            if sync.status == 'success':
                messages.success(request, _(
                    'Data sync completed successfully. {processed} users processed, {created} created, {updated} updated.'
                ).format(
                    processed=sync.records_processed,
                    created=sync.records_created,
                    updated=sync.records_updated
                ))
            else:
                messages.error(request, _('Data sync failed: {}').format(sync.error_message))
            
        except Exception as e:
            messages.error(request, _('Error syncing data: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:ad_detail', pk=pk)

class ADDetectFieldsView(LoginRequiredMixin, View):
    """
    View for auto-detecting fields from Active Directory
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'active_directory':
            messages.error(request, _('This is not an Active Directory data source.'))
            return redirect('datasources:index')
        
        try:
            # Create connector with the datasource instance
            connector = ADConnector(datasource=datasource)
            fields = connector.detect_fields()
            
            # Replace existing fields with detected ones
            with transaction.atomic():
                # Delete existing fields
                datasource.fields.all().delete()
                
                # Create new fields
                for field_dict in fields:
                    DataSourceField.objects.create(
                        datasource=datasource,
                        **field_dict
                    )
            
            messages.success(
                request, 
                _('Successfully detected {count} fields from Active Directory.').format(
                    count=len(fields)
                )
            )
        except Exception as e:
            messages.error(request, _('Error detecting fields: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:ad_detail', pk=pk)