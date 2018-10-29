import django.dispatch

profile_saved = django.dispatch.Signal(providing_args=["user_id",])
