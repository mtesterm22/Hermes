"""
ASGI config for hermes project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""
from __future__ import absolute_import, unicode_literals
import os
from django.core.asgi import get_asgi_application
from .celery import app as celery_app

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hermes.settings')

application = get_asgi_application()

__all__ = ('celery_app',)