# users/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, FormView, View
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from .models import Person, ExternalIdentity, AttributeChange
from datasources.models import DataSource
from users.profile_integration import AttributeSource, ProfileFieldMapping, ProfileAttributeChange, AttributeDisplayConfig
from users.utils import coalesce_identifiers

from django.http import JsonResponse
from django.db import transaction


# Person views
class PersonListView(LoginRequiredMixin, ListView):
    """
    List view for all user profiles
    """
    model = Person
    template_name = 'users/person_list.html'
    context_object_name = 'persons'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Handle search
        search_query = self.request.GET.get('search', '')
        if search_query:
            # Basic search on Person model fields
            basic_search = Q(first_name__icontains=search_query) | \
                        Q(last_name__icontains=search_query) | \
                        Q(display_name__icontains=search_query) | \
                        Q(email__icontains=search_query) | \
                        Q(secondary_email__icontains=search_query) | \
                        Q(unique_id__icontains=search_query)
            
            # Search in JSON attributes field
            # This works for PostgreSQL, but may need to be adjusted for other databases
            json_search = Q(attributes__icontains=search_query)
            
            # Combine searches
            queryset = queryset.filter(basic_search | json_search)
            
            # Also search in attribute sources
            # First, find all AttributeSource records that contain the search term
            from users.profile_integration import AttributeSource
            matching_sources = AttributeSource.objects.filter(
                Q(attribute_value__icontains=search_query) & 
                Q(is_current=True)
            ).values_list('person_id', flat=True).distinct()
            
            # Then include persons with matching attribute sources
            queryset = queryset.filter(
                Q(id__in=matching_sources) | basic_search | json_search
            ).distinct()
    
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all person IDs from the current queryset
        person_ids = [person.id for person in context['persons']]
        
        # Query attribute counts in a single database hit
        from django.db.models import Count
        from users.profile_integration import AttributeSource
        
        # Get attribute counts
        attribute_counts = AttributeSource.objects.filter(
            person_id__in=person_ids,
            is_current=True
        ).values('person_id').annotate(
            count=Count('attribute_name', distinct=True)
        ).values_list('person_id', 'count')
        
        # Get datasource counts
        datasource_counts = AttributeSource.objects.filter(
            person_id__in=person_ids,
            is_current=True
        ).values('person_id').annotate(
            count=Count('datasource', distinct=True)
        ).values_list('person_id', 'count')
        
        # Convert to dictionaries for easy lookup
        attribute_count_dict = dict(attribute_counts)
        datasource_count_dict = dict(datasource_counts)
        
        # Add identifiers and counts to each person in the list
        from users.models import get_identifiers
        from users.utils import coalesce_identifiers
        
        # Get the sort parameter
        sort_by = self.request.GET.get('sort', 'display_name')
        
        # Prepare a list to hold the persons if we need to sort them manually
        persons_list = list(context['persons'])
        
        for person in persons_list:
            # Get raw identifiers
            identifiers = get_identifiers(person)
            person.identifiers = identifiers
            
            # Coalesce identifiers for display
            person.coalesced_identifiers = coalesce_identifiers(identifiers)
            
            # Add attribute and datasource counts
            person.attribute_count = attribute_count_dict.get(person.id, 0)
            person.datasource_count = datasource_count_dict.get(person.id, 0)
        
        # Handle sorting for calculated fields
        if sort_by == 'attribute_count':
            persons_list.sort(key=lambda p: p.attribute_count)
        elif sort_by == '-attribute_count':
            persons_list.sort(key=lambda p: p.attribute_count, reverse=True)
        elif sort_by == 'datasource_count':
            persons_list.sort(key=lambda p: p.datasource_count)
        elif sort_by == '-datasource_count':
            persons_list.sort(key=lambda p: p.datasource_count, reverse=True)
        
        # Replace the paginated persons with our sorted list if we did manual sorting
        if sort_by in ['attribute_count', '-attribute_count', 'datasource_count', '-datasource_count']:
            # This is a bit tricky since we're dealing with a paginated queryset
            # We'll replace the object_list in the paginator with our sorted list
            context['persons'].object_list = persons_list
        
        context['search_query'] = self.request.GET.get('search', '')
        context['sort_by'] = sort_by
        context['total_count'] = Person.objects.count()
        return context


class PersonDetailView(LoginRequiredMixin, DetailView):
    """
    Detail view for a single user profile with data source filtering
    """
    model = Person
    template_name = 'users/person_detail.html'
    context_object_name = 'person'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get identifiers for this person
        from users.models import get_identifiers
        raw_identifiers = get_identifiers(self.object)
        
        # Store original format for backwards compatibility
        context['identifiers'] = raw_identifiers
        
        # Use the new coalescing function
        context['coalesced_identifiers'] = coalesce_identifiers(raw_identifiers)
        
        # Get selected datasource from query parameter (if any)
        selected_datasource_id = self.request.GET.get('datasource', None)
        selected_datasource = None
        
        if selected_datasource_id:
            try:
                selected_datasource = DataSource.objects.get(pk=selected_datasource_id)
            except (DataSource.DoesNotExist, ValueError):
                pass
        
        # Get all datasources for this profile
        datasources = {}
        all_sources = AttributeSource.objects.filter(
            person=self.object,
            is_current=True
        ).select_related('datasource', 'mapping')
        
        for source in all_sources:
            if source.datasource.id not in datasources:
                datasources[source.datasource.id] = {
                    'datasource': source.datasource,
                    'attribute_count': 0,
                    'last_updated': None
                }
            
            datasources[source.datasource.id]['attribute_count'] += 1
            
            if (datasources[source.datasource.id]['last_updated'] is None or 
                source.last_updated > datasources[source.datasource.id]['last_updated']):
                datasources[source.datasource.id]['last_updated'] = source.last_updated
        
        # Sort by attribute count (most attributes first)
        datasources_list = sorted(
            datasources.values(), 
            key=lambda x: x['attribute_count'], 
            reverse=True
        )
        
        context['datasources'] = datasources_list
        context['selected_datasource'] = selected_datasource
        
        # Get attributes filtered by selected datasource if applicable
        if selected_datasource:
            filtered_sources = all_sources.filter(datasource=selected_datasource)
        else:
            filtered_sources = all_sources
        
        # Group attributes by name
        attributes = {}
        for source in filtered_sources:
            if source.attribute_name not in attributes:
                attributes[source.attribute_name] = []
            
            attributes[source.attribute_name].append({
                'value': source.attribute_value,
                'datasource': source.datasource,
                'priority': source.mapping.priority if source.mapping else 0,
                'last_updated': source.last_updated,
                'id': source.id
            })
        
        # Sort values by priority
        for attr_name, values in attributes.items():
            attributes[attr_name] = sorted(values, key=lambda x: -x['priority'])
        
        context['attributes'] = attributes
        
        # Get recent attribute changes, possibly filtered by datasource
        if selected_datasource:
            recent_changes = ProfileAttributeChange.objects.filter(
                person=self.object,
                datasource=selected_datasource
            ).select_related('datasource').order_by('-changed_at')[:10]
        else:
            recent_changes = ProfileAttributeChange.objects.filter(
                person=self.object
            ).select_related('datasource').order_by('-changed_at')[:10]
        
        context['recent_changes'] = recent_changes
        
        return context

class PersonCreateView(LoginRequiredMixin, CreateView):
    model = Person
    template_name = 'users/form.html'
    fields = ['unique_id', 'first_name', 'last_name', 'display_name', 'email', 'secondary_email', 'phone', 'status']
    success_url = reverse_lazy('users:index')
    
    def form_valid(self, form):
        messages.success(self.request, _('Person created successfully.'))
        return super().form_valid(form)


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    model = Person
    template_name = 'users/form.html'
    fields = ['unique_id', 'first_name', 'last_name', 'display_name', 'email', 'secondary_email', 'phone', 'status']
    
    def get_success_url(self):
        return reverse_lazy('users:detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, _('Person updated successfully.'))
        return super().form_valid(form)


class PersonDeleteView(LoginRequiredMixin, DeleteView):
    model = Person
    template_name = 'users/confirm_delete.html'
    success_url = reverse_lazy('users:index')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, _('Person deleted successfully.'))
        return super().delete(request, *args, **kwargs)


# External Identity views
class ExternalIdentityListView(LoginRequiredMixin, ListView):
    template_name = 'users/identities.html'
    context_object_name = 'identities'
    
    def get_queryset(self):
        self.person = get_object_or_404(Person, pk=self.kwargs['pk'])
        return self.person.external_ids.all().order_by('datasource__name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = self.person
        return context


class ExternalIdentityCreateView(LoginRequiredMixin, CreateView):
    model = ExternalIdentity
    template_name = 'users/identity_form.html'
    fields = ['datasource', 'external_id', 'username', 'email', 'attributes', 'is_active']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = get_object_or_404(Person, pk=self.kwargs['person_pk'])
        return context
    
    def form_valid(self, form):
        form.instance.person = get_object_or_404(Person, pk=self.kwargs['person_pk'])
        messages.success(self.request, _('External identity created successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('users:identities', kwargs={'pk': self.kwargs['person_pk']})


class ExternalIdentityUpdateView(LoginRequiredMixin, UpdateView):
    model = ExternalIdentity
    template_name = 'users/identity_form.html'
    fields = ['datasource', 'external_id', 'username', 'email', 'attributes', 'is_active']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = get_object_or_404(Person, pk=self.kwargs['person_pk'])
        return context
    
    def get_success_url(self):
        return reverse_lazy('users:identities', kwargs={'pk': self.kwargs['person_pk']})


class ExternalIdentityDeleteView(LoginRequiredMixin, DeleteView):
    model = ExternalIdentity
    template_name = 'users/identity_confirm_delete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = get_object_or_404(Person, pk=self.kwargs['person_pk'])
        return context
    
    def get_success_url(self):
        return reverse_lazy('users:identities', kwargs={'pk': self.kwargs['person_pk']})


# Attribute Change views
class AttributeChangeListView(LoginRequiredMixin, ListView):
    template_name = 'users/changes.html'
    context_object_name = 'changes'
    paginate_by = 50
    
    def get_queryset(self):
        self.person = get_object_or_404(Person, pk=self.kwargs['pk'])
        return self.person.attribute_changes.all().order_by('-changed_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = self.person
        return context

class AttributeConfigListView(LoginRequiredMixin, ListView):
    """
    List view for attribute display configurations by data source
    """
    model = AttributeDisplayConfig
    template_name = 'users/attribute_config_list.html'
    context_object_name = 'configs'
    
    def get_queryset(self):
        # Get the data source from the URL
        datasource_id = self.kwargs.get('datasource_id')
        return AttributeDisplayConfig.objects.filter(datasource_id=datasource_id).order_by('category', 'display_order')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = get_object_or_404(DataSource, pk=self.kwargs.get('datasource_id'))
        
        # Group configs by category
        grouped_configs = {}
        for config in context['configs']:
            if config.category not in grouped_configs:
                grouped_configs[config.category] = []
            grouped_configs[config.category].append(config)
        
        context['grouped_configs'] = grouped_configs
        
        # Get all known attributes for this data source
        known_attributes = set(config.attribute_name for config in context['configs'])
        
        # Find attributes from mappings that don't have a display config yet
        mappings = ProfileFieldMapping.objects.filter(datasource_id=self.kwargs.get('datasource_id'))
        missing_attributes = set()
        for mapping in mappings:
            if mapping.profile_attribute not in known_attributes:
                missing_attributes.add(mapping.profile_attribute)
        
        context['missing_attributes'] = sorted(list(missing_attributes))
        context['has_missing_attributes'] = len(missing_attributes) > 0
        
        return context

class AttributeConfigCreateView(LoginRequiredMixin, CreateView):
    """
    Create view for attribute display configuration
    """
    model = AttributeDisplayConfig
    template_name = 'users/attribute_config_form.html'
    fields = ['attribute_name', 'display_name', 'category', 'display_order', 'is_primary', 'is_visible']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = get_object_or_404(DataSource, pk=self.kwargs.get('datasource_id'))
        return context
    
    def form_valid(self, form):
        form.instance.datasource = get_object_or_404(DataSource, pk=self.kwargs.get('datasource_id'))
        messages.success(self.request, _('Attribute configuration created successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('users:attribute_config_list', kwargs={'datasource_id': self.kwargs.get('datasource_id')})

class AttributeConfigUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update view for attribute display configuration
    """
    model = AttributeDisplayConfig
    template_name = 'users/attribute_config_form.html'
    fields = ['attribute_name', 'display_name', 'category', 'display_order', 'is_primary', 'is_visible']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = self.object.datasource
        return context
    
    def get_success_url(self):
        return reverse_lazy('users:attribute_config_list', kwargs={'datasource_id': self.object.datasource.id})

class AttributeConfigDeleteView(LoginRequiredMixin, DeleteView):
    """
    Delete view for attribute display configuration
    """
    model = AttributeDisplayConfig
    template_name = 'users/attribute_config_confirm_delete.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = self.object.datasource
        return context
    
    def get_success_url(self):
        return reverse_lazy('users:attribute_config_list', kwargs={'datasource_id': self.object.datasource.id})

class AttributeConfigBulkCreateView(LoginRequiredMixin, FormView):
    """
    Bulk create view for missing attribute configurations
    """
    template_name = 'users/attribute_config_bulk_create.html'
    
    def get_form(self, form_class=None):
        from django import forms
        
        class BulkCreateForm(forms.Form):
            attributes = forms.MultipleChoiceField(
                choices=[], 
                widget=forms.CheckboxSelectMultiple,
                required=False
            )
            
            def __init__(self, *args, missing_attributes=None, **kwargs):
                super().__init__(*args, **kwargs)
                if missing_attributes:
                    self.fields['attributes'].choices = [(attr, attr) for attr in missing_attributes]
        
        # Get missing attributes
        datasource_id = self.kwargs.get('datasource_id')
        known_attributes = set(config.attribute_name for config in 
                           AttributeDisplayConfig.objects.filter(datasource_id=datasource_id))
        
        mappings = ProfileFieldMapping.objects.filter(datasource_id=datasource_id)
        missing_attributes = []
        for mapping in mappings:
            if mapping.profile_attribute not in known_attributes:
                missing_attributes.append(mapping.profile_attribute)
        
        # Create and return the form
        return BulkCreateForm(self.request.POST or None, missing_attributes=sorted(missing_attributes))
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['datasource'] = get_object_or_404(DataSource, pk=self.kwargs.get('datasource_id'))
        return context
    
    def form_valid(self, form):
        datasource_id = self.kwargs.get('datasource_id')
        datasource = get_object_or_404(DataSource, pk=datasource_id)
        
        # Process the checked attributes
        selected_attributes = form.cleaned_data.get('attributes', [])
        
        for i, attr_name in enumerate(selected_attributes):
            # Make an educated guess about the category based on attribute name
            category = self._guess_category(attr_name)
            
            AttributeDisplayConfig.objects.create(
                datasource=datasource,
                attribute_name=attr_name,
                # Use attribute name as display name by default
                display_name=attr_name.replace('_', ' ').title(),
                category=category,
                # Order by selection order
                display_order=i * 10,
                is_primary=False,
                is_visible=True
            )
        
        messages.success(self.request, _(f'Created {len(selected_attributes)} attribute configurations.'))
        return redirect('users:attribute_config_list', datasource_id=datasource_id)
    
    def _guess_category(self, attribute_name):
        """Make an educated guess about which category an attribute belongs to"""
        attribute_name = attribute_name.lower()
        
        # Identity attributes
        if any(term in attribute_name for term in ['id', 'uuid', 'guid', 'unique']):
            return 'identity'
        
        # Contact information
        if any(term in attribute_name for term in ['email', 'phone', 'address', 'contact']):
            return 'contact'
        
        # Personal information
        if any(term in attribute_name for term in ['name', 'first', 'last', 'birth', 'gender']):
            return 'personal'
        
        # Employment information
        if any(term in attribute_name for term in ['job', 'title', 'department', 'manager', 'hire', 'employee']):
            return 'employment'
        
        # System information
        if any(term in attribute_name for term in ['status', 'created', 'modified', 'updated', 'active']):
            return 'system'
        
        # Default
        return 'general'

class AttributeConfigReorderView(LoginRequiredMixin, View):
    """
    AJAX view for reordering attributes via drag and drop
    """
    def post(self, request, datasource_id):
        try:
            # Verify the data source exists
            datasource = get_object_or_404(DataSource, pk=datasource_id)
            
            # Get the ordering data from the request
            data = request.POST.get('order')
            if not data:
                return JsonResponse({'status': 'error', 'message': 'No ordering data provided'})
            
            import json
            order_data = json.loads(data)
            
            # Update the ordering in a transaction
            with transaction.atomic():
                for category, items in order_data.items():
                    for i, item_id in enumerate(items):
                        try:
                            # Update the display order
                            config = AttributeDisplayConfig.objects.get(id=item_id, datasource=datasource)
                            config.display_order = i
                            config.category = category  # Update category in case item was moved between categories
                            config.save(update_fields=['display_order', 'category'])
                        except AttributeDisplayConfig.DoesNotExist:
                            continue
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

class CategoryManagementView(LoginRequiredMixin, View):
    """
    View for managing categories
    """
    template_name = 'users/category_management.html'
    
    def get(self, request, datasource_id):
        datasource = get_object_or_404(DataSource, pk=datasource_id)
        
        # Get all unique categories for this data source
        categories = AttributeDisplayConfig.objects.filter(
            datasource=datasource
        ).values_list('category', flat=True).distinct().order_by('category')
        
        context = {
            'datasource': datasource,
            'categories': categories
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, datasource_id):
        datasource = get_object_or_404(DataSource, pk=datasource_id)
        
        action = request.POST.get('action')
        
        if action == 'rename':
            old_name = request.POST.get('old_name')
            new_name = request.POST.get('new_name')
            
            if old_name and new_name:
                # Update all configs with this category
                count = AttributeDisplayConfig.objects.filter(
                    datasource=datasource,
                    category=old_name
                ).update(category=new_name)
                
                messages.success(request, _(f'Renamed category "{old_name}" to "{new_name}" (affected {count} attributes).'))
            else:
                messages.error(request, _('Both old and new category names are required.'))
        
        elif action == 'delete':
            category = request.POST.get('category')
            new_category = request.POST.get('new_category', 'general')
            
            if category:
                # Move attributes to the new category
                count = AttributeDisplayConfig.objects.filter(
                    datasource=datasource,
                    category=category
                ).update(category=new_category)
                
                messages.success(request, _(f'Deleted category "{category}" and moved {count} attributes to "{new_category}".'))
            else:
                messages.error(request, _('Category name is required.'))
        
        elif action == 'create':
            new_category = request.POST.get('new_category')
            
            if new_category:
                # Nothing to do here since categories are created implicitly
                # when assigning them to attributes
                messages.success(request, _(f'Created new category "{new_category}".'))
            else:
                messages.error(request, _('New category name is required.'))
        
        else:
            messages.error(request, _('Invalid action.'))
        
        return redirect('users:category_management', datasource_id=datasource_id)