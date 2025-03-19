# users/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from .models import Person, ExternalIdentity, AttributeChange
from datasources.models import DataSource
from users.profile_integration import AttributeSource, ProfileFieldMapping, ProfileAttributeChange

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
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) | 
                Q(last_name__icontains=search_query) | 
                Q(display_name__icontains=search_query) | 
                Q(email__icontains=search_query) | 
                Q(unique_id__icontains=search_query)
            )
        
        # Handle sorting
        sort_by = self.request.GET.get('sort', 'display_name')
        if sort_by.startswith('-'):
            direction = '-'
            field = sort_by[1:]
        else:
            direction = ''
            field = sort_by
        
        # Apply sorting (add more cases as needed)
        if field == 'display_name':
            queryset = queryset.order_by(f'{direction}display_name', f'{direction}last_name', f'{direction}first_name')
        else:
            queryset = queryset.order_by(sort_by)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add identifiers to each person in the list
        from users.models import get_identifiers
        for person in context['persons']:
            # Get raw identifiers
            identifiers = get_identifiers(person)
            person.identifiers = identifiers
            
            # Coalesce identifiers
            person.coalesced_identifiers = {}
            if identifiers:
                for source_name, source_ids in identifiers.items():
                    for attr_name, value in source_ids.items():
                        if attr_name not in person.coalesced_identifiers:
                            person.coalesced_identifiers[attr_name] = []
                        
                        # Check if this exact value already exists
                        duplicate = False
                        for existing in person.coalesced_identifiers[attr_name]:
                            if existing['value'] == value:
                                # Just add this source to the existing value's sources
                                existing['sources'].append(source_name)
                                duplicate = True
                                break
                        
                        # If not a duplicate, add new entry
                        if not duplicate:
                            person.coalesced_identifiers[attr_name].append({
                                'value': value,
                                'sources': [source_name]
                            })
        
        context['search_query'] = self.request.GET.get('search', '')
        context['sort_by'] = self.request.GET.get('sort', 'display_name')
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
        
        # Restructure identifiers to be grouped by attribute name first
        # This is the key change - we flip the structure from source->attribute to attribute->values
        coalesced_identifiers = {}
        
        if raw_identifiers:
            # First, collect all values for each attribute across all sources
            for source, attributes in raw_identifiers.items():
                for attr_name, value in attributes.items():
                    if attr_name not in coalesced_identifiers:
                        coalesced_identifiers[attr_name] = {}
                    
                    # Use the value as a key to group by unique values
                    if value not in coalesced_identifiers[attr_name]:
                        coalesced_identifiers[attr_name][value] = []
                    
                    # Add this source to the list of sources for this value
                    coalesced_identifiers[attr_name][value].append(source)
            
            # Convert the nested dict to the final format expected by the template
            for attr_name in coalesced_identifiers:
                # Convert dict of value->sources to list of {value, sources} objects
                value_list = []
                for value, sources in coalesced_identifiers[attr_name].items():
                    value_list.append({
                        'value': value,
                        'sources': sources
                    })
                coalesced_identifiers[attr_name] = value_list
        
        context['coalesced_identifiers'] = coalesced_identifiers
        
        # Rest of the function (existing code) continues here...
        
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