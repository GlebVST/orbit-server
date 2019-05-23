import logging
from users.models import *
from goals.models import *

logger = logging.getLogger('mgmt.updsl')

gt_lic = GoalType.objects.get(name=GoalType.LICENSE)
cgts = GoalType.objects.getCreditGoalTypes()
ltype_fluo = LicenseType.objects.get(name=LicenseType.TYPE_FLUO)
ltype_state = LicenseType.objects.get(name=LicenseType.TYPE_STATE)

def handleTriage(ugs):
    """Use indirect method"""
    hopeless = []
    for ug in ugs:
        user = ug.user
        basegoal = ug.goal
        cg = basegoal.cmegoal if basegoal.goalType.name == GoalType.CME else basegoal.srcmegoal
        if ug.cmeTag and ug.cmeTag.name == CmeTag.FLUOROSCOPY:
            ltype = ltype_fluo
        else:
            ltype = ltype_state
        # find the lug for cg.licenseGoal.goal
        lugs = user.usergoals.filter(goal=cg.licenseGoal.goal).order_by('dueDate','pk')
        licenses = set([lug.license for lug in lugs])
        if len(licenses) == 1:
            sl = licenses.pop()
            ug.license = sl
            ug.save(update_fields=('license',))
            msg = 'Assign License {0.license.pk}|{0.license.expireDate:%Y-%m-%d} to usergoal {0.pk}|{0}.'.format(ug)
            print(msg)
            logger.info(msg)
        else:
            hopeless.append(ug)
            msg = 'Multiple Licenses found for {0.user} usergoal {1.pk}|{1}'.format(ltype, ug)
            print(msg)
            logger.warning(msg)
    return hopeless

def main():
    triage = []
    userids = StateLicense.objects.values_list('user', flat=True).distinct()
    for userid in userids:
        user = User.objects.get(pk=userid)
        ugs = user.usergoals \
            .select_related('goal__goalType') \
            .filter(
                goal__goalType__in=cgts,
                is_composite_goal=False,
                state__isnull=False,
                license__isnull=True
            ) \
            .order_by('dueDate','pk')
        for ug in ugs:
            basegoal = ug.goal
            if not basegoal.usesLicenseDate():
                continue
            if ug.cmeTag and ug.cmeTag.name == CmeTag.FLUOROSCOPY:
                ltype = ltype_fluo
            else:
                ltype = ltype_state
            qs = user.statelicenses.filter(
                state=ug.state,
                licenseType=ltype,
                expireDate__year=ug.dueDate.year,
                expireDate__month=ug.dueDate.month,
                expireDate__day=ug.dueDate.day
            )
            if not qs.exists():
                # check for uninitialized license (e.g. expireDate is null)
                qs2 = user.statelicenses.filter(
                    state=ug.state,
                    licenseType=ltype,
                    expireDate__isnull=True,
                ).order_by('-is_active', 'pk')
                if qs2.exists():
                    sl = qs2[0]
                    ug.license = sl
                    ug.save(update_fields=('license',))
                    msg = 'Assign Uninitialized License {0.license.pk}|{0.license.is_active} to usergoal {0.pk}|{0}.'.format(ug)
                    print(msg)
                    logger.info(msg)
                else:
                    msg = 'No {0.name} License found for {1.user}: {1.state.abbrev} and usergoal {1.pk}|{1}'.format(ltype, ug)
                    print(msg)
                    #logger.warning(msg)
                    triage.append(ug)
                continue
            sl = qs[0]
            ug.license = sl
            ug.save(update_fields=('license',))
            msg = 'Assign License {0.license.pk}|{0.license.expireDate:%Y-%m-%d} to usergoal {0.pk}|{0}.'.format(ug)
            print(msg)
            logger.info(msg)
    return triage
