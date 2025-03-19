# dashboard/views.py
import psutil
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta

from datasources.models import DataSource
from users.models import Person
from workflows.models import Workflow, Schedule, WorkflowExecution

@login_required
def index(request):
    """
    Main dashboard view showing system overview
    """
    # Retrieve counts for summary cards
    data_source_count = DataSource.objects.count()
    person_count = Person.objects.count()
    workflow_count = Workflow.objects.filter(is_active=True).count()
    
    # Get active schedules
    active_schedules = Schedule.objects.filter(
        enabled=True,
        workflow__is_active=True
    ).order_by('next_run')[:5]
    
    # Get recent data source activity
    recent_sources = DataSource.objects.all().order_by('-last_sync')[:5]
    
    # Get recent workflow executions
    recent_executions = WorkflowExecution.objects.all().order_by('-start_time')[:5]
    
    # Get basic system stats
    system_stats = {
        'cpu_usage': round(psutil.cpu_percent(interval=0.1), 1),
        'memory_usage': round(psutil.virtual_memory().percent, 1),
        'disk_usage': round(psutil.disk_usage('/').percent, 1),
    }
    
    context = {
        'data_source_count': data_source_count,
        'person_count': person_count,
        'workflow_count': workflow_count,
        'active_schedules': active_schedules,
        'recent_sources': recent_sources,
        'recent_executions': recent_executions,
        'system_stats': system_stats,
    }
    
    return render(request, 'dashboard/index.html', context)

@login_required
def system_status(request):
    """
    View for more detailed system status information
    """
    # Get detailed system information
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Calculate memory values in GB
    memory_total_gb = round(memory.total / (1024**3), 2)
    memory_used_gb = round(memory.used / (1024**3), 2)
    memory_available_gb = round(memory.available / (1024**3), 2)
    
    # Calculate disk values in GB
    disk_total_gb = round(disk.total / (1024**3), 2)
    disk_used_gb = round(disk.used / (1024**3), 2)
    disk_free_gb = round(disk.free / (1024**3), 2)
    
    # Get application statistics
    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    
    workflows_run_24h = WorkflowExecution.objects.filter(start_time__gte=last_24h).count()
    workflows_run_7d = WorkflowExecution.objects.filter(start_time__gte=last_7d).count()
    
    # Get data source statistics
    datasources_synced_24h = DataSource.objects.filter(last_sync__gte=last_24h).count()
    datasources_with_errors = DataSource.objects.filter(status='error').count()
    
    # Get workflow success/failure stats
    workflows_success_24h = WorkflowExecution.objects.filter(
        start_time__gte=last_24h, 
        status='success'
    ).count()
    
    workflows_error_24h = WorkflowExecution.objects.filter(
        start_time__gte=last_24h, 
        status='error'
    ).count()
    
    # Calculate success rate
    success_rate = 0
    if workflows_run_24h > 0:
        success_rate = round((workflows_success_24h / workflows_run_24h) * 100)
    
    context = {
        'cpu_percent': round(psutil.cpu_percent(interval=0.1), 1),
        'memory': {
            'percent': memory.percent,
            'total_gb': memory_total_gb,
            'used_gb': memory_used_gb,
            'available_gb': memory_available_gb,
        },
        'disk': {
            'percent': disk.percent,
            'total_gb': disk_total_gb,
            'used_gb': disk_used_gb,
            'free_gb': disk_free_gb,
        },
        'app_stats': {
            'workflows_run_24h': workflows_run_24h,
            'workflows_run_7d': workflows_run_7d,
            'workflows_success_24h': workflows_success_24h,
            'workflows_error_24h': workflows_error_24h,
            'success_rate': success_rate,
            'datasources_synced_24h': datasources_synced_24h,
            'datasources_with_errors': datasources_with_errors,
        }
    }
    
    return render(request, 'dashboard/system_status.html', context)

@login_required
def activity_log(request):
    """
    View for system activity logs
    """
    # Combine recent activities from different sources
    activities = []
    
    # Get workflow executions
    workflow_executions = WorkflowExecution.objects.all().order_by('-start_time')[:20]
    for execution in workflow_executions:
        activities.append({
            'type': 'workflow_execution',
            'timestamp': execution.start_time,
            'object': execution.workflow.name,
            'status': execution.status,
            'user': execution.triggered_by.username if execution.triggered_by else 'System',
            'details': f"Duration: {execution.duration}" if execution.duration else "In progress"
        })
    
    # Get data source syncs
    from datasources.models import DataSourceSync
    syncs = DataSourceSync.objects.all().order_by('-start_time')[:20]
    for sync in syncs:
        activities.append({
            'type': 'datasource_sync',
            'timestamp': sync.start_time,
            'object': sync.datasource.name,
            'status': sync.status,
            'user': sync.triggered_by.username if sync.triggered_by else 'System',
            'details': f"Records: {sync.records_processed} processed"
        })
    
    # Sort all activities by timestamp
    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    activities = activities[:30]  # Limit to most recent 30
    
    context = {
        'activities': activities
    }
    
    return render(request, 'dashboard/activity_log.html', context)