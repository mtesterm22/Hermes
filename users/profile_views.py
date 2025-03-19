# users/profile_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _

from .models import Person
from .profile_integration import AttributeSource, ProfileAttributeChange, DataSource


# Updated PersonListView in users/profile_views.py
class PersonListView(LoginRequiredMixin, ListView):
    """
    List view for all user profiles
    """
    model = Person
    template_name = 'users/person_list.html'
    context_object_name = 'persons'
    paginate_by = 20
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add identifiers to each person in the list
        from users.models import get_identifiers
        for person in context['persons']:
            person.identifiers = get_identifiers(person)
        
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
        from users.models import get_identifiers  # Import the function we added
        context['identifiers'] = get_identifiers(self.object)
        
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


class AttributeHistoryView(LoginRequiredMixin, View):
    """
    View for attribute change history
    """
    template_name = 'users/attribute_history.html'
    
    def get(self, request, pk, attribute_name=None):
        person = get_object_or_404(Person, pk=pk)
        
        # Get the attribute name from query param if not provided in URL
        if not attribute_name:
            attribute_name = request.GET.get('attribute')
        
        # If still no attribute name, redirect to person detail
        if not attribute_name:
            return redirect('users:person_detail', pk=pk)
        
        # Get current values
        current_values = AttributeSource.objects.filter(
            person=person,
            attribute_name=attribute_name,
            is_current=True
        ).select_related('datasource', 'mapping').order_by('-mapping__priority')
        
        # Get attribute history
        history = ProfileAttributeChange.objects.filter(
            person=person,
            attribute_name=attribute_name
        ).select_related('datasource').order_by('-changed_at')
        
        context = {
            'person': person,
            'attribute_name': attribute_name,
            'current_values': current_values,
            'history': history
        }
        
        return render(request, self.template_name, context)