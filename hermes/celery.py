# hermes/celery.py
from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hermes.settings')

# Create Celery application
app = Celery('hermes')

# Load configuration from Django settings with namespace 'CELERY'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

# Define a simple test task
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
    return "Debug task completed successfully!"