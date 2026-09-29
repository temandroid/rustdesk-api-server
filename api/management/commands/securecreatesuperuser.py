from django.contrib.auth.management.commands.createsuperuser import Command as BaseCommand


class Command(BaseCommand):
    # Kept for compatibility: createsuperuser already asks for the password without echoing it
    help = 'Create a superuser (same as createsuperuser)'
