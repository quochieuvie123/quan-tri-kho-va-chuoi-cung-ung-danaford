from django.apps import AppConfig


class AlertsConfig(AppConfig):
    name = "alerts"

    def ready(self):
        from . import signals