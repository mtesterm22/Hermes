# workflows/actions/profile_query_action.py
"""
Profile query action for workflows.

This module implements a profile query action that can find users whose profile attributes
match various conditions, supporting existence checks, value comparisons, and more.
It returns a list of matching profiles rather than validating a single profile.
"""

import logging
import time
import traceback
from typing import Dict, Any, Optional, Tuple, List, Union
import operator
import re
from datetime import datetime

from django.utils import timezone
from django.db.models import Q, F, Value, Count
from django.db.models.functions import Coalesce

from users.models import Person
from users.profile_integration import AttributeSource
from workflows.models import Action, ActionExecution

logger = logging.getLogger(__name__)

class ProfileQueryAction:
    """
    Implementation of profile query action for workflows.
    
    This action allows searching for user profiles based on attribute criteria,
    returning a list of matching profiles rather than a single match result.
    It's useful for generating lists of users that meet certain criteria.
    """
    
    # Map string operation names to Q object operations
    OPERATORS = {
        'equals': lambda field, value: Q(**{f"{field}": value}),
        'not_equals': lambda field, value: ~Q(**{f"{field}": value}),
        'contains': lambda field, value: Q(**{f"{field}__contains": value}),
        'not_contains': lambda field, value: ~Q(**{f"{field}__contains": value}),
        'greater_than': lambda field, value: Q(**{f"{field}__gt": value}),
        'less_than': lambda field, value: Q(**{f"{field}__lt": value}),
        'greater_than_or_equal': lambda field, value: Q(**{f"{field}__gte": value}),
        'less_than_or_equal': lambda field, value: Q(**{f"{field}__lte": value}),
        'starts_with': lambda field, value: Q(**{f"{field}__startswith": value}),
        'ends_with': lambda field, value: Q(**{f"{field}__endswith": value}),
        'matches_regex': lambda field, value: Q(**{f"{field}__regex": value}),
        'is_null': lambda field, value: Q(**{f"{field}__isnull": True}),
        'is_not_null': lambda field, value: Q(**{f"{field}__isnull": False}),
    }
    
    def __init__(self, action: Action):
        """
        Initialize the profile query action.
        
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
        Execute the profile query action.
        
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
            query_type = params.get('query_type', 'attribute_exists')
            attribute_name = params.get('attribute_name', '')
            comparison_value = params.get('comparison_value', '')
            comparison_operator = params.get('comparison_operator', 'equals')
            datasource_id = params.get('datasource_id')
            # Maximum number of profiles to return (0 for unlimited)
            max_results = params.get('max_results', 1000)
            # Include profile details level
            detail_level = params.get('detail_level', 'basic')  # basic, full, or custom
            # Custom fields to include in the results
            custom_fields = params.get('custom_fields', [])
            # Boolean to include attribute sources in results
            include_attributes = params.get('include_attributes', False)
            # Optional field to group results by
            group_by = params.get('group_by', '')
            
            # Validate parameters based on query type
            if query_type != 'all_profiles':
                if not attribute_name and query_type != 'datasource_exists':
                    error_message = "No attribute name specified for attribute query"
                    action_execution.complete('error', error_message=error_message)
                    return False, {"error": error_message, "success": False}
                
                if query_type == 'attribute_compare' and not comparison_operator:
                    error_message = "No comparison operator specified for comparison query"
                    action_execution.complete('error', error_message=error_message)
                    return False, {"error": error_message, "success": False}
            
            # Find matching profiles
            profiles, query_details = self._find_matching_profiles(
                query_type=query_type,
                attribute_name=attribute_name,
                comparison_value=comparison_value,
                comparison_operator=comparison_operator,
                datasource_id=datasource_id,
                max_results=max_results,
                group_by=group_by
            )
            
            # Prepare profile data for results
            profile_results = self._prepare_profile_results(
                profiles=profiles,
                detail_level=detail_level,
                custom_fields=custom_fields,
                include_attributes=include_attributes,
                attribute_name=attribute_name if query_type != 'all_profiles' else None,
                datasource_id=datasource_id
            )
            
            # Prepare result data
            execution_time = time.time() - start_time
            result_data = {
                "success": True,
                "execution_time": f"{execution_time:.2f}s",
                "total_profiles": len(profiles),
                "query_details": query_details,
                "profiles": profile_results,
                "run_date": datetime.now().isoformat()
            }
            
            # Add grouping results if applicable
            if group_by and isinstance(profiles, dict):
                result_data["groups"] = profiles
                result_data["total_profiles"] = sum(len(profiles[group]) for group in profiles)
            
            # Complete the execution
            action_execution.complete('success', output_data=result_data)
            
            return True, result_data
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"Error executing profile query action: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_message)
            
            # Complete the execution with error
            action_execution.complete('error', error_message=str(e))
            
            return False, {
                "success": False,
                "execution_time": f"{execution_time:.2f}s",
                "error": str(e)
            }
    
    def _find_matching_profiles(
        self, 
        query_type: str,
        attribute_name: str,
        comparison_value: str,
        comparison_operator: str,
        datasource_id: Optional[int] = None,
        max_results: int = 1000,
        group_by: str = ''
    ) -> Tuple[Union[List[Person], Dict[str, List[Person]]], Dict[str, Any]]:
        """
        Find all profiles matching the specified criteria.
        
        Args:
            query_type: Type of query to perform
            attribute_name: Name of the attribute to query
            comparison_value: Value to compare against
            comparison_operator: Comparison operator to use
            datasource_id: Optional ID of the datasource to filter by
            max_results: Maximum number of results to return
            group_by: Optional field to group results by
            
        Returns:
            Tuple of (matching_profiles, query_details)
        """
        query_details = {
            "query_type": query_type,
            "attribute_name": attribute_name,
            "comparison_value": comparison_value,
            "comparison_operator": comparison_operator,
            "datasource_id": datasource_id,
            "max_results": max_results,
            "filter_query": ""
        }
        
        # Create datasource filter
        datasource_filter = {}
        if datasource_id:
            try:
                datasource_id = int(datasource_id)
                datasource_filter['datasource_id'] = datasource_id
                from datasources.models import DataSource
                datasource = DataSource.objects.get(id=datasource_id)
                query_details['datasource_name'] = datasource.name
            except (ValueError, TypeError, DataSource.DoesNotExist):
                query_details['error'] = f"Invalid datasource ID: {datasource_id}"
        
        # Find profiles based on query type
        if query_type == 'all_profiles':
            # Simplest case - get all profiles
            profiles = Person.objects.all()
            
            # Apply max results limit
            if max_results > 0:
                profiles = profiles[:max_results]
            
            query_details['filter_query'] = "All profiles"
            
        elif query_type == 'attribute_exists':
            # Find profiles where the attribute exists
            attr_sources = AttributeSource.objects.filter(
                attribute_name=attribute_name,
                is_current=True,
                **datasource_filter
            ).values('person_id').distinct()
            
            profiles = Person.objects.filter(id__in=attr_sources)
            
            # Apply max results limit
            if max_results > 0:
                profiles = profiles[:max_results]
            
            query_details['filter_query'] = f"Attribute '{attribute_name}' exists"
            
        elif query_type == 'attribute_not_exists':
            # Find profiles where the attribute doesn't exist
            attr_sources = AttributeSource.objects.filter(
                attribute_name=attribute_name,
                is_current=True,
                **datasource_filter
            ).values('person_id').distinct()
            
            profiles = Person.objects.exclude(id__in=attr_sources)
            
            # Apply max results limit
            if max_results > 0:
                profiles = profiles[:max_results]
            
            query_details['filter_query'] = f"Attribute '{attribute_name}' does not exist"
            
        elif query_type == 'datasource_exists':
            # Find profiles with any data from a specific datasource
            if not datasource_id:
                query_details['error'] = "No datasource specified for datasource_exists query"
                return [], query_details
                
            attr_sources = AttributeSource.objects.filter(
                is_current=True,
                **datasource_filter
            ).values('person_id').distinct()
            
            profiles = Person.objects.filter(id__in=attr_sources)
            
            # Apply max results limit
            if max_results > 0:
                profiles = profiles[:max_results]
            
            query_details['filter_query'] = f"Has any attribute from datasource {query_details.get('datasource_name', datasource_id)}"
            
        elif query_type == 'attribute_compare':
            # Find profiles where the attribute meets comparison criteria
            if comparison_operator not in self.OPERATORS:
                query_details['error'] = f"Invalid comparison operator: {comparison_operator}"
                return [], query_details
            
            # Get attribute sources matching the criteria
            attr_query_field = 'attribute_value'
            
            # Get the Q object for this comparison
            query_func = self.OPERATORS[comparison_operator]
            q_filter = query_func(attr_query_field, comparison_value)
            
            # Add base filters
            attr_sources = AttributeSource.objects.filter(
                attribute_name=attribute_name,
                is_current=True,
                **datasource_filter
            ).filter(q_filter).values('person_id').distinct()
            
            profiles = Person.objects.filter(id__in=attr_sources)
            
            # Apply max results limit
            if max_results > 0:
                profiles = profiles[:max_results]
            
            query_details['filter_query'] = f"Attribute '{attribute_name}' {comparison_operator} '{comparison_value}'"
            
        else:
            query_details['error'] = f"Unknown query type: {query_type}"
            return [], query_details
        
        # Apply grouping if requested
        if group_by:
            return self._group_profiles(profiles, group_by), query_details
        
        return list(profiles), query_details
    
    def _group_profiles(self, profiles, group_by: str) -> Dict[str, List[Person]]:
        """
        Group profiles by a specified field.
        
        Args:
            profiles: QuerySet of Person objects
            group_by: Field to group by
            
        Returns:
            Dictionary of group name -> list of profiles
        """
        grouped_profiles = {}
        
        # Handle special grouping types
        if group_by == 'first_letter':
            # Group by first letter of display name
            for profile in profiles:
                name = profile.display_name or profile.full_name or profile.unique_id
                letter = name[0].upper() if name else '#'
                if not letter.isalpha():
                    letter = '#'
                
                if letter not in grouped_profiles:
                    grouped_profiles[letter] = []
                grouped_profiles[letter].append(profile)
            
        elif group_by == 'status':
            # Group by profile status
            for profile in profiles:
                status = profile.status or 'unknown'
                if status not in grouped_profiles:
                    grouped_profiles[status] = []
                grouped_profiles[status].append(profile)
                
        else:
            # Try to group by a profile field
            valid_fields = ['first_name', 'last_name', 'email', 'status']
            
            if group_by in valid_fields:
                for profile in profiles:
                    value = getattr(profile, group_by, '') or 'None'
                    if value not in grouped_profiles:
                        grouped_profiles[value] = []
                    grouped_profiles[value].append(profile)
            else:
                # Try to group by an attribute
                # Get all attribute sources for the attribute
                attr_sources = AttributeSource.objects.filter(
                    person__in=profiles,
                    attribute_name=group_by,
                    is_current=True
                ).select_related('person')
                
                # Create a mapping of person_id to attribute value
                person_attr_map = {}
                for source in attr_sources:
                    person_attr_map[source.person_id] = source.attribute_value
                
                # Group profiles by attribute value
                for profile in profiles:
                    value = person_attr_map.get(profile.id, 'None')
                    if value not in grouped_profiles:
                        grouped_profiles[value] = []
                    grouped_profiles[value].append(profile)
        
        return grouped_profiles
    
    def _prepare_profile_results(
        self,
        profiles: Union[List[Person], Dict[str, List[Person]]],
        detail_level: str = 'basic',
        custom_fields: List[str] = None,
        include_attributes: bool = False,
        attribute_name: Optional[str] = None,
        datasource_id: Optional[int] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        """
        Prepare profile data for results based on detail level.
        
        Args:
            profiles: List of profiles or dictionary of grouped profiles
            detail_level: Level of detail to include ('basic', 'full', or 'custom')
            custom_fields: List of specific fields to include when detail_level is 'custom'
            include_attributes: Whether to include attribute sources
            attribute_name: Optional attribute to include specifically
            datasource_id: Optional datasource ID to filter attributes by
            
        Returns:
            List of profile data dictionaries or grouped dictionaries
        """
        if isinstance(profiles, dict):
            # Handle grouped profiles
            grouped_results = {}
            for group, group_profiles in profiles.items():
                grouped_results[group] = self._format_profiles(
                    group_profiles,
                    detail_level,
                    custom_fields,
                    include_attributes,
                    attribute_name,
                    datasource_id
                )
            return grouped_results
        else:
            # Handle flat list of profiles
            return self._format_profiles(
                profiles,
                detail_level,
                custom_fields,
                include_attributes,
                attribute_name,
                datasource_id
            )
    
    def _format_profiles(
        self,
        profiles: List[Person],
        detail_level: str,
        custom_fields: List[str],
        include_attributes: bool,
        attribute_name: Optional[str],
        datasource_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """
        Format profiles into a list of dictionaries.
        
        Args:
            profiles: List of Person objects
            detail_level: Level of detail to include
            custom_fields: List of specific fields to include
            include_attributes: Whether to include attribute sources
            attribute_name: Optional attribute to include specifically
            datasource_id: Optional datasource ID to filter attributes by
            
        Returns:
            List of formatted profile dictionaries
        """
        results = []
        
        # Prefetch attribute sources if needed
        if include_attributes or attribute_name:
            profile_ids = [p.id for p in profiles]
            
            # Build the attribute filter
            attr_filter = {
                'person_id__in': profile_ids,
                'is_current': True
            }
            
            if attribute_name:
                attr_filter['attribute_name'] = attribute_name
                
            if datasource_id:
                attr_filter['datasource_id'] = datasource_id
                
            # Get relevant attribute sources
            attr_sources = AttributeSource.objects.filter(
                **attr_filter
            ).select_related('datasource')
            
            # Create a mapping of person_id to attribute sources
            person_attrs = {}
            for source in attr_sources:
                if source.person_id not in person_attrs:
                    person_attrs[source.person_id] = []
                person_attrs[source.person_id].append(source)
                
        for profile in profiles:
            # Build profile data based on detail level
            profile_data = {}
            
            if detail_level == 'basic':
                # Basic info - just enough to identify the profile
                profile_data = {
                    'id': profile.id,
                    'unique_id': profile.unique_id,
                    'display_name': profile.display_name or profile.full_name,
                    'email': profile.email,
                    'status': profile.status
                }
            elif detail_level == 'full':
                # Full info - all fields from the Person model
                profile_data = {
                    'id': profile.id,
                    'unique_id': profile.unique_id,
                    'first_name': profile.first_name,
                    'last_name': profile.last_name,
                    'display_name': profile.display_name,
                    'email': profile.email,
                    'secondary_email': profile.secondary_email,
                    'phone': profile.phone,
                    'status': profile.status,
                    'created_at': profile.created_at.isoformat() if profile.created_at else None,
                    'modified_at': profile.modified_at.isoformat() if profile.modified_at else None
                }
                
                # Include any JSON attributes stored directly on Person
                if hasattr(profile, 'attributes') and profile.attributes:
                    profile_data['person_attributes'] = profile.attributes
            
            elif detail_level == 'custom':
                # Custom fields only
                if not custom_fields:
                    custom_fields = ['id', 'unique_id', 'display_name']
                    
                for field in custom_fields:
                    if hasattr(profile, field):
                        value = getattr(profile, field)
                        # Format datetime objects
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        profile_data[field] = value
            
            # Include the specific attribute that was queried, if applicable
            if attribute_name and profile.id in person_attrs:
                matching_attrs = [src for src in person_attrs[profile.id] 
                                if src.attribute_name == attribute_name]
                
                if matching_attrs:
                    # Get highest priority attribute source
                    matching_attrs.sort(key=lambda x: x.mapping.priority if x.mapping else 0, reverse=True)
                    attr_source = matching_attrs[0]
                    
                    profile_data[attribute_name] = attr_source.attribute_value
                    profile_data[f"{attribute_name}_source"] = attr_source.datasource.name if attr_source.datasource else None
            
            # Include all attributes if requested
            if include_attributes and profile.id in person_attrs:
                attributes = {}
                for attr_source in person_attrs[profile.id]:
                    attr_name = attr_source.attribute_name
                    
                    # Build attribute info with value and source
                    attr_info = {
                        'value': attr_source.attribute_value,
                        'source': attr_source.datasource.name if attr_source.datasource else None,
                        'last_updated': attr_source.last_updated.isoformat() if attr_source.last_updated else None
                    }
                    
                    attributes[attr_name] = attr_info
                
                profile_data['attributes'] = attributes
            
            results.append(profile_data)
            
        return results