"""If new cmeTags are associated with a PracticeSpecialty, this script assigns the new cmeTags to the user profiles"""
from users.models import *

def main():
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
