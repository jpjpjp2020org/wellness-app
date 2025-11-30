# pw reset test setup - micmis IRL as with email ver

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.conf import settings

User = get_user_model()

class Command(BaseCommand):
    help = "Generate password reset link for a user and print it"

    def add_arguments(self, parser):
        parser.add_argument('email', type=str)

    def handle(self, *args, **options):
        try:
            user = User.objects.get(email=options['email'])
        except User.DoesNotExist:
            self.stderr.write("User not found")
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"http://127.0.0.1:8000/reset/{uid}/{token}/"
        self.stdout.write(f"Password reset link for {user.email}:\n{link}")
