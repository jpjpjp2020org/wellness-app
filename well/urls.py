"""
URL configuration for well project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from two_factor.urls import urlpatterns as tf_urls

urlpatterns = [
    path('welladmin/', admin.site.urls),
    path('', include('users.urls', namespace='users')),
    path('accounts/', include('allauth.urls')),  # auth paths
    path('2fa/', include(tf_urls)),
    path('health/', include('health.urls', namespace='health')),
    path('diet/', include('diet.urls', namespace='diet')),
    path('analytics/', include('analytics.urls', namespace='analytics')),
]
