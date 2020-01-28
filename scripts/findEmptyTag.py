from users.models import *
from collections import defaultdict
from datetime import timedelta
from django.utils import timezone

def main():
    now = timezone.now()
    cutoffDate = now - timedelta(days=366)
    anes_tag = CmeTag.objects.get(name='Anesthesiology')
    ps_anes = PracticeSpecialty.objects.get(name='Anesthesiology')
    profiles = Profile.objects.filter(specialties=ps_anes).order_by('pk')
    userids = [] # bt_status=active only
    for p in profiles:
        if not p.ABANumber:
            print("User {0} missing ABANumber".format(p))
            continue
        us = UserSubscription.objects.getLatestSubscription(p.user)
        if us and us.status == UserSubscription.ACTIVE:
            userids.append(p.pk)
    entries = Entry.objects \
        .select_related('entryType') \
        .filter(
            entryType__name=ENTRYTYPE_BRCME,
            user__in=userids, valid=True,
            submitABADate__isnull=True,
            created__gte=cutoffDate
        ).order_by('user','id')
    entriesByUser = defaultdict(list)
    empty = []
    for entry in entries:
        user  = entry.user
        offer = OrbitCmeOffer.objects.get(pk=entry.brcme.offerId)
        d = dict(entry=entry, offer=offer)
        if not entry.tags.exists():
            print("Entry {0} has no tags".format(entry))
            empty.append(d)
        entriesByUser[user].append(d)
    num_empty = len(empty)
    print("Num empty entries: {0}.".format(num_empty))
    return (empty, entriesByUser)
