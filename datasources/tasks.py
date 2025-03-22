from celery import shared_task
import logging
from django.utils import timezone

from .models import DataSource, DataSourceSync

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def sync_datasource(self, datasource_id, triggered_by_id=None):
    """
    Task to synchronize a data source asynchronously.
    """
    logger.info(f"Starting sync for DataSource ID: {datasource_id}")
    try:
        # Get data source
        datasource = DataSource.objects.get(id=datasource_id)
        
        # Get user who triggered sync (if applicable)
        triggered_by = None
        if triggered_by_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            triggered_by = User.objects.get(id=triggered_by_id)
        
        # Create sync record if it doesn't exist
        sync, created = DataSourceSync.objects.get_or_create(
            datasource=datasource,
            status='running',
            triggered_by=triggered_by,
            defaults={
                'start_time': timezone.now()
            }
        )
        
        if not created:
            logger.warning(f"Using existing sync record ID: {sync.id}")
        
        # Get appropriate connector
        if datasource.type == 'csv':
            from .connectors.csv_connector import CSVConnector
            connector = CSVConnector(datasource)
        elif datasource.type == 'database':
            from .connectors.database_connector import DatabaseConnector
            connector = DatabaseConnector(datasource)
        else:
            error_msg = f"Unsupported data source type: {datasource.type}"
            logger.error(error_msg)
            sync.complete(status='error', error_message=error_msg)
            return False
        
        # Execute sync
        result = connector.sync_data(triggered_by=triggered_by)
        
        logger.info(f"Sync completed for DataSource ID: {datasource_id}, Status: {result.status}")
        
        return {
            'success': result.status == 'success',
            'datasource_id': datasource_id,
            'sync_id': result.id,
            'records_processed': result.records_processed
        }
    
    except Exception as e:
        logger.error(f"Error syncing DataSource ID {datasource_id}: {str(e)}", exc_info=True)
        
        # Try to update sync record if possible
        try:
            sync = DataSourceSync.objects.filter(
                datasource_id=datasource_id,
                status='running'
            ).first()
            
            if sync:
                sync.complete(status='error', error_message=str(e))
        except Exception as inner_e:
            logger.error(f"Error updating sync record: {str(inner_e)}")
        
        return {
            'success': False,
            'error': str(e),
            'datasource_id': datasource_id
        }

@shared_task
def add(x, y):
    return x + y