# users/page_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.db import transaction
from django.utils.text import slugify

from datasources.models import DataSource
from users.profile_integration import AttributeDisplayConfig
from users.page_models import ProfilePage, PageDataSource, PageAttribute

class ProfilePageListView(LoginRequiredMixin, ListView):
    """
    List view for profile pages
    """
    model = ProfilePage
    template_name = 'users/pages/index.html'
    context_object_name = 'pages'
    
    def get_queryset(self):
        return ProfilePage.objects.all().order_by('display_order', 'name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get counts for each page
        for page in context['pages']:
            page.datasource_count = page.datasources.count()
        
        # Count datasources not assigned to any page
        assigned_datasources = PageDataSource.objects.values_list('datasource_id', flat=True).distinct()
        context['unassigned_count'] = DataSource.objects.exclude(id__in=assigned_datasources).count()
        
        return context

# users/page_views.py
# Fix for unconfigured attributes loading and attribute add handling

class PageAttributeReorderView(LoginRequiredMixin, View):
    """
    AJAX view for reordering attributes on a page data source
    """
    def post(self, request, slug, ds_id):
        page = get_object_or_404(ProfilePage, slug=slug)
        page_ds = get_object_or_404(PageDataSource, id=ds_id, page=page)
        
        try:
            # Get the new ordering data
            order_data = request.POST.getlist('ids[]', [])
            
            if not order_data:
                return JsonResponse({'status': 'error', 'message': 'No ordering data provided'})
            
            # Update the display order for each attribute
            with transaction.atomic():
                for i, attr_id in enumerate(order_data):
                    try:
                        page_attr = PageAttribute.objects.get(page_datasource=page_ds, id=attr_id)
                        page_attr.display_order = i * 10
                        page_attr.save(update_fields=['display_order'])
                    except PageAttribute.DoesNotExist:
                        pass
            
            return JsonResponse({'status': 'success'})
            
        except Exception as e:
            import traceback
            return JsonResponse({
                'status': 'error', 
                'message': str(e),
                'traceback': traceback.format_exc()
            })


class PageAttributeAddView(LoginRequiredMixin, View):
    """
    View for adding an attribute to a page data source
    """
    def post(self, request, slug, ds_id):
        page = get_object_or_404(ProfilePage, slug=slug)
        
        try:
            # Find the page data source
            page_ds = get_object_or_404(PageDataSource, id=ds_id, page=page)
            attribute_name = request.POST.get('attribute_name')
            
            if not attribute_name:
                messages.error(request, _('No attribute selected.'))
                return redirect('users:page_detail', slug=slug)
            
            # Check if attribute already exists
            if PageAttribute.objects.filter(page_datasource=page_ds, attribute_name=attribute_name).exists():
                messages.warning(request, _('This attribute is already on this page.'))
                return redirect('users:page_detail', slug=slug)
            
            # Get display configuration if it exists
            try:
                config = AttributeDisplayConfig.objects.get(
                    datasource=page_ds.datasource,
                    attribute_name=attribute_name
                )
                is_highlighted = config.is_primary
                display_name = config.display_name if config.display_name else None
            except AttributeDisplayConfig.DoesNotExist:
                is_highlighted = False
                display_name = None
            
            # Get highest display order for this page data source's attributes
            highest_order = PageAttribute.objects.filter(page_datasource=page_ds).order_by('-display_order').values_list('display_order', flat=True).first()
            if highest_order is None:
                highest_order = 0
            
            # Create the page attribute
            page_attr = PageAttribute.objects.create(
                page_datasource=page_ds,
                attribute_name=attribute_name,
                display_name_override=display_name,
                display_order=highest_order + 10,
                is_highlighted=is_highlighted
            )
            
            messages.success(request, _(f'Added attribute {attribute_name} to the page.'))
            
        except Exception as e:
            import traceback
            print(f"Error adding attribute: {str(e)}")
            print(traceback.format_exc())
            messages.error(request, _(f'Error adding attribute: {str(e)}'))
        
        return redirect('users:page_detail', slug=slug)


class ProfilePageDetailView(LoginRequiredMixin, DetailView):
    """
    Detail view for a profile page
    """
    model = ProfilePage
    template_name = 'users/pages/detail.html'
    context_object_name = 'page'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get data sources for this page with their attributes
        page_datasources = PageDataSource.objects.filter(
            page=self.object
        ).select_related('datasource').order_by('display_order')
        
        # For each page datasource, get its attributes
        for page_ds in page_datasources:
            # Get page attributes (configured ones)
            page_ds.page_attributes = list(PageAttribute.objects.filter(
                page_datasource=page_ds
            ).order_by('display_order'))
            
            # Get list of attribute names already configured for this page
            configured_attrs = set(attr.attribute_name for attr in page_ds.page_attributes)
            
            # Get all display configs for this datasource
            all_configs = AttributeDisplayConfig.objects.filter(
                datasource=page_ds.datasource,
                is_visible=True
            ).exclude(attribute_name__in=configured_attrs).order_by('category', 'display_order')
            
            # Group by category
            unconfigured_attrs = {}
            for config in all_configs:
                category = config.category if config.category else 'General'
                if category not in unconfigured_attrs:
                    unconfigured_attrs[category] = []
                unconfigured_attrs[category].append(config)
            
            page_ds.unconfigured_attrs = unconfigured_attrs
        
        context['page_datasources'] = page_datasources
        
        # Get available data sources that aren't yet on this page
        assigned_ids = page_datasources.values_list('datasource_id', flat=True)
        context['available_datasources'] = DataSource.objects.exclude(
            id__in=assigned_ids
        ).order_by('name')
        
        return context

class ProfilePageCreateView(LoginRequiredMixin, CreateView):
    """
    Create view for profile pages
    """
    model = ProfilePage
    template_name = 'users/pages/form.html'
    fields = ['name', 'description', 'icon']
    
    def form_valid(self, form):
        # Generate slug from name
        form.instance.slug = slugify(form.instance.name)
        
        # Get highest display order and add 10
        highest_order = ProfilePage.objects.all().order_by('-display_order').values_list('display_order', flat=True).first()
        if highest_order is None:
            highest_order = 0
        form.instance.display_order = highest_order + 10
        
        messages.success(self.request, _('Profile page created successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('users:page_detail', kwargs={'slug': self.object.slug})

class ProfilePageUpdateView(LoginRequiredMixin, UpdateView):
    """
    Update view for profile pages
    """
    model = ProfilePage
    template_name = 'users/pages/form.html'
    fields = ['name', 'description', 'icon', 'display_order', 'is_visible']
    slug_url_kwarg = 'slug'
    
    def form_valid(self, form):
        # Update slug if name changed
        if 'name' in form.changed_data:
            form.instance.slug = slugify(form.instance.name)
        
        messages.success(self.request, _('Profile page updated successfully.'))
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('users:page_detail', kwargs={'slug': self.object.slug})

class ProfilePageDeleteView(LoginRequiredMixin, DeleteView):
    """
    Delete view for profile pages
    """
    model = ProfilePage
    template_name = 'users/pages/confirm_delete.html'
    slug_url_kwarg = 'slug'
    success_url = reverse_lazy('users:page_list')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check if this is a system page
        context['is_system_page'] = self.object.is_system
        return context
    
    def delete(self, request, *args, **kwargs):
        page = self.get_object()
        
        # Prevent deletion of system pages
        if page.is_system:
            messages.error(request, _('Cannot delete system pages.'))
            return redirect('users:page_detail', slug=page.slug)
        
        messages.success(request, _('Profile page deleted successfully.'))
        return super().delete(request, *args, **kwargs)

class PageDataSourceAddView(LoginRequiredMixin, View):
    """
    View for adding a data source to a page
    """
    def post(self, request, slug):
        page = get_object_or_404(ProfilePage, slug=slug)
        datasource_id = request.POST.get('datasource_id')
        
        if not datasource_id:
            messages.error(request, _('No data source selected.'))
            return redirect('users:page_detail', slug=slug)
        
        try:
            datasource = DataSource.objects.get(pk=datasource_id)
            
            # Check if this data source is already on this page
            if PageDataSource.objects.filter(page=page, datasource=datasource).exists():
                messages.warning(request, _('This data source is already on this page.'))
                return redirect('users:page_detail', slug=slug)
            
            # Get highest display order for this page's data sources
            highest_order = PageDataSource.objects.filter(page=page).order_by('-display_order').values_list('display_order', flat=True).first()
            if highest_order is None:
                highest_order = 0
            
            # Create the page data source
            page_ds = PageDataSource.objects.create(
                page=page,
                datasource=datasource,
                display_order=highest_order + 10
            )
            
            # Create page attributes for all visible attributes
            display_configs = AttributeDisplayConfig.objects.filter(
                datasource=datasource,
                is_visible=True
            )
            
            for i, config in enumerate(display_configs):
                PageAttribute.objects.create(
                    page_datasource=page_ds,
                    attribute_name=config.attribute_name,
                    display_order=i * 10,
                    is_highlighted=config.is_primary
                )
            
            messages.success(request, _(f'Added {datasource.name} to the page with {display_configs.count()} attributes.'))
            
        except DataSource.DoesNotExist:
            messages.error(request, _('Data source not found.'))
        except Exception as e:
            messages.error(request, _(f'Error adding data source: {str(e)}'))
        
        return redirect('users:page_detail', slug=slug)

class PageDataSourceRemoveView(LoginRequiredMixin, View):
    """
    View for removing a data source from a page
    """
    def post(self, request, slug, ds_id):
        page = get_object_or_404(ProfilePage, slug=slug)
        
        try:
            # Find the page data source
            page_ds = get_object_or_404(PageDataSource, id=ds_id, page=page)
            attribute_name = request.POST.get('attribute_name')
            
            if not attribute_name:
                messages.error(request, _('No attribute selected.'))
                return redirect('users:page_detail', slug=slug)
            
            # Check if attribute already exists
            if PageAttribute.objects.filter(page_datasource=page_ds, attribute_name=attribute_name).exists():
                messages.warning(request, _('This attribute is already on this page.'))
                return redirect('users:page_detail', slug=slug)
            
            # Get display configuration if it exists
            try:
                config = AttributeDisplayConfig.objects.get(
                    datasource=page_ds.datasource,
                    attribute_name=attribute_name
                )
                is_highlighted = config.is_primary
            except AttributeDisplayConfig.DoesNotExist:
                is_highlighted = False
            
            # Get highest display order for this page data source's attributes
            highest_order = PageAttribute.objects.filter(page_datasource=page_ds).order_by('-display_order').values_list('display_order', flat=True).first()
            if highest_order is None:
                highest_order = 0
            
            # Create the page attribute
            PageAttribute.objects.create(
                page_datasource=page_ds,
                attribute_name=attribute_name,
                display_order=highest_order + 10,
                is_highlighted=is_highlighted
            )
            
            messages.success(request, _(f'Added attribute {attribute_name} to the page.'))
            
        except Exception as e:
            messages.error(request, _(f'Error adding attribute: {str(e)}'))
        
        return redirect('users:page_detail', slug=slug)


class PageAttributeRemoveView(LoginRequiredMixin, View):
    """
    View for removing an attribute from a page data source
    """
    def post(self, request, slug, ds_id, attr_id):
        page = get_object_or_404(ProfilePage, slug=slug)
        
        try:
            # Find the page attribute
            page_ds = get_object_or_404(PageDataSource, id=ds_id, page=page)
            page_attr = get_object_or_404(PageAttribute, id=attr_id, page_datasource=page_ds)
            attribute_name = page_attr.attribute_name
            
            # Delete it
            page_attr.delete()
            
            messages.success(request, _(f'Removed attribute {attribute_name} from the page.'))
            
        except Exception as e:
            messages.error(request, _(f'Error removing attribute: {str(e)}'))
        
        return redirect('users:page_detail', slug=slug)

class PageDataSourceReorderView(LoginRequiredMixin, View):
    """
    AJAX view for reordering data sources on a page
    """
    def post(self, request, slug):
        page = get_object_or_404(ProfilePage, slug=slug)
        
        try:
            # Get the new ordering data
            order_data = request.POST.getlist('ids[]', [])
            
            if not order_data:
                return JsonResponse({'status': 'error', 'message': 'No ordering data provided'})
            
            # Update the display order for each data source
            with transaction.atomic():
                for i, ds_id in enumerate(order_data):
                    try:
                        page_ds = PageDataSource.objects.get(page=page, id=ds_id)
                        page_ds.display_order = i * 10
                        page_ds.save(update_fields=['display_order'])
                    except PageDataSource.DoesNotExist:
                        pass
            
            return JsonResponse({'status': 'success'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
class PageAttributeToggleHighlightView(LoginRequiredMixin, View):
    """
    View for toggling the highlighted status of an attribute
    """
    def post(self, request, slug, ds_id, attr_id):
        page = get_object_or_404(ProfilePage, slug=slug)
        
        try:
            # Find the page attribute
            page_ds = get_object_or_404(PageDataSource, id=ds_id, page=page)
            page_attr = get_object_or_404(PageAttribute, id=attr_id, page_datasource=page_ds)
            
            # Toggle the highlighted status
            page_attr.is_highlighted = not page_attr.is_highlighted
            page_attr.save(update_fields=['is_highlighted'])
            
            if page_attr.is_highlighted:
                messages.success(request, _(f'Highlighted attribute {page_attr.attribute_name}.'))
            else:
                messages.success(request, _(f'Unhighlighted attribute {page_attr.attribute_name}.'))
            
        except Exception as e:
            messages.error(request, _(f'Error toggling highlight status: {str(e)}'))
        
        return redirect('users:page_detail', slug=slug)

class CreateDefaultPagesView(LoginRequiredMixin, View):
    """
    View for creating default profile pages based on existing data sources and attribute configurations
    """
    def post(self, request):
        try:
            # Start a transaction for creating all pages
            with transaction.atomic():
                # Create the main system pages if they don't exist
                identity_page, created = ProfilePage.objects.get_or_create(
                    slug='identity',
                    defaults={
                        'name': 'Identity',
                        'description': 'Basic identity information',
                        'icon': 'fa-id-card',
                        'display_order': 10,
                        'is_system': True
                    }
                )
                
                contact_page, created = ProfilePage.objects.get_or_create(
                    slug='contact',
                    defaults={
                        'name': 'Contact Information',
                        'description': 'Contact details and addresses',
                        'icon': 'fa-address-book',
                        'display_order': 20,
                        'is_system': True
                    }
                )
                
                employment_page, created = ProfilePage.objects.get_or_create(
                    slug='employment',
                    defaults={
                        'name': 'Employment',
                        'description': 'Job-related information',
                        'icon': 'fa-briefcase',
                        'display_order': 30,
                        'is_system': True
                    }
                )
                
                other_page, created = ProfilePage.objects.get_or_create(
                    slug='other',
                    defaults={
                        'name': 'Other Information',
                        'description': 'Additional profile data',
                        'icon': 'fa-info-circle',
                        'display_order': 100,
                        'is_system': True
                    }
                )
                
                # Assign data sources to pages based on categories
                for datasource in DataSource.objects.all():
                    # Check if already assigned to any page
                    if PageDataSource.objects.filter(datasource=datasource).exists():
                        continue
                    
                    # Get all attribute configs for this datasource
                    configs = AttributeDisplayConfig.objects.filter(datasource=datasource)
                    
                    # Count attributes by category to determine the best page
                    categories = {}
                    for config in configs:
                        cat = config.category.lower()
                        if cat not in categories:
                            categories[cat] = 0
                        categories[cat] += 1
                    
                    # Determine the best page based on most common category
                    target_page = other_page  # Default to other page
                    
                    if 'identity' in categories or 'personal' in categories:
                        target_page = identity_page
                    elif 'contact' in categories or 'address' in categories:
                        target_page = contact_page
                    elif 'employment' in categories or 'job' in categories or 'work' in categories:
                        target_page = employment_page
                    
                    # Add to the page
                    page_ds = PageDataSource.objects.create(
                        page=target_page,
                        datasource=datasource,
                        display_order=100
                    )
                    
                    # Add all visible attributes to the page
                    for i, config in enumerate(configs.filter(is_visible=True)):
                        PageAttribute.objects.create(
                            page_datasource=page_ds,
                            attribute_name=config.attribute_name,
                            display_order=i * 10,
                            is_highlighted=config.is_primary
                        )
                
                messages.success(request, _('Default profile pages created successfully.'))
                
            return redirect('users:page_list')
            
        except Exception as e:
            messages.error(request, _(f'Error creating default pages: {str(e)}'))
            return redirect('users:page_list')

class UnassignedDataSourcesView(LoginRequiredMixin, ListView):
    """
    View for listing data sources not assigned to any profile page
    """
    model = DataSource
    template_name = 'users/pages/unassigned.html'
    context_object_name = 'datasources'
    
    def get_queryset(self):
        # Get IDs of data sources already assigned to pages
        assigned_ids = PageDataSource.objects.values_list('datasource_id', flat=True).distinct()
        
        # Return unassigned data sources
        return DataSource.objects.exclude(id__in=assigned_ids).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Provide all available pages for assignment
        context['pages'] = ProfilePage.objects.all().order_by('display_order', 'name')
        
        return context


class PageAddAllUnassignedView(LoginRequiredMixin, View):
    """
    View for adding all unassigned data sources to a page
    """
    def post(self, request):
        page_slug = request.POST.get('page_slug')
        
        if not page_slug:
            messages.error(request, _('No page selected.'))
            return redirect('users:unassigned_datasources')
        
        try:
            page = get_object_or_404(ProfilePage, slug=page_slug)
            
            # Get all unassigned data sources
            assigned_datasources = PageDataSource.objects.values_list('datasource_id', flat=True).distinct()
            unassigned_datasources = DataSource.objects.exclude(id__in=assigned_datasources)
            
            count = 0
            # Add each unassigned data source to the page
            for datasource in unassigned_datasources:
                # Get highest display order for this page's data sources
                highest_order = PageDataSource.objects.filter(page=page).order_by('-display_order').values_list('display_order', flat=True).first()
                if highest_order is None:
                    highest_order = 0
                
                # Create the page data source
                page_ds = PageDataSource.objects.create(
                    page=page,
                    datasource=datasource,
                    display_order=highest_order + 10
                )
                
                # Create page attributes for all visible attributes
                display_configs = AttributeDisplayConfig.objects.filter(
                    datasource=datasource,
                    is_visible=True
                )
                
                for i, config in enumerate(display_configs):
                    PageAttribute.objects.create(
                        page_datasource=page_ds,
                        attribute_name=config.attribute_name,
                        display_order=i * 10,
                        is_highlighted=config.is_primary
                    )
                
                count += 1
            
            messages.success(request, _(f'Added {count} data sources to the page "{page.name}".'))
            
        except Exception as e:
            messages.error(request, _(f'Error adding data sources: {str(e)}'))
        
        return redirect('users:page_detail', slug=page_slug)

class PageAddAllUnassignedView(LoginRequiredMixin, View):
    """
    View for adding all unassigned data sources to a page
    """
    def post(self, request):
        page_slug = request.POST.get('page_slug')
        
        if not page_slug:
            messages.error(request, _('No page selected.'))
            return redirect('users:unassigned_datasources')
        
        try:
            page = get_object_or_404(ProfilePage, slug=page_slug)
            
            # Get all unassigned data sources
            assigned_datasources = PageDataSource.objects.values_list('datasource_id', flat=True).distinct()
            unassigned_datasources = DataSource.objects.exclude(id__in=assigned_datasources)
            
            count = 0
            # Add each unassigned data source to the page
            for datasource in unassigned_datasources:
                # Get highest display order for this page's data sources
                highest_order = PageDataSource.objects.filter(page=page).order_by('-display_order').values_list('display_order', flat=True).first()
                if highest_order is None:
                    highest_order = 0
                
                # Create the page data source
                page_ds = PageDataSource.objects.create(
                    page=page,
                    datasource=datasource,
                    display_order=highest_order + 10
                )
                
                # Create page attributes for all visible attributes
                display_configs = AttributeDisplayConfig.objects.filter(
                    datasource=datasource,
                    is_visible=True
                )
                
                for i, config in enumerate(display_configs):
                    PageAttribute.objects.create(
                        page_datasource=page_ds,
                        attribute_name=config.attribute_name,
                        display_order=i * 10,
                        is_highlighted=config.is_primary
                    )
                
                count += 1
            
            messages.success(request, _(f'Added {count} data sources to the page "{page.name}".'))
            
        except Exception as e:
            messages.error(request, _(f'Error adding data sources: {str(e)}'))
        
        return redirect('users:page_detail', slug=page_slug)