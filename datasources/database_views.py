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
from .database_models import DatabaseDataSource, DatabaseQuery, DatabaseQueryExecution, DatabaseConnection, DatabaseQuery  
from .forms import DatabaseDataSourceForm, DatabaseSettingsForm, DatabaseQueryForm, DatabaseConnectionForm, DataSourceBaseForm
from .connectors.database_connector import DatabaseConnector

logger = logging.getLogger(__name__)

class DatabaseDataSourceCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new database query data source
    """
    template_name = 'datasources/database/create.html'
    form_class = DatabaseDataSourceForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get available connections
        context['connections'] = DatabaseConnection.objects.all().order_by('name')
        
        # Add query form
        if self.request.POST:
            context['query_form'] = DatabaseQueryForm(self.request.POST)
        else:
            context['query_form'] = DatabaseQueryForm()
            
        # Try to get available tables for reference if connection_id is in GET
        connection_id = self.request.GET.get('connection_id')
        if connection_id:
            try:
                connection = DatabaseConnection.objects.get(id=connection_id)
                from core.database import get_connector
                connector = get_connector(connection.get_connection_info())
                context['tables'] = connector.get_table_names()
            except Exception as e:
                context['connection_error'] = str(e)
                
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        query_form = context['query_form']
        
        if query_form.is_valid():
            with transaction.atomic():
                # Create the base DataSource
                datasource = DataSource(
                    name=form.cleaned_data['name'],
                    description=form.cleaned_data['description'],
                    type='database',
                    status=form.cleaned_data.get('status', 'active'),
                    created_by=self.request.user,
                    modified_by=self.request.user
                )
                datasource.save()
                
                # Create the database settings with selected connection
                db_settings = DatabaseDataSource(
                    datasource=datasource,
                    connection=form.cleaned_data['connection'],
                    query_timeout=form.cleaned_data.get('query_timeout', 60),
                    max_rows=form.cleaned_data.get('max_rows', 10000)
                )
                db_settings.save()
                
                # Create the query
                query = query_form.save(commit=False)
                query.database_datasource = db_settings
                query.created_by = self.request.user
                query.modified_by = self.request.user
                
                # Set as default query
                query.is_default = True
                
                # Auto-detect query type if not specified
                if not query.query_type or query.query_type == 'auto':
                    from core.database.utils import extract_query_type
                    query.query_type = extract_query_type(query.query_text)
                
                query.save()
                
                messages.success(self.request, _('Database query data source created successfully.'))
                return redirect('datasources:database_detail', pk=datasource.pk)
        else:
            return self.form_invalid(form)
    
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
        
        self._test_connection(request, datasource)
        return redirect('datasources:database_detail', pk=pk)
    
    def post(self, request, pk):
        # Add this method to handle POST requests
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        self._test_connection(request, datasource)
        return redirect('datasources:database_detail', pk=pk)
    
    def _test_connection(self, request, datasource):
        try:
            # Get or create database settings
            try:
                db_settings = datasource.database_settings
            except DatabaseDataSource.DoesNotExist:
                messages.error(request, _('Database settings not found for this data source.'))
                return
            
            # Create connector and test connection
            connector = DatabaseConnector(datasource)
            success, message = connector.test_connection()
            
            if success:
                messages.success(request, _('Connection test successful: {}').format(message))
            else:
                messages.error(request, _('Connection test failed: {}').format(message))
            
        except Exception as e:
            messages.error(request, _('Error testing connection: {}').format(str(e)))


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
            
            # Add available tables for reference
            try:
                connector = DatabaseConnector(context['datasource'])
                context['tables'] = connector.get_tables()
            except Exception as e:
                context['connection_error'] = str(e)
                
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
        form.instance.created_by = self.request.user 
        form.instance.modified_by = self.request.user
        
        # Determine query type if not specified
        if not form.instance.query_type or form.instance.query_type == 'auto':
            from core.database.utils import extract_query_type
            form.instance.query_type = extract_query_type(form.instance.query_text)
        
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
        
        # Print debug info to help diagnose the issue
        print(f"Query text in context: {self.object.query_text[:100]}...")
        
        # Add available tables for reference
        try:
            from core.database import get_connector
            connector = get_connector(self.object.database_datasource.get_connection_info())
            context['tables'] = connector.get_table_names() if connector else []
        except Exception as e:
            context['connection_error'] = str(e)
            
        return context
    
    def get_initial(self):
        """Get initial data to use for the form"""
        initial = super().get_initial()
        # Ensure query_text is included in initial data
        initial['query_text'] = self.object.query_text
        initial['parameters'] = self.object.parameters
        return initial
    
    def form_valid(self, form):
        # Update the modified_by field
        form.instance.modified_by = self.request.user
        
        # Auto-detect query type if changed to 'auto'
        if form.instance.query_type == 'auto':
            from core.database.utils import extract_query_type
            form.instance.query_type = extract_query_type(form.instance.query_text)
            
        messages.success(self.request, _('Query updated successfully.'))
        return super().form_valid(form)
    
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
            
            # Use query default parameters if none provided
            if not params and query.parameters:
                params = query.parameters
            
            # Create connector and execute query
            connector = DatabaseConnector(datasource)
            
            # Debug connection info
            print(f"Executing query for datasource: {datasource.name}")
            print(f"Query text: {query.query_text[:100]}...")
            
            # Check for Oracle database
            is_oracle = False
            try:
                is_oracle = (connector.db_settings.connection.db_type.lower() == 'oracle')
                print(f"Detected database type: {'Oracle' if is_oracle else connector.db_settings.connection.db_type}")
            except Exception as e:
                print(f"Error detecting database type: {str(e)}")
            
            # Use Oracle-specific handling
            if is_oracle:
                print("Using Oracle-specific query execution")
                success, results, execution = connector.execute_oracle_query(
                    query.query_text,
                    params
                )
            else:
                # Normal execution for other database types
                success, results, execution = connector.execute_query(
                    query.query_text,
                    params
                )
            
            if success:
                messages.success(request, _('Query executed successfully.'))
                
                # Redirect to execution detail page if available
                if execution:
                    return redirect('datasources:database_execution_detail', pk=execution.pk)
            else:
                error_msg = _('Query execution failed.')
                if isinstance(execution, DatabaseQueryExecution) and execution.error_message:
                    error_msg = f"{error_msg} {execution.error_message}"
                messages.error(request, error_msg)
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error executing query: {str(e)}")
            print(error_details)
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

"""
Views for detecting and managing database fields from queries.
"""

class DatabaseFieldDetectionView(LoginRequiredMixin, View):
    """
    View for detecting fields from database queries
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        try:
            # Get query ID from form
            query_id = request.POST.get('query_id')
            
            if query_id:
                # Use existing query
                query = get_object_or_404(DatabaseQuery, pk=query_id)
                query_text = query.query_text
                params = query.parameters
            else:
                # Use ad-hoc query from form
                query_text = request.POST.get('query_text')
                params_text = request.POST.get('parameters', '{}')
                
                if not query_text:
                    messages.error(request, _('No query provided for field detection.'))
                    return redirect('datasources:database_detail', pk=pk)
                
                # Parse parameters
                try:
                    params = json.loads(params_text) if params_text else {}
                except json.JSONDecodeError:
                    messages.error(request, _('Invalid JSON parameters.'))
                    return redirect('datasources:database_detail', pk=pk)
            
            # Create connector and detect fields
            connector = DatabaseConnector(datasource)
            
            # Option to replace existing fields
            replace_fields = request.POST.get('replace_fields') == 'on'
            
            # Detect and create fields
            if replace_fields:
                # Delete existing fields first
                datasource.fields.all().delete()
                messages.success(request, _('Existing fields removed.'))
            
            # Detect fields and create them
            fields = connector.create_fields_from_query(datasource, query_text, params)
            
            messages.success(
                request,
                _('Successfully detected {count} fields from database query.').format(
                    count=len(fields)
                )
            )
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error detecting fields: {str(e)}")
            print(error_details)
            messages.error(request, _('Error detecting fields: {}').format(str(e)))
        
        return redirect('datasources:database_detail', pk=pk)
    

class DatabaseFieldManagementView(LoginRequiredMixin, View):
    """
    View for managing fields for database data sources
    """
    template_name = 'datasources/database/fields.html'
    
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        # Get available queries for this data source
        try:
            db_settings = datasource.database_settings
            queries = DatabaseQuery.objects.filter(
                database_datasource=db_settings,
                is_enabled=True
            ).order_by('name')
        except Exception:
            queries = []
        
        formset = DataSourceFieldFormSet(instance=datasource)
        
        return render(request, self.template_name, {
            'datasource': datasource,
            'formset': formset,
            'queries': queries
        })
    
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        formset = DataSourceFieldFormSet(request.POST, instance=datasource)
        
        if formset.is_valid():
            formset.save()
            messages.success(request, _('Fields updated successfully.'))
            return redirect('datasources:database_detail', pk=pk)
        else:
            messages.error(request, _('Please correct the errors below.'))
            
        # Get available queries for this data source for re-rendering the form
        try:
            db_settings = datasource.database_settings
            queries = DatabaseQuery.objects.filter(
                database_datasource=db_settings,
                is_enabled=True
            ).order_by('name')
        except Exception:
            queries = []
            
        return render(request, self.template_name, {
            'datasource': datasource,
            'formset': formset,
            'queries': queries
        })

class DatabaseDataSourceSyncView(LoginRequiredMixin, View):
    """
    View to trigger a manual sync of a database data source with profile integration
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'database':
            messages.error(request, _('This is not a database data source.'))
            return redirect('datasources:index')
        
        try:
            # Create connector and sync data with profile integration
            connector = DatabaseConnector(datasource)
            sync = connector.sync_data(triggered_by=request.user)
            
            if sync.status == 'success':
                messages.success(
                    request, 
                    _('Data sync completed successfully. {processed} records processed, {created} profiles created, {updated} profiles updated.').format(
                        processed=sync.records_processed,
                        created=sync.records_created,
                        updated=sync.records_updated
                    )
                )
            else:
                messages.error(request, _('Data sync failed: {}').format(sync.error_message))
            
        except Exception as e:
            messages.error(request, _('Error syncing data: {}').format(str(e)))
        
        # Redirect back to detail page
        return redirect('datasources:database_detail', pk=pk)