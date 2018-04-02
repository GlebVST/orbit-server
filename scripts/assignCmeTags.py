"""If new cmeTags are associated with a PracticeSpecialty, this script assigns the new cmeTags to the user profiles"""
from users.models import *
from django.utils import timezone
from datetime import timedelta

def updateProfiles():
    ps_qset = PracticeSpecialty.objects.all().prefetch_related('cmeTags')
    psTagDict = dict()
    for ps in ps_qset:
        psTagDict[ps.pk] = list(ps.cmeTags.all())
    profiles = Profile.objects.all().order_by('created')
    for p in profiles:
        specs = p.specialties.all()
        tags = p.cmeTags.all()
        cur_tag_pks = [t.pk for t in tags]
        for ps in specs:
            ps_tags = psTagDict[ps.pk]
            for t in ps_tags:
                if t.pk not in cur_tag_pks:
                    # since user might have multiple specialties that share a common new tag, use get_or_create
                    pct, created = ProfileCmetag.objects.get_or_create(profile=p, tag=t)
                    if created:
                        print('Add pct {0} to profile {1} for ps: {2}'.format(pct, p, ps))
    return psTagDict

def assignPctSaCme():
    satag = CmeTag.objects.get(name=CMETAG_SACME)
    profiles = Profile.objects.all().prefetch_related('degrees')
    for p in profiles:
        if p.isPhysician() and p.specialties.filter(name__in=SACME_SPECIALTIES).exists():
            qset = ProfileCmetag.objects.filter(tag=satag, profile=p)
            if not qset.exists():
                pct = ProfileCmetag.objects.create(tag=satag, profile=p, is_active=True)
                print('Add pct {0} to profile {1}'.format(pct, p))
