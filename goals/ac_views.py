"""Autocomplete views: used by autocomplete widget in the admin interface"""
from dal import autocomplete
from .models import LicenseGoal

class LicenseGoalAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated():
            return LicenseGoal.objects.none()
        qs = LicenseGoal.objects.all().order_by('title')
        if self.q:
            qs = qs.filter(title__icontains=self.q)
        return qs
