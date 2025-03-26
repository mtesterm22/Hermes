# datasources/active_directory_forms.py
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import DataSource
from .active_directory_models import ActiveDirectoryConnection, ActiveDirectoryDataSource
from core.utils.encryption import encrypt_credentials

class ActiveDirectoryConnectionForm(forms.ModelForm):
    """
    Form for creating/editing an Active Directory connection.
    """
    password = forms.CharField(
        label=_('Password'),
        required=False,
        widget=forms.PasswordInput,
        help_text=_('Leave blank to keep the current password')
    )
    
    test_filter = forms.CharField(
        label=_('Test Filter'),
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '(objectClass=user)'}),
        help_text=_('Optional filter to test the connection (e.g., (objectClass=user))')
    )
    
    class Meta:
        model = ActiveDirectoryConnection
        fields = [
            'name', 'description', 'server', 'port', 'use_ssl', 'use_start_tls',
            'ldap_version', 'bind_dn', 'base_dn', 'search_scope', 
            'user_search_filter', 'group_search_filter', 'connect_timeout'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'bind_dn': forms.TextInput(attrs={'placeholder': 'cn=admin,dc=example,dc=com'}),
            'base_dn': forms.TextInput(attrs={'placeholder': 'dc=example,dc=com'}),
            'user_search_filter': forms.TextInput(attrs={'placeholder': '(objectClass=user)'}),
            'group_search_filter': forms.TextInput(attrs={'placeholder': '(objectClass=group)'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Apply Tailwind classes to form fields
        for field_name, field in self.fields.items():
            css_class = 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
            
            field.widget.attrs.update({'class': css_class})
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Handle password
        if self.cleaned_data.get('password'):
            # Initialize credentials dict if it doesn't exist
            if not instance.credentials:
                instance.credentials = {}
            
            # Encrypt the password and store it securely
            credentials_dict = {'password': self.cleaned_data['password']}
            encrypted = encrypt_credentials(credentials_dict)
            instance.credentials['encrypted_credentials'] = encrypted
        
        if commit:
            instance.save()
        
        return instance


class ActiveDirectoryDataSourceForm(forms.ModelForm):
    """
    Form for creating/editing an Active Directory data source.
    """
    name = forms.CharField(
        label=_("Data Source Name"),
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    description = forms.CharField(
        label=_("Description"),
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3, 
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    status = forms.ChoiceField(
        label=_("Status"),
        choices=DataSource.STATUS_CHOICES,
        initial='active',
        widget=forms.Select(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    create_new_connection = forms.BooleanField(
        label=_("Create new Active Directory connection"),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded',
            'data-toggle': 'connection-form'
        })
    )
    
    connection = forms.ModelChoiceField(
        label=_("Active Directory Connection"),
        queryset=ActiveDirectoryConnection.objects.all(),
        required=True,
        widget=forms.Select(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    user_filter = forms.CharField(
        label=_("User Filter"),
        initial='(&(objectClass=user)(objectCategory=person))',
        widget=forms.TextInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    user_attributes = forms.CharField(
        label=_("User Attributes"),
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3, 
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            'placeholder': 'sAMAccountName,userPrincipalName,mail,displayName,givenName,sn,title,department'
        }),
        help_text=_('Comma-separated list of attributes to retrieve. Leave blank for all attributes.')
    )
    
    include_groups = forms.BooleanField(
        label=_("Include Group Membership"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'})
    )
    
    include_nested_groups = forms.BooleanField(
        label=_("Include Nested Groups"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'})
    )
    
    group_filter = forms.CharField(
        label=_("Group Filter"),
        initial='(objectClass=group)',
        widget=forms.TextInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    group_attributes = forms.CharField(
        label=_("Group Attributes"),
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2, 
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            'placeholder': 'cn,description,member'
        }),
        help_text=_('Comma-separated list of attributes to retrieve. Leave blank for all attributes.')
    )
    
    page_size = forms.IntegerField(
        label=_("Page Size"),
        initial=1000,
        min_value=10,
        max_value=10000,
        widget=forms.NumberInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    sync_deleted = forms.BooleanField(
        label=_("Sync Deleted Objects"),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'})
    )
    
    class Meta:
        model = ActiveDirectoryDataSource
        fields = ['connection', 'user_filter', 'include_groups', 'include_nested_groups', 
                 'group_filter', 'page_size', 'sync_deleted']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the queryset for connections
        self.fields['connection'].queryset = ActiveDirectoryConnection.objects.all().order_by('name')
        
        # If we have an instance with user_attributes as a list, convert to comma-separated string
        if self.instance and self.instance.pk and self.instance.user_attributes:
            if isinstance(self.instance.user_attributes, list):
                self.initial['user_attributes'] = ','.join(self.instance.user_attributes)
        
        # Same for group_attributes
        if self.instance and self.instance.pk and self.instance.group_attributes:
            if isinstance(self.instance.group_attributes, list):
                self.initial['group_attributes'] = ','.join(self.instance.group_attributes)
    
    def clean_user_attributes(self):
        """Convert comma-separated string to list."""
        user_attrs = self.cleaned_data.get('user_attributes', '')
        if not user_attrs:
            return []
        return [attr.strip() for attr in user_attrs.split(',') if attr.strip()]
    
    def clean_group_attributes(self):
        """Convert comma-separated string to list."""
        group_attrs = self.cleaned_data.get('group_attributes', '')
        if not group_attrs:
            return []
        return [attr.strip() for attr in group_attrs.split(',') if attr.strip()]