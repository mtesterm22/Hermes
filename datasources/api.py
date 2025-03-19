# datasources/api.py
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import DataSource, DataSourceField, DataSourceSync

class DataSourceViewSet(viewsets.ModelViewSet):
    """
    API endpoint for data sources
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return DataSource.objects.all().order_by('name')
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        """
        Trigger a sync for the data source
        """
        datasource = self.get_object()
        
        # Here you would actually trigger the sync process
        # For now, we'll just create a sync record
        sync = DataSourceSync.objects.create(
            datasource=datasource,
            triggered_by=request.user,
            status='running'
        )
        
        return Response({'status': 'sync initiated'})