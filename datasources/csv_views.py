# datasources/csv_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, View
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.db import transaction

from .models import DataSource, DataSourceField, DataSourceSync
from .csv_models import CSVDataSource, CSVFileUpload
from .forms import CSVDataSourceForm, CSVSettingsForm, CSVFileUploadForm, DataSourceFieldFormSet
from .connectors.csv_connector import CSVConnector
import csv

class CSVDataSourceCreateView(LoginRequiredMixin, CreateView):
    """
    View for creating a new CSV data source
    """
    template_name = 'datasources/csv/create.html'
    form_class = CSVDataSourceForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['settings_form'] = CSVSettingsForm(self.request.POST)
        else:
            context['settings_form'] = CSVSettingsForm()
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        settings_form = context['settings_form']
        
        if settings_form.is_valid():
            with transaction.atomic():
                # Save the base data source
                datasource = form.save(commit=False)
                datasource.type = 'csv'
                datasource.created_by = self.request.user
                datasource.modified_by = self.request.user
                datasource.save()
                
                # Save the CSV settings
                csv_settings = settings_form.save(commit=False)
                csv_settings.datasource = datasource
                csv_settings.save()
                
                messages.success(self.request, _('CSV data source created successfully.'))
                return redirect('datasources:csv_detail', pk=datasource.pk)
        else:
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, _('Please correct the errors below.'))
        return super().form_invalid(form)

class CSVDataSourceUpdateView(LoginRequiredMixin, UpdateView):
    """
    View for updating a CSV data source
    """
    model = DataSource
    template_name = 'datasources/csv/update.html'
    form_class = CSVDataSourceForm
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.type != 'csv':
            messages.error(self.request, _('This is not a CSV data source.'))
            return redirect('datasources:index')
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['settings_form'] = CSVSettingsForm(
                self.request.POST, 
                instance=self.object.csv_settings
            )
        else:
            try:
                context['settings_form'] = CSVSettingsForm(instance=self.object.csv_settings)
            except CSVDataSource.DoesNotExist:
                # Create settings if they don't exist
                context['settings_form'] = CSVSettingsForm(initial={'datasource': self.object})
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
                
                # Update or create the CSV settings
                csv_settings = settings_form.save(commit=False)
                csv_settings.datasource = datasource
                csv_settings.save()
                
                messages.success(self.request, _('CSV data source updated successfully.'))
                return redirect('datasources:csv_detail', pk=datasource.pk)
        else:
            return self.form_invalid(form)

class CSVDataSourceDetailView(LoginRequiredMixin, DetailView):
    """
    View for CSV data source details
    """
    model = DataSource
    template_name = 'datasources/csv/detail.html'
    context_object_name = 'datasource'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.type != 'csv':
            messages.error(self.request, _('This is not a CSV data source.'))
            return redirect('datasources:index')
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get CSV settings
        try:
            context['csv_settings'] = self.object.csv_settings
        except CSVDataSource.DoesNotExist:
            context['csv_settings'] = None
        
        # Get recent uploads
        if context['csv_settings']:
            context['uploads'] = CSVFileUpload.objects.filter(
                csv_datasource=context['csv_settings']
            ).order_by('-uploaded_at')[:5]
        else:
            context['uploads'] = []
        
        # Get field information
        context['fields'] = self.object.fields.all().order_by('name')
        
        # Get recent syncs
        context['recent_syncs'] = self.object.syncs.all().order_by('-start_time')[:5]
        
        # Upload form
        context['upload_form'] = CSVFileUploadForm()
        
        return context

class CSVFileUploadView(LoginRequiredMixin, View):
    """
    View for uploading a CSV file
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'csv':
            messages.error(request, _('This is not a CSV data source.'))
            return redirect('datasources:index')
        
        # Make sure we have CSV settings
        try:
            csv_settings = datasource.csv_settings
        except CSVDataSource.DoesNotExist:
            # Create default settings if they don't exist
            csv_settings = CSVDataSource.objects.create(datasource=datasource)
        
        form = CSVFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Process the upload
                connector = CSVConnector(datasource)
                upload = connector.process_upload(request.FILES['file'])
                
                messages.success(
                    request, 
                    _('File uploaded successfully. {count} rows detected.').format(
                        count=upload.row_count
                    )
                )
            except Exception as e:
                messages.error(request, _('Error uploading file: {error}').format(error=str(e)))
        else:
            messages.error(request, _('Invalid file upload.'))
        
        return redirect('datasources:csv_detail', pk=pk)

class CSVDataSourceSyncView(LoginRequiredMixin, View):
    """
    View to trigger a manual sync of a CSV data source
    with profile integration
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'csv':
            messages.error(request, _('This is not a CSV data source.'))
            return redirect('datasources:index')
        
        # Create a sync record
        sync = None
        
        try:
            # Create a sync record
            sync = DataSourceSync.objects.create(
                datasource=datasource,
                triggered_by=request.user,
                status='running'
            )
            
            # Get the CSV connector
            connector = CSVConnector(datasource)
            file_path = connector._get_file_path()
            
            # Set up profile integration service
            from users.services.profile_integration import ProfileIntegrationService
            profile_service = ProfileIntegrationService(datasource, sync)
            
            created_count = 0
            updated_count = 0
            record_ids = []
            
            # Process the CSV file - use a smaller transaction scope
            with open(file_path, 'r', encoding=connector.csv_settings.encoding) as f:
                reader = csv.reader(f, delimiter=connector.csv_settings.delimiter, quotechar=connector.csv_settings.quote_char)
                
                # Skip header if needed
                if connector.csv_settings.has_header:
                    next(reader, None)
                
                # Skip additional rows if configured
                skip_count = connector.csv_settings.skip_rows
                if skip_count and skip_count > 0:
                    for i in range(skip_count):
                        next(reader, None)
                
                # Process each row
                row_count = 0
                max_rows = connector.csv_settings.max_rows
                
                # Get fields for this data source
                fields = DataSourceField.objects.filter(datasource=datasource).order_by('id')
                field_list = list(fields)
                
                # Process each row
                for row in reader:
                    # Convert row to dictionary with field names
                    record_data = {}
                    for i, value in enumerate(row):
                        if i < len(field_list):
                            record_data[field_list[i].name] = value
                    
                    # Store record ID if available
                    if 'id' in record_data:
                        record_ids.append(record_data['id'])
                    
                    # Process the record through profile integration - in its own transaction
                    try:
                        person, created, changes = profile_service.process_record(record_data, record_data.get('id', ''))
                        
                        if created:
                            created_count += 1
                        elif changes > 0:
                            updated_count += 1
                    except Exception as row_error:
                        logger.error(f"Error processing row: {str(row_error)}")
                        # Continue with next row
                    
                    row_count += 1
                    if max_rows and row_count >= max_rows:
                        break
            
            # Handle cleanup of missing records - in its own transaction
            removed_count = 0
            if record_ids:
                try:
                    removed_count = profile_service.remove_missing_attributes(record_ids)
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up missing attributes: {str(cleanup_error)}")
            
            # Update sync stats
            sync.records_processed = row_count
            sync.records_created = created_count  
            sync.records_updated = updated_count
            sync.complete(status='success')
            
            messages.success(
                request, 
                _('Data source sync completed successfully. {processed} records processed, {created} profiles created, {updated} profiles updated.').format(
                    processed=row_count,
                    created=created_count,
                    updated=updated_count
                )
            )
            
        except Exception as e:
            if sync:
                sync.complete(status='error', error_message=str(e))
            
            messages.error(request, _('Error syncing data: {error}').format(error=str(e)))
        
        return redirect('datasources:csv_detail', pk=pk)

class CSVFieldsUpdateView(LoginRequiredMixin, View):
    """
    View for updating CSV fields
    """
    template_name = 'datasources/csv/fields.html'
    
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'csv':
            messages.error(request, _('This is not a CSV data source.'))
            return redirect('datasources:index')
        
        formset = DataSourceFieldFormSet(instance=datasource)
        
        return render(request, self.template_name, {
            'datasource': datasource,
            'formset': formset
        })
    
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'csv':
            messages.error(request, _('This is not a CSV data source.'))
            return redirect('datasources:index')
        
        formset = DataSourceFieldFormSet(request.POST, instance=datasource)
        
        if formset.is_valid():
            formset.save()
            messages.success(request, _('Fields updated successfully.'))
            return redirect('datasources:csv_detail', pk=pk)
        else:
            messages.error(request, _('Please correct the errors below.'))
            
        return render(request, self.template_name, {
            'datasource': datasource,
            'formset': formset
        })

class CSVDetectFieldsView(LoginRequiredMixin, View):
    """
    View for auto-detecting fields from a CSV file
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        if datasource.type != 'csv':
            messages.error(request, _('This is not a CSV data source.'))
            return redirect('datasources:index')
        
        try:
            connector = CSVConnector(datasource)
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
                _('Successfully detected {count} fields from CSV file.').format(
                    count=len(fields)
                )
            )
        except Exception as e:
            messages.error(request, _('Error detecting fields: {error}').format(error=str(e)))
        
        return redirect('datasources:csv_detail', pk=pk)