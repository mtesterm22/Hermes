# users/apps.py
from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'

    def ready(self):
        # Connect signals
        from django.db.models.signals import pre_delete
        from datasources.models import DataSource
        from users.profile_integration import handle_datasource_deletion
        
        # Connect the pre_delete signal for DataSource
        pre_delete.connect(handle_datasource_deletion, sender=DataSource)