from users.models import *
from goals.models import *

def print_license_goal(ug):
    lic = ug.license
    if lic.expireDate:
        print('{0.pk}: {0.title} expireDate:{1.expireDate:%Y-%m-%d}'.format(ug, lic))
    else:
        print('{0.pk}: {0.title} expireDate: *Un-Initialized*'.format(ug, lic))

def print_board_goal(ug):
    bg = ug.goal
    dueDateType = bg.formatDueDateType()
    srcgoal = bg.cmegoal
    cmeTag = srcgoal.getTag() # handles mapNullToSpecialty
    print('{0.board}|{0.goal.goalType}|dueDateType:{1}|Lookback: {0.goal.interval} years|{0.credits} credits in {2}'.format(srcgoal, dueDateType, cmeTag))
    print('  {0.pk}: status:{0.status}|dueDate:{0.dueDate:%Y-%m-%d}|creditsEarned:{0.creditsEarned}|creditsDue:{0.creditsDue} in {0.cmeTag}/{1}'.format(ug, ug.formatCreditTypes()))
    print(' ')

def print_state_goal(ug):
    bg = ug.goal
    gtype = bg.goalType.name
    dueDateType = bg.formatDueDateType()
    if gtype == GoalType.CME:
        srcgoal = bg.cmegoal
        cmeTag = srcgoal.getTag() # handles mapNullToSpecialty
    else:
        srcgoal = bg.srcmegoal
        cmeTag = srcgoal.cmeTag
        if not cmeTag:
            cmeTag = ANY_TOPIC
    if bg.isOneOff():
        print('{0.state}|{0.goal.goalType}|dueDateType:{1}|{0.credits} credits in {2}'.format(srcgoal, dueDateType, cmeTag))
    else:
        print('{0.state}|{0.goal.goalType}|dueDateType:{1}|Lookback: {0.goal.interval} years|{0.credits} credits in {2}'.format(srcgoal, dueDateType, cmeTag))
    print('  {0.pk}: status:{0.status}|dueDate:{0.dueDate:%Y-%m-%d}|creditsEarned:{0.creditsEarned}|creditsDue:{0.creditsDue} in {0.cmeTag}/{1}'.format(ug, ug.formatCreditTypes()))
    print(' ')

def getMembersOfOrg(joinCode):
    org = Organization.objects.get(joinCode=joinCode)
    members = org.orgmembers.filter(pending=False, removeDate__isnull=True, is_admin=False).order_by('pk')
    profiles = [member.user.profile for member in members]
    return (members, profiles)

def main(user):
    fkwargs = {
        'is_composite_goal': False,
        'status__in': [UserGoal.PASTDUE, UserGoal.IN_PROGRESS, UserGoal.COMPLETED]
    }
    ugs = user.usergoals \
        .select_related('goal__goalType','state','cmeTag') \
        .filter(**fkwargs) \
        .order_by('dueDate','-creditsDue', 'pk')
    board_goals = []
    state_goals = []
    license_goals = []
    for ug in ugs:
        bg = ug.goal
        gtype = bg.goalType.name
        if gtype == GoalType.LICENSE:
            license_goals.append(ug)
            continue
        if ug.state:
            state_goals.append(ug)
        else:
            board_goals.append(ug)
    profile = user.profile
    print(user)
    print(" Degree: {0}".format(profile.formatDegrees()))
    print(" Specialties: {0}".format(profile.formatSpecialties()))
    print(" SubSpecialties: {0}".format(profile.formatSubSpecialties()))
    print('Num Licenses: {0}'.format(len(license_goals)))
    for ug in license_goals:
        print_license_goal(ug)
    print(' ')
    print('Num Board goals: {0}'.format(len(board_goals)))
    for ug in board_goals:
        print_board_goal(ug)
    print('Num State goals: {0}'.format(len(state_goals)))
    for ug in state_goals:
        print_state_goal(ug)
    # composite goals
    cugs = user.usergoals \
        .select_related('goal__goalType','state','cmeTag') \
        .filter(is_composite_goal=True) \
        .order_by('dueDate','-creditsDue', 'pk')
    print('Num Composite goals: {0}'.format(len(cugs)))
    for ug in cugs:
        print("{0.pk}: {0}".format(ug))
        for m in ug.constituentGoals.all():
            print("  {0.pk}: {0}".format(m))
        print(' ')
    return ugs
