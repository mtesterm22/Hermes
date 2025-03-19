# workflows/urls.py
from django.urls import path
from . import views

app_name = 'workflows'

urlpatterns = [
    # Workflows
    path('', views.WorkflowListView.as_view(), name='index'),
    path('<int:pk>/', views.WorkflowDetailView.as_view(), name='detail'),
    path('create/', views.WorkflowCreateView.as_view(), name='create'),
    path('<int:pk>/update/', views.WorkflowUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.WorkflowDeleteView.as_view(), name='delete'),
    path('<int:pk>/run/', views.WorkflowRunView.as_view(), name='run'),
    
    # Workflow Actions
    path('<int:workflow_pk>/actions/create/', views.WorkflowActionCreateView.as_view(), name='workflow_action_create'),
    path('<int:workflow_pk>/actions/<int:pk>/update/', views.WorkflowActionUpdateView.as_view(), name='workflow_action_update'),
    path('<int:workflow_pk>/actions/<int:pk>/delete/', views.WorkflowActionDeleteView.as_view(), name='workflow_action_delete'),
    
    # Actions
    path('actions/', views.ActionListView.as_view(), name='actions'),
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