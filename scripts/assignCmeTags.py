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
                    pct = ProfileCmetag.objects.create(profile=p, tag=t)
                    print('Add pct {0} to profile {1} for ps: {2}'.format(pct, p, ps))
    return psTagDict

def updateOffers(cutoff_days=7):
    """Add SA-CME tag to unredeemed Radiology offers since cutoff"""
    now = timezone.now()
    cutoff = now - timedelta(days=cutoff_days)
    ps_rad = PracticeSpecialty.objects.get(name='Radiology')
    satag = CmeTag.objects.get(name=CMETAG_SACME)
    offers = OrbitCmeOffer.objects.filter(
        redeemed=False,
        valid=True,
        expireDate__gt=now,
        activityDate__lte=cutoff,
        eligible_site__specialties__pk=ps_rad.pk
    ).order_by('id')
    for offer in offers:
        tags = offer.tags.all()
        cur_tag_pks = set([t.pk for t in tags])
        if satag.pk not in cur_tag_pks:
            offer.tags.add(satag)
            print('Update offer {0.pk}/{0}'.format(offer))
