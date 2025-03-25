# users/page_models.py
from django.db import models
from django.utils.translation import gettext_lazy as _

from datasources.models import DataSource

class ProfilePage(models.Model):
    """
    Represents a page in the user profile interface.
    Pages can contain multiple data sources and their attributes.
    """
    name = models.CharField(_('Page Name'), max_length=100)
    slug = models.SlugField(_('Slug'), max_length=100, unique=True)
    description = models.TextField(_('Description'), blank=True)
    icon = models.CharField(_('Icon'), max_length=50, blank=True, 
                          help_text=_('Font awesome icon class (e.g., fa-user)'))
    display_order = models.PositiveIntegerField(_('Display Order'), default=100,
                                              help_text=_('Lower numbers appear first'))
    is_visible = models.BooleanField(_('Visible'), default=True)
    is_system = models.BooleanField(_('System Page'), default=False,
                                  help_text=_('System pages cannot be deleted'))
    
    class Meta:
        verbose_name = _('Profile Page')
        verbose_name_plural = _('Profile Pages')
        ordering = ['display_order', 'name']
    
    def __str__(self):
        return self.name

class PageDataSource(models.Model):
    """
    Associates data sources with profile pages and controls their display order.
    """
    page = models.ForeignKey(
        ProfilePage,
        on_delete=models.CASCADE,
        related_name='datasources'
    )
    datasource = models.ForeignKey(
        DataSource,
        on_delete=models.CASCADE,
        related_name='profile_pages'
    )
    display_order = models.PositiveIntegerField(_('Display Order'), default=100)
    title_override = models.CharField(_('Title Override'), max_length=100, blank=True,
                                   help_text=_('Custom title to use instead of data source name'))
    description_override = models.TextField(_('Description Override'), blank=True,
                                         help_text=_('Custom description to use instead of data source description'))
    
    class Meta:
        verbose_name = _('Page Data Source')
        verbose_name_plural = _('Page Data Sources')
        unique_together = ('page', 'datasource')
        ordering = ['display_order']
    
    def __str__(self):
        return f"{self.page.name} - {self.datasource.name}"

class PageAttribute(models.Model):
    """
    Customizes which attributes appear on a page and how they are displayed.
    This allows overriding the default attribute display settings for specific pages.
    """
    page_datasource = models.ForeignKey(
        PageDataSource,
        on_delete=models.CASCADE,
        related_name='attributes'
    )
    attribute_name = models.CharField(_('Attribute Name'), max_length=100)
    display_name_override = models.CharField(_('Display Name Override'), max_length=100, blank=True)
    display_order = models.PositiveIntegerField(_('Display Order'), default=100)
    is_visible = models.BooleanField(_('Visible'), default=True)
    is_highlighted = models.BooleanField(_('Highlighted'), default=False,
                                      help_text=_('Show prominently at the top of the page'))
    
    class Meta:
        verbose_name = _('Page Attribute')
        verbose_name_plural = _('Page Attributes')
        unique_together = ('page_datasource', 'attribute_name')
        ordering = ['display_order']
    
    def __str__(self):
        return f"{self.page_datasource.page.name} - {self.attribute_name}"
    
    def get_display_name(self):
        """
        Returns the display name to use for this attribute,
        using override if set, otherwise falling back to a formatted version of the attribute name.
        """
        if self.display_name_override:
            return self.display_name_override
        
        # Try to get the display name from the datasource's attribute config
        from users.profile_integration import AttributeDisplayConfig
        try:
            config = AttributeDisplayConfig.objects.get(
                datasource=self.page_datasource.datasource,
                attribute_name=self.attribute_name
            )
            if config.display_name:
                return config.display_name
        except AttributeDisplayConfig.DoesNotExist:
            pass
        
        # Fallback to a formatted version of the attribute name
        return self.attribute_name.replace('_', ' ').title()