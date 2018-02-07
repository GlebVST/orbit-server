from dal import autocomplete
from .models import User

class UserEmailAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated():
            return User.objects.none()
        qs = User.objects.exclude(username='admin').order_by('email')
        if self.q:
            qs = qs.filter(email__icontains=self.q)
        return qs