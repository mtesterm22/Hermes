# Updated datasources/urls.py
from django.urls import path
from . import views
from . import csv_views
from . import profile_views 

app_name = 'datasources'

urlpatterns = [
    # List view
    path('', views.DataSourceListView.as_view(), name='index'),
    
    # Type selection for creation
    path('select-type/', views.DataSourceTypeSelectView.as_view(), name='select_type'),
    
    # Detail view
    path('<int:pk>/', views.DataSourceDetailView.as_view(), name='detail'),
    
    # Create/Update/Delete views
    path('create/', views.DataSourceCreateView.as_view(), name='create'),
    path('<int:pk>/update/', views.DataSourceUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.DataSourceDeleteView.as_view(), name='delete'),
    
    path('<int:pk>/sync/', views.DataSourceSyncView.as_view(), name='sync'),
    path('syncs/<int:pk>/', views.DataSourceSyncDetailView.as_view(), name='sync_detail'),
    path('<int:pk>/fields/', views.DataSourceFieldListView.as_view(), name='fields'),
    path('<int:datasource_pk>/fields/create/', views.DataSourceFieldCreateView.as_view(), name='field_create'),
    path('<int:datasource_pk>/fields/<int:pk>/update/', views.DataSourceFieldUpdateView.as_view(), name='field_update'),
    path('<int:datasource_pk>/fields/<int:pk>/delete/', views.DataSourceFieldDeleteView.as_view(), name='field_delete'),
    
    # CSV-specific views
    path('csv/create/', csv_views.CSVDataSourceCreateView.as_view(), name='csv_create'),
    path('csv/<int:pk>/', csv_views.CSVDataSourceDetailView.as_view(), name='csv_detail'),
    path('csv/<int:pk>/update/', csv_views.CSVDataSourceUpdateView.as_view(), name='csv_update'),
    path('csv/<int:pk>/upload/', csv_views.CSVFileUploadView.as_view(), name='csv_upload'),
    path('csv/<int:pk>/sync/', csv_views.CSVDataSourceSyncView.as_view(), name='csv_sync'),
    path('csv/<int:pk>/fields/', csv_views.CSVFieldsUpdateView.as_view(), name='csv_fields'),
    path('csv/<int:pk>/detect_fields/', csv_views.CSVDetectFieldsView.as_view(), name='csv_detect_fields'),

    # Profile mapping
    path('<int:pk>/profile-mapping/', profile_views.ProfileMappingView.as_view(), name='profile_mapping'),
    path('<int:pk>/save-identity-config/', profile_views.SaveIdentityConfigView.as_view(), name='save_identity_config'),
    path('<int:pk>/create-mapping/', profile_views.CreateFieldMappingView.as_view(), name='create_mapping'),
    path('<int:datasource_pk>/edit-mapping/<int:mapping_pk>/', profile_views.EditFieldMappingView.as_view(), name='edit_mapping'),
    path('<int:datasource_pk>/delete-mapping/<int:mapping_pk>/', profile_views.DeleteFieldMappingView.as_view(), name='delete_mapping'),
]