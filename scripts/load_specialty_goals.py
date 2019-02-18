import pandas as pd
import numpy as np
import logging
from users.models import *
from goals.models import *
from import_state_goals import *

logger = logging.getLogger('mgmt.goals')

#
# Specialty srcmegoals
# df2 = df[(~df.Specialties.isnull()) & (~df.Srcme_tag.isnull()) & (~df.Credits.isnull()) & (~df.Interval.isnull())]
#

def load_ia_childabuse_srcmegoal():
    """
    ('IA', 'MD, DO', 'pediatrics, family medicine', 'child abuse (IA-specific)', '5', 2.0, 'any')
    Returns: SRCmeGoal
    """
    tag = CmeTag.objects.get(name__iexact='Child Abuse (IA-specific)')
    state = statesDict['IA']
    degrees = [degreeDict['MD'], degreeDict['DO']]
    creditTypes = [] # any
    interval = 5
    credits = 2
    has_credit = True
    specialties = [
            specialtyDict['Pediatrics'],
            specialtyDict['Family Medicine'],
        ]
    lg = getStateLicenseGoal(state)
    # check if exist
    fkwargs = {
            'state': state,
            'licenseGoal': lg,
            'cmeTag': tag,
            'credits': credits,
            'goal__interval': interval,
            'has_credit': has_credit,
        }
    # check if exist
    qs = SRCmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
    for cmegoal in qs:
        for cg in qs:
            if (isEqual(degrees, cmegoal.goal.degrees.all())
                    and isEqual(specialties, cmegoal.goal.specialties.all())
                    and isEqual(creditTypes, cmegoal.creditTypes.all())):
                print('Found existing srcmegoal: {0}'.format(cg))
                return cg
    # create basegoal
    bg_dueDateType = BaseGoal.RECUR_LICENSE_DATE if interval > 0 else BaseGoal.ONE_OFF
    bg = BaseGoal.objects.create(
        goalType=goaltype_srcme,
        dueDateType=bg_dueDateType,
        interval=interval,
        notes=''
    )
    for deg in degrees:
        bg.degrees.add(deg)
    for spec in specialties:
        bg.specialties.add(spec)
    # create srcmegoal
    cmegoal = SRCmeGoal.objects.create(
        goal=bg,
        state=state,
        cmeTag=tag,
        licenseGoal=lg,
        credits=credits,
        has_credit=has_credit
    )
    for m in creditTypes:
        cmegoal.creditTypes.add(m)
    msg = "Created {0.state} Specialty SRCmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
    print(msg)
    logger.info(msg)
    return cmegoal

def load_ia_adultabuse_srcmegoal():
    """
    ('IA', 'internal medicine/primary care, emergency medicine/primary care', 'adult abuse (IA-specific)', '5', 2.0, 'any')
    Returns: SRCmeGoal
    """
    tag = CmeTag.objects.get(name__iexact='Child Abuse (IA-specific)')
    state = statesDict['IA']
    degrees = [degreeDict['MD'], degreeDict['DO']]
    creditTypes = [] # any
    interval = 5
    credits = 2
    has_credit = True
    specialties = [
            specialtyDict['Emergency Medicine'],
            specialtyDict['Internal Medicine'],
        ]
    subspecialties = [
            subspecialtyDict[('Internal Medicine', 'Primary Care')],
            subspecialtyDict[('Emergency Medicine', 'Primary Care')],
        ]
    lg = getStateLicenseGoal(state)
    # check if exist
    fkwargs = {
            'state': state,
            'licenseGoal': lg,
            'cmeTag': tag,
            'credits': credits,
            'goal__interval': interval,
            'has_credit': has_credit,
        }
    # check if exist
    qs = SRCmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
    for cmegoal in qs:
        for cg in qs:
            if (isEqual(degrees, cmegoal.goal.degrees.all())
                    and isEqual(specialties, cmegoal.goal.specialties.all())
                    and isEqual(subspecialties, cmegoal.goal.subspecialties.all())
                    and isEqual(creditTypes, cmegoal.creditTypes.all())):
                print('Found existing srcmegoal: {0}'.format(cg))
                return cg
    # create basegoal
    bg_dueDateType = BaseGoal.RECUR_LICENSE_DATE if interval > 0 else BaseGoal.ONE_OFF
    bg = BaseGoal.objects.create(
        goalType=goaltype_srcme,
        dueDateType=bg_dueDateType,
        interval=interval,
        notes=''
    )
    for deg in degrees:
        bg.degrees.add(deg)
    for spec in specialties:
        bg.specialties.add(spec)
    for subspec in subspecialties:
        bg.subspecialties.add(subspec)
    # create srcmegoal
    cmegoal = SRCmeGoal.objects.create(
        goal=bg,
        state=state,
        cmeTag=tag,
        licenseGoal=lg,
        credits=credits,
        has_credit=has_credit
    )
    for m in creditTypes:
        cmegoal.creditTypes.add(m)
    msg = "Created {0.state} Specialty SRCmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
    print(msg)
    logger.info(msg)
    return cmegoal

def load_ky_dvt_srcmegoal():
    """
    ('KY', 'internal medicine/primary care', 'domestic violence training (KY-specific)', 'once', 3.0, 'any')
    Returns: SRCmeGoal
    """
    tag = CmeTag.objects.get(name__iexact='Domestic Violence Training (KY-specific)')
    state = statesDict['KY']
    degrees = [degreeDict['MD'], degreeDict['DO']]
    creditTypes = [] # any
    interval = 0 # once
    credits = 3
    has_credit = True
    specialties = [
            specialtyDict['Internal Medicine'],
        ]
    subspecialties = [
            subspecialtyDict[('Internal Medicine', 'Primary Care')],
        ]
    lg = getStateLicenseGoal(state)
    # check if exist
    fkwargs = {
            'state': state,
            'licenseGoal': lg,
            'cmeTag': tag,
            'credits': credits,
            'goal__interval': interval,
            'has_credit': has_credit,
        }
    # check if exist
    qs = SRCmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
    for cmegoal in qs:
        for cg in qs:
            if (isEqual(degrees, cmegoal.goal.degrees.all())
                    and isEqual(specialties, cmegoal.goal.specialties.all())
                    and isEqual(subspecialties, cmegoal.goal.subspecialties.all())
                    and isEqual(creditTypes, cmegoal.creditTypes.all())):
                print('Found existing srcmegoal: {0}'.format(cg))
                return cg
    # create basegoal
    bg_dueDateType = BaseGoal.RECUR_LICENSE_DATE if interval > 0 else BaseGoal.ONE_OFF
    bg = BaseGoal.objects.create(
        goalType=goaltype_srcme,
        dueDateType=bg_dueDateType,
        interval=interval,
        notes=''
    )
    for deg in degrees:
        bg.degrees.add(deg)
    for spec in specialties:
        bg.specialties.add(spec)
    for subspec in subspecialties:
        bg.subspecialties.add(subspec)
    # create srcmegoal
    cmegoal = SRCmeGoal.objects.create(
        goal=bg,
        state=state,
        cmeTag=tag,
        licenseGoal=lg,
        credits=credits,
        has_credit=has_credit
    )
    for m in creditTypes:
        cmegoal.creditTypes.add(m)
    msg = "Created {0.state} Specialty SRCmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
    print(msg)
    logger.info(msg)
    return cmegoal

def load_ky_pediatric_srcmegoal():
    """
    ('KY', 'pediatrics, radiology, family medicine, emergency medicine, internal medicine/urgent care', 'pediatric abusive head trauma (KY-specific)', 'once', 1.0, 'any')
    Returns: SRCmeGoal
    """
    tag = CmeTag.objects.get(name__iexact='Pediatric Abusive Head Trauma (KY-specific)')
    state = statesDict['KY']
    degrees = [degreeDict['MD'], degreeDict['DO']]
    creditTypes = [] # any
    interval = 0 # once
    credits = 1
    has_credit = True
    specialties = [
            specialtyDict['Pediatrics'],
            specialtyDict['Radiology'],
            specialtyDict['Family Medicine'],
            specialtyDict['Emergency Medicine'],
            specialtyDict['Internal Medicine'],
        ]
    subspecialties = [
            subspecialtyDict[('Internal Medicine', 'Urgent Care')],
        ]
    lg = getStateLicenseGoal(state)
    # check if exist
    fkwargs = {
            'state': state,
            'licenseGoal': lg,
            'cmeTag': tag,
            'credits': credits,
            'goal__interval': interval,
            'has_credit': has_credit,
        }
    # check if exist
    qs = SRCmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
    for cmegoal in qs:
        for cg in qs:
            if (isEqual(degrees, cmegoal.goal.degrees.all())
                    and isEqual(specialties, cmegoal.goal.specialties.all())
                    and isEqual(subspecialties, cmegoal.goal.subspecialties.all())
                    and isEqual(creditTypes, cmegoal.creditTypes.all())):
                print('Found existing srcmegoal: {0}'.format(cg))
                return cg
    # create basegoal
    bg_dueDateType = BaseGoal.RECUR_LICENSE_DATE if interval > 0 else BaseGoal.ONE_OFF
    bg = BaseGoal.objects.create(
        goalType=goaltype_srcme,
        dueDateType=bg_dueDateType,
        interval=interval,
        notes=''
    )
    for deg in degrees:
        bg.degrees.add(deg)
    for spec in specialties:
        bg.specialties.add(spec)
    for subspec in subspecialties:
        bg.subspecialties.add(subspec)
    # create srcmegoal
    cmegoal = SRCmeGoal.objects.create(
        goal=bg,
        state=state,
        cmeTag=tag,
        licenseGoal=lg,
        credits=credits,
        has_credit=has_credit
    )
    for m in creditTypes:
        cmegoal.creditTypes.add(m)
    msg = "Created {0.state} Specialty SRCmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
    print(msg)
    logger.info(msg)
    return cmegoal


def load_tx_forensic_srcmegoal():
    """
    Note: we decided to make this a credits=1 goal since it is a CME course.
    ('TX', 'Emergency Medicine, Internal Medicine, Family Medicine', 'forensic evidence collection in sexual assault (TX-specific)', 'once', 0.0, 'AMA-1, AOA-1A')
    Returns: SRCmeGoal
    """
    tag = CmeTag.objects.get(name__iexact='Forensic Evidence Collection in Sexual Assault (TX-specific)')
    state = statesDict['TX']
    degrees = [degreeDict['MD'], degreeDict['DO']]
    creditTypes = [
            get_creditType('AMA-1'),
            get_creditType('AOA-1A'),
        ]
    interval = 0 # once
    credits = 1
    has_credit = True
    specialties = [
            specialtyDict['Family Medicine'],
            specialtyDict['Emergency Medicine'],
            specialtyDict['Internal Medicine'],
        ]
    subspecialties = []
    lg = getStateLicenseGoal(state)
    # check if exist
    fkwargs = {
            'state': state,
            'licenseGoal': lg,
            'cmeTag': tag,
            'credits': credits,
            'goal__interval': interval,
            'has_credit': has_credit,
        }
    # check if exist
    qs = SRCmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
    for cmegoal in qs:
        for cg in qs:
            if (isEqual(degrees, cmegoal.goal.degrees.all())
                    and isEqual(specialties, cmegoal.goal.specialties.all())
                    and isEqual(subspecialties, cmegoal.goal.subspecialties.all())
                    and isEqual(creditTypes, cmegoal.creditTypes.all())):
                print('Found existing srcmegoal: {0}'.format(cg))
                return cg
    # create basegoal
    bg_dueDateType = BaseGoal.RECUR_LICENSE_DATE if interval > 0 else BaseGoal.ONE_OFF
    bg = BaseGoal.objects.create(
        goalType=goaltype_srcme,
        dueDateType=bg_dueDateType,
        interval=interval,
        notes=''
    )
    for deg in degrees:
        bg.degrees.add(deg)
    for spec in specialties:
        bg.specialties.add(spec)
    for subspec in subspecialties:
        bg.subspecialties.add(subspec)
    # create srcmegoal
    cmegoal = SRCmeGoal.objects.create(
        goal=bg,
        state=state,
        cmeTag=tag,
        licenseGoal=lg,
        credits=credits,
        has_credit=has_credit
    )
    for m in creditTypes:
        cmegoal.creditTypes.add(m)
    msg = "Created {0.state} Specialty SRCmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
    print(msg)
    logger.info(msg)
    return cmegoal


def load_tx_emsdir_srcmegoal():
    """
    ('TX', 'Emergency Medicine/EMS Medical Director', 'DSHS-approved EMS medical director course (TX-specific)', 'once', 12.0, 'any')
    """
    tag = CmeTag.objects.get(name__iexact='DSHS-approved EMS Medical Director Course (TX-specific)')
    state = statesDict['TX']
    degrees = [degreeDict['MD'], degreeDict['DO']]
    creditTypes = [] # any
    interval = 0 # once
    credits = 12
    has_credit = True
    specialties = [
            specialtyDict['Emergency Medicine'],
        ]
    subspecialties = [
            subspecialtyDict[('Emergency Medicine', 'EMS Medical Director')],
        ]
    lg = getStateLicenseGoal(state)
    # check if exist
    fkwargs = {
            'state': state,
            'licenseGoal': lg,
            'cmeTag': tag,
            'credits': credits,
            'goal__interval': interval,
            'has_credit': has_credit,
        }
    # check if exist
    qs = SRCmeGoal.objects.filter(**fkwargs).select_related('goal').order_by('pk')
    for cmegoal in qs:
        for cg in qs:
            if (isEqual(degrees, cmegoal.goal.degrees.all())
                    and isEqual(specialties, cmegoal.goal.specialties.all())
                    and isEqual(subspecialties, cmegoal.goal.subspecialties.all())
                    and isEqual(creditTypes, cmegoal.creditTypes.all())):
                print('Found existing srcmegoal: {0}'.format(cg))
                return cg
    # create basegoal
    bg_dueDateType = BaseGoal.RECUR_LICENSE_DATE if interval > 0 else BaseGoal.ONE_OFF
    bg = BaseGoal.objects.create(
        goalType=goaltype_srcme,
        dueDateType=bg_dueDateType,
        interval=interval,
        notes=''
    )
    for deg in degrees:
        bg.degrees.add(deg)
    for spec in specialties:
        bg.specialties.add(spec)
    for subspec in subspecialties:
        bg.subspecialties.add(subspec)
    # create srcmegoal
    cmegoal = SRCmeGoal.objects.create(
        goal=bg,
        state=state,
        cmeTag=tag,
        licenseGoal=lg,
        credits=credits,
        has_credit=has_credit
    )
    for m in creditTypes:
        cmegoal.creditTypes.add(m)
    msg = "Created {0.state} Specialty SRCmeGoal {0.pk}|{0}|{0.credits}|{1}".format(cmegoal, cmegoal.formatCreditTypes())
    print(msg)
    logger.info(msg)
    return cmegoal


