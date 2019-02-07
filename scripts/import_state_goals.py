import pandas as pd
import numpy as np
import logging
from users.models import *
from goals.models import *

logger = logging.getLogger('mgmt.goals')

# degree abbrev => Degreeinstance
degreeDict = {}
degrees = Degree.objects.all()
for m in degrees:
    degreeDict[m.abbrev] = m

# credit type abbrev => CreditType instance
creditTypeDict = {}
creditTypes = CreditType.objects.all()
for m in creditTypes:
    creditTypeDict[m.abbrev] = m

# state-abbrev => State instance
statesDict = {}
country = Country.objects.get(code=Country.USA)
states = country.states.all()
for state in states:
    statesDict[state.abbrev] = state

med_board_lt = LicenseType.objects.get(name='Medical Board')
goaltype_cme = GoalType.objects.get(name=GoalType.CME)

def getStateLicenseGoal(state):
    return LicenseGoal.objects.get(state=state, licenseType=med_board_lt)

def clean_tag(name):
    L = name.split()
    L2 = []
    for v in L:
        if v == 'subtances':
            v = 'substances'
        if v != 'and':
            v2 = v[0].upper() + v[1:]
        else:
            v2 = v
        L2.append(v2)
    name2 = ' '.join(L2)
    return name2

def get_state(val):
    if val == 'DC':
        return statesDict['Washington DC']
    return statesDict[val]

def handle_subspecialty(df):
    """need to run this in prod"""
    pm_name = 'Pain Management' # for all specs
    pc_name = 'Primary Care' # for Internal Med, EM
    uc_name = 'Urgent Care'
    uc_specs = ('Pediatrics','Radiology','Family Medicine','Emergency Medicine','Internal Medicine')
    sa_name = 'Sexual Assault'
    sa_specs = ('Emergency Medicine', 'Internal Medicine', 'Family Medicine')

    specs = PracticeSpecialty.objects.all().order_by('name')
    for ps in specs:
        pm_subspec, created = SubSpecialty.objects.get_or_create(specialty=ps, name=pm_name)
        if created:
            logger.info('Created {0} SubSpecialty {1}'.format(ps, pm_subspec))
        if ps.name == 'Emergency Medicine' or ps.name == 'Internal Medicine':
            pc_subspec, created = SubSpecialty.objects.get_or_create(specialty=ps, name=pc_name)
            if created:
                logger.info('Created {0} SubSpecialty {1}'.format(ps, pm_subspec))
        if ps.name in uc_specs:
            uc_subspec, created = SubSpecialty.objects.get_or_create(specialty=ps, name=uc_name)
            if created:
                logger.info('Created {0} SubSpecialty {1}'.format(ps, uc_subspec))
        if ps.name in sa_specs:
            sa_subspec, created = SubSpecialty.objects.get_or_create(specialty=ps, name=sa_name)
            if created:
                logger.info('Created {0} SubSpecialty {1}'.format(ps, sa_subspec))


def handle_dea_state_tag(df):
    df2 = df[df.DEA_specific == 'this_state']
    for index, row in df2.iterrows():
        srcme_only = False
        state = get_state(row['State'])
        raw_tag = row['Tag']
        if pd.isnull(raw_tag):
            raw_tag = row['Srcme_tag']
            srcme_only = True
        if pd.isnull(raw_tag):
            logger.warning('!! State {0} for DEA this_state has no tag!')
            continue
        if ',' in raw_tag:
            logger.warning('Skip tag with comma in it: {0} for State {1}'.format(raw_tag, state))
            continue
        if raw_tag == 'general' or raw_tag == 'specialty':
            logger.warning('Skip raw_tag: {0} for State {1}'.format(raw_tag, state))
            continue
        tagname = clean_tag(raw_tag)
        tag, created = CmeTag.objects.get_or_create(name=tagname, description=tagname, srcme_only=srcme_only)
        if created:
            logger.info('Created {0} srcme_only: {0.srcme_only} for DEA in_state {1}'.format(tag, state))
        # add it to state.deaTags
        dat = StateDeatag.objects.get_or_create(state=state, tag=tag, dea_in_state=True)
    df2 = df[df.DEA_specific == 'any_state']
    for index, row in df2.iterrows():
        srcme_only = False
        state = get_state(row['State'])
        raw_tag = row['Tag']
        if pd.isnull(raw_tag):
            raw_tag = row['Srcme_tag']
            srcme_only = True
        if pd.isnull(raw_tag):
            logger.warning('!! State {0} for DEA any_state has no tag!')
            continue
        if ',' in raw_tag:
            logger.warning('Skip tag with comma in it: {0} for State {1}'.format(raw_tag, state))
            continue
        if raw_tag == 'general' or raw_tag == 'specialty':
            logger.warning('Skip raw_tag: {0} for State {1}'.format(raw_tag, state))
            continue
        tagname = clean_tag(raw_tag)
        tag, created = CmeTag.objects.get_or_create(name=tagname, description=tagname, srcme_only=srcme_only)
        if created:
            logger.info('Created {0} srcme_only: {0.srcme_only} for DEA any_state {1}'.format(tag, state))
        # add it to state.deaTags
        dat = StateDeatag.objects.get_or_create(state=state, tag=tag, dea_in_state=False)


def handle_state_cme_tag(df):
    """Non-DEA regular state cme tags"""
    df2 = df[(df.DEA_specific.isnull()) & (~df.Tag.isnull())]
    for index, row in df2.iterrows():
        state = get_state(row['State'])
        raw_tag = row['Tag']
        if ',' in raw_tag:
            logger.warning('Skip tag with comma in it: {0} for State {1}'.format(raw_tag, state))
            continue
        if raw_tag == 'general' or raw_tag == 'specialty':
            logger.warning('Skip raw_tag: {0} for State {1}'.format(raw_tag, state))
            continue
        tagname = clean_tag(raw_tag)
        tag, created = CmeTag.objects.get_or_create(name=tagname, description=tagname, srcme_only=False)
        if created:
            logger.info('Created tag: {0} for state {1}'.format(tag, state))
        # assign to state.cmeTags
        state.cmeTags.add(tag)

def handle_state_srcme_tag(df):
    """Non-DEA srcme tags"""
    df2 = df[(df.EntryType == 'self') & (df.DEA_specific.isnull()) & (~df.Srcme_tag.isnull())]
    for index, row in df2.iterrows():
        state = get_state(row['State'])
        raw_tag = row['Srcme_tag']
        if ',' in raw_tag:
            logger.warning('Skip tag with comma in it: {0} for State {1}'.format(raw_tag, state))
            continue
        if raw_tag == 'general' or raw_tag == 'specialty':
            logger.warning('Skip raw_tag: {0} for State {1}'.format(raw_tag, state))
            continue
        tagname = clean_tag(raw_tag)
        tag, created = CmeTag.objects.get_or_create(name=tagname, description=tagname, srcme_only=True)
        if created:
            logger.info('Created srcme_only tag: {0} for state {1}'.format(tag, state))
        # assign to state.cmeTags
        state.cmeTags.add(tag)

def handle_state_DO_tag(df):
    """state.doTags"""
    df2 = df[(df.EntryType == 'self') & (df.DEA_specific.isnull()) & (~df.AOA_srcme_tag.isnull())]
    for index, row in df2.iterrows():
        state = get_state(row['State'])
        raw_tag = row['AOA_srcme_tag']
        if ',' in raw_tag:
            logger.warning('Skip tag with comma in it: {0} for State {1}'.format(raw_tag, state))
            continue
        if raw_tag == 'general' or raw_tag == 'specialty':
            logger.warning('Skip raw_tag: {0} for State {1}'.format(raw_tag, state))
            continue
        tagname = clean_tag(raw_tag)
        tag, created = CmeTag.objects.get_or_create(name=tagname, description=tagname, srcme_only=True)
        if created:
            logger.info('Created DO srcme_only tag: {0} for state {1}'.format(tag, state))
        # assign to state.doTags
        state.doTags.add(tag)


def getCreditTypesFromRow(row):
    s = row['CreditTypes']
    if pd.isnull(s): # to handle nan??
        return []
    s = s.strip()
    if not s:
        return []
    if s.lower() == 'any':
        return []
    if ',' in s:
        L = s.split(',')
        data = [creditTypeDict[k.strip()] for k in L]
    else:
        k = s.strip()
        data = [creditTypeDict[k],]
    return data

def getDegreesFromRow(row):
    s = row['Degree']
    if ',' in s:
        L = s.split(',')
        data = [degreeDict[k.strip()] for k in L]
    else:
        k = s.strip()
        data = [degreeDict[k],]
    return data

def isEqual(a, b):
    """Compare lists/querysets of model instances"""
    a_set = set([m.pk for m in a])
    b_set = set([m.pk for m in b])
    return a_set == b_set


def handle_plain_general_cme_goals(df):
    cmegoals = []
    df2 = df[(df.Tag == 'general') & (df.EntryType == 'both') & (df.Exclude_specialties.isnull()) & (df.Specialties.isnull()) & (~df.Credits.isnull()) & (~df.Interval.isnull())]
    for index, row in df2.iterrows():
        print(row['State'], row['Degree'], row['Interval'], row['Credits'], row['CreditTypes'])
        state = get_state(row['State'])
        raw_tag = row['Tag']
        interval = int(row['Interval'])
        credits = int(row['Credits'])
        creditTypes = getCreditTypesFromRow(row)
        degrees = getDegreesFromRow(row)
        # Create CmeGoal with associated licenseGoal and tag=null
        lg = getStateLicenseGoal(state)
        fkwargs = {
            'entityType': CmeGoal.STATE,
            'state': state,
            'licenseGoal': lg,
            'cmeTag__isnull': True,
            'mapNullTagToSpecialty': False,
            'credits': credits,
            'goal__interval': interval
        }
        do_create = True
        # check if exist
        qs = CmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
        for cmegoal in qs:
            if isEqual(degrees, cmegoal.goal.degrees.all()) and isEqual(creditTypes, cmegoal.creditTypes.all()):
                do_create = False
                cmegoals.append(cmegoal)
                break
        if not do_create:
            msg = " - exists: CmeGoal {0.pk}|{0}|{0.credits} credits in {1}".format(cmegoal, cmegoal.formatCreditTypes())
            print(msg)
            logger.debug(msg)
            continue
        # create basegoal
        bg = BaseGoal.objects.create(
            goalType=goaltype_cme,
            dueDateType=BaseGoal.RECUR_LICENSE_DATE,
            interval=interval,
            notes=row['Description']
        )
        for deg in degrees:
            bg.degrees.add(deg)
        # create cmegoal
        cmegoal = CmeGoal.objects.create(
            goal=bg,
            entityType=CmeGoal.STATE,
            state=state,
            cmeTag=None,
            mapNullTagToSpecialty=False,
            licenseGoal=lg,
            credits=credits,
        )
        for m in creditTypes:
            cmegoal.creditTypes.add(m)
        msg = "Created general CmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
        print(msg)
        logger.info(msg)
        cmegoals.append(cmegoal)
    return cmegoals

def handle_plain_mapnulltospec_cme_goals(df):
    cmegoals = []
    df2 = df[(df.Tag == 'specialty') & (df.Exclude_specialties.isnull()) & (df.Specialties.isnull())  & (~df.Credits.isnull()) & (~df.Interval.isnull())]
    for index, row in df2.iterrows():
        print(row['State'], row['Degree'], row['Interval'], row['Credits'], row['CreditTypes'])
        state = get_state(row['State'])
        raw_tag = row['Tag']
        interval = int(row['Interval'])
        credits = int(row['Credits'])
        creditTypes = getCreditTypesFromRow(row)
        degrees = getDegreesFromRow(row)
        # Create CmeGoal with associated licenseGoal and tag=null
        lg = getStateLicenseGoal(state)
        fkwargs = {
            'entityType': CmeGoal.STATE,
            'state': state,
            'licenseGoal': lg,
            'cmeTag__isnull': True,
            'mapNullTagToSpecialty': True,
            'credits': credits,
            'goal__interval': interval
        }
        do_create = True
        # check if exist
        qs = CmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
        for cmegoal in qs:
            if isEqual(degrees, cmegoal.goal.degrees.all()) and isEqual(creditTypes, cmegoal.creditTypes.all()):
                do_create = False
                cmegoals.append(cmegoal)
                break
        if not do_create:
            msg = " - exists: mapNullToSpec CmeGoal {0.pk}|{0}|{0.credits} credits in {1}".format(cmegoal, cmegoal.formatCreditTypes())
            print(msg)
            logger.debug(msg)
            continue
        # create basegoal
        bg = BaseGoal.objects.create(
            goalType=goaltype_cme,
            dueDateType=BaseGoal.RECUR_LICENSE_DATE,
            interval=interval,
            notes=row['Description']
        )
        for deg in degrees:
            bg.degrees.add(deg)
        # create cmegoal
        cmegoal = CmeGoal.objects.create(
            goal=bg,
            entityType=CmeGoal.STATE,
            state=state,
            cmeTag=None,
            mapNullTagToSpecialty=True,
            licenseGoal=lg,
            credits=credits,
        )
        for m in creditTypes:
            cmegoal.creditTypes.add(m)
        msg = "Created mapNullToSpec CmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
        print(msg)
        logger.info(msg)
        cmegoals.append(cmegoal)
    return cmegoals

def handle_plain_tagged_cme_goals(df):
    """OMIT once!"""
    cmegoals = []
    df2 = df[(~df.Tag.isnull()) & (df.Exclude_specialties.isnull()) & (df.Specialties.isnull())  & (~df.Credits.isnull()) & (~df.Interval.isnull())]
    for index, row in df2.iterrows():
        raw_tag = row['Tag']
        if raw_tag == 'general' or raw_tag == 'specialty':
            continue # already handled these in other methods
        if ',' in raw_tag:
            logger.warning('Skip tag with comma in it: {0} for State {1}'.format(raw_tag, state))
            continue
        if row['Interval'] == 'once':
            logger.warning('Skip once goal: {0} for State {1}'.format(raw_tag, state))
            continue
        print(row['State'], row['Degree'], row['Interval'], row['Tag'], row['Credits'], row['CreditTypes'])
        state = get_state(row['State'])
        interval = int(row['Interval'])
        credits = int(row['Credits'])
        creditTypes = getCreditTypesFromRow(row)
        degrees = getDegreesFromRow(row)
        tagname = clean_tag(raw_tag)
        tag = CmeTag.objects.get(name=tagname)
        # Create CmeGoal with associated licenseGoal and tag
        lg = getStateLicenseGoal(state)
        fkwargs = {
            'entityType': CmeGoal.STATE,
            'state': state,
            'licenseGoal': lg,
            'cmeTag': tag,
            'credits': credits,
            'goal__interval': interval
        }
        do_create = True
        # check if exist
        qs = CmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
        for cmegoal in qs:
            if isEqual(degrees, cmegoal.goal.degrees.all()) and isEqual(creditTypes, cmegoal.creditTypes.all()):
                do_create = False
                cmegoals.append(cmegoal)
                break
        if not do_create:
            msg = " - exists: tagged CmeGoal {0.pk}|{0}|{0.cmeTag}|{0.credits} credits in {1}".format(cmegoal, cmegoal.formatCreditTypes())
            print(msg)
            logger.debug(msg)
            continue
        # create basegoal
        bg = BaseGoal.objects.create(
            goalType=goaltype_cme,
            dueDateType=BaseGoal.RECUR_LICENSE_DATE,
            interval=interval,
            notes=row['Description']
        )
        for deg in degrees:
            bg.degrees.add(deg)
        # create cmegoal
        cmegoal = CmeGoal.objects.create(
            goal=bg,
            entityType=CmeGoal.STATE,
            state=state,
            cmeTag=tag,
            licenseGoal=lg,
            credits=credits,
        )
        for m in creditTypes:
            cmegoal.creditTypes.add(m)
        msg = "Created tagged CmeGoal {0.pk}|{0}|{0.cmeTag}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
        print(msg)
        logger.info(msg)
        cmegoals.append(cmegoal)
    return cmegoals

def handle_entrytype_self(df):
    df2 = df[df.EntryType == 'self']
    for index, row in df2.iterrows():
        state = statesDict[row['State']]

def main(fpath):
    df = pd.read_csv(fpath)