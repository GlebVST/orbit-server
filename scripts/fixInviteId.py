"""Re-generate inviteId using new alphabet and update profile model"""
from hashids import Hashids
from django.conf import settings
from users.models import Profile
from users.auth_backends import HASHIDS_ALPHABET

def main():
    hashgen = Hashids(salt=settings.HASHIDS_SALT, alphabet=HASHIDS_ALPHABET, min_length=5)
    qset = Profile.objects.all().order_by('created')
    for m in qset:
        user = m.user
        m.inviteId = hashgen.encode(user.pk)
        m.save()
        print('{0.email} inviteId {1.inviteId}'.format(user, m))

