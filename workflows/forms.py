# workflows/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _

from datasources.models import DataSource
from workflows.models import Action, Workflow, WorkflowAction, Schedule
from datasources.connection_models import DatabaseConnection

class ActionTypeForm(forms.Form):
    """
    Form for selecting an action type.
    """
    action_type = forms.ChoiceField(
        label=_('Action Type'),
        choices=Action.ACTION_TYPES,
        widget=forms.Select(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )

class DataSourceRefreshActionForm(forms.ModelForm):
    """
    Form for the Data Source Refresh action.
    """
    
    # Datasource selection fields - multi-select plus option for single datasource
    single_datasource = forms.ModelChoiceField(
        queryset=DataSource.objects.all().order_by('name'),
        required=False,
        label=_('Refresh a Single Data Source'),
        help_text=_('Select a single data source to refresh'),
        widget=forms.Select(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    multiple_datasources = forms.ModelMultipleChoiceField(
        queryset=DataSource.objects.all().order_by('name'),
        required=False,
        label=_('Refresh Multiple Data Sources'),
        help_text=_('Select multiple data sources to refresh in sequence'),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
        })
    )
    
    # Execution options
    wait_for_completion = forms.BooleanField(
        required=False,
        initial=True,
        label=_('Wait for Completion'),
        help_text=_('Wait for the refresh to complete before continuing the workflow'),
        widget=forms.CheckboxInput(attrs={
            'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
        })
    )
    
    timeout = forms.IntegerField(
        required=False,
        initial=600,
        min_value=10,
        max_value=3600,
        label=_('Timeout (seconds)'),
        help_text=_('Maximum time to wait for completion (10-3600 seconds)'),
        widget=forms.NumberInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    class Meta:
        model = Action
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If editing an existing action, populate the form with existing values
        if self.instance and self.instance.pk and self.instance.parameters:
            params = self.instance.parameters
            
            # Handle datasource selection
            if 'datasource_id' in params:
                try:
                    self.fields['single_datasource'].initial = DataSource.objects.get(id=params['datasource_id']).id
                except (DataSource.DoesNotExist, ValueError):
                    pass
                    
            if 'datasource_ids' in params and isinstance(params['datasource_ids'], list):
                try:
                    datasource_ids = [ds_id for ds_id in params['datasource_ids'] 
                                     if DataSource.objects.filter(id=ds_id).exists()]
                    self.fields['multiple_datasources'].initial = datasource_ids
                except (ValueError, TypeError):
                    pass
                    
            # Set other fields
            if 'wait_for_completion' in params:
                self.fields['wait_for_completion'].initial = params['wait_for_completion']
                
            if 'timeout' in params:
                self.fields['timeout'].initial = params['timeout']
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Ensure at least one datasource is selected
        single_datasource = cleaned_data.get('single_datasource')
        multiple_datasources = cleaned_data.get('multiple_datasources')
        
        if not single_datasource and not multiple_datasources:
            raise forms.ValidationError(_('You must select at least one data source to refresh'))
        
        return cleaned_data
    
    def save(self, commit=True):
        action = super().save(commit=False)
        
        # Set the action type
        action.action_type = 'datasource_refresh'
        
        # Prepare parameters
        params = {}
        
        # Handle datasource selection
        single_datasource = self.cleaned_data.get('single_datasource')
        multiple_datasources = self.cleaned_data.get('multiple_datasources', [])
        
        if single_datasource:
            params['datasource_id'] = single_datasource.id
            
        if multiple_datasources:
            params['datasource_ids'] = [ds.id for ds in multiple_datasources]
        elif single_datasource:
            params['datasource_ids'] = [single_datasource.id]
            
        # Add other parameters
        params['wait_for_completion'] = self.cleaned_data.get('wait_for_completion', True)
        params['timeout'] = self.cleaned_data.get('timeout', 600)
        
        # Save parameters to the action
        action.parameters = params
        
        if commit:
            action.save()
            
        return action


class WorkflowActionForm(forms.ModelForm):
    """
    Form for adding or editing an action within a workflow.
    """
    class Meta:
        model = WorkflowAction
        fields = ['action', 'sequence', 'condition', 'parameters']
        widgets = {
            'action': forms.Select(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'sequence': forms.NumberInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'condition': forms.Textarea(attrs={
                'rows': 3,
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'parameters': forms.Textarea(attrs={
                'rows': 5,
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md font-mono'
            }),
        }


class ScheduleForm(forms.ModelForm):
    """
    Form for creating or editing a workflow schedule.
    """
    class Meta:
        model = Schedule
        fields = ['name', 'workflow', 'frequency', 'cron_expression', 
                 'start_date', 'end_date', 'enabled', 'parameters']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'workflow': forms.Select(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'frequency': forms.Select(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'cron_expression': forms.TextInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'placeholder': '0 0 * * *  # Run at midnight every day'
            }),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'type': 'datetime-local'
            }),
            'end_date': forms.DateTimeInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
                'type': 'datetime-local'
            }),
            'enabled': forms.CheckboxInput(attrs={
                'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
            }),
            'parameters': forms.Textarea(attrs={
                'rows': 5,
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md font-mono'
            }),
        }

# Add this to workflows/forms.py

class DatabaseQueryActionForm(forms.ModelForm):
    """
    Form for the Database Query action.
    """
    
    connection = forms.ModelChoiceField(
    queryset=DatabaseConnection.objects.all().order_by('name'),
    required=True,
    label=_('Database Connection'),
    help_text=_('Select a database connection to use for this query'),
    widget=forms.Select(attrs={
        'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
    })
)
    
    query = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 8,
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md font-mono',
            'placeholder': 'SELECT * FROM users WHERE active = true'
        }),
        label=_('SQL Query'),
        help_text=_('The SQL query to execute')
    )
    
    # Execution options
    timeout = forms.IntegerField(
        required=False,
        initial=30,
        min_value=1,
        max_value=300,
        label=_('Timeout (seconds)'),
        help_text=_('Maximum time to wait for query execution (1-300 seconds)'),
        widget=forms.NumberInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    max_rows = forms.IntegerField(
        required=False,
        initial=1000,
        min_value=1,
        max_value=10000,
        label=_('Maximum Rows'),
        help_text=_('Maximum number of rows to return (1-10000)'),
        widget=forms.NumberInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    store_results = forms.BooleanField(
        required=False,
        initial=False,
        label=_('Store Results'),
        help_text=_('Save the query results for later use in the workflow'),
        widget=forms.CheckboxInput(attrs={
            'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
        })
    )
    
    result_format = forms.ChoiceField(
        choices=[
            ('json', _('JSON')),
            ('csv', _('CSV')),
            ('dict', _('Python Dictionary')),
        ],
        initial='json',
        required=False,
        label=_('Result Format'),
        help_text=_('Format for the query results'),
        widget=forms.Select(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    class Meta:
        model = Action
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
            }),
        }
    
    def clean_query(self):
        """Validate the SQL query."""
        query = self.cleaned_data.get('query')
        if not query:
            raise forms.ValidationError(_('Query is required'))
        
        # Here we could add more validation, like checking for dangerous SQL commands
        # if the query is unsafe, we could raise a ValidationError
        
        return query
    
    def save(self, commit=True):
        action = super().save(commit=False)
        
        # Set the action type
        action.action_type = 'database_query'
        
        # Don't set the datasource, it's not needed anymore
        # action.datasource = self.cleaned_data.get('datasource')
        
        # Prepare parameters
        params = {
            'connection_id': self.cleaned_data.get('connection').id,
            'query': self.cleaned_data.get('query'),
            'timeout': self.cleaned_data.get('timeout', 30),
            'max_rows': self.cleaned_data.get('max_rows', 1000),
            'store_results': self.cleaned_data.get('store_results', False),
            'result_format': self.cleaned_data.get('result_format', 'json'),
        }
        
        # Save parameters to the action
        action.parameters = params
        
        if commit:
            action.save()
            
        return action
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If we're editing an existing action, populate from parameters
        if self.instance and self.instance.pk and self.instance.parameters:
            params = self.instance.parameters
            
            # Set connection if provided
            connection_id = params.get('connection_id')
            if connection_id:
                try:
                    self.fields['connection'].initial = connection_id
                except (ValueError, DatabaseConnection.DoesNotExist):
                    pass
                    
            # Set other fields from parameters
            self.fields['query'].initial = params.get('query', '')
            self.fields['timeout'].initial = params.get('timeout', 30)
            self.fields['max_rows'].initial = params.get('max_rows', 1000)
            self.fields['store_results'].initial = params.get('store_results', False)
            self.fields['result_format'].initial = params.get('result_format', 'json')

class FileCreateActionForm(forms.ModelForm):
    """
    Form for the File Create action.
    """
    
    # Data source selection
    DATA_SOURCE_CHOICES = [
        ('previous_action', _('Previous Action')),
        ('custom_data', _('Custom Data')),
        ('workflow_context', _('Workflow Context')),
    ]
    
    data_source = forms.ChoiceField(
        choices=DATA_SOURCE_CHOICES,
        initial='previous_action',
        required=True,
        label=_('Data Source'),
        help_text=_('Where to get the data to write to the file'),
        widget=forms.Select(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    # Previous action selection (shown when data_source = 'previous_action')
    previous_action_id = forms.IntegerField(
        required=False,
        label=_('Previous Action'),
        help_text=_('Select a specific action to get data from'),
        widget=forms.Select(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    # Custom data (shown when data_source = 'custom_data')
    custom_data = forms.CharField(
        required=False,
        label=_('Custom Data'),
        help_text=_('Enter JSON data to write to the file'),
        widget=forms.Textarea(attrs={
            'rows': 5,
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md font-mono'
        })
    )
    
    # File format selection
    FILE_FORMAT_CHOICES = [
        ('csv', _('CSV')),
        ('json', _('JSON')),
        ('jsonl', _('JSON Lines')),
        ('excel', _('Excel')),
        ('txt', _('Text')),
    ]
    
    file_format = forms.ChoiceField(
        choices=FILE_FORMAT_CHOICES,
        initial='csv',
        required=True,
        label=_('File Format'),
        help_text=_('Format of the output file'),
        widget=forms.Select(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    # Filename
    filename = forms.CharField(
        required=False,
        label=_('Filename'),
        help_text=_('Name of the output file (date will be added automatically if left blank)'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            'placeholder': 'output.csv'
        })
    )
    
    # Output directory
    output_directory = forms.CharField(
        required=False,
        label=_('Output Directory'),
        help_text=_('Directory where the file will be saved (leave blank for default)'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            'placeholder': 'workflow_files/'
        })
    )
    
    # CSV-specific options (shown when file_format = 'csv')
    include_headers = forms.BooleanField(
        required=False,
        initial=True,
        label=_('Include Headers'),
        help_text=_('Include field names as headers in the first row'),
        widget=forms.CheckboxInput(attrs={
            'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
        })
    )
    
    header_fields = forms.CharField(
        required=False,
        label=_('Header Fields'),
        help_text=_('Comma-separated list of field names to use as headers (leave blank to use all fields)'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            'placeholder': 'id,name,email,status'
        })
    )
    
    selected_fields = forms.CharField(
        required=False,
        label=_('Selected Fields'),
        help_text=_('Comma-separated list of fields to include in the output (leave blank to include all fields)'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md',
            'placeholder': 'id,name,email,status'
        })
    )
    
    csv_delimiter = forms.CharField(
        required=False,
        initial=',',
        label=_('CSV Delimiter'),
        help_text=_('Character to use as delimiter in CSV files'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    csv_quotechar = forms.CharField(
        required=False,
        initial='"',
        label=_('CSV Quote Character'),
        help_text=_('Character to use for quoting in CSV files'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    # Excel-specific options
    excel_sheet_name = forms.CharField(
        required=False,
        initial='Data',
        label=_('Excel Sheet Name'),
        help_text=_('Name of the worksheet in Excel files'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    # JSON-specific options
    json_indent = forms.IntegerField(
        required=False,
        initial=2,
        min_value=0,
        max_value=8,
        label=_('JSON Indent'),
        help_text=_('Number of spaces for indentation in JSON files (0 for no indentation)'),
        widget=forms.NumberInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    # Text file options
    text_format = forms.CharField(
        required=False,
        initial='{record}',
        label=_('Text Format'),
        help_text=_('Format template for text output (use {record} or field names like {name})'),
        widget=forms.TextInput(attrs={
            'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
        })
    )
    
    class Meta:
        model = Action
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        workflow_pk = kwargs.pop('workflow_pk', None)
        super().__init__(*args, **kwargs)
        
        # Populate previous action dropdown if workflow_pk is provided
        if workflow_pk:
            workflow = Workflow.objects.get(pk=workflow_pk)
            actions = Action.objects.filter(workflow_actions__workflow=workflow)
            self.fields['previous_action_id'].widget.choices = [(a.id, a.name) for a in actions]
        
        # If editing an existing action, populate the form with existing values
        if self.instance and self.instance.pk and self.instance.parameters:
            params = self.instance.parameters
            
            # Set data source fields
            if 'data_source' in params:
                self.fields['data_source'].initial = params['data_source']
            
            if 'previous_action_id' in params:
                self.fields['previous_action_id'].initial = params['previous_action_id']
            
            if 'custom_data' in params:
                self.fields['custom_data'].initial = json.dumps(params['custom_data'], indent=2)
            
            # Set file format fields
            if 'file_format' in params:
                self.fields['file_format'].initial = params['file_format']
            
            if 'filename' in params:
                self.fields['filename'].initial = params['filename']
            
            if 'output_directory' in params:
                self.fields['output_directory'].initial = params['output_directory']
            
            # Set formatting options
            if 'include_headers' in params:
                self.fields['include_headers'].initial = params['include_headers']
            
            if 'header_fields' in params:
                if isinstance(params['header_fields'], list):
                    self.fields['header_fields'].initial = ','.join(params['header_fields'])
                else:
                    self.fields['header_fields'].initial = params['header_fields']
            
            if 'selected_fields' in params:
                if isinstance(params['selected_fields'], list):
                    self.fields['selected_fields'].initial = ','.join(params['selected_fields'])
                else:
                    self.fields['selected_fields'].initial = params['selected_fields']
            
            # CSV options
            if 'csv_delimiter' in params:
                self.fields['csv_delimiter'].initial = params['csv_delimiter']
            
            if 'csv_quotechar' in params:
                self.fields['csv_quotechar'].initial = params['csv_quotechar']
            
            # Excel options
            if 'excel_sheet_name' in params:
                self.fields['excel_sheet_name'].initial = params['excel_sheet_name']
            
            # JSON options
            if 'json_indent' in params:
                self.fields['json_indent'].initial = params['json_indent']
            
            # Text options
            if 'text_format' in params:
                self.fields['text_format'].initial = params['text_format']
    
    def clean_custom_data(self):
        """Validate and parse the custom data JSON."""
        custom_data = self.cleaned_data.get('custom_data')
        data_source = self.cleaned_data.get('data_source')
        
        if data_source == 'custom_data' and custom_data:
            try:
                return json.loads(custom_data)
            except json.JSONDecodeError:
                raise forms.ValidationError(_('Invalid JSON format. Please check your syntax.'))
        
        return custom_data
    
    def clean_header_fields(self):
        """Convert comma-separated header fields to a list."""
        header_fields = self.cleaned_data.get('header_fields')
        
        if header_fields:
            return [field.strip() for field in header_fields.split(',') if field.strip()]
        
        return []
    
    def clean_selected_fields(self):
        """Convert comma-separated selected fields to a list."""
        selected_fields = self.cleaned_data.get('selected_fields')
        
        if selected_fields:
            return [field.strip() for field in selected_fields.split(',') if field.strip()]
        
        return []
    
    def save(self, commit=True):
        action = super().save(commit=False)
        
        # Set the action type
        action.action_type = 'file_create'
        
        # Prepare parameters
        params = {}
        
        # Data source parameters
        params['data_source'] = self.cleaned_data.get('data_source')
        
        if params['data_source'] == 'previous_action':
            previous_action_id = self.cleaned_data.get('previous_action_id')
            if previous_action_id:
                params['previous_action_id'] = previous_action_id
        elif params['data_source'] == 'custom_data':
            params['custom_data'] = self.cleaned_data.get('custom_data')
        
        # File format and location
        params['file_format'] = self.cleaned_data.get('file_format')
        
        filename = self.cleaned_data.get('filename')
        if filename:
            params['filename'] = filename
        
        output_directory = self.cleaned_data.get('output_directory')
        if output_directory:
            params['output_directory'] = output_directory
        
        # Formatting options
        params['include_headers'] = self.cleaned_data.get('include_headers', True)
        params['header_fields'] = self.cleaned_data.get('header_fields', [])
        params['selected_fields'] = self.cleaned_data.get('selected_fields', [])
        
        # Format-specific options
        if params['file_format'] == 'csv':
            params['csv_delimiter'] = self.cleaned_data.get('csv_delimiter', ',')
            params['csv_quotechar'] = self.cleaned_data.get('csv_quotechar', '"')
        elif params['file_format'] in ['json', 'jsonl']:
            params['json_indent'] = self.cleaned_data.get('json_indent', 2)
        elif params['file_format'] == 'excel':
            params['excel_sheet_name'] = self.cleaned_data.get('excel_sheet_name', 'Data')
        elif params['file_format'] == 'txt':
            params['text_format'] = self.cleaned_data.get('text_format', '{record}')
        
        # Save parameters to the action
        action.parameters = params
        
        if commit:
            action.save()
            
        return action