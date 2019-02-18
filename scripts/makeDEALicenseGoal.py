from users.models import *
from goals.models import *
from django.db import transaction

def main():
    created = []
    lg = LicenseGoal.objects.get(pk=20) # CA Medical Board license on test db
    lt = lg.licenseType
    bg = lg.goal
    degs = [d.pk for d in bg.degrees.all()]
    states = State.objects.all().order_by('name')
    for state in states:
        qset = LicenseGoal.objects.filter(licenseType=lt, state=state)
        if qset.exists():
            print('LG exists for {0}'.format(state))
            continue
        title = 'Medical Board License ({0})'.format(state.abbrev)
        with transaction.atomic():
            sbg = BaseGoal.objects.create(
                    goalType=bg.goalType,
                    dueDateType=bg.dueDateType,
                    interval=bg.interval
                )
            sbg.degrees.set(degs)
            slg = LicenseGoal.objects.create(
                    title=title,
                    goal=sbg,
                    state=state,
                    licenseType=lt
                )
            print(slg)
            created.append(slg)
    return created

def doDEA():
    created = []
    lg = LicenseGoal.objects.get(pk=34) # Alabama DEA on test db
    lt = lg.licenseType
    bg = lg.goal
    degs = [d.pk for d in bg.degrees.all()]
    states = State.objects.all().order_by('name')
    for state in states:
        qset = LicenseGoal.objects.filter(licenseType=lt, state=state)
        if qset.exists():
            print('LG exists for {0}'.format(state))
            continue
        title = 'DEA Registration ({0})'.format(state.abbrev)
        with transaction.atomic():
            sbg = BaseGoal.objects.create(
                    goalType=bg.goalType,
                    dueDateType=bg.dueDateType,
                    interval=bg.interval
                )
            sbg.degrees.set(degs)
            slg = LicenseGoal.objects.create(
                    title=title,
                    goal=sbg,
                    state=state,
                    licenseType=lt
                )
            print(slg)
            created.append(slg)
    return created
