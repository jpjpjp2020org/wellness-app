from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib.auth import get_user_model, login
from allauth.account.auth_backends import AuthenticationBackend
from allauth.account.utils import user_email
from allauth.socialaccount.models import SocialLogin
from django.contrib import messages

User = get_user_model()

class LinkOnlyIfUserExistsAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('email')
        if not email:
            return

        try:
            user = User.objects.get(email=email)
            
            # Connect the social account to the existing user
            if not sociallogin.is_existing:
                sociallogin.connect(request, user)
            
            # Set the user and state
            sociallogin.state['process'] = 'connect'
            sociallogin.user = user
            
            # Log the user in
            login(request, user, backend='allauth.account.auth_backends.AuthenticationBackend')
            
            # Redirect to dashboard
            raise ImmediateHttpResponse(redirect("/dashboard/"))
            
        except User.DoesNotExist:
            return

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.email = data.get('email')
        return user

    def is_auto_signup_allowed(self, request, sociallogin):
        email = sociallogin.account.extra_data.get('email')
        if email:
            try:
                user = User.objects.get(email=email)
                return False
            except User.DoesNotExist:
                return True
        return True

