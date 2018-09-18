from django.contrib import admin
from django.conf import settings

# http://stackoverflow.com/questions/32612400/auto-register-django-auth-models-using-custom-admin-site
class MyAdminSite(admin.AdminSite):
    site_header = "Orbit Site administration" if settings.ENV_TYPE == settings.ENV_PROD else "Test Site administration"
    site_url = None

    def __init__(self, *args, **kwargs):
        super(MyAdminSite, self).__init__(*args, **kwargs)
        self._registry.update(admin.site._registry)

admin_site = MyAdminSite()
