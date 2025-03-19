# accounts/management/commands/cleanup_sessions.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.utils import cleanup_expired_sessions, get_suspicious_login_attempts

class Command(BaseCommand):
    help = 'Clean up expired user sessions and report suspicious login attempts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to keep inactive sessions'
        )
        parser.add_argument(
            '--threshold',
            type=int,
            default=5,
            help='Threshold of failed login attempts to consider suspicious'
        )
        parser.add_argument(
            '--hours',
            type=int,
            default=24,
            help='Hours to look back for suspicious login attempts'
        )

    def handle(self, *args, **options):
        days = options['days']
        threshold = options['threshold']
        hours = options['hours']
        
        # Clean up expired sessions
        expired_count, deleted_count = cleanup_expired_sessions(days_threshold=days)
        self.stdout.write(self.style.SUCCESS(
            f'Cleaned up user sessions: {expired_count} marked as expired, {deleted_count} deleted'
        ))
        
        # Check for suspicious login attempts
        suspicious = get_suspicious_login_attempts(threshold=threshold, timespan_hours=hours)
        if suspicious:
            self.stdout.write(self.style.WARNING(
                f'Found {len(suspicious)} suspicious IP addresses with failed login attempts:'
            ))
            for item in suspicious:
                self.stdout.write(self.style.WARNING(
                    f"  - {item['ip_address']}: {item['failed_count']} failed attempts"
                ))
        else:
            self.stdout.write(self.style.SUCCESS(
                'No suspicious login activity detected'
            ))