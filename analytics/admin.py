from django.contrib import admin
from .models import UserDataSnapshot


@admin.register(UserDataSnapshot)
class UserDataSnapshotAdmin(admin.ModelAdmin):
    list_display = ['user', 'data_type', 'created_at']
    list_filter = ['data_type', 'created_at']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['created_at']
    
    def has_add_permission(self, request):
        return False  # Only allow creation through the app, not admin
