from django.apps import AppConfig


class HealthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'health'

    # for django and signals - need to wire it up later
    def ready(self):
        import health.signals
