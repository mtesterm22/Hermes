# datasources/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory

from .models import DataSource, DataSourceField
from .csv_models import CSVDataSource, CSVFileUpload
from .database_models import DatabaseDataSource, DatabaseQuery
from .connection_models import DatabaseConnection
from cryptography.fernet import Fernet
from django.conf import settings
import json
from core.utils.encryption import encrypt_credentials, decrypt_credentials

class CSVDataSourceForm(forms.ModelForm):
    """
    Form for creating/editing a CSV data source.
    """
    class Meta:
        model = DataSource
        fields = ['name', 'description', 'status']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['description'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['status'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})

class CSVSettingsForm(forms.ModelForm):
    """
    Form for CSV-specific settings.
    """
    class Meta:
        model = CSVDataSource
        fields = ['file_location', 'file_path', 'delimiter', 'has_header', 
                 'encoding', 'quote_char', 'skip_rows', 'max_rows']
        widgets = {
            'file_path': forms.TextInput(attrs={'placeholder': '/path/to/file.csv or leave blank for uploaded files'}),
            'delimiter': forms.TextInput(attrs={'placeholder': ','}),
            'quote_char': forms.TextInput(attrs={'placeholder': '"'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file_location'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['file_path'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['delimiter'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['encoding'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['quote_char'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['skip_rows'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
        self.fields['max_rows'].widget.attrs.update({'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})

class CSVFileUploadForm(forms.ModelForm):
    """
    Form for uploading a CSV file.
    """
    class Meta:
        model = CSVFileUpload
        fields = ['file']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].widget.attrs.update({
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100',
            'accept': '.csv,.txt'
        })

class DataSourceFieldInlineForm(forms.ModelForm):
    """
    Form for editing data source fields inline.
    """
    class Meta:
        model = DataSourceField
        fields = ['name', 'display_name', 'field_type', 'is_key', 'is_nullable']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'display_name': forms.TextInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'field_type': forms.Select(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'is_key': forms.CheckboxInput(attrs={'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'}),
            'is_nullable': forms.CheckboxInput(attrs={'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'}),
        }

# Create a formset for managing multiple DataSourceField instances
DataSourceFieldFormSet = inlineformset_factory(
    DataSource, 
    DataSourceField,
    form=DataSourceFieldInlineForm,
    extra=1,
    can_delete=True
)

DataSourceFieldFormSet = inlineformset_factory(
    DataSource, 
    DataSourceField,
    form=DataSourceFieldInlineForm,
    extra=1,
    can_delete=True
)

# Add to datasources/forms.py

class DatabaseConnectionForm(forms.ModelForm):
    """
    Form for creating/editing a database connection.
    """
    password = forms.CharField(
        label=_('Password'),
        required=False,
        widget=forms.PasswordInput,
        help_text=_('Leave blank to keep the current password')
    )
    
    test_query = forms.CharField(
        label=_('Test Query'),
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text=_('Optional query to test the connection (e.g., SELECT 1)')
    )
    
    class Meta:
        model = DatabaseConnection
        fields = [
            'name', 'description', 'db_type', 'host', 'port', 'database_name', 
            'schema', 'username', 'oracle_service_name', 'oracle_sid',
            'use_ssl', 'ssl_cert_path', 'connection_timeout',
            'query_timeout', 'max_rows', 'fetch_size'
        ]
        widgets = {
            'host': forms.TextInput(attrs={'placeholder': 'localhost or IP address'}),
            'database_name': forms.TextInput(attrs={'placeholder': 'Database name'}),
            'schema': forms.TextInput(attrs={'placeholder': 'Schema (e.g., public)'}),
            'username': forms.TextInput(attrs={'placeholder': 'Username'}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Apply Tailwind classes to form fields
        for field_name, field in self.fields.items():
            css_class = 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
            
            field.widget.attrs.update({'class': css_class})
            
        if not self.instance or self.instance.db_type != 'oracle':
            # Don't add hidden class to the fields directly
            pass
    
    def get_default_port(self, db_type):
        """Get the default port for a database type."""
        port_map = {
            'postgresql': 5432,
            'mysql': 3306,
            'oracle': 1521,
            'sqlserver': 1433,
            'sqlite': None,  # SQLite doesn't use ports
        }
        return port_map.get(db_type)
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Handle password
        if self.cleaned_data.get('password'):
            # Initialize credentials dict if it doesn't exist
            if not instance.credentials:
                instance.credentials = {}
            
            # Import encryption utilities
            from core.utils.encryption import encrypt_credentials
            
            # Encrypt the password and store it securely
            credentials_dict = {'password': self.cleaned_data['password']}
            encrypted = encrypt_credentials(credentials_dict)
            instance.credentials['encrypted_credentials'] = encrypted
            
            # Add this debug statement
            print(f"Saved encrypted credentials: {instance.credentials}")
        
        if commit:
            instance.save()
        
        return instance
        
        return instance



class DatabaseSettingsForm(forms.ModelForm):
    """
    Form for database-specific data source settings.
    """
    class Meta:
        model = DatabaseDataSource
        fields = ['connection', 'query_timeout', 'max_rows']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Apply Tailwind classes to form fields
        for field_name, field in self.fields.items():
            css_class = 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            field.widget.attrs.update({'class': css_class})


class DatabaseDataSourceForm(forms.ModelForm):
    """
    Form for creating/editing a database data source with an integrated query.
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
        label=_("Create new database connection"),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded',
            'data-toggle': 'connection-form'
        })
    )
    
    connection = forms.ModelChoiceField(
        label=_("Database Connection"),
        queryset=DatabaseConnection.objects.all(),
        required=True,
        widget=forms.Select(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    query_timeout = forms.IntegerField(
        label=_("Query Timeout (seconds)"),
        initial=60,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    max_rows = forms.IntegerField(
        label=_("Maximum Rows"),
        initial=10000,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'})
    )
    
    class Meta:
        model = DatabaseDataSource  # Add this model class
        fields = ['connection', 'query_timeout', 'max_rows']  # These are the fields from the DatabaseDataSource model
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the queryset for connections
        self.fields['connection'].queryset = DatabaseConnection.objects.all().order_by('name')

class DatabaseQueryForm(forms.ModelForm):
    """
    Form for database queries.
    """
    class Meta:
        model = DatabaseQuery
        fields = ['name', 'description', 'query_text', 'query_type', 'parameters', 'is_enabled']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'query_text': forms.Textarea(attrs={'rows': 10, 'class': 'font-mono focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'query_type': forms.Select(attrs={'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'parameters': forms.Textarea(attrs={'rows': 3, 'class': 'font-mono focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'}),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'}),
        }

class DataSourceBaseForm(forms.ModelForm):
    """
    Form for the base DataSource model.
    """
    class Meta:
        model = DataSource
        fields = ['name', 'description', 'status']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            css_class = 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            field.widget.attrs.update({'class': css_class})