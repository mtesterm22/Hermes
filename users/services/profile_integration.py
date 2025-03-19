# users/services/profile_integration.py
import logging
import re
from datetime import datetime
from django.db import transaction
from django.utils import timezone

from users.models import Person
from users.profile_integration import AttributeSource, ProfileAttributeChange, ProfileFieldMapping, IdentityResolutionConfig

logger = logging.getLogger(__name__)

class ProfileIntegrationService:
    """
    Service for integrating data source records with user profiles.
    """
    def __init__(self, datasource, sync=None):
        self.datasource = datasource
        self.sync = sync
        
        # Get identity resolution config or create default
        try:
            self.id_config = IdentityResolutionConfig.objects.get(datasource=datasource)
        except IdentityResolutionConfig.DoesNotExist:
            self.id_config = IdentityResolutionConfig(
                datasource=datasource,
                is_enabled=True,
                create_missing_profiles=False,
                matching_method='exact'
            )
            self.id_config.save()
        
        # Get field mappings
        self.mappings = list(ProfileFieldMapping.objects.filter(
            datasource=datasource,
            is_enabled=True
        ).select_related('source_field'))
        
        # Get key field mappings for identity resolution
        self.key_mappings = [m for m in self.mappings if m.is_key_field]
    
    def process_record(self, record_data, record_id=None):
        """
        Process a single record from a data source and update user profiles.
        
        Args:
            record_data: Dictionary of field values from the data source
            record_id: Optional ID of the record in the source system
        
        Returns:
            Tuple of (person, created, changes_count)
        """
        if not self.mappings:
            logger.warning(f"No field mappings configured for {self.datasource.name}")
            return None, False, 0
        
        # Skip processing if identity resolution is disabled
        if not self.id_config.is_enabled:
            logger.info(f"Identity resolution disabled for {self.datasource.name}")
            return None, False, 0
        
        # Debug log the record data and mappings
        logger.debug(f"Processing record: {record_data}")
        logger.debug(f"Key mappings: {[m.source_field.name for m in self.key_mappings]}")
        
        # Build key-value pairs for matching
        match_fields = {}
        for mapping in self.key_mappings:
            field_name = mapping.source_field.name
            if field_name in record_data and record_data[field_name]:
                match_fields[mapping.profile_attribute] = record_data[field_name]
        
        if not match_fields:
            logger.warning(f"No key fields found in record for {self.datasource.name}. Available fields: {list(record_data.keys())}")
            logger.warning(f"Key mappings: {[f'{m.source_field.name} -> {m.profile_attribute}' for m in self.key_mappings]}")
            return None, False, 0
        
        logger.info(f"Match fields: {match_fields}")
        
        # Find matching person
        person = self._find_matching_person(match_fields)
        logger.info(f"Matching person found: {person is not None}")
        
        # Create new person if needed and allowed
        created = False
        if not person and self.id_config.create_missing_profiles:
            logger.info(f"No match found, creating new person with {match_fields}")
            person = self._create_new_person(record_data)
            created = True
        
        # If we couldn't find or create a person, stop processing
        if not person:
            logger.warning("Could not find or create a matching person")
            return None, False, 0
        
        # Process all field mappings and update attributes
        changes_count = self._update_person_attributes(person, record_data, record_id)
        
        return person, created, changes_count
    
    def _find_matching_person(self, match_fields):
        """
        Find a person matching the given key fields using the configured matching method.
        """
        method = self.id_config.matching_method
        
        if method == 'exact':
            return self._exact_match(match_fields)
        elif method == 'case_insensitive':
            return self._case_insensitive_match(match_fields)
        elif method == 'fuzzy':
            return self._fuzzy_match(match_fields)
        elif method == 'custom':
            return self._custom_match(match_fields)
        else:
            logger.error(f"Unknown matching method: {method}")
            return None
    
    def _exact_match(self, match_fields):
        """
        Find an exact match for the given fields.
        """
        try:
            for attribute, value in match_fields.items():
                # Look for attribute sources that match this key
                attr_sources = AttributeSource.objects.filter(
                    attribute_name=attribute,
                    attribute_value=value,
                    is_current=True
                )
                
                if attr_sources.exists():
                    # Return the first matching person
                    return attr_sources.first().person
            
            return None
        except Exception as e:
            logger.error(f"Error in exact matching: {str(e)}")
            return None
    
    def _case_insensitive_match(self, match_fields):
        """
        Find a case-insensitive match for the given fields.
        """
        try:
            for attribute, value in match_fields.items():
                # Look for attribute sources that match this key (case insensitive)
                attr_sources = AttributeSource.objects.filter(
                    attribute_name=attribute,
                    attribute_value__iexact=value,
                    is_current=True
                )
                
                if attr_sources.exists():
                    # Return the first matching person
                    return attr_sources.first().person
            
            return None
        except Exception as e:
            logger.error(f"Error in case-insensitive matching: {str(e)}")
            return None
    
    def _fuzzy_match(self, match_fields):
        """
        Find a fuzzy match for the given fields.
        This is a simplified version - a real implementation would use a more 
        sophisticated fuzzy matching algorithm.
        """
        # Placeholder for fuzzy matching - would need a real implementation
        logger.warning("Fuzzy matching is not fully implemented")
        return self._case_insensitive_match(match_fields)
    
    def _custom_match(self, match_fields):
        """
        Find a match using custom matching logic defined in the config.
        """
        if not self.id_config.custom_matcher:
            logger.error("Custom matcher selected but no code provided")
            return None
        
        # Placeholder - would need a safe way to execute custom code
        logger.warning("Custom matching is not fully implemented")
        return None
    
    def _create_new_person(self, record_data):
        """
        Create a new person based on the record data.
        """
        try:
            from users.models import Person
            import uuid
            
            # Check if there's a unique_id in the mappings outside of transaction
            unique_id = None
            for mapping in self.mappings:
                if mapping.profile_attribute == 'unique_id':
                    field_name = mapping.source_field.name
                    if field_name in record_data and record_data[field_name]:
                        unique_id = record_data[field_name]
                        # Check if a person with this unique_id already exists
                        existing = Person.objects.filter(unique_id=unique_id).first()
                        if existing:
                            logger.warning(f"Person with unique_id '{unique_id}' already exists")
                            return existing
            
            # Use a shorter transaction
            with transaction.atomic():
                # Create a new Person with basic fields
                person_fields = {}
                
                # Find mappings that map to direct Person fields
                for mapping in self.mappings:
                    field_name = mapping.source_field.name
                    attr_name = mapping.profile_attribute
                    
                    # Only include fields that exist on the Person model and have values
                    if hasattr(Person, attr_name) and field_name in record_data and record_data[field_name]:
                        person_fields[attr_name] = record_data[field_name]
                
                # If no unique_id was found or it was empty, generate one
                if 'unique_id' not in person_fields or not person_fields['unique_id']:
                    person_fields['unique_id'] = str(uuid.uuid4())
                
                # Generate a display name if not provided
                if 'display_name' not in person_fields:
                    if 'first_name' in person_fields and 'last_name' in person_fields:
                        person_fields['display_name'] = f"{person_fields['first_name']} {person_fields['last_name']}"
                    elif 'email' in person_fields:
                        person_fields['display_name'] = person_fields['email'].split('@')[0]
                    elif 'unique_id' in person_fields:
                        person_fields['display_name'] = f"User {person_fields['unique_id']}"
                
                # Set status to active by default
                if 'status' not in person_fields:
                    person_fields['status'] = 'active'
                
                # Create the person
                logger.info(f"Creating person with fields: {person_fields}")
                person = Person.objects.create(**person_fields)
                
                logger.info(f"Created new person: {person.display_name or person.id}")
                return person
        except Exception as e:
            logger.error(f"Error creating new person: {str(e)}")
            logger.exception("Detailed traceback:")
            return None

    
    def _update_person_attributes(self, person, record_data, record_id):
        """
        Update a person's attributes based on record data and return the number of changes.
        """
        changes_count = 0
        
        try:
            # Process each field mapping - using smaller transactions
            for mapping in self.mappings:
                field_name = mapping.source_field.name
                if field_name not in record_data:
                    continue
                
                # Get the attribute value
                value = record_data[field_name]
                
                # Apply transformations if needed
                if mapping.mapping_type == 'transform' and mapping.transformation_logic:
                    value = self._apply_transformation(value, mapping.transformation_logic)
                
                if value is None:
                    continue
                
                # Convert to string for storage
                if not isinstance(value, str):
                    value = str(value)
                
                # Handle attribute update based on mapping type - in its own transaction
                try:
                    with transaction.atomic():
                        if mapping.is_multivalued:
                            changes = self._update_multi_valued_attribute(person, mapping, value, record_id)
                        else:
                            changes = self._update_single_valued_attribute(person, mapping, value, record_id)
                    
                    changes_count += changes
                except Exception as attr_error:
                    logger.error(f"Error updating attribute {mapping.profile_attribute}: {str(attr_error)}")
                    # Continue with next attribute
            
            return changes_count
        except Exception as e:
            logger.error(f"Error updating person attributes: {str(e)}")
            return 0
    
    def _apply_transformation(self, value, transformation_logic):
        """
        Apply a transformation to a value using the provided logic.
        """
        # Placeholder - would need a safe way to execute transformations
        # For now, just return the original value
        return value
    
    def _update_single_valued_attribute(self, person, mapping, value, record_id):
        """
        Update a single-valued attribute and track changes.
        """
        attribute_name = mapping.profile_attribute
        
        # Check for existing attribute from this source
        try:
            existing = AttributeSource.objects.get(
                person=person,
                attribute_name=attribute_name,
                datasource=self.datasource,
                is_current=True
            )
            
            # If value hasn't changed, do nothing
            if existing.attribute_value == value:
                return 0
            
            # Mark the existing value as no longer current
            existing.is_current = False
            existing.save()
            
            # Record the change
            ProfileAttributeChange.objects.create(
                person=person,
                attribute_name=attribute_name,
                old_value=existing.attribute_value,
                new_value=value,
                change_type='modify',
                datasource=self.datasource,
                sync=self.sync
            )
            
        except AttributeSource.DoesNotExist:
            # This is a new attribute for this person from this source
            ProfileAttributeChange.objects.create(
                person=person,
                attribute_name=attribute_name,
                new_value=value,
                change_type='add',
                datasource=self.datasource,
                sync=self.sync
            )
        
        # Create new current attribute
        AttributeSource.objects.create(
            person=person,
            attribute_name=attribute_name,
            attribute_value=value,
            datasource=self.datasource,
            mapping=mapping,
            source_record_id=record_id or '',
            is_current=True
        )
        
        return 1
    
    def _update_multi_valued_attribute(self, person, mapping, value, record_id):
        """
        Update a multi-valued attribute and track changes.
        """
        attribute_name = mapping.profile_attribute
        
        # For multi-valued attributes, we check if this specific value already exists
        try:
            existing = AttributeSource.objects.get(
                person=person,
                attribute_name=attribute_name,
                attribute_value=value,
                datasource=self.datasource
            )
            
            # If it exists but was marked as not current, mark it as current again
            if not existing.is_current:
                existing.is_current = True
                existing.last_updated = timezone.now()
                existing.save()
                
                # Record the re-addition
                ProfileAttributeChange.objects.create(
                    person=person,
                    attribute_name=attribute_name,
                    new_value=value,
                    change_type='add',
                    datasource=self.datasource,
                    sync=self.sync
                )
                
                return 1
            
            # If it's already current, no change needed
            return 0
            
        except AttributeSource.DoesNotExist:
            # This is a new value for this multi-valued attribute
            AttributeSource.objects.create(
                person=person,
                attribute_name=attribute_name,
                attribute_value=value,
                datasource=self.datasource,
                mapping=mapping,
                source_record_id=record_id or '',
                is_current=True
            )
            
            # Record the addition
            ProfileAttributeChange.objects.create(
                person=person,
                attribute_name=attribute_name,
                new_value=value,
                change_type='add',
                datasource=self.datasource,
                sync=self.sync
            )
            
            return 1
    
    def remove_missing_attributes(self, current_record_ids):
        """
        Mark attributes as removed if they came from records no longer in the data source.
        Only applicable for data sources that provide record IDs.
        
        Args:
            current_record_ids: List of record IDs currently in the data source
        
        Returns:
            Number of attributes removed
        """
        if not current_record_ids:
            # Can't determine what's missing without record IDs
            return 0
        
        removed_count = 0
        
        # Find attribute sources from this data source with record IDs not in the current set
        to_remove = AttributeSource.objects.filter(
            datasource=self.datasource,
            is_current=True
        ).exclude(source_record_id='').exclude(source_record_id__in=current_record_ids)
        
        for attr in to_remove:
            # Mark as not current
            attr.is_current = False
            attr.save()
            
            # Record the removal
            ProfileAttributeChange.objects.create(
                person=attr.person,
                attribute_name=attr.attribute_name,
                old_value=attr.attribute_value,
                change_type='remove',
                datasource=self.datasource,
                sync=self.sync
            )
            
            removed_count += 1
        
        return removed_count