# Updated workflows/urls.py
from django.urls import path
from . import views
from . import action_views
from . import designer_views
from .action_views import FileCreateActionCreateView, FileCreateActionUpdateView

app_name = 'workflows'

urlpatterns = [
    # Workflows
    path('', views.WorkflowListView.as_view(), name='index'),
    path('<int:pk>/', views.WorkflowDetailView.as_view(), name='detail'),
    path('create/', views.WorkflowCreateView.as_view(), name='create'),
    path('<int:pk>/update/', views.WorkflowUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.WorkflowDeleteView.as_view(), name='delete'),
    path('<int:pk>/run/', views.WorkflowRunView.as_view(), name='run'),
    path('<int:pk>/api/run/', views.WorkflowRunAPIView.as_view(), name='api_run'),
    
    # Workflow Designer
    path('designer/', designer_views.WorkflowDesignerView.as_view(), name='designer'),
    path('designer/<int:pk>/', designer_views.WorkflowDesignerView.as_view(), name='designer_edit'),
    
    # Workflow Actions
    path('<int:workflow_pk>/actions/create/', views.WorkflowActionCreateView.as_view(), name='workflow_action_create'),
    path('<int:workflow_pk>/actions/<int:pk>/update/', views.WorkflowActionUpdateView.as_view(), name='workflow_action_update'),
    path('<int:workflow_pk>/actions/<int:pk>/delete/', views.WorkflowActionDeleteView.as_view(), name='workflow_action_delete'),
    
    # Actions
    path('actions/', views.ActionListView.as_view(), name='actions'),
    path('actions/type-select/', action_views.ActionTypeSelectView.as_view(), name='action_type_select'),
    path('actions/<int:pk>/run/', action_views.RunActionView.as_view(), name='run_action'),
    
    # Specific Action Types
    path('actions/create/datasource-refresh/', action_views.DataSourceRefreshActionCreateView.as_view(), name='datasource_refresh_action_create'),
    path('actions/<int:pk>/update/datasource-refresh/', action_views.DataSourceRefreshActionUpdateView.as_view(), name='datasource_refresh_action_update'),
    path('actions/create/database-query/', action_views.DatabaseQueryActionCreateView.as_view(), name='database_query_action_create'),
    path('actions/<int:pk>/update/database-query/', action_views.DatabaseQueryActionUpdateView.as_view(), name='database_query_action_update'),
    path('actions/create/file-create/', action_views.FileCreateActionCreateView.as_view(), name='file_create_action_create'),
    path('actions/<int:pk>/update/file-create/', action_views.FileCreateActionUpdateView.as_view(), name='file_create_action_update'),
    
    # Generic Actions
    path('actions/create/', views.ActionCreateView.as_view(), name='action_create'),
    path('actions/<int:pk>/', views.ActionDetailView.as_view(), name='action_detail'),
    path('actions/<int:pk>/update/', views.ActionUpdateView.as_view(), name='action_update'),
    path('actions/<int:pk>/delete/', views.ActionDeleteView.as_view(), name='action_delete'),
    
    # Schedules
    path('schedules/', views.ScheduleListView.as_view(), name='schedules'),
    path('schedules/create/', views.ScheduleCreateView.as_view(), name='schedule_create'),
    path('schedules/<int:pk>/', views.ScheduleDetailView.as_view(), name='schedule_detail'),
    path('schedules/<int:pk>/update/', views.ScheduleUpdateView.as_view(), name='schedule_update'),
    path('schedules/<int:pk>/delete/', views.ScheduleDeleteView.as_view(), name='schedule_delete'),
    path('schedules/<int:pk>/toggle/', views.ScheduleToggleView.as_view(), name='schedule_toggle'),
    
    # Executions
    path('executions/', views.WorkflowExecutionListView.as_view(), name='executions'),
    path('executions/<int:pk>/', views.WorkflowExecutionDetailView.as_view(), name='execution_detail'),
]