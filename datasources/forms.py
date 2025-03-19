# datasources/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms import inlineformset_factory

from .models import DataSource, DataSourceField
from .csv_models import CSVDataSource, CSVFileUpload

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