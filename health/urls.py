from django.urls import path
from . import views

app_name = "health"

urlpatterns = [
    path("profile/", views.profile_entry, name="profile_entry"),
    path("goals/", views.goals_tracking, name="goals_tracking"),
    path("export/", views.export_health_data, name="export_health_data"),
]