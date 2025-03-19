# dashboard/urls.py
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('system-status/', views.system_status, name='system_status'),
    path('activity-log/', views.activity_log, name='activity_log'),
]