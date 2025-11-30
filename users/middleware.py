from django.shortcuts import redirect
from django.urls import reverse
from django_otp import user_has_device

class OTPRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.path.startswith('/welladmin/') or request.path.startswith('/2fa/') or request.path.startswith('/accounts/'):
            return self.get_response(request)

        if request.user.is_authenticated:
            if user_has_device(request.user) and not request.user.is_verified:
                return redirect(reverse('two_factor:login'))

        return self.get_response(request)
