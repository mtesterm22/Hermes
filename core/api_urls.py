# core/api_urls.py
from django.urls import path, include
from rest_framework import routers

from datasources.api import DataSourceViewSet
from users.api import PersonViewSet
from workflows.api import WorkflowViewSet, ActionViewSet, ScheduleViewSet

# Initialize the router
router = routers.DefaultRouter()

# Register viewsets
router.register(r'datasources', DataSourceViewSet, basename='api-datasource')
router.register(r'people', PersonViewSet, basename='api-person')
router.register(r'workflows', WorkflowViewSet, basename='api-workflow')
router.register(r'actions', ActionViewSet, basename='api-action')
router.register(r'schedules', ScheduleViewSet, basename='api-schedule')

# API URL patterns
urlpatterns = [
    # DRF router URLs
    path('', include(router.urls)),
    
    # DRF auth URLs
    path('auth/', include('rest_framework.urls', namespace='rest_framework')),
]