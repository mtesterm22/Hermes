# datasources/profile_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View, FormView
from django.utils.translation import gettext_lazy as _
from django.db import transaction

from .models import DataSource, DataSourceField
from users.profile_integration import ProfileFieldMapping, IdentityResolutionConfig


class ProfileMappingView(LoginRequiredMixin, View):
    """
    View for managing profile mapping configuration
    """
    template_name = 'datasources/csv/profile_mapping.html'
    
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        # Get or create identity resolution config
        id_config, created = IdentityResolutionConfig.objects.get_or_create(
            datasource=datasource,
            defaults={
                'is_enabled': True,
                'create_missing_profiles': False,
                'matching_method': 'exact'
            }
        )
        
        # Get field mappings
        mappings = ProfileFieldMapping.objects.filter(
            datasource=datasource
        ).select_related('source_field').order_by('-priority', 'profile_attribute')
        
        context = {
            'datasource': datasource,
            'id_config': id_config,
            'mappings': mappings
        }
        
        return render(request, self.template_name, context)


class SaveIdentityConfigView(LoginRequiredMixin, View):
    """
    View for saving identity resolution configuration
    """
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        
        # Get or create identity resolution config
        id_config, created = IdentityResolutionConfig.objects.get_or_create(
            datasource=datasource
        )
        
        # Update config from form data
        id_config.is_enabled = 'is_enabled' in request.POST
        id_config.create_missing_profiles = 'create_missing_profiles' in request.POST
        id_config.matching_method = request.POST.get('matching_method', 'exact')
        
        if id_config.matching_method == 'fuzzy':
            try:
                threshold = float(request.POST.get('match_confidence_threshold', '0.9'))
                id_config.match_confidence_threshold = min(1.0, max(0.0, threshold))
            except (ValueError, TypeError):
                id_config.match_confidence_threshold = 0.9
        
        if id_config.matching_method == 'custom':
            id_config.custom_matcher = request.POST.get('custom_matcher', '')
        
        id_config.save()
        
        messages.success(request, _('Identity resolution configuration saved successfully.'))
        return redirect('datasources:profile_mapping', pk=pk)


class CreateFieldMappingView(LoginRequiredMixin, View):
    """
    View for creating a new field mapping
    """
    template_name = 'datasources/csv/mapping_form.html'
    
    def get(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        fields = DataSourceField.objects.filter(datasource=datasource).order_by('name')
        
        if not fields.exists():
            messages.warning(request, _('No fields available for mapping. Please add fields to the data source first.'))
            return redirect('datasources:profile_mapping', pk=pk)
        
        context = {
            'datasource': datasource,
            'fields': fields,
            'mapping': None,
            'form': None
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        datasource = get_object_or_404(DataSource, pk=pk)
        fields = DataSourceField.objects.filter(datasource=datasource).order_by('name')
        
        try:
            # Get selected source field
            source_field_id = request.POST.get('source_field')
            source_field = get_object_or_404(DataSourceField, pk=source_field_id, datasource=datasource)
            
            # Get profile attribute
            profile_attribute = request.POST.get('profile_attribute', '').strip()
            if not profile_attribute:
                raise ValueError(_('Profile attribute is required.'))
            
            # Check for existing mapping with the same source field and profile attribute
            if ProfileFieldMapping.objects.filter(
                datasource=datasource,
                source_field=source_field,
                profile_attribute=profile_attribute
            ).exists():
                raise ValueError(_('A mapping for this field and attribute already exists.'))
            
            # Create new mapping
            mapping = ProfileFieldMapping(
                datasource=datasource,
                source_field=source_field,
                profile_attribute=profile_attribute,
                mapping_type=request.POST.get('mapping_type', 'direct'),
                is_key_field='is_key_field' in request.POST,
                is_multivalued='is_multivalued' in request.POST,
                is_enabled='is_enabled' in request.POST,
                priority=int(request.POST.get('priority', 100)),
                transformation_logic=request.POST.get('transformation_logic', '')
            )
            mapping.save()
            
            messages.success(request, _('Field mapping created successfully.'))
            return redirect('datasources:profile_mapping', pk=pk)
            
        except (ValueError, TypeError) as e:
            messages.error(request, str(e))
            
            context = {
                'datasource': datasource,
                'fields': fields,
                'mapping': None,
                'form': request.POST
            }
            
            return render(request, self.template_name, context)


class EditFieldMappingView(LoginRequiredMixin, View):
    """
    View for editing an existing field mapping
    """
    template_name = 'datasources/csv/mapping_form.html'
    
    def get(self, request, datasource_pk, mapping_pk):
        datasource = get_object_or_404(DataSource, pk=datasource_pk)
        mapping = get_object_or_404(ProfileFieldMapping, pk=mapping_pk, datasource=datasource)
        fields = DataSourceField.objects.filter(datasource=datasource).order_by('name')
        
        context = {
            'datasource': datasource,
            'fields': fields,
            'mapping': mapping,
            'form': None
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, datasource_pk, mapping_pk):
        datasource = get_object_or_404(DataSource, pk=datasource_pk)
        mapping = get_object_or_404(ProfileFieldMapping, pk=mapping_pk, datasource=datasource)
        fields = DataSourceField.objects.filter(datasource=datasource).order_by('name')
        
        try:
            # Get selected source field
            source_field_id = request.POST.get('source_field')
            source_field = get_object_or_404(DataSourceField, pk=source_field_id, datasource=datasource)
            
            # Get profile attribute
            profile_attribute = request.POST.get('profile_attribute', '').strip()
            if not profile_attribute:
                raise ValueError(_('Profile attribute is required.'))
            
            # Check for existing mapping with the same source field and profile attribute
            if (ProfileFieldMapping.objects.filter(
                datasource=datasource,
                source_field=source_field,
                profile_attribute=profile_attribute
            ).exclude(pk=mapping_pk).exists()):
                raise ValueError(_('A mapping for this field and attribute already exists.'))
            
            # Update mapping
            mapping.source_field = source_field
            mapping.profile_attribute = profile_attribute
            mapping.mapping_type = request.POST.get('mapping_type', 'direct')
            mapping.is_key_field = 'is_key_field' in request.POST
            mapping.is_multivalued = 'is_multivalued' in request.POST
            mapping.is_enabled = 'is_enabled' in request.POST
            mapping.priority = int(request.POST.get('priority', 100))
            mapping.transformation_logic = request.POST.get('transformation_logic', '')
            mapping.save()
            
            messages.success(request, _('Field mapping updated successfully.'))
            return redirect('datasources:profile_mapping', pk=datasource_pk)
            
        except (ValueError, TypeError) as e:
            messages.error(request, str(e))
            
            context = {
                'datasource': datasource,
                'fields': fields,
                'mapping': mapping,
                'form': request.POST
            }
            
            return render(request, self.template_name, context)


class DeleteFieldMappingView(LoginRequiredMixin, View):
    """
    View for deleting a field mapping
    """
    def get(self, request, datasource_pk, mapping_pk):
        datasource = get_object_or_404(DataSource, pk=datasource_pk)
        mapping = get_object_or_404(ProfileFieldMapping, pk=mapping_pk, datasource=datasource)
        
        mapping.delete()
        
        messages.success(request, _('Field mapping deleted successfully.'))
        return redirect('datasources:profile_mapping', pk=datasource_pk)