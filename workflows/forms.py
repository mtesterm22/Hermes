# workflows/forms.py
from django import forms
from django.utils.translation import gettext_lazy as _

from datasources.models import DataSource
from workflows.models import Action, Workflow, WorkflowAction, Schedule

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

class DatabaseQueryActionForm(forms.ModelForm):
    """
    Form for the Database Query action.
    """
    
    # Database connection fields
    datasource = forms.ModelChoiceField(
        queryset=DataSource.objects.filter(type='database').order_by('name'),
        required=True,
        label=_('Database Source'),
        help_text=_('Select a database source to query'),
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
        
        # Use the utility function to validate the query
        from core.database.utils import validate_query
        is_valid, error_message = validate_query(query)
        
        if not is_valid:
            raise forms.ValidationError(error_message)
        
        return query
    
    def save(self, commit=True):
        action = super().save(commit=False)
        
        # Set the action type
        action.action_type = 'database_query'
        
        # Set the selected datasource
        action.datasource = self.cleaned_data.get('datasource')
        
        # Prepare parameters
        params = {
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
            
        return actions