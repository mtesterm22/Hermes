# hermes/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='dashboard:index'), name='home'),
    path('dashboard/', include('dashboard.urls')),
    path('datasources/', include('datasources.urls')),
    path('users/', include('users.urls')),
    path('workflows/', include('workflows.urls')),
    path('accounts/', include('accounts.urls')),
    path('api/', include('core.api_urls')),
]

# Add static/media URLs in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)