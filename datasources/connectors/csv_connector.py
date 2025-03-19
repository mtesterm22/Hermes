# datasources/connectors/csv_connector.py
import os
import csv
import codecs
from datetime import datetime
import logging
from django.utils import timezone
from django.core.files.storage import default_storage
from django.db import transaction

from ..models import DataSource, DataSourceField, DataSourceSync
from ..csv_models import CSVDataSource, CSVFileUpload

logger = logging.getLogger(__name__)

class CSVConnector:
    """
    Connector for CSV data sources.
    """
    def __init__(self, datasource):
        """
        Initialize with a DataSource instance.
        """
        self.datasource = datasource
        try:
            self.csv_settings = datasource.csv_settings
        except CSVDataSource.DoesNotExist:
            raise ValueError("CSV settings not found for this data source")
        
        self.sync = None
    
    def _get_file_path(self):
        """
        Get the file path based on the location type.
        """
        if self.csv_settings.file_location == 'upload':
            # Get the most recent upload
            latest_upload = self.csv_settings.uploads.order_by('-uploaded_at').first()
            if not latest_upload:
                raise ValueError("No uploaded file found for this data source")
            return latest_upload.file.path
        elif self.csv_settings.file_location == 'local':
            # Check if file exists
            if not os.path.exists(self.csv_settings.file_path):
                raise ValueError(f"Local file not found: {self.csv_settings.file_path}")
            return self.csv_settings.file_path
        elif self.csv_settings.file_location in ['sftp', 's3']:
            # These would require additional implementation
            raise NotImplementedError(f"{self.csv_settings.get_file_location_display()} not implemented yet")
        else:
            raise ValueError(f"Unknown file location: {self.csv_settings.file_location}")
    
    def detect_fields(self):
        """
        Auto-detect fields from CSV header or first data row.
        Returns a list of DataSourceField dictionaries.
        """
        try:
            file_path = self._get_file_path()
            fields = []
            
            with codecs.open(file_path, 'r', encoding=self.csv_settings.encoding) as f:
                reader = csv.reader(f, delimiter=self.csv_settings.delimiter, quotechar=self.csv_settings.quote_char)
                
                # Skip rows if needed
                for _ in range(self.csv_settings.skip_rows):
                    next(reader, None)
                
                # Read the header row if present, otherwise use the first data row
                if self.csv_settings.has_header:
                    header_row = next(reader, None)
                    if not header_row:
                        raise ValueError("CSV file is empty after skipping rows")
                    
                    # Create field entries from header names
                    for i, name in enumerate(header_row):
                        field_name = name.strip() or f"col_{i+1}"
                        fields.append({
                            'name': field_name,
                            'display_name': field_name,
                            'field_type': 'text',  # Default type, will be refined later
                            'is_key': False,
                            'is_nullable': True,
                            'sample_data': ''
                        })
                    
                    # Get first data row for samples
                    sample_row = next(reader, None)
                    if sample_row:
                        for i, value in enumerate(sample_row):
                            if i < len(fields):
                                fields[i]['sample_data'] = value
                                # Try to determine field type
                                fields[i]['field_type'] = self._guess_field_type(value)
                else:
                    # No header, use first data row for field names and samples
                    first_row = next(reader, None)
                    if not first_row:
                        raise ValueError("CSV file is empty after skipping rows")
                    
                    for i, value in enumerate(first_row):
                        field_name = f"col_{i+1}"
                        fields.append({
                            'name': field_name,
                            'display_name': field_name,
                            'field_type': self._guess_field_type(value),
                            'is_key': False,
                            'is_nullable': True,
                            'sample_data': value
                        })
            
            return fields
        except Exception as e:
            logger.error(f"Error detecting fields: {str(e)}")
            raise
    
    def _guess_field_type(self, value):
        """
        Try to guess the field type from a sample value.
        """
        if not value or value.strip() == '':
            return 'text'
        
        value = value.strip()
        
        # Check if boolean
        if value.lower() in ['true', 'false', 'yes', 'no', 't', 'f', 'y', 'n', '1', '0']:
            return 'boolean'
        
        # Check if integer
        try:
            int(value)
            return 'integer'
        except ValueError:
            pass
        
        # Check if float
        try:
            float(value)
            return 'float'
        except ValueError:
            pass
        
        # Check if date
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d']:
            try:
                datetime.strptime(value, fmt)
                return 'date'
            except ValueError:
                pass
        
        # Check if datetime
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%m/%d/%Y %H:%M:%S']:
            try:
                datetime.strptime(value, fmt)
                return 'datetime'
            except ValueError:
                pass
        
        # Default to text
        return 'text'
    
    def process_upload(self, file_obj):
        """
        Process a newly uploaded CSV file.
        """
        try:
            # Store the file
            upload = CSVFileUpload(csv_datasource=self.csv_settings)
            upload.file.save(file_obj.name, file_obj)
            upload.file_size = file_obj.size
            
            # Count rows
            row_count = 0
            with codecs.open(upload.file.path, 'r', encoding=self.csv_settings.encoding) as f:
                reader = csv.reader(f, delimiter=self.csv_settings.delimiter, quotechar=self.csv_settings.quote_char)
                for _ in reader:
                    row_count += 1
            
            # Adjust count if there's a header
            if self.csv_settings.has_header and row_count > 0:
                row_count -= 1
            
            upload.row_count = row_count
            upload.save()
            
            # If this is the first upload, try to detect fields
            if self.datasource.fields.count() == 0:
                try:
                    detected_fields = self.detect_fields()
                    with transaction.atomic():
                        for field_dict in detected_fields:
                            DataSourceField.objects.create(
                                datasource=self.datasource,
                                **field_dict
                            )
                except Exception as e:
                    logger.error(f"Error auto-detecting fields: {str(e)}")
            
            return upload
        except Exception as e:
            logger.error(f"Error processing upload: {str(e)}")
            raise
    
    def sync_data(self, triggered_by=None):
        """
        Synchronize data from the CSV file.
        In a real implementation, this would process the data and store it.
        For this example, we'll just simulate counting records.
        """
        try:
            # Create sync record
            self.sync = DataSourceSync.objects.create(
                datasource=self.datasource,
                triggered_by=triggered_by,
                status='running'
            )
            
            file_path = self._get_file_path()
            
            # Read and count rows
            with codecs.open(file_path, 'r', encoding=self.csv_settings.encoding) as f:
                reader = csv.reader(f, delimiter=self.csv_settings.delimiter, quotechar=self.csv_settings.quote_char)
                
                # Skip header if needed
                if self.csv_settings.has_header:
                    next(reader, None)
                
                # Skip additional rows if configured
                for _ in range(self.csv_settings.skip_rows):
                    next(reader, None)
                
                # Process rows
                row_count = 0
                max_rows = self.csv_settings.max_rows
                
                for row in reader:
                    row_count += 1
                    # Here you would actually process each row
                    # For now, we're just counting
                    
                    if max_rows and row_count >= max_rows:
                        break
            
            # Update sync record with results
            self.sync.records_processed = row_count
            self.sync.records_created = row_count  # Simplification
            self.sync.complete(status='success')
            
            # Update datasource
            self.datasource.update_last_sync()
            
            return self.sync
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error syncing CSV data: {error_message}")
            
            if self.sync:
                self.sync.complete(status='error', error_message=error_message)
            
            # Update datasource status
            self.datasource.status = 'error'
            self.datasource.save(update_fields=['status'])
            
            raise