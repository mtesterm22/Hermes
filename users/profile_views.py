# users/profile_views.py
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.db.models import Count, Q 
from django.utils.translation import gettext_lazy as _

from .models import Person
from .profile_integration import AttributeSource, ProfileAttributeChange, DataSource, AttributeDisplayConfig
from .page_models import ProfilePage, PageDataSource, PageAttribute
from .utils import coalesce_identifiers

logger = logging.getLogger(__name__)

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

# users/profile_views.py
# Update PersonDetailView to better handle switching between curated pages and datasource views

class PersonDetailView(LoginRequiredMixin, DetailView):
    """
    Detail view for a single user profile with data source filtering
    """
    model = Person
    template_name = 'users/person_detail.html'
    context_object_name = 'person'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Debug info
        logger.info(f"Loading profile for person ID: {self.object.id}")
        
        # Get identifiers for this person
        from users.models import get_identifiers
        context['identifiers'] = get_identifiers(self.object)
        
        # Restructure identifiers to be grouped by attribute name
        coalesced_identifiers = {}
        
        if context['identifiers']:
            # First, collect all values for each attribute across all sources
            for source, attributes in context['identifiers'].items():
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
                # Convert dict of value->sources to list of {value, source_names} objects
                entries = []
                for value, sources in coalesced_identifiers[attr_name].items():
                    entries.append({
                        'value': value,
                        'source_names': sources
                    })
                coalesced_identifiers[attr_name] = entries
        
        context['coalesced_identifiers'] = coalesced_identifiers
        
        # Get selected datasource from query parameter (if any)
        selected_datasource_id = self.request.GET.get('datasource', None)
        selected_datasource = None
        
        if selected_datasource_id:
            try:
                selected_datasource = DataSource.objects.get(pk=selected_datasource_id)
                logger.info(f"Selected datasource: {selected_datasource.name} (ID: {selected_datasource.id})")
            except (DataSource.DoesNotExist, ValueError):
                logger.warning(f"Invalid datasource ID: {selected_datasource_id}")
        
        # Get all datasources for this profile
        datasources = {}
        all_sources = AttributeSource.objects.filter(
            person=self.object,
            is_current=True
        ).select_related('datasource', 'mapping')
        
        # Log what we found
        logger.info(f"Found {all_sources.count()} attribute sources for person {self.object.id}")
        
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
        
        logger.info(f"Prepared {len(datasources_list)} datasources for sidebar")
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
        
        # Check if a specific data source has been selected
        context['has_selected_datasource'] = selected_datasource is not None
        
        # Get profile pages for organization - regardless of datasource selection
        # We'll always prepare the curated pages, but only show them when no datasource is selected
        has_pages = ProfilePage.objects.filter(is_visible=True).exists()
        logger.info(f"Profile pages exist: {has_pages}")
        context['has_pages'] = has_pages

        if has_pages:
            # Get visible pages
            pages = ProfilePage.objects.filter(is_visible=True).order_by('display_order')
            logger.info(f"Found {pages.count()} visible pages")
            
            # Organize datasources and attributes by page
            profile_pages = []
            
            for page in pages:
                logger.info(f"Processing page: {page.name} (ID: {page.id})")
                page_datasources = []
                
                # Get data sources for this page
                page_ds_objects = PageDataSource.objects.filter(page=page).order_by('display_order')
                logger.info(f"Found {page_ds_objects.count()} datasources for page {page.name}")
                
                for page_ds in page_ds_objects:
                    logger.info(f"Processing datasource: {page_ds.datasource.name} (ID: {page_ds.datasource.id})")
                    # Only include if this person has attributes from this data source
                    person_attributes = AttributeSource.objects.filter(
                        person=self.object,
                        datasource=page_ds.datasource,
                        is_current=True
                    )
                    
                    logger.info(f"Found {person_attributes.count()} attributes from datasource {page_ds.datasource.name}")
                    
                    if person_attributes.exists():
                        # Get attributes for this page data source
                        highlighted_attributes = []
                        regular_attributes = []
                        
                        # Get available PageAttribute configurations
                        page_attrs = PageAttribute.objects.filter(
                            page_datasource=page_ds,
                            is_visible=True
                        ).order_by('display_order')
                        
                        logger.info(f"Found {page_attrs.count()} page attribute configurations")
                        
                        # Map attribute names to configurations
                        attr_configs = {attr.attribute_name: attr for attr in page_attrs}
                        
                        # Group by attribute name
                        attr_groups = {}
                        for attr in person_attributes:
                            if attr.attribute_name not in attr_groups:
                                attr_groups[attr.attribute_name] = []
                            attr_groups[attr.attribute_name].append(attr)
                        
                        # Process each attribute
                        for attr_name, attr_list in attr_groups.items():
                            # Skip attributes not configured for this page
                            if attr_name not in attr_configs:
                                logger.info(f"Skipping attribute {attr_name} - not configured for this page")
                                continue
                                
                            # Sort by priority if multiple values
                            attr_list.sort(key=lambda x: -x.mapping.priority if x.mapping else 0)
                            
                            # Create display information for this attribute
                            attr_display = {
                                'name': attr_name,
                                'values': attr_list,
                                'is_highlighted': attr_configs[attr_name].is_highlighted,
                                'display_name': attr_configs[attr_name].get_display_name(),
                                'display_order': attr_configs[attr_name].display_order
                            }
                            
                            # Add to the appropriate list
                            if attr_display['is_highlighted']:
                                highlighted_attributes.append(attr_display)
                                logger.info(f"Added {attr_name} to highlighted attributes")
                            else:
                                regular_attributes.append(attr_display)
                                logger.info(f"Added {attr_name} to regular attributes")
                        
                        # Sort attributes by display order
                        highlighted_attributes.sort(key=lambda x: x['display_order'])
                        regular_attributes.sort(key=lambda x: x['display_order'])
                        
                        logger.info(f"Datasource has {len(highlighted_attributes)} highlighted and {len(regular_attributes)} regular attributes")
                        
                        # Only add this datasource if it has attributes to show
                        if highlighted_attributes or regular_attributes:
                            # Add to page data source
                            page_ds_data = {
                                'datasource': page_ds.datasource,
                                'title': page_ds.title_override or page_ds.datasource.name,
                                'description': page_ds.description_override or page_ds.datasource.description,
                                'highlighted_attributes': highlighted_attributes,
                                'regular_attributes': regular_attributes
                            }
                            
                            page_datasources.append(page_ds_data)
                            logger.info(f"Added datasource {page_ds.datasource.name} to page datasources")
                
                # Only add page if it has data sources with data
                if page_datasources:
                    page_data = {
                        'page': page,
                        'datasources': page_datasources
                    }
                    profile_pages.append(page_data)
                    logger.info(f"Added page {page.name} with {len(page_datasources)} datasources to profile pages")
            
            context['profile_pages'] = profile_pages
            logger.info(f"Final result: {len(profile_pages)} pages with data")
        
        # When a datasource is selected, prepare a filtered view of all attributes
        if selected_datasource:
            logger.info(f"Preparing filtered view for datasource: {selected_datasource.name}")
            
            # Get all attributes for this person from the selected datasource
            datasource_attributes = AttributeSource.objects.filter(
                person=self.object,
                datasource=selected_datasource,
                is_current=True
            ).select_related('datasource', 'mapping')
            
            # Group attributes by category if possible
            categorized_attributes = {}
            
            # Try to get display configs for the attributes
            display_configs = AttributeDisplayConfig.objects.filter(
                datasource=selected_datasource
            ).select_related()
            
            # Create a mapping of attribute names to their display configs
            config_map = {config.attribute_name: config for config in display_configs}
            
            # Group the attributes by name
            attr_by_name = {}
            for attr in datasource_attributes:
                if attr.attribute_name not in attr_by_name:
                    attr_by_name[attr.attribute_name] = []
                attr_by_name[attr.attribute_name].append(attr)
            
            # Organize attributes by category
            for attr_name, attrs in attr_by_name.items():
                # Get display info from config if available
                if attr_name in config_map:
                    config = config_map[attr_name]
                    category = config.category or "Uncategorized"
                    display_name = config.get_formatted_display_name()
                    is_primary = config.is_primary
                    display_order = config.display_order
                else:
                    # Default display info if no config exists
                    category = "Uncategorized"
                    display_name = attr_name.replace('_', ' ').title()
                    is_primary = False
                    display_order = 999
                
                # Sort the attributes by priority
                sorted_attrs = sorted(attrs, key=lambda x: -x.mapping.priority if x.mapping else 0)
                
                # Create attribute display info
                attr_info = {
                    'name': attr_name,
                    'display_name': display_name,
                    'values': sorted_attrs,
                    'is_primary': is_primary,
                    'display_order': display_order
                }
                
                # Add to the category
                if category not in categorized_attributes:
                    categorized_attributes[category] = []
                
                categorized_attributes[category].append(attr_info)
            
            # Sort attributes within each category
            for category in categorized_attributes:
                categorized_attributes[category] = sorted(
                    categorized_attributes[category], 
                    key=lambda x: (x['display_order'], x['display_name'])
                )
            
            # Sort categories (Identity first, then alphabetically)
            sorted_categories = {}
            if 'Identity' in categorized_attributes:
                sorted_categories['Identity'] = categorized_attributes.pop('Identity')
            
            # Add remaining categories in alphabetical order
            for category in sorted(categorized_attributes.keys()):
                sorted_categories[category] = categorized_attributes[category]
            
            # Add to context
            context['datasource_view'] = True
            context['filtered_datasource'] = selected_datasource
            context['categorized_attributes'] = sorted_categories
            
            logger.info(f"Prepared filtered view with {sum(len(attrs) for attrs in sorted_categories.values())} attributes in {len(sorted_categories)} categories")
        else:
            context['datasource_view'] = False
        
        # Log the actual context keys being passed to the template
        logger.info(f"Template context keys: {', '.join(context.keys())}")
        
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