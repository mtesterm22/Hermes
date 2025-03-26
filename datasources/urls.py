# Updated datasources/urls.py
from django.urls import path
from . import views
from . import csv_views
from . import profile_views 
from . import database_views
from . import connection_views
from . import active_directory_views

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

    # Database-specific views
    path('database/create/', database_views.DatabaseDataSourceCreateView.as_view(), name='database_create'),
    path('database/<int:pk>/', database_views.DatabaseDataSourceDetailView.as_view(), name='database_detail'),
    path('database/<int:pk>/update/', database_views.DatabaseDataSourceUpdateView.as_view(), name='database_update'),
    path('database/<int:pk>/test-connection/', database_views.DatabaseTestConnectionView.as_view(), name='database_test_connection'),
    path('database/<int:pk>/sync/', database_views.DatabaseDataSourceSyncView.as_view(), name='database_sync'),
    path('database/<int:pk>/fields/', database_views.DatabaseFieldsUpdateView.as_view(), name='database_fields'),
    path('database/<int:pk>/detect-fields/', database_views.DatabaseDetectFieldsView.as_view(), name='database_detect_fields'),
    path('database/<int:pk>/tables/', database_views.DatabaseTableListView.as_view(), name='database_tables'),
    path('database/<int:pk>/tables/<str:table_name>/', database_views.DatabaseTableSchemaView.as_view(), name='database_table_schema'),
    
    # Database query management
    path('database/<int:datasource_pk>/queries/create/', database_views.DatabaseQueryCreateView.as_view(), name='database_query_create'),
    path('database/queries/<int:pk>/update/', database_views.DatabaseQueryUpdateView.as_view(), name='database_query_update'),
    path('database/queries/<int:pk>/delete/', database_views.DatabaseQueryDeleteView.as_view(), name='database_query_delete'),
    path('database/queries/<int:pk>/execute/', database_views.DatabaseQueryExecuteView.as_view(), name='database_query_execute'),
    path('database/executions/<int:pk>/', database_views.DatabaseQueryExecutionDetailView.as_view(), name='database_execution_detail'),
    path('database/<int:pk>/detect-fields/', database_views.DatabaseFieldDetectionView.as_view(), name='database_detect_fields'),
    path('database/<int:pk>/fields/', database_views.DatabaseFieldManagementView.as_view(), name='database_fields'),

    # Database Connections
    path('connections/', connection_views.ConnectionListView.as_view(), name='connections'),
    path('connections/create/', connection_views.ConnectionCreateView.as_view(), name='connection_create'),
    path('connections/<int:pk>/', connection_views.ConnectionDetailView.as_view(), name='connection_detail'),
    path('connections/<int:pk>/update/', connection_views.ConnectionUpdateView.as_view(), name='connection_update'),
    path('connections/<int:pk>/delete/', connection_views.ConnectionDeleteView.as_view(), name='connection_delete'),
    path('connections/<int:pk>/test/', connection_views.ConnectionTestView.as_view(), name='connection_test'),
    path('connections/<int:pk>/tables/', connection_views.ConnectionTablesView.as_view(), name='connection_tables'),
    path('oracle/templates/', database_views.OracleHelperView.as_view(), name='oracle_templates'),
    path('connections/<int:pk>/test-oracle/', connection_views.TestOracleConnectionView.as_view(), name='test_oracle_connection'),

    # Active Directory Connection Management
    path('ad-connections/', active_directory_views.ADConnectionListView.as_view(), name='ad_connections'),
    path('ad-connections/create/', active_directory_views.ADConnectionCreateView.as_view(), name='ad_connection_create'),
    path('ad-connections/<int:pk>/', active_directory_views.ADConnectionDetailView.as_view(), name='ad_connection_detail'),
    path('ad-connections/<int:pk>/update/', active_directory_views.ADConnectionUpdateView.as_view(), name='ad_connection_update'),
    path('ad-connections/<int:pk>/delete/', active_directory_views.ADConnectionDeleteView.as_view(), name='ad_connection_delete'),
    path('ad-connections/<int:pk>/test/', active_directory_views.ADConnectionTestView.as_view(), name='ad_connection_test'),

    # Active Directory Data Source Management
    path('active-directory/create/', active_directory_views.ADDataSourceCreateView.as_view(), name='ad_create'),
    path('active-directory/<int:pk>/', active_directory_views.ADDataSourceDetailView.as_view(), name='ad_detail'),
    path('active-directory/<int:pk>/update/', active_directory_views.ADDataSourceUpdateView.as_view(), name='ad_update'),
    path('active-directory/<int:pk>/test-connection/', active_directory_views.ADTestConnectionView.as_view(), name='ad_test_connection'),
    path('active-directory/<int:pk>/sync/', active_directory_views.ADDataSourceSyncView.as_view(), name='ad_sync'),
    path('active-directory/<int:pk>/detect-fields/', active_directory_views.ADDetectFieldsView.as_view(), name='ad_detect_fields'),
]