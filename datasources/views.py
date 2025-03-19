# datasources/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, TemplateView
from django.utils.translation import gettext_lazy as _

from .models import DataSource, DataSourceField, DataSourceSync

# DataSource views
class DataSourceListView(LoginRequiredMixin, ListView):
    model = DataSource
    template_name = 'datasources/index.html'
    context_object_name = 'datasources'
    
    def get_queryset(self):
        return DataSource.objects.all().order_by('name')


class DataSourceDetailView(LoginRequiredMixin, DetailView):
    model = DataSource
    template_name = 'datasources/detail.html'
    context_object_name = 'datasource'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = self.object.fields.all().order_by('name')
        context['recent_syncs'] = self.object.syncs.all().order_by('-start_time')[:5]
        return context


class DataSourceCreateView(LoginRequiredMixin, CreateView):
    model = DataSource
    template_name = 'datasources/form.html'
    fields = ['name', 'description', 'type', 'connection_string', 'credentials']
    success_url = reverse_lazy('datasources:index')
    
    def get(self, request, *args, **kwargs):
        # If type is not specified in the URL, show the type selection page
        if 'type' not in request.GET:
            return redirect('datasources:select_type')
        return super().get(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Data source created successfully.'))
        return super().form_valid(form)


class DataSourceUpdateView(LoginRequiredMixin, UpdateView):
    model = DataSource
    template_name = 'datasources/form.html'
    fields = ['name', 'description', 'type', 'connection_string', 'credentials', 'status']
    
    def get_success_url(self):
        return reverse_lazy('datasources:detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        form.instance.modified_by = self.request.user
        messages.success(self.request, _('Data source updated successfully.'))
        return super().form_valid(form)


class DataSourceDeleteView(LoginRequiredMixin, DeleteView):
    model = DataSource
    template_name = 'datasources/confirm_delete.html'
    success_url = reverse_lazy('datasources:index')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Count associated data to show what will be deleted
        datasource = self.get_object()
        
        # Count attributes and people affected
        from users.profile_integration import AttributeSource
        attribute_count = AttributeSource.objects.filter(
            datasource=datasource,
            is_current=True
        ).count()
        
        person_count = AttributeSource.objects.filter(
            datasource=datasource,
            is_current=True
        ).values('person').distinct().count()
        
        context.update({
            'attribute_count': attribute_count,
            'person_count': person_count,
        })
        
        return context
    
    def delete(self, request, *args, **kwargs):
        datasource = self.get_object()
        
        # Log what's being deleted
        logger.info(f"Deleting data source {datasource.name} (ID: {datasource.id})")
        
        # Get counts before deletion for the message
        from users.profile_integration import AttributeSource
        attribute_count = AttributeSource.objects.filter(
            datasource=datasource,
            is_current=True
        ).count()
        
        # Trigger data cleanup before deletion
        try:
            # Import signal handler and run it manually
            from users.profile_integration import handle_datasource_deletion
            handle_datasource_deletion(sender=DataSource, instance=datasource)
            logger.info(f"Cleaned up {attribute_count} attributes from data source {datasource.name}")
        except Exception as e:
            logger.error(f"Error cleaning up data source data: {str(e)}")
        
        # Now delete the data source
        result = super().delete(request, *args, **kwargs)
        
        # Add more detailed message
        messages.success(
            request, 
            _(f'Data source "{datasource.name}" deleted successfully. {attribute_count} attributes were removed.')
        )
        
        return result


class DataSourceSyncView(LoginRequiredMixin, View):
    """View to trigger a manual sync of a data source"""
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        # Here you would actually trigger the sync process
        # For now, we'll just create a sync record
        sync = DataSourceSync.objects.create(
            datasource=datasource,
            triggered_by=request.user,
            status='running'
        )
        
        messages.info(request, _('Data source sync initiated.'))
        return redirect('datasources:detail', pk=pk)


class DataSourceSyncDetailView(LoginRequiredMixin, DetailView):
    model = DataSourceSync
    template_name = 'datasources/sync_detail.html'
    context_object_name = 'sync'


# DataSourceField views
class DataSourceFieldListView(LoginRequiredMixin, ListView):
    template_name = 'datasources/fields.html'
    context_object_name = 'fields'
    
    def get_queryset(self):
        self.datasource = get_object_or_404(DataSource, pk=self.kwargs['pk'])
        return self.datasource.fields.all().order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = self.datasource
        return context


class DataSourceFieldCreateView(LoginRequiredMixin, CreateView):
    model = DataSourceField
    template_name = 'datasources/field_form.html'
    fields = ['name', 'display_name', 'field_type', 'is_key', 'is_nullable', 'sample_data']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = get_object_or_404(DataSource, pk=self.kwargs['datasource_pk'])
        return context
    
    def form_valid(self, form):
        form.instance.datasource = get_object_or_404(DataSource, pk=self.kwargs['datasource_pk'])
        messages.success(self.request, _('Field created successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('datasources:fields', kwargs={'pk': self.kwargs['datasource_pk']})


class DataSourceFieldUpdateView(LoginRequiredMixin, UpdateView):
    model = DataSourceField
    template_name = 'datasources/field_form.html'
    fields = ['name', 'display_name', 'field_type', 'is_key', 'is_nullable', 'sample_data']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = get_object_or_404(DataSource, pk=self.kwargs['datasource_pk'])
        return context
    
    def get_success_url(self):
        return reverse_lazy('datasources:fields', kwargs={'pk': self.kwargs['datasource_pk']})


class DataSourceFieldDeleteView(LoginRequiredMixin, DeleteView):
    model = DataSourceField
    template_name = 'datasources/field_confirm_delete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = get_object_or_404(DataSource, pk=self.kwargs['datasource_pk'])
        return context
    
    def get_success_url(self):
        return reverse_lazy('datasources:fields', kwargs={'pk': self.kwargs['datasource_pk']})

class DataSourceTypeSelectView(LoginRequiredMixin, TemplateView):
    """
    View for selecting the type of data source to create
    """
    template_name = 'datasources/select_type.html'