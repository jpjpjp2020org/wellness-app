from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):

    ordering = ['email']
    list_display = ['email', 'user_id', 'is_staff', 'is_active', 'email_verified']
    search_fields = ['email', 'user_id']
    fieldsets = (
        (None, {'fields': ('email', 'password', 'user_id')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'email_verified', 'groups', 'user_permissions')}),
        (_('Important dates'), {'fields': ('last_login',)}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )

    readonly_fields = ['user_id']  # no edits in admin

