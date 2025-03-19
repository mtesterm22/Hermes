# users/urls.py
from django.urls import path, re_path
from . import views
from . import profile_views

app_name = 'users'

urlpatterns = [
    # List view
    path('', views.PersonListView.as_view(), name='index'),
    
    # Detail view
    path('<int:pk>/', views.PersonDetailView.as_view(), name='detail'),
    
    # Create/Update/Delete views
    path('create/', views.PersonCreateView.as_view(), name='create'),
    path('<int:pk>/update/', views.PersonUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.PersonDeleteView.as_view(), name='delete'),
    
    # External identities
    path('<int:pk>/identities/', views.ExternalIdentityListView.as_view(), name='identities'),
    path('<int:person_pk>/identities/create/', views.ExternalIdentityCreateView.as_view(), name='identity_create'),
    path('<int:person_pk>/identities/<int:pk>/update/', views.ExternalIdentityUpdateView.as_view(), name='identity_update'),
    path('<int:person_pk>/identities/<int:pk>/delete/', views.ExternalIdentityDeleteView.as_view(), name='identity_delete'),
    
    # Attribute changes
    path('<int:pk>/changes/', views.AttributeChangeListView.as_view(), name='changes'),

    # Profile review views
    path('profiles/', profile_views.PersonListView.as_view(), name='person_list'),
    path('profiles/<int:pk>/', profile_views.PersonDetailView.as_view(), name='person_detail'),
    # Attribute history views - fixed to handle attribute names properly
    path('profiles/<int:pk>/history/', profile_views.AttributeHistoryView.as_view(), name='attribute_history'),
    re_path(r'profiles/(?P<pk>[0-9]+)/history/(?P<attribute_name>[\w\-\.]+)/', 
            profile_views.AttributeHistoryView.as_view(), name='attribute_history_named'),

    # Attribute display configuration
    path('datasources/<int:datasource_id>/attributes/', views.AttributeConfigListView.as_view(), name='attribute_config_list'),
    path('datasources/<int:datasource_id>/attributes/create/', views.AttributeConfigCreateView.as_view(), name='attribute_config_create'),
    path('datasources/<int:datasource_id>/attributes/bulk-create/', views.AttributeConfigBulkCreateView.as_view(), name='attribute_config_bulk_create'),
    path('datasources/<int:datasource_id>/attributes/reorder/', views.AttributeConfigReorderView.as_view(), name='attribute_config_reorder'),
    path('datasources/<int:datasource_id>/categories/', views.CategoryManagementView.as_view(), name='category_management'),
    path('attributes/<int:pk>/update/', views.AttributeConfigUpdateView.as_view(), name='attribute_config_update'),
    path('attributes/<int:pk>/delete/', views.AttributeConfigDeleteView.as_view(), name='attribute_config_delete'),
]