from django.urls import path, reverse_lazy
from . import views
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .api_views import EmailTokenObtainPairView
from . import api_views
from django.contrib.auth import views as auth_views


app_name = 'users'

urlpatterns = [
    path('', views.auth_landing, name='landing'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    # path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/me/', api_views.me_view, name='api_me'),
    path('verify/<uidb64>/<token>/', views.verify_email, name='verify_email'),
    path("reset-me/", views.generate_reset_link, name="reset_me"),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="users/password_reset_confirm.html",
            success_url=reverse_lazy("users:password_reset_complete")
        ),
        name="password_reset_confirm"
    ),
    path(
        "reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="users/password_reset_complete.html"
        ),
        name="password_reset_complete"
    ),
]