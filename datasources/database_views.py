"""
Views for database data sources.

This module implements views for managing database data sources,
executing queries, and viewing results.
"""

import logging
import json
from typing import Dict, Any, List

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, FormView
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.db import transaction

from .models import DataSource, DataSourceField, DataSourceSync
from .database_models import DatabaseDataSource, DatabaseQuery, DatabaseQueryExecution, DatabaseConnection
from .forms import DatabaseDataSourceForm, DatabaseSettingsForm, DatabaseQueryForm, DatabaseConnectionForm, DataSourceBaseForm
from .connectors.database_connector import DatabaseConnector

logger = logging.getLogger(__name__)

class DatabaseDataSourceCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new database data source
    """
    template_name = 'datasources/database/create.html'
    form_class = DatabaseDataSourceForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get available connections
        context['connections'] = DatabaseConnection.objects.all().order_by('name')
        return context
    
    def form_valid(self, form):
        with transaction.atomic():
            # Create the base DataSource
            datasource = DataSource(
                name=self.request.POST.get('name', ''),
                description=self.request.POST.get('description', ''),
                type='database',
                status=self.request.POST.get('status', 'active'),
                created_by=self.request.user,
                modified_by=self.request.user
            )
            datasource.save()
            
            # Handle connection
            create_new = form.cleaned_data.get('create_new_connection', False)
            
            if create_new:
                # Redirect to connection creation page with return URL
                messages.info(self.request, _('Please create a new database connection first.'))
                return redirect(reverse('datasources:connection_create') + f'?return_to=datasource&datasource_id={datasource.id}')
                
            else:
                # Save the database settings with existing connection
                db_settings = form.save(commit=False)
                db_settings.datasource = datasource
                db_settings.save()
                
                messages.success(self.request, _('Database data source created successfully.'))
                return redirect('datasources:database_detail', pk=datasource.pk)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)


class DatabaseDataSourceUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating a database data source
    """
    model = DataSource
    template_name = 'datasources/database/update.html'
    form_class = DatabaseDataSourceForm
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.type != 'database':
            messages.error(self.request, _('This is not a database data source.'))
            return redirect('datasources:index')
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['settings_form'] = DatabaseSettingsForm(
                self.request.POST, 
                instance=self.object.database_settings
            )
        else:
            try:
                context['settings_form'] = DatabaseSettingsForm(instance=self.object.database_settings)
            except DatabaseDataSource.DoesNotExist:
                # Create settings if they don't exist
                context['settings_form'] = DatabaseSettingsForm(initial={'datasource': self.object})
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
                
                # Update or create the database settings
                db_settings = settings_form.save(commit=False)
                db_settings.datasource = datasource
                db_settings.save()
                
                messages.success(self.request, _('Database data source updated successfully.'))
                
                # Test connection if requested
                if 'test_connection' in self.request.POST:
                    return redirect('datasources:database_test_connection', pk=datasource.pk)
                
                return redirect('datasources:database_detail', pk=datasource.pk)
        else:
            return self.form_invalid(form)


class DatabaseDataSourceDetailView(LoginRequiredMixin, DetailView):
    """
    View for database data source details
    """
    model = DataSource
    template_name = 'datasources/database/detail.html'
    context_object_name = 'datasource'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.type != 'database':
            messages.error(self.request, _('This is not a database data source.'))
            return redirect('datasources:index')
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get database settings
        try:
            context['db_settings'] = self.object.database_settings
        except DatabaseDataSource.DoesNotExist:
            context['db_settings'] = None
        
        # Get saved queries
        if context['db_settings']:
            context['queries'] = DatabaseQuery.objects.filter(
                database_datasource=context['db_settings']
            ).order_by('name')
        else:
            context['queries'] = []
        
        # Get field information
        context['fields'] = self.object.fields.all().order_by('name')
        
        # Get recent syncs
        context['recent_syncs'] = self.object.syncs.all().order_by('-start_time')[:5]
        
        # Get recent query executions
        if context['db_settings']:
            context['recent_executions'] = DatabaseQueryExecution.objects.filter(
                database_datasource=context['db_settings']
            ).order_by('-start_time')[:10]
        else:
            context['recent_executions'] = []
        
        # Form for new query
        context['query_form'] = DatabaseQueryForm()
        
        return context


class DatabaseTestConnectionView(LoginRequiredMixin, View):
    """
    View for testing database connection
    """
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        try:
            # Get or create database settings
            try:
                db_settings = datasource.database_settings
            except DatabaseDataSource.DoesNotExist:
                messages.error(request, _('Database settings not found for this data source.'))
                return redirect('datasources:database_detail', pk=pk)
            
            # Create connector and test connection
            connector = DatabaseConnector(datasource)
            success, message = connector.test_connection()
            
            if success:
                messages.success(request, _('Connection test successful: {}').format(message))
            else:
                messages.error(request, _('Connection test failed: {}').format(message))
            
        except Exception as e:
            messages.error(request, _('Error testing connection: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:database_detail', pk=pk)


class DatabaseTableListView(LoginRequiredMixin, View):
    """
    View for listing database tables
    """
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            return JsonResponse({'error': 'Not a database data source'}, status=400)
        
        try:
            connector = DatabaseConnector(datasource)
            tables = connector.get_tables()
            return JsonResponse({'tables': tables})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class DatabaseTableSchemaView(LoginRequiredMixin, View):
    """
    View for getting database table schema
    """
    def get(self, request, pk, table_name):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            return JsonResponse({'error': 'Not a database data source'}, status=400)
        
        try:
            connector = DatabaseConnector(datasource)
            schema = connector.get_table_schema(table_name)
            return JsonResponse({'schema': schema})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class DatabaseQueryCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new database query
    """
    model = DatabaseQuery
    form_class = DatabaseQueryForm
    template_name = 'datasources/database/query_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = get_object_or_404(DataSource, pk=self.kwargs['datasource_pk'])
        
        try:
            context['db_settings'] = context['datasource'].database_settings
        except DatabaseDataSource.DoesNotExist:
            messages.error(self.request, _('Database settings not found for this data source.'))
            return redirect('datasources:database_detail', pk=self.kwargs['datasource_pk'])
        
        return context
    
    def form_valid(self, form):
        datasource = get_object_or_404(DataSource, pk=self.kwargs['datasource_pk'])
        
        try:
            db_settings = datasource.database_settings
        except DatabaseDataSource.DoesNotExist:
            messages.error(self.request, _('Database settings not found for this data source.'))
            return redirect('datasources:database_detail', pk=self.kwargs['datasource_pk'])
        
        form.instance.database_datasource = db_settings
        
        messages.success(self.request, _('Query created successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('datasources:database_detail', kwargs={'pk': self.kwargs['datasource_pk']})


class DatabaseQueryUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating a database query
    """
    model = DatabaseQuery
    form_class = DatabaseQueryForm
    template_name = 'datasources/database/query_form.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = self.object.database_datasource.datasource
        context['db_settings'] = self.object.database_datasource
        return context
    
    def get_success_url(self):
        return reverse('datasources:database_detail', kwargs={'pk': self.object.database_datasource.datasource.pk})


class DatabaseQueryDeleteView(LoginRequiredMixin, DeleteView):
    """
    View for deleting a database query
    """
    model = DatabaseQuery
    template_name = 'datasources/database/query_confirm_delete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = self.object.database_datasource.datasource
        return context
    
    def get_success_url(self):
        return reverse('datasources:database_detail', kwargs={'pk': self.object.database_datasource.datasource.pk})


class DatabaseQueryExecuteView(LoginRequiredMixin, View):
    """
    View for executing a database query
    """
    def post(self, request, pk):
        query = get_object_or_404(DatabaseQuery, pk=pk)
        datasource = query.database_datasource.datasource
        
        try:
            # Parse parameters if provided
            params = {}
            if request.POST.get('parameters'):
                try:
                    params = json.loads(request.POST.get('parameters'))
                except json.JSONDecodeError:
                    messages.error(request, _('Invalid JSON parameters.'))
                    return redirect('datasources:database_detail', pk=datasource.pk)
            
            # Create connector and execute query
            connector = DatabaseConnector(datasource)
            success, results, execution = connector.execute_query(
                query.query_text,
                params or query.parameters
            )
            
            if success:
                messages.success(request, _('Query executed successfully.'))
                
                # Redirect to execution detail page if available
                if execution:
                    return redirect('datasources:database_execution_detail', pk=execution.pk)
            else:
                messages.error(request, _('Query execution failed.'))
            
        except Exception as e:
            messages.error(request, _('Error executing query: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:database_detail', pk=datasource.pk)


class DatabaseQueryExecutionDetailView(LoginRequiredMixin, DetailView):
    """
    View for database query execution details
    """
    model = DatabaseQueryExecution
    template_name = 'datasources/database/execution_detail.html'
    context_object_name = 'execution'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = self.object.database_datasource.datasource
        return context


class DatabaseDataSourceSyncView(LoginRequiredMixin, View):
    """
    View to trigger a manual sync of a database data source
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        try:
            # Create connector and sync data
            connector = DatabaseConnector(datasource)
            sync = connector.sync_data(triggered_by=request.user)
            
            if sync.status == 'success':
                messages.success(request, _('Data sync completed successfully.'))
            else:
                messages.error(request, _('Data sync failed: {}').format(sync.error_message))
            
        except Exception as e:
            messages.error(request, _('Error syncing data: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:database_detail', pk=pk)


class DatabaseDetectFieldsView(LoginRequiredMixin, View):
    """
    View for auto-detecting fields from a database table or query
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        try:
            # Get parameters
            table_name = request.POST.get('table_name')
            query = request.POST.get('query')
            
            if not table_name and not query:
                messages.error(request, _('Either table name or query must be provided.'))
                return redirect('datasources:database_detail', pk=pk)
            
            # Create connector and detect fields
            connector = DatabaseConnector(datasource)
            fields = connector.detect_fields(table_name, query)
            
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
                _('Successfully detected {count} fields.').format(
                    count=len(fields)
                )
            )
        except Exception as e:
            messages.error(request, _('Error detecting fields: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:database_detail', pk=pk)


class DatabaseFieldsUpdateView(LoginRequiredMixin, View):
    """
    View for updating database fields
    """
    template_name = 'datasources/database/fields.html'
    
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        from .forms import DataSourceFieldFormSet
        formset = DataSourceFieldFormSet(instance=datasource)
        
        return render(request, self.template_name, {
            'datasource': datasource,
            'formset': formset
        })
    
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        from .forms import DataSourceFieldFormSet
        formset = DataSourceFieldFormSet(request.POST, instance=datasource)
        
        if formset.is_valid():
            formset.save()
            messages.success(request, _('Fields updated successfully.'))
            return redirect('datasources:database_detail', pk=pk)
        else:
            messages.error(request, _('Please correct the errors below.'))
            
        return render(request, self.template_name, {
            'datasource': datasource,
            'formset': formset
        })

class OracleHelperView(LoginRequiredMixin, View):
    """
    View to provide Oracle-specific query templates
    """
    def get(self, request):
        templates = {
            "table_list": """
SELECT OWNER, TABLE_NAME 
FROM ALL_TABLES 
WHERE OWNER = :schema
ORDER BY TABLE_NAME
            """,
            "column_list": """
SELECT 
    COLUMN_NAME, 
    DATA_TYPE,
    DATA_LENGTH,
    NULLABLE
FROM ALL_TAB_COLUMNS
WHERE OWNER = :schema
AND TABLE_NAME = :table_name
ORDER BY COLUMN_ID
            """,
            "user_info": """
SELECT 
    USERNAME, 
    CREATED,
    PROFILE,
    ACCOUNT_STATUS
FROM DBA_USERS
WHERE USERNAME LIKE :username_pattern
            """,
            "basic_selection": """
SELECT * FROM :table_name
WHERE ROWNUM <= 100
            """
        }
        
        template_name = request.GET.get('template', '')
        if template_name in templates:
            return JsonResponse({'query': templates[template_name]})
        else:
            return JsonResponse({'templates': list(templates.keys())})