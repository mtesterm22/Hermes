from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.db import transaction

from .connection_models import DatabaseConnection
from .forms import DatabaseConnectionForm, DatabaseDataSourceForm
from core.database import get_connector

class ConnectionListView(LoginRequiredMixin, ListView):
    """
    View for listing database connections
    """
    model = DatabaseConnection
    template_name = 'datasources/connections/index.html'
    context_object_name = 'connections'
    
    def get_queryset(self):
        return DatabaseConnection.objects.all().order_by('name')

class ConnectionDetailView(LoginRequiredMixin, DetailView):
    """
    View for connection details
    """
    model = DatabaseConnection
    template_name = 'datasources/connections/detail.html'
    context_object_name = 'connection'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get data sources using this connection
        context['data_sources'] = self.object.data_sources.all()
        
        return context

class ConnectionCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new database connection
    """
    model = DatabaseConnection
    form_class = DatabaseConnectionForm
    template_name = 'datasources/connections/form.html'
    
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
            
            messages.success(self.request, _('Database connection created successfully.'))
            
            # Check if we need to return to a data source
            if self.request.GET.get('return_to') == 'datasource':
                datasource_id = self.request.GET.get('datasource_id')
                if datasource_id:
                    try:
                        datasource = DataSource.objects.get(id=datasource_id)
                        # Create database settings for the datasource
                        db_settings = DatabaseDataSource(
                            datasource=datasource,
                            connection=connection,
                            query_timeout=connection.query_timeout,
                            max_rows=connection.max_rows
                        )
                        db_settings.save()
                        
                        return redirect('datasources:database_detail', pk=datasource_id)
                    except DataSource.DoesNotExist:
                        pass
            
            # Otherwise go to connection detail
            return redirect('datasources:connection_detail', pk=connection.pk)

class ConnectionUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating a database connection
    """
    model = DatabaseConnection
    form_class = DatabaseConnectionForm
    template_name = 'datasources/connections/form.html'
    
    def form_valid(self, form):
        with transaction.atomic():
            # Save the connection
            connection = form.save(commit=False)
            connection.modified_by = self.request.user
            connection.save()
            
            messages.success(self.request, _('Database connection updated successfully.'))
            
            # Test connection if requested
            if 'test_connection' in self.request.POST:
                return redirect('datasources:connection_test', pk=connection.pk)
            
            return redirect('datasources:connection_detail', pk=connection.pk)

class ConnectionDeleteView(LoginRequiredMixin, DeleteView):
    """
    View for deleting a database connection
    """
    model = DatabaseConnection
    template_name = 'datasources/connections/confirm_delete.html'
    success_url = reverse_lazy('datasources:connections')
    
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
            return redirect('datasources:connection_detail', pk=connection.pk)
        
        messages.success(request, _('Database connection deleted successfully.'))
        return super().delete(request, *args, **kwargs)

class ConnectionTestView(LoginRequiredMixin, View):
    """
    View for testing a database connection
    """
    def get(self, request, pk):
        connection = get_object_or_404(DatabaseConnection, pk=pk)
        
        try:
            # Test the connection
            success, message = connection.test_connection()
            
            if success:
                messages.success(request, _('Connection test successful: {}').format(message))
            else:
                messages.error(request, _('Connection test failed: {}').format(message))
        
        except Exception as e:
            messages.error(request, _('Error testing connection: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:connection_detail', pk=pk)

class ConnectionTablesView(LoginRequiredMixin, View):
    """
    View for listing database tables
    """
    def get(self, request, pk):
        connection = get_object_or_404(DatabaseConnection, pk=pk)
        
        try:
            # Get tables using the connection info
            connector = get_connector(connection.get_connection_info())
            tables = connector.get_table_names()
            return JsonResponse({'tables': tables})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

class TestOracleConnectionView(LoginRequiredMixin, View):
    """
    View for testing Oracle connections specifically
    """
    def get(self, request, pk):
        connection = get_object_or_404(DatabaseConnection, pk=pk)
        
        # Only for Oracle connections
        if connection.db_type != 'oracle':
            messages.error(request, _('This is not an Oracle connection.'))
            return redirect('datasources:connection_detail', pk=pk)
        
        try:
            # Test the connection
            connection_info = connection.get_connection_info()
            from core.database.oracle_connector import OracleConnector
            connector = OracleConnector(connection_info)
            success, message = connector.test_connection()
            
            if success:
                # Get table count as an additional test
                tables = connector.get_table_names()
                table_count = len(tables)
                messages.success(request, _(
                    'Oracle connection test successful: {message}. Found {count} tables.'
                ).format(message=message, count=table_count))
            else:
                messages.error(request, _('Oracle connection test failed: {message}').format(message=message))
        
        except Exception as e:
            messages.error(request, _('Error testing Oracle connection: {error}').format(error=str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:connection_detail', pk=pk)