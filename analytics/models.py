from django.db import models
from django.conf import settings


class UserDataSnapshot(models.Model):
    """
    Stores user data snapshots for AI assistant context
    Simple denormalized storage for testing and validation
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    data_type = models.CharField(max_length=50)  # 'health_summary', 'nutrition_current', etc.
    data_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'data_type']),
            models.Index(fields=['user', 'created_at'])
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.data_type} @ {self.created_at}"
