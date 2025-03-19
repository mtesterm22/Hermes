# users/management/commands/test_profile_integration.py
from django.core.management.base import BaseCommand
from django.db import transaction
from datasources.models import DataSource, DataSourceField, DataSourceSync
from datasources.csv_models import CSVDataSource, CSVFileUpload
from datasources.connectors.csv_connector import CSVConnector
from users.profile_integration import ProfileFieldMapping, IdentityResolutionConfig
from users.services.profile_integration import ProfileIntegrationService
import csv
import os
import tempfile
from django.core.files.base import ContentFile
from django.utils import timezone


class Command(BaseCommand):
    help = 'Test populating user profiles from a CSV data source'

    def add_arguments(self, parser):
        parser.add_argument('--create', action='store_true', help='Create test profiles')
        parser.add_argument('--clear', action='store_true', help='Clear test data')

    def handle(self, *args, **options):
        if options['clear']:
            self._clear_test_data()
            return

        if options['create']:
            datasource = self._create_test_datasource()
            self._create_test_csv(datasource)
            self._create_field_mappings(datasource)
            self._configure_identity_resolution(datasource)
            self._process_data(datasource)
        else:
            self.stdout.write(self.style.WARNING('Please specify an action: --create or --clear'))

    def _clear_test_data(self):
        """Clear test data from the database"""
        # Delete test data source and associated data
        DataSource.objects.filter(name='Test User Profiles').delete()
        self.stdout.write(self.style.SUCCESS('Cleared test data'))

    def _create_test_datasource(self):
        """Create a test CSV data source"""
        # Create the base data source
        datasource = DataSource.objects.create(
            name='Test User Profiles',
            description='Test data source for populating user profiles',
            type='csv',
            status='active'
        )

        # Create CSV settings
        csv_settings = CSVDataSource.objects.create(
            datasource=datasource,
            file_location='upload',
            delimiter=',',
            has_header=True,
            encoding='utf-8'
        )

        self.stdout.write(self.style.SUCCESS(f'Created test data source: {datasource.name}'))
        return datasource

    def _create_test_csv(self, datasource):
        """Create and upload a test CSV file"""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w', newline='') as temp_file:
            writer = csv.writer(temp_file)
            
            # Write header
            writer.writerow(['id', 'first_name', 'last_name', 'email', 'secondary_email', 'department', 'phone', 'active'])
            
            # Write sample data
            writer.writerow(['1001', 'John', 'Doe', 'john.doe@example.com', 'johnd@personal.com', 'Engineering', '555-123-4567', 'Yes'])
            writer.writerow(['1002', 'Jane', 'Smith', 'jane.smith@example.com', '', 'Marketing', '555-987-6543', 'Yes'])
            writer.writerow(['1003', 'Bob', 'Johnson', 'bob.johnson@example.com', 'bob@personal.com', 'Finance', '555-246-8101', 'Yes'])
            writer.writerow(['1004', 'Alice', 'Williams', 'alice.williams@example.com', '', 'Product', '555-369-1470', 'Yes'])
            writer.writerow(['1005', 'Charlie', 'Brown', 'charlie.brown@example.com', 'charlie@personal.com', 'Engineering', '555-258-1472', 'No'])

        temp_file_path = temp_file.name
        
        # Get the CSV settings
        csv_settings = CSVDataSource.objects.get(datasource=datasource)
        
        # Create an upload record
        with open(temp_file_path, 'rb') as f:
            file_content = f.read()
        
        upload = CSVFileUpload(csv_datasource=csv_settings)
        upload.file.save('test_users.csv', ContentFile(file_content))
        upload.file_size = len(file_content)
        upload.row_count = 5  # We know there are 5 data rows
        upload.save()
        
        # Auto-detect fields using the connector
        connector = CSVConnector(datasource)
        detected_fields = connector.detect_fields()
        
        with transaction.atomic():
            # Clear any existing fields first
            DataSourceField.objects.filter(datasource=datasource).delete()
            
            # Create the detected fields
            for field_dict in detected_fields:
                DataSourceField.objects.create(
                    datasource=datasource,
                    **field_dict
                )
        
        self.stdout.write(self.style.SUCCESS(f'Created test CSV file with 5 users and detected {len(detected_fields)} fields'))
        
        # Clean up the temporary file
        os.unlink(temp_file_path)

    def _create_field_mappings(self, datasource):
        """Create field mappings for the data source"""
        # Get fields
        fields = DataSourceField.objects.filter(datasource=datasource)
        field_dict = {field.name: field for field in fields}
        
        # Create mappings
        mappings = [
            # Basic profile attributes
            ('id', 'unique_id', True, 100, False),  # Key field for matching
            ('first_name', 'first_name', False, 100, False),
            ('last_name', 'last_name', False, 100, False),
            ('email', 'email', True, 100, False),  # Also a key field
            ('secondary_email', 'secondary_email', False, 100, False),
            ('phone', 'phone', False, 100, False),
            
            # Additional attributes stored as attribute values
            ('department', 'department', False, 100, False),
            ('active', 'active', False, 100, False),
        ]
        
        # Clear existing mappings
        ProfileFieldMapping.objects.filter(datasource=datasource).delete()
        
        # Create new mappings
        for field_name, attribute_name, is_key, priority, is_multi in mappings:
            if field_name in field_dict:
                ProfileFieldMapping.objects.create(
                    datasource=datasource,
                    source_field=field_dict[field_name],
                    profile_attribute=attribute_name,
                    mapping_type='direct',
                    is_key_field=is_key,
                    priority=priority,
                    is_multivalued=is_multi,
                    is_enabled=True
                )
        
        mapping_count = ProfileFieldMapping.objects.filter(datasource=datasource).count()
        self.stdout.write(self.style.SUCCESS(f'Created {mapping_count} field mappings'))

    def _configure_identity_resolution(self, datasource):
        """Configure identity resolution settings"""
        # Delete any existing config
        IdentityResolutionConfig.objects.filter(datasource=datasource).delete()
        
        # Create new config
        IdentityResolutionConfig.objects.create(
            datasource=datasource,
            is_enabled=True,
            create_missing_profiles=True,  # Create new profiles when no match found
            matching_method='case_insensitive',
            match_confidence_threshold=0.9
        )
        
        self.stdout.write(self.style.SUCCESS(f'Configured identity resolution'))

    def _process_data(self, datasource):
        """Process the CSV data to create/update profiles"""
        # Create a sync record
        sync = DataSourceSync.objects.create(
            datasource=datasource,
            status='running',
        )
        
        try:
            # Get the CSV connector
            connector = CSVConnector(datasource)
            
            # Get the file path
            file_path = connector._get_file_path()
            
            # Set up the profile integration service
            profile_service = ProfileIntegrationService(datasource, sync)
            
            # Process the CSV file
            created_count = 0
            updated_count = 0
            record_ids = []
            
            with open(file_path, 'r', encoding=connector.csv_settings.encoding) as f:
                reader = csv.reader(f, delimiter=connector.csv_settings.delimiter)
                
                # Skip header if needed
                if connector.csv_settings.has_header:
                    next(reader)
                
                # Process each row
                for row in reader:
                    # Convert row to a dictionary
                    fields = DataSourceField.objects.filter(datasource=datasource).order_by('id')
                    record_data = {fields[i].name: value for i, value in enumerate(row) if i < len(fields)}
                    
                    # Store the record ID if available
                    if 'id' in record_data:
                        record_ids.append(record_data['id'])
                    
                    # Process the record
                    person, created, changes = profile_service.process_record(record_data, record_data.get('id', ''))
                    
                    if created:
                        created_count += 1
                    elif changes > 0:
                        updated_count += 1
                    
                    if person:
                        self.stdout.write(f"Processed record for {person.first_name} {person.last_name}: {'Created' if created else 'Updated'} with {changes} changes")
            
            # Handle cleanup of missing records
            if record_ids:
                removed_count = profile_service.remove_missing_attributes(record_ids)
                self.stdout.write(f"Removed {removed_count} attributes from records no longer in the source")
            
            # Update sync status
            sync.status = 'success'
            sync.end_time = timezone.now()
            sync.records_processed = created_count + updated_count
            sync.records_created = created_count
            sync.records_updated = updated_count
            sync.save()
            
            # Update datasource status
            datasource.status = 'active'
            datasource.last_sync = timezone.now()
            datasource.sync_count += 1
            datasource.save()
            
            self.stdout.write(self.style.SUCCESS(
                f'Successfully processed data: {created_count} profiles created, {updated_count} profiles updated'
            ))
            
        except Exception as e:
            # Update sync status
            sync.status = 'error'
            sync.end_time = timezone.now()
            sync.error_message = str(e)
            sync.save()
            
            # Update datasource status
            datasource.status = 'error'
            datasource.save()
            
            self.stdout.write(self.style.ERROR(f'Error processing data: {str(e)}'))
            raise