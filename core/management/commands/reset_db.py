"""
Management command to clear database data for testing.
This utility allows clearing the entire database or specific apps/models.
"""
from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import connection
from django.db.models import Q
from django.conf import settings
from django.contrib.auth import get_user_model
import importlib
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Reset the database by deleting data from specified apps or models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear all data from all apps except for admin user',
        )
        parser.add_argument(
            '--app',
            action='append',
            dest='apps',
            help='Specify app(s) to clear (can be used multiple times)',
        )
        parser.add_argument(
            '--model',
            action='append',
            dest='models',
            help='Specify models to clear in format app_label.ModelName (can be used multiple times)',
        )
        parser.add_argument(
            '--keep-admin',
            action='store_true',
            default=True,
            help='Keep admin user(s) when clearing data (default: True)',
        )
        parser.add_argument(
            '--skip-app',
            action='append',
            dest='skip_apps',
            help='Specify app(s) to skip when using --all (can be used multiple times)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        if not any([options['all'], options['apps'], options['models']]):
            raise CommandError("You must specify what to clear using --all, --app, or --model")

        # Get the list of apps/models to clear
        apps_to_clear = []
        models_to_clear = []
        
        # Django built-in apps to skip by default
        default_skip_apps = [
            'contenttypes', 
            'auth', 
            'sessions', 
            'admin', 
            'staticfiles',
            'messages',
        ]
        
        # Get skip_apps and ensure it's a list (since options.get('skip_apps') might be None)
        skip_apps = options.get('skip_apps') or []
        skip_apps = skip_apps + default_skip_apps
        
        if options['all']:
            # Get all app configs except those that should be skipped
            for app_config in apps.get_app_configs():
                if app_config.label not in skip_apps:
                    apps_to_clear.append(app_config.label)
        
        if options['apps']:
            # Add specific apps requested
            for app_label in options['apps']:
                try:
                    apps.get_app_config(app_label)
                    apps_to_clear.append(app_label)
                except LookupError:
                    self.stdout.write(self.style.WARNING(f"App '{app_label}' not found. Skipping."))
        
        # Remove duplicates
        apps_to_clear = list(set(apps_to_clear))
        
        # Get models for specified apps
        for app_label in apps_to_clear:
            app_models = apps.get_app_config(app_label).get_models()
            for model in app_models:
                models_to_clear.append((app_label, model.__name__))
        
        # Add individual models if specified
        if options['models']:
            for model_name in options['models']:
                try:
                    app_label, model_name = model_name.split('.')
                    model = apps.get_model(app_label, model_name)
                    models_to_clear.append((app_label, model.__name__))
                except (ValueError, LookupError):
                    self.stdout.write(self.style.WARNING(
                        f"Model '{model_name}' not found. Format should be 'app_label.ModelName'. Skipping."
                    ))
        
        # Remove duplicates
        models_to_clear = list(set(models_to_clear))
        
        # Early exit if no models to clear
        if not models_to_clear:
            self.stdout.write(self.style.WARNING("No valid models found to clear."))
            return
        
        # Confirm action
        if not options['force']:
            models_str = "\n".join([f"  • {app}.{model}" for app, model in models_to_clear])
            self.stdout.write(self.style.WARNING(
                f"You are about to DELETE ALL DATA from the following models:\n{models_str}"
            ))
            answer = input("Are you sure you want to proceed? [y/N]: ")
            if answer.lower() not in ['y', 'yes']:
                self.stdout.write(self.style.SUCCESS("Operation cancelled."))
                return
        
        # Process deletions
        User = get_user_model()
        admin_filter = None
        
        if options['keep_admin']:
            # Define filter for admin users based on User model
            # This tries to be smart about different User models
            if hasattr(User, 'is_superuser'):
                admin_filter = Q(is_superuser=True)
            elif hasattr(User, 'is_admin'):
                admin_filter = Q(is_admin=True)
            elif hasattr(User, 'is_staff'):
                admin_filter = Q(is_staff=True)
            elif hasattr(User, 'role') and 'admin' in [choice[0].lower() for choice in getattr(User, 'role').field.choices]:
                # Try to find an 'admin' role in choices
                admin_value = next((choice[0] for choice in getattr(User, 'role').field.choices 
                                   if 'admin' in choice[0].lower()), None)
                if admin_value:
                    admin_filter = Q(role=admin_value)
        
        # Counter for deleted objects
        deleted_counts = {}
            
        # First pass: Delete everything except User model and models with foreign keys to User
        # This helps avoid integrity errors
        for app_label, model_name in sorted(models_to_clear):
            model_class = apps.get_model(app_label, model_name)
            
            # Skip the User model on first pass
            if model_class == User:
                continue
                
            # Check if model has a direct foreign key to User
            has_user_fk = False
            for field in model_class._meta.fields:
                if field.is_relation and field.related_model == User:
                    has_user_fk = True
                    break
                    
            if has_user_fk:
                continue
                
            try:
                # Delete all objects for this model
                count, _ = model_class.objects.all().delete()
                if count:
                    deleted_counts[f"{app_label}.{model_name}"] = count
                    self.stdout.write(f"Deleted {count} objects from {app_label}.{model_name}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Error deleting {app_label}.{model_name}: {str(e)}"
                ))
        
        # Second pass: Delete models with foreign keys to User
        for app_label, model_name in sorted(models_to_clear):
            model_class = apps.get_model(app_label, model_name)
            
            # Skip the User model again
            if model_class == User:
                continue
                
            # Check if model was already processed
            if f"{app_label}.{model_name}" in deleted_counts:
                continue
                
            try:
                # Delete all objects for this model
                count, _ = model_class.objects.all().delete()
                if count:
                    deleted_counts[f"{app_label}.{model_name}"] = count
                    self.stdout.write(f"Deleted {count} objects from {app_label}.{model_name}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Error deleting {app_label}.{model_name}: {str(e)}"
                ))
        
        # Finally, handle User model if it's in the list
        if any(model_name == User.__name__ for _, model_name in models_to_clear):
            try:
                query = User.objects.all()
                
                # Filter out admin users if keep_admin is True
                if options['keep_admin'] and admin_filter:
                    admin_users = User.objects.filter(admin_filter)
                    admin_count = admin_users.count()
                    if admin_count:
                        query = query.exclude(admin_filter)
                        self.stdout.write(f"Keeping {admin_count} admin user(s)")
                
                count, _ = query.delete()
                if count:
                    deleted_counts[f"{User._meta.app_label}.{User.__name__}"] = count
                    self.stdout.write(f"Deleted {count} users")
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Error deleting users: {str(e)}"
                ))
        
        # Summary
        total_deleted = sum(deleted_counts.values())
        if total_deleted:
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {total_deleted} objects."))
        else:
            self.stdout.write("No objects were deleted.")