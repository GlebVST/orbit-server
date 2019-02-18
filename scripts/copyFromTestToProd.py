"""This requires a key called prod in settings.DATABASES containing the prod db, and default points to testdb."""
import logging
from django.db import transaction
from users.models import *
from goals.models import *

#
# Used for one-time push to prod 02/18/19 only.
#
logger = logging.getLogger('mgmt.goals')

# PROD: board name  => Board instance
boardDict = {}
boards = Board.objects.using('prod').all()
for m in boards:
    boardDict[m.name] = m

# PROD credit type abbrev => CreditType instance
creditTypeDict = {}
creditTypes = CreditType.objects.using('prod').all()
for m in creditTypes:
    creditTypeDict[m.abbrev] = m

# PROD state abbrev => State instance
statesDict = {}
country_prod = Country.objects.using('prod').get(code=Country.USA)
states_prod = country_prod.states.all()
for state in states_prod:
    statesDict[state.abbrev] = state

# PROD: degree abbrev => Degree instance
degreeDict = {}
degs = Degree.objects.using('prod').all()
for m in degs:
    degreeDict[m.abbrev] = m

# PROD: Specialty name  => PracticeSpecialty instance
specialtyDict = {}
specs = PracticeSpecialty.objects.using('prod').all()
for m in specs:
    specialtyDict[m.name] = m

# PROD (Specialty name, SubSpec name)  => SubSpecialty instance
subspecialtyDict = {}
subspecs = SubSpecialty.objects.using('prod').select_related('specialty').all()
for m in subspecs:
    subspecialtyDict[(m.specialty.name, m.name)] = m

# PROD: license type name  => LicenseType instance
ltypeDict = {}
ltypes = LicenseType.objects.using('prod').all()
for m in ltypes:
    ltypeDict[m.name] = m

# PROD: goal type name  => GoalType instance
goaltypeDict = {}
goaltypes = GoalType.objects.using('prod').all()
for m in goaltypes:
    goaltypeDict[m.name] = m

# PROD: cmetag name  => CmeTag instance
tagDict = {}
cmetags = CmeTag.objects.using('prod').all()
for m in cmetags:
    tagDict[m.name] = m


def copyCmeTags():
    num_created = 0
    tags_test = CmeTag.objects.all().order_by('pk')
    for tag in tags_test:
        qs = CmeTag.objects.using('prod').filter(name__iexact=tag.name)
        if not qs.exists():
            tag_prod = CmeTag.objects.using('prod').create(
                    name=tag.name,
                    description=tag.description,
                    srcme_only=tag.srcme_only,
                    instructions=tag.instructions
                )
            print('Created tag_prod: {0} srcme_only: {0.srcme_only}'.format(tag_prod))
            num_created += 1
        else:
            tag_prod = qs[0]
            if tag_prod.name != tag.name:
                tag_prod.name = tag.name
            tag_prod.description = tag.description
            tag_prod.srcme_only = tag.srcme_only
            tag_prod.instructions = tag.instructions
            tag_prod.save()
            print('Updated tag_prod: {0} srcme_only: {0.srcme_only}'.format(tag_prod))
    return num_created

def copySubSpecs():
    num_created = 0
    subspecs_test = SubSpecialty.objects.select_related('specialty').all().order_by('pk')
    for m in subspecs_test:
        qs = SubSpecialty.objects.using('prod').select_related('specialty').filter(specialty__name=m.specialty.name, name=m.name)
        if not qs.exists():
            ps_prod = specialtyDict[m.specialty.name]
            m_prod = SubSpecialty.objects.using('prod').create(specialty=ps_prod, name=m.name)
            print('Created subspec_prod: {0.specialty}|{0.name}'.format(m_prod))
            num_created += 1
    return num_created

def copyStateTags():
    """Copy state.cmeTags, doTags, and StateDeatag"""
    num_created = 0
    tagsDict = {}
    tags_prod = CmeTag.objects.using('prod').all()
    for tag in tags_prod:
        tagsDict[tag.name] = tag
    country = Country.objects.get(code=Country.USA)
    states = country.states.all().order_by('abbrev')
    for state in states:
        state_prod = statesDict[state.abbrev]
        # cmeTags
        for tag in state.cmeTags.all():
            tag_prod = tagsDict[tag.name]
            state_prod.cmeTags.add(tag_prod)
            logger.info('State {0} cmeTag {1}'.format(state_prod, tag_prod))
        # doTags
        for tag in state.doTags.all():
            tag_prod = tagsDict[tag.name]
            state_prod.doTags.add(tag_prod)
            logger.info('State {0} doTag {1}'.format(state_prod, tag_prod))
        # StateDeatag
        dea_tags = StateDeatag.objects.select_related('tag').filter(state=state)
        for sd in dea_tags:
            tag_prod = tagsDict[sd.tag.name]
            sd_prod, created = StateDeatag.objects.using('prod').get_or_create(state=state_prod, tag=tag_prod, dea_in_state=sd.dea_in_state)
            if created:
                logger.info('Created StateDeatag {0} dea_in_state: {0.dea_in_state}'.format(sd_prod))
                num_created += 1
    return num_created # StateDeatag only

def copyLicenseGoals():
    num_created = 0
    lgoals_test = LicenseGoal.objects.select_related('licenseType','state','goal').order_by('pk')
    for lgoal in lgoals_test:
        bg = lgoal.goal
        # get prod refs
        goaltype_prod = goaltypeDict[bg.goalType.name]
        ltype_prod = ltypeDict[lgoal.licenseType.name]
        degs_prod = [degreeDict[deg.abbrev] for deg in bg.degrees.all()]
        state_prod = statesDict[lgoal.state.abbrev]
        qset_prod = LicenseGoal.objects.using('prod').filter(licenseType=ltype_prod, state=state_prod)
        if qset_prod.exists():
            print('Prod LG exists for {0}/{1}'.format(state_prod, ltype_prod))
            continue
        # else create
        with transaction.atomic():
            bg_prod = BaseGoal.objects.using('prod').create(
                    goalType=goaltype_prod,
                    dueDateType=bg.dueDateType,
                    interval=bg.interval
                )
            bg_prod.degrees.set(degs_prod)
            lg_prod = LicenseGoal.objects.using('prod').create(
                    title=lgoal.title,
                    goal=bg_prod,
                    state=state_prod,
                    licenseType=ltype_prod
                )
            logger.info('Created Prod LicenseGoal: {0}'.format(lg_prod))
            num_created += 1
    return num_created


def createBoardCmeGoals():
    """Board CMEGoals"""
    created = []
    cmegoals_test = CmeGoal.objects \
        .select_related('goal','board','cmeTag') \
        .prefetch_related('goal__degrees','goal__specialties','creditTypes') \
        .filter(board__isnull=False) \
        .order_by('pk')
    for cg in cmegoals_test:
        bg = cg.goal # basegoal
        # get prod refs
        if cg.cmeTag:
            tag_prod = tagDict[cg.cmeTag.name]
        else:
            tag_prod = None
        goaltype_prod = goaltypeDict[bg.goalType.name]
        board_prod = boardDict[cg.board.name]
        degs_prod = [degreeDict[deg.abbrev] for deg in bg.degrees.all()]
        specs_prod = [specialtyDict[ps.name] for ps in bg.specialties.all()]
        subspecs_prod = [subspecialtyDict[(ss.specialty.name, ss.name)] for ss in bg.subspecialties.all()]
        ctypes_prod = [creditTypeDict[ct.abbrev] for ct in cg.creditTypes.all()]
        # create basegoal
        with transaction.atomic():
            bg_prod = BaseGoal.objects.using('prod').create(
                goalType=goaltype_prod,
                dueDateType=bg.dueDateType,
                interval=bg.interval,
                notes=bg.notes
            )
            for deg in degs_prod:
                bg_prod.degrees.add(deg)
            for spec in specs_prod:
                bg_prod.specialties.add(spec)
            for subspec in subspecs_prod:
                bg_prod.subspecialties.add(subspec)
            # create cmegoal
            cg_prod = CmeGoal.objects.using('prod').create(
                goal=bg_prod,
                entityType=CmeGoal.BOARD,
                board=board_prod,
                cmeTag=tag_prod,
                credits=cg.credits,
                mapNullTagToSpecialty=cg.mapNullTagToSpecialty,
                dueMonth=cg.dueMonth,
                dueDay=cg.dueDay
            )
            for m in ctypes_prod:
                cg_prod.creditTypes.add(m)
        msg = "Created PROD {0.board} Board {0.goal.goalType}-Goal {0.pk}|{0}|{0.cmeTag}|{0.credits}|{1}".format(cg_prod, cg_prod.formatCreditTypes())
        print(msg)
        logger.info(msg)
        created.append(cg_prod)
    return created

def createStateCmeGoals():
    """one-time create only"""
    created = []
    cmegoals_test = CmeGoal.objects \
        .select_related('goal','state','cmeTag','licenseGoal') \
        .prefetch_related('goal__degrees','goal__specialties','creditTypes') \
        .filter(entityType=CmeGoal.STATE, state__isnull=False) \
        .order_by('pk')
    for cg in cmegoals_test:
        bg = cg.goal # basegoal
        lgoal = cg.licenseGoal
        # get prod refs
        if cg.cmeTag:
            tag_prod = tagDict[cg.cmeTag.name]
        else:
            tag_prod = None
        goaltype_prod = goaltypeDict[bg.goalType.name]
        degs_prod = [degreeDict[deg.abbrev] for deg in bg.degrees.all()]
        specs_prod = [specialtyDict[ps.name] for ps in bg.specialties.all()]
        subspecs_prod = [subspecialtyDict[(ss.specialty.name, ss.name)] for ss in bg.subspecialties.all()]
        ctypes_prod = [creditTypeDict[ct.abbrev] for ct in cg.creditTypes.all()]
        ltype_prod = ltypeDict[lgoal.licenseType.name]
        state_prod = statesDict[lgoal.state.abbrev]
        lg_prod = LicenseGoal.objects.using('prod').get(state=state_prod, licenseType=ltype_prod)
        # create basegoal
        with transaction.atomic():
            bg_prod = BaseGoal.objects.using('prod').create(
                goalType=goaltype_prod,
                dueDateType=bg.dueDateType,
                interval=bg.interval,
                notes=bg.notes
            )
            for deg in degs_prod:
                bg_prod.degrees.add(deg)
            for spec in specs_prod:
                bg_prod.specialties.add(spec)
            for subspec in subspecs_prod:
                bg_prod.subspecialties.add(subspec)
            # create cmegoal
            cg_prod = CmeGoal.objects.using('prod').create(
                goal=bg_prod,
                entityType=CmeGoal.STATE,
                state=state_prod,
                licenseGoal=lg_prod,
                cmeTag=tag_prod,
                credits=cg.credits,
                mapNullTagToSpecialty=cg.mapNullTagToSpecialty,
                dueMonth=cg.dueMonth,
                dueDay=cg.dueDay
            )
            for m in ctypes_prod:
                cg_prod.creditTypes.add(m)
        msg = "Created PROD {0.state} State {0.goal.goalType}-Goal {0.pk}|{0}|{0.cmeTag}|{0.credits}|{1}".format(cg_prod, cg_prod.formatCreditTypes())
        print(msg)
        logger.info(msg)
        created.append(cg_prod)
    return created


def createSRCmeGoals():
    """one-time create only"""
    created = []
    srcmegoals_test = SRCmeGoal.objects \
        .select_related('goal','state','cmeTag','licenseGoal') \
        .prefetch_related('goal__degrees','goal__specialties','creditTypes') \
        .filter(entityType=CmeGoal.STATE, state__isnull=False) \
        .order_by('pk')
    for cg in srcmegoals_test:
        bg = cg.goal # basegoal
        lgoal = cg.licenseGoal
        # get prod refs
        tag_prod = tagDict[cg.cmeTag.name]
        goaltype_prod = goaltypeDict[bg.goalType.name]
        degs_prod = [degreeDict[deg.abbrev] for deg in bg.degrees.all()]
        specs_prod = [specialtyDict[ps.name] for ps in bg.specialties.all()]
        subspecs_prod = [subspecialtyDict[(ss.specialty.name, ss.name)] for ss in bg.subspecialties.all()]
        ctypes_prod = [creditTypeDict[ct.abbrev] for ct in cg.creditTypes.all()]
        ltype_prod = ltypeDict[lgoal.licenseType.name]
        state_prod = statesDict[lgoal.state.abbrev]
        lg_prod = LicenseGoal.objects.using('prod').get(state=state_prod, licenseType=ltype_prod)
        # create basegoal
        with transaction.atomic():
            bg_prod = BaseGoal.objects.using('prod').create(
                goalType=goaltype_prod,
                dueDateType=bg.dueDateType,
                interval=bg.interval,
                notes=bg.notes
            )
            for deg in degs_prod:
                bg_prod.degrees.add(deg)
            for spec in specs_prod:
                bg_prod.specialties.add(spec)
            for subspec in subspecs_prod:
                bg_prod.subspecialties.add(subspec)
            # create cmegoal
            cg_prod = SRCmeGoal.objects.using('prod').create(
                goal=bg_prod,
                state=state_prod,
                licenseGoal=lg_prod,
                cmeTag=tag_prod,
                credits=cg.credits,
                has_credit=cg.has_credit,
                dueMonth=cg.dueMonth,
                dueDay=cg.dueDay
            )
            for m in ctypes_prod:
                cg_prod.creditTypes.add(m)
        msg = "Created PROD {0.state} State {0.goal.goalType}-Goal {0.pk}|{0}|{0.cmeTag}|{0.credits}|{1}".format(cg_prod, cg_prod.formatCreditTypes())
        print(msg)
        logger.info(msg)
        created.append(cg_prod)
    return created
