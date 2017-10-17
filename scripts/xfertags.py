from users.models import *

def transferTags(profile):
    user = profile.user
    ps_pks = profile.specialties.values_list('id', flat=True) # current specialties
    ps_tag_pks = CmeTag.objects.filter(specialties__in=ps_pks).values_list('id', flat=True).distinct()
    print(user)
    for tagid in ps_tag_pks:
        t = CmeTag.objects.get(pk=tagid)
        pct, created = ProfileCmetag.objects.get_or_create(profile=profile, tag=t, is_active=True)
        if created:
            print('-- Create active {0}'.format(pct))
        else:
            print('-- Exists {0}'.format(pct))
    # Now find any inactive tags
    vqset = user.entries.all().values('tags').distinct() # <QuerySet [{'tags': None}, {'tags': 28}, {'tags': 21}, ...]>
    for d in vqset:
        if d['tags'] is None:
            continue
        tagid = d['tags']
        t = CmeTag.objects.get(pk=tagid)
        if t.name == CMETAG_SACME:
            continue
        if not ProfileCmetag.objects.filter(profile=profile, tag=t):
            pct = ProfileCmetag.objects.create(profile=profile, tag=t, is_active=False)
            print('-- Create inactive tag: {0}'.format(pct))
