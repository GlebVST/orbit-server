"""Autocomplete views: used by autocomplete widget in the admin interface"""
from dal import autocomplete
from .models import User, State

class UserEmailAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated():
            return User.objects.none()
        qs = User.objects.exclude(username='admin').order_by('email')
        if self.q:
            qs = qs.filter(email__icontains=self.q)
        return qs

class StateNameAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated():
            return State.objects.none()
        qs = State.objects.all().order_by('name')
        if self.q:
            qs = qs.filter(name__istartswith=self.q)
        return qs
