"""If new cmeTags are associated with a PracticeSpecialty, this script assigns the new cmeTags to the user profiles"""
from users.models import *
from django.utils import timezone
from datetime import timedelta

def isDeg(profile, deg_abbrev):
    degs = list(profile.degrees.all())
    for deg in degs:
        if deg.abbrev == deg_abbrev:
            return True
    return False

def updatePcts(p, ps_tags):
    tags = p.cmeTags.all()
    cur_tag_pks = set([t.pk for t in tags])
    created = 0
    for t in ps_tags:
        if t.pk not in cur_tag_pks:
            # since user might have multiple specialties that share a common new tag, use get_or_create
            pct, created = ProfileCmetag.objects.get_or_create(profile=p, tag=t)
            if created:
                print('Add pct {0} to profile {1}.'.format(pct, p))
                cur_tag_pks.add(t.pk)
                created += 1
    return created

def updateProfiles():
    ps_qset = PracticeSpecialty.objects.all().prefetch_related('cmeTags')
    psTagDict = dict()
    for ps in ps_qset:
        psTagDict[ps.pk] = list(ps.cmeTags.all())
    ss_qset = SubSpecialty.objects.all().prefetch_related('cmeTags')
    subSpecTagDict = dict()
    for ss in ss_qset:
        subSpecTagDict[ss.pk] = list(ss.cmeTags.all())
    profiles = Profile.objects.all().order_by('created')
    for p in profiles:
        if not p.organization:
            # only assign tags from specialty for individual users
            specs = p.specialties.all()
            for ps in specs:
                created = updatePcts(p, psTagDict[ps.pk])
        subspecs = p.subspecialties.all()
        for ss in subspecs:
            created = updatePcts(p, subSpecTagDict[ss.pk])
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

def cleanupTag(tagname):
    if tagname == 'Fluoroscopy':
        print('Use cleanUpFluo instead')
        return
    etag = CmeTag.objects.get(name=tagname)
    subspecs = list(etag.subspecialties.all())
    states = list(etag.states.all())
    dostates = list(etag.dostates.all())
    dea_states = [m for m in StateDeatag.objects.filter(tag=etag).all()]
    profiles = Profile.objects.filter(organization__isnull=False).select_related('organization').order_by('created')
    toremove = set([])
    for p in profiles:
        qs = ProfileCmetag.objects.filter(profile=p, tag=etag)
        if not qs.exists():
            continue
        removeTag = True
        if isDeg(p, 'DO') and dostates:
            for s in dostates:
                pqs = s.profiles.filter(user=p.user)
                if pqs.exists():
                    removeTag = False
                    print('User {0} is DO and belongs to State: {1}'.format(p, s))
                    break
        if not removeTag:
            continue
        for s in subspecs:
            pqs = p.subspecialties.filter(pk=s.pk)
            if pqs.exists():
                removeTag = False
                print('User {0} has SubSpecialty: {1}'.format(p, s))
                break
        if not removeTag:
            continue
        for s in states:
            pqs = s.profiles.filter(user=p.user)
            if pqs.exists():
                removeTag = False
                print('User {0} belongs to State: {1}'.format(p, s))
                break
        if not removeTag:
            continue
        for sd in dea_states: # sd is a StateDeatag instance
            if sd.dea_in_state:
                pqs = p.deaStates.filter(pk=sd.state.pk)
                if pqs.exists():
                    removeTag = False
                    print('User {0} has dea_in_state: {1.state}'.format(p, sd))
                    break
            else:
                # does user belong to sd.state and have DEA in any state?
                in_state = p.states.filter(pk=sd.state.pk).exists()
                dea_in_any_state = p.deaStates.exists()
                if in_state and dea_in_any_state:
                    removeTag = False
                    print('User {0} belongs to state: {1.state} and has DEA in any state.'.format(p, sd))
                    break
        if removeTag:
            toremove.add(p)
    return (etag, toremove)

def removeTagFromProfile(p, etag):
    qs = ProfileCmetag.objects.filter(profile=p, tag=etag)
    if not qs.exists():
        return True
    pct = qs[0]
    eqs = p.user.entries.filter(tags=etag)
    if eqs.exists():
        print('User {0} has used tag {1} in entries.'.format(p, etag))
        return False
    ugs = p.user.usergoals.filter(cmeTag=etag)
    if ugs.exists():
        print('! User {0} has usergoals for tag {1}'.format(p, etag))
        return False
    # else delete
    pct.delete()
    return True
