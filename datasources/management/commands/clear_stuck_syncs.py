# datasources/management/commands/clear_stuck_syncs.py
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

from datasources.models import DataSource, DataSourceSync


class Command(BaseCommand):
    help = 'Clear sync records that are stuck in running status'

    def add_arguments(self, parser):
        parser.add_argument(
            '--datasource', '-d',
            type=int,
            help='ID of the data source to clear syncs for (default: all data sources)'
        )
        
        parser.add_argument(
            '--hours', '-t',
            type=float,
            default=1,
            help='Only clear syncs older than this many hours (default: 1)'
        )
        
        parser.add_argument(
            '--force', '-f',
            action='store_true',
            help='Clear all syncs regardless of age'
        )

    def handle(self, *args, **options):
        datasource_id = options['datasource']
        hours_threshold = options['hours']
        force = options['force']
        
        # Build the base query
        query = DataSourceSync.objects.filter(status='running')
        
        # Apply time threshold unless force is specified
        if not force:
            time_threshold = timezone.now() - timedelta(hours=hours_threshold)
            query = query.filter(start_time__lt=time_threshold)
            self.stdout.write(f"Targeting syncs older than {hours_threshold} hours")
        else:
            self.stdout.write(self.style.WARNING("Force flag set - clearing ALL running syncs regardless of age"))
        
        # Filter by data source if provided
        if datasource_id:
            try:
                datasource = DataSource.objects.get(id=datasource_id)
                query = query.filter(datasource=datasource)
                self.stdout.write(f"Targeting data source: {datasource.name} (ID: {datasource.id})")
            except DataSource.DoesNotExist:
                raise CommandError(f"Data source with ID {datasource_id} does not exist")
        
        # Count matching records
        count = query.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No stuck sync records found"))
            return
        
        # Confirm with user unless force is specified
        if not force:
            self.stdout.write(f"Found {count} stuck sync records to clear")
            confirm = input("Do you want to proceed? [y/N] ")
            if confirm.lower() != 'y':
                self.stdout.write(self.style.WARNING("Operation cancelled"))
                return
        
        # Update the records
        with transaction.atomic():
            # Mark all matching sync records as error
            updated = query.update(
                status='error',
                end_time=timezone.now(),
                error_message="Sync manually cleared due to being stuck in running state"
            )
            
            # Update any affected data sources
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
                        self.stdout.write(f"Updated data source ID {ds_id} status to 'warning'")
        
        self.stdout.write(self.style.SUCCESS(f"Successfully cleared {updated} stuck sync records"))