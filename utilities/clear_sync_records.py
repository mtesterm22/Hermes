# utilities/clear_sync_records.py
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from datasources.models import DataSource, DataSourceSync

logger = logging.getLogger(__name__)

def clear_running_syncs(datasource_id=None, hours_threshold=1):
    """
    Clear any sync records that are stuck in 'running' status for a specific data source
    or for all data sources if no ID is provided.
    
    Args:
        datasource_id: Optional ID of specific data source to target
        hours_threshold: Consider syncs older than this many hours as stuck
    
    Returns:
        Number of sync records cleared
    """
    time_threshold = timezone.now() - timedelta(hours=hours_threshold)
    
    # Build the query for stuck sync records
    query = DataSourceSync.objects.filter(
        status='running',
        start_time__lt=time_threshold  # Only consider syncs older than threshold
    )
    
    # Filter by data source if provided
    if datasource_id:
        query = query.filter(datasource_id=datasource_id)
    
    # Log what we're about to do
    count = query.count()
    if count > 0:
        if datasource_id:
            logger.info(f"Clearing {count} stuck sync records for data source ID {datasource_id}")
        else:
            logger.info(f"Clearing {count} stuck sync records across all data sources")
    
    # Update the records in a transaction
    with transaction.atomic():
        # Mark all matching sync records as error
        updated = query.update(
            status='error',
            end_time=timezone.now(),
            error_message="Sync manually cleared due to being stuck in running state"
        )
        
        # Also update any affected data sources that might be locked in syncing state
        if updated > 0:
            # Get list of affected data sources
            datasource_ids = query.values_list('datasource_id', flat=True).distinct()
            
            # For each affected data source, check if it has no remaining running syncs
            for ds_id in datasource_ids:
                # If no running syncs remain, update the data source status
                if not DataSourceSync.objects.filter(datasource_id=ds_id, status='running').exists():
                    DataSource.objects.filter(id=ds_id).update(
                        status='warning'  # Set to warning to indicate intervention was needed
                    )
                    logger.info(f"Updated data source ID {ds_id} status to 'warning'")
    
    return updated

# Command-line interface for running from shell
if __name__ == "__main__":
    import sys
    import django
    
    # Setup Django environment if running standalone
    django.setup()
    
    datasource_id = None
    hours = 1
    
    # Parse command-line arguments
    if len(sys.argv) > 1:
        try:
            datasource_id = int(sys.argv[1])
        except ValueError:
            print(f"Invalid data source ID: {sys.argv[1]}")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        try:
            hours = float(sys.argv[2])
        except ValueError:
            print(f"Invalid hours threshold: {sys.argv[2]}")
            sys.exit(1)
    
    # Run the function
    cleared = clear_running_syncs(datasource_id, hours)
    print(f"Cleared {cleared} stuck sync records")