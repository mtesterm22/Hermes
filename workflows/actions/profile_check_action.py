# workflows/actions/profile_check_action.py
"""
Profile check action for workflows.

This module implements a profile checking action that can evaluate user profile attributes
against various conditions, supporting both existence checks and value comparisons.
"""

import logging
import time
import traceback
from typing import Dict, Any, Optional, Tuple, List, Union
import operator
import re

from django.utils import timezone

from users.models import Person
from users.profile_integration import AttributeSource
from workflows.models import Action, ActionExecution

logger = logging.getLogger(__name__)

class ProfileCheckAction:
    """
    Implementation of profile check action for workflows.
    
    This action allows checking user profile attributes for existence or comparing
    their values against specified criteria. It's useful for conditional branching
    in workflows based on user profile data.
    """
    
    # Map string operation names to functions
    OPERATORS = {
        'equals': operator.eq,
        'not_equals': operator.ne,
        'contains': lambda a, b: b in a if isinstance(a, str) else False,
        'not_contains': lambda a, b: b not in a if isinstance(a, str) else True,
        'greater_than': operator.gt,
        'less_than': operator.lt,
        'greater_than_or_equal': operator.ge,
        'less_than_or_equal': operator.le,
        'matches_regex': lambda a, b: bool(re.search(b, a)) if isinstance(a, str) and isinstance(b, str) else False,
    }
    
    def __init__(self, action: Action):
        """
        Initialize the profile check action.
        
        Args:
            action: Action model instance
        """
        self.action = action
        self.parameters = action.parameters or {}
    
    def run(
        self, 
        action_execution: ActionExecution, 
        execution_params: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Execute the profile check action.
        
        Args:
            action_execution: ActionExecution model instance
            execution_params: Parameters for this execution
            
        Returns:
            Tuple of (success, result_data)
        """
        start_time = time.time()
        
        try:
            # Update execution status
            action_execution.start()
            
            # Merge default parameters with execution parameters
            params = {**self.parameters, **execution_params}
            
            # Extract required parameters
            profile_identifier = params.get('profile_identifier', '')
            id_type = params.get('id_type', 'unique_id')
            check_type = params.get('check_type', 'exists')
            attribute_name = params.get('attribute_name', '')
            comparison_value = params.get('comparison_value', '')
            comparison_operator = params.get('comparison_operator', 'equals')
            compare_to_attribute = params.get('compare_to_attribute', '')
            
            # Validate parameters
            if not profile_identifier:
                error_message = "No profile identifier specified"
                action_execution.complete('error', error_message=error_message)
                return False, {"error": error_message, "success": False}
            
            if not attribute_name and check_type != 'exists_any_from_datasource':
                error_message = "No attribute name specified"
                action_execution.complete('error', error_message=error_message)
                return False, {"error": error_message, "success": False}
            
            # Find the person
            person = self._find_person(profile_identifier, id_type)
            
            if not person:
                error_message = f"Person not found with {id_type}={profile_identifier}"
                action_execution.complete('error', error_message=error_message)
                return False, {"error": error_message, "person_found": False, "success": False}
            
            # Perform the check based on check_type
            result, details = self._perform_check(
                person, 
                check_type,
                attribute_name,
                comparison_value,
                comparison_operator,
                compare_to_attribute,
                params
            )
            
            # Prepare result data
            execution_time = time.time() - start_time
            result_data = {
                "success": True,
                "execution_time": f"{execution_time:.2f}s",
                "person_found": True,
                "person_id": person.id,
                "person_name": str(person),
                "check_result": result,
                "details": details
            }
            
            # Complete the execution
            action_execution.complete('success', output_data=result_data)
            
            return True, result_data
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"Error executing profile check action: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_message)
            
            # Complete the execution with error
            action_execution.complete('error', error_message=str(e))
            
            return False, {
                "success": False,
                "execution_time": f"{execution_time:.2f}s",
                "error": str(e)
            }
    
    def _find_person(self, identifier: str, id_type: str) -> Optional[Person]:
        """
        Find a person by the specified identifier type.
        
        Args:
            identifier: The identifier value
            id_type: The type of identifier (unique_id, email, attribute, etc.)
            
        Returns:
            Person object or None if not found
        """
        try:
            if id_type == 'unique_id':
                return Person.objects.filter(unique_id=identifier).first()
            elif id_type == 'email':
                return Person.objects.filter(email=identifier).first()
            elif id_type == 'id':
                try:
                    person_id = int(identifier)
                    return Person.objects.filter(id=person_id).first()
                except (ValueError, TypeError):
                    return None
            elif id_type == 'attribute':
                # The identifier should be in format attribute_name:value
                if ':' not in identifier:
                    return None
                    
                attr_name, attr_value = identifier.split(':', 1)
                
                # Find attribute sources that match
                attr_sources = AttributeSource.objects.filter(
                    attribute_name=attr_name.strip(),
                    attribute_value=attr_value.strip(),
                    is_current=True
                )
                
                if attr_sources.exists():
                    return attr_sources.first().person
                
                return None
            else:
                return None
        except Exception as e:
            logger.error(f"Error finding person: {str(e)}")
            return None
    
    def _perform_check(
        self, 
        person: Person,
        check_type: str,
        attribute_name: str,
        comparison_value: str,
        comparison_operator: str,
        compare_to_attribute: str,
        params: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Perform the specified check on the person's attributes.
        
        Args:
            person: Person object to check
            check_type: Type of check to perform (exists, not_exists, compare, etc.)
            attribute_name: Name of the attribute to check
            comparison_value: Value to compare against
            comparison_operator: Comparison operator to use
            compare_to_attribute: Name of another attribute to compare with
            params: Additional parameters
            
        Returns:
            Tuple of (result, details)
        """
        details = {}
        
        # Select the datasource to filter by, if specified
        datasource_id = params.get('datasource_id')
        datasource_filter = {}
        if datasource_id:
            try:
                datasource_id = int(datasource_id)
                datasource_filter['datasource_id'] = datasource_id
                from datasources.models import DataSource
                datasource = DataSource.objects.get(id=datasource_id)
                details['datasource'] = datasource.name
            except (ValueError, TypeError, DataSource.DoesNotExist):
                details['error'] = f"Invalid datasource ID: {datasource_id}"
        
        # Handle different check types
        if check_type == 'exists':
            # Check if the attribute exists
            attr_sources = AttributeSource.objects.filter(
                person=person,
                attribute_name=attribute_name,
                is_current=True,
                **datasource_filter
            )
            
            result = attr_sources.exists()
            details['attribute_name'] = attribute_name
            if result:
                details['values'] = [src.attribute_value for src in attr_sources]
            
            return result, details
            
        elif check_type == 'not_exists':
            # Check if the attribute doesn't exist
            result = not AttributeSource.objects.filter(
                person=person,
                attribute_name=attribute_name,
                is_current=True,
                **datasource_filter
            ).exists()
            
            details['attribute_name'] = attribute_name
            return result, details
            
        elif check_type == 'exists_any_from_datasource':
            # Check if any attributes from the specified datasource exist
            if not datasource_id:
                details['error'] = "No datasource specified for exists_any_from_datasource check"
                return False, details
                
            result = AttributeSource.objects.filter(
                person=person,
                is_current=True,
                **datasource_filter
            ).exists()
            
            if result:
                # Get the count of attributes
                count = AttributeSource.objects.filter(
                    person=person,
                    is_current=True,
                    **datasource_filter
                ).count()
                details['attribute_count'] = count
                
            return result, details
            
        elif check_type == 'compare_value':
            # Compare attribute value with a specified value
            attr_sources = AttributeSource.objects.filter(
                person=person,
                attribute_name=attribute_name,
                is_current=True,
                **datasource_filter
            ).order_by('-mapping__priority')
            
            if not attr_sources.exists():
                details['error'] = f"Attribute {attribute_name} not found"
                return False, details
            
            # Get highest priority value
            attr_value = attr_sources.first().attribute_value
            
            # Get comparison function
            if comparison_operator not in self.OPERATORS:
                details['error'] = f"Invalid comparison operator: {comparison_operator}"
                return False, details
                
            compare_func = self.OPERATORS[comparison_operator]
            
            # Convert values for comparison if needed
            attr_value, comparison_value = self._convert_values_for_comparison(
                attr_value, comparison_value
            )
            
            # Perform comparison
            result = compare_func(attr_value, comparison_value)
            
            details['attribute_name'] = attribute_name
            details['attribute_value'] = attr_value
            details['comparison_value'] = comparison_value
            details['comparison_operator'] = comparison_operator
            
            return result, details
            
        elif check_type == 'compare_attributes':
            # Compare two attribute values
            if not compare_to_attribute:
                details['error'] = "No comparison attribute specified"
                return False, details
                
            # Get first attribute value
            attr1_sources = AttributeSource.objects.filter(
                person=person,
                attribute_name=attribute_name,
                is_current=True,
                **datasource_filter
            ).order_by('-mapping__priority')
            
            if not attr1_sources.exists():
                details['error'] = f"Attribute {attribute_name} not found"
                return False, details
                
            attr1_value = attr1_sources.first().attribute_value
            
            # Get second attribute value
            attr2_sources = AttributeSource.objects.filter(
                person=person,
                attribute_name=compare_to_attribute,
                is_current=True,
                **datasource_filter
            ).order_by('-mapping__priority')
            
            if not attr2_sources.exists():
                details['error'] = f"Attribute {compare_to_attribute} not found"
                return False, details
                
            attr2_value = attr2_sources.first().attribute_value
            
            # Get comparison function
            if comparison_operator not in self.OPERATORS:
                details['error'] = f"Invalid comparison operator: {comparison_operator}"
                return False, details
                
            compare_func = self.OPERATORS[comparison_operator]
            
            # Convert values for comparison if needed
            attr1_value, attr2_value = self._convert_values_for_comparison(
                attr1_value, attr2_value
            )
            
            # Perform comparison
            result = compare_func(attr1_value, attr2_value)
            
            details['attribute1_name'] = attribute_name
            details['attribute1_value'] = attr1_value
            details['attribute2_name'] = compare_to_attribute
            details['attribute2_value'] = attr2_value
            details['comparison_operator'] = comparison_operator
            
            return result, details
            
        else:
            details['error'] = f"Unknown check type: {check_type}"
            return False, details
    
    def _convert_values_for_comparison(
        self, 
        value1: str, 
        value2: str
    ) -> Tuple[Any, Any]:
        """
        Attempt to convert string values to appropriate types for comparison.
        
        Args:
            value1: First value to convert
            value2: Second value to convert
            
        Returns:
            Tuple of converted values
        """
        # Try to convert to numeric types if both look like numbers
        try:
            # Check if both values represent integers
            if re.match(r'^\d+$', str(value1)) and re.match(r'^\d+$', str(value2)):
                return int(value1), int(value2)
                
            # Check if both values represent floats
            if (re.match(r'^\d+(\.\d+)?$', str(value1)) and 
                re.match(r'^\d+(\.\d+)?$', str(value2))):
                return float(value1), float(value2)
        except (ValueError, TypeError):
            pass
            
        # Handle boolean values
        if str(value1).lower() in ('true', 'yes', 'y', '1'):
            value1 = True
        elif str(value1).lower() in ('false', 'no', 'n', '0'):
            value1 = False
            
        if str(value2).lower() in ('true', 'yes', 'y', '1'):
            value2 = True
        elif str(value2).lower() in ('false', 'no', 'n', '0'):
            value2 = False
        
        # Return as strings if no conversion was applicable
        return value1, value2