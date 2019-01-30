# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging
from collections import defaultdict
from decimal import Decimal
from datetime import datetime, timedelta
from operator import itemgetter
import math
import pytz
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from common.appconstants import PERM_VIEW_GOAL
from common.dateutils import UNKNOWN_DATE, makeAwareDatetime
from users.models import (
    ARTICLE_CREDIT,
    CMETAG_SACME,
    CmeTag,
    CreditType,
    Degree,
    Document,
    Entry,
    Hospital,
    Profile,
    PracticeSpecialty,
    LicenseType,
    State,
    StateLicense,
    SubSpecialty
)

logger = logging.getLogger('gen.goals')

INTERVAL_ERROR = u'Interval in years must be specified for recurring dueDateType'
DUE_MONTH_ERROR = u'dueMonth must be a valid month in range 1-12'
DUE_DAY_ERROR = u'dueDay must be a valid day for the selected month in range 1-31'
MARGINAL_COMPLIANT_CUTOFF_DAYS = 30
SRCME_MARGINAL_COMPLIANT_CUTOFF_DAYS = 90
ANY_TOPIC = u'Any Topic'

def makeDueDate(year, month, day, now, advance_if_past=True):
    """Create dueDate as (year,month,day) and advance to next year if dueDate is < now
    Returns: datetime
    """
    dueDate = makeAwareDatetime(year, month, day)
    if dueDate < now and advance_if_past:
        dueDate = makeAwareDatetime(year+1, month, day)
    return dueDate

def nround(n):
    """Rounding for creditsDue
    >>> nround(1.0)
    1.0
    >>> nround(1.1)
    1.5
    >>> nround(1.6)
    2.0
    """
    f = math.floor(n)
    d = n - f
    if d == 0:
        return f
    if d <= 0.5:
        return f + 0.5
    return math.ceil(n)

@python_2_unicode_compatible
class Board(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

@python_2_unicode_compatible
class GoalType(models.Model):
    CME = 'CME'
    LICENSE = 'License'
    SRCME = 'SR-CME'
    TRAINING = 'Training'
    # fields
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0,
            help_text='sort order for goals list')
    description = models.CharField(max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

@python_2_unicode_compatible
class BaseGoal(models.Model):
    """This model is the OneToOneField on the individual Goal models"""
    ONE_OFF = 0
    RECUR_MMDD = 1
    RECUR_ANY = 2
    RECUR_BIRTH_DATE = 3
    RECUR_LICENSE_DATE = 4
    ONE_OFF_LABEL =  u'One-off. Due immediately'
    RECUR_MMDD_LABEL = u'Recurring. Due on fixed MM/DD'
    RECUR_ANY_LABEL = u'Recurring. Due at any time counting back over interval'
    RECUR_BIRTH_DATE_LABEL = u'Recurring. Due on user birth date'
    RECUR_LICENSE_DATE_LABEL =  u'Recurring. Due on license expiration date'
    DUEDATE_TYPE_CHOICES = (
        (ONE_OFF, ONE_OFF_LABEL),
        (RECUR_MMDD, RECUR_MMDD_LABEL),
        (RECUR_ANY, RECUR_ANY_LABEL),
        (RECUR_BIRTH_DATE, RECUR_BIRTH_DATE_LABEL),
        (RECUR_LICENSE_DATE, RECUR_LICENSE_DATE_LABEL),
    )
    # fields
    goalType = models.ForeignKey(GoalType,
        on_delete=models.PROTECT,
        db_index=True
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    dueDateType = models.IntegerField(
        choices=DUEDATE_TYPE_CHOICES
    )
    interval = models.DecimalField(max_digits=7, decimal_places=5, blank=True, null=True,
            validators=[MinValueValidator(0)],
            help_text='Interval in years for recurring goal')
    degrees = models.ManyToManyField(Degree, blank=True,
            related_name='basegoals',
            help_text='Applicable primary roles. No selection means any')
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True,
            related_name='basegoals',
            help_text='Applicable specialties. No selection means any')
    subspecialties = models.ManyToManyField(SubSpecialty, blank=True,
            related_name='basegoals',
            help_text='Applicable sub-specialties. If selected, they must be sub-specialties of the chosen PracticeSpecialties above. No selection means any')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    modifiedBy = models.ForeignKey(User,
        on_delete=models.SET_NULL,
        related_name='basegoals',
        null=True,
        blank=True,
        db_index=True,
        help_text='User who last modified this goal'
    )

    def __str__(self):
        return self.goalType.name

    def isOneOff(self):
        return self.dueDateType == BaseGoal.ONE_OFF

    def isRecurMMDD(self):
        return self.dueDateType == BaseGoal.RECUR_MMDD

    def isRecurAny(self):
        return self.dueDateType == BaseGoal.RECUR_ANY

    def usesLicenseDate(self):
        return self.dueDateType == BaseGoal.RECUR_LICENSE_DATE

    def usesBirthDate(self):
        return self.dueDateType == BaseGoal.RECUR_BIRTH_DATE

    def formatDueDateType(self):
        if self.dueDateType == BaseGoal.ONE_OFF:
            return u'One-off'
        if self.dueDateType == BaseGoal.RECUR_MMDD:
            return u'Fixed MM/DD'
        if self.dueDateType == BaseGoal.RECUR_ANY:
            return u'Any time'
        if self.dueDateType == BaseGoal.RECUR_LICENSE_DATE:
            return u'License expireDate'
        return u'Birthdate'

    @cached_property
    def formatDegrees(self):
        if self.degrees.exists():
            return u", ".join([d.abbrev for d in self.degrees.all()])
        return u'Any'
    formatDegrees.short_description = "Primary Roles"

    @cached_property
    def formatSpecialties(self):
        if self.specialties.exists():
            return ", ".join([d.name for d in self.specialties.all()])
        return u'Any'
    formatSpecialties.short_description = "Specialties"

    @cached_property
    def formatSubSpecialties(self):
        if self.subspecialties.exists():
            return ", ".join([d.name for d in self.subspecialties.all()])
        return u'Any'
    formatSubSpecialties.short_description = "Sub-Specialties"

    def degreeSet(self):
        """Returns set of pkeyids from self.degrees or all"""
        degrees = self.degrees.all() if self.degrees.exists() else Degree.objects.all()
        return set([m.pk for m in degrees])

    def isMatchProfile(self, profile):
        """Returns True if intersection exists with profile degrees, specialties and subspecialties.
        Args:
            profile: Profile instance
        Returns: bool
        """
        degrees = self.degreeSet()
        if degrees.isdisjoint(profile.degreeSet):
            return False
        if not self.specialties.exists():
            # matches all specialties
            return True
        # else
        specs = set([m.pk for m in self.specialties.all().only('pk')])
        if specs.isdisjoint(profile.specialtySet):
            return False
        if not self.subspecialties.exists():
            # matches all subspecialties
            return True
        # else
        subspecs = set([m.pk for m in self.subspecialties.all().only('pk')])
        if subspecs.isdisjoint(profile.subspecialtySet):
            return False
        return True

#
# Proxy models to BaseGoal used by Admin interface
# Each proxy model is assigned its own admin form customized for its goalType.
#
class LicenseBaseGoalManager(models.Manager):
    def get_queryset(self):
        qs = super(LicenseBaseGoalManager, self).get_queryset()
        return qs.filter(goalType__name=GoalType.LICENSE)

class LicenseBaseGoal(BaseGoal):
    """Proxy model to BaseGoal for License goalType"""
    objects = LicenseBaseGoalManager()

    class Meta:
        proxy = True
        verbose_name_plural = 'License-Goals'

    def __str__(self):
        return self.licensegoal.title

    def clean(self):
        """Validation checks. Invoked by admin form
        Note: self is an instance of BaseGoal with goalType=LICENSE
        """
        if not self.interval:
            raise ValidationError({'interval': 'Duration of license in years is required'})
        if self.dueDateType != BaseGoal.RECUR_LICENSE_DATE:
            raise ValidationError({'dueDateType': 'dueDateType must be {0}'.format(BaseGoal.RECUR_LICENSE_DATE_LABEL)})


class SRCmeBaseGoalManager(models.Manager):
    def get_queryset(self):
        qs = super(SRCmeBaseGoalManager, self).get_queryset()
        return qs.filter(goalType__name=GoalType.SRCME)

class SRCmeBaseGoal(BaseGoal):
    """Proxy model to BaseGoal for SRCme goalType"""
    objects = SRCmeBaseGoalManager()

    class Meta:
        proxy = True
        verbose_name_plural = 'SRCME-Goals'

    def __str__(self):
        if self.srcmegoal.cmeTag:
            return self.srcmegoal.cmeTag
        return ANY_TOPIC

    def clean(self):
        """Validation checks. Invoked by admin form
        Note: self is an instance of BaseGoal with goalType=SRCME
        """
        if self.dueDateType > BaseGoal.ONE_OFF and not self.interval:
            raise ValidationError({'interval': INTERVAL_ERROR})


class CmeBaseGoalManager(models.Manager):
    def get_queryset(self):
        qs = super(CmeBaseGoalManager, self).get_queryset()
        return qs.filter(goalType__name=GoalType.CME)

class CmeBaseGoal(BaseGoal):
    """Proxy model to BaseGoal for CME goalType"""
    objects = CmeBaseGoalManager()
    class Meta:
        proxy = True
        verbose_name_plural = 'CME-Goals'

    def clean(self):
        """Validation checks. Invoked by admin form
        Note: self is an instance of BaseGoal with goalType=CME
        """
        if self.dueDateType > BaseGoal.ONE_OFF and not self.interval:
            raise ValidationError({'interval': INTERVAL_ERROR})


class LicenseGoalManager(models.Manager):

    def getMatchingGoalsForProfile(self, profile):
        """Find the goals that match the given profile:
        Returns: list of LicenseGoals.
        """
        matchedGoals = []
        if not profile.degreeSet:
            return []
        stateids = list(profile.stateSet.union(profile.deaStateSet))
        if not stateids:
            return []
        profileDegrees = list(profile.degreeSet)
        profileSpecs = list(profile.specialtySet)
        profileSubSpecs = list(profile.subspecialtySet)
        base_qs = self.model.objects \
                .select_related('goal','licenseType') \
                .prefetch_related(
                        'goal__degrees',
                        'goal__specialties',
                        'goal__subspecialties')
        Q_degree = Q(goal__degrees__in=profileDegrees) | Q(goal__degrees=None)
        Q_goal = Q_degree
        if profileSpecs:
            Q_spec = Q(goal__specialties__in=profileSpecs) | Q(goal__specialties=None)
            Q_goal &= Q_spec
            if profileSubSpecs:
                Q_subspec = Q(goal__subspecialties__in=profileSubSpecs) | Q(goal__subspecialties=None)
                Q_goal &= Q_subspec

        filter_kwargs = {
            'goal__is_active': True,
            'state__in': stateids
        }
        qset = base_qs.filter(Q_goal, **filter_kwargs).order_by('pk')
        for goal in qset:
            if goal.isMatchProfile(profile):
                matchedGoals.append(goal)
        return matchedGoals


@python_2_unicode_compatible
class LicenseGoal(models.Model):
    DUEDATE_TYPE_CHOICES = (
        (BaseGoal.RECUR_LICENSE_DATE, BaseGoal.RECUR_LICENSE_DATE_LABEL),
    )
    # fields
    title = models.CharField(max_length=100, blank=True, help_text='Title of goal')
    goal = models.OneToOneField(BaseGoal,
        on_delete=models.CASCADE,
        related_name='licensegoal',
        primary_key=True
    )
    state = models.ForeignKey(State,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='licensegoals',
    )
    licenseType= models.ForeignKey(LicenseType,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='licensegoals',
    )
    daysBeforeDue = models.PositiveIntegerField(default=90,
            help_text='Days before license dueDate at which status switches from Complete to In-Progress')
    objects = LicenseGoalManager()

    class Meta:
        unique_together = ('state','licenseType','title')

    def __str__(self):
        return self.title

    def clean(self):
        """Validation checks"""
        if not self.title:
            self.title = "{0.licenseType.name} License ({0.state.abbrev})".format(self)

    def isMatchProfile(self, profile):
        """Checks if self matches profile attributes
        Returns: bool
        """
        basegoal = self.goal
        # check state match (use state_id instead of state.pk b/c it is direct attr on self)
        if not self.state_id in profile.stateSet:
            return False
        if self.licenseType.name == LicenseType.TYPE_DEA:
            # check DEA state match
            if not self.state_id in profile.deaStateSet:
                return False
        # check basegoal
        if not basegoal.isMatchProfile(profile):
            return False
        return True

def groupGoalsByTagAndCreditType(goals):
    """Group the given goals by tag and common-intersection creditTypes
    Args:
        goals: list of CmeGoals or SRCmeGoals
    Returns: dict {tag.pk/None => (creditType.pks tuple) => list of goals}

    """
    allCreditTypes = set([m.pk for m in CreditType.objects.all()])
    allct_tuple = tuple(allCreditTypes)
    grouped = defaultdict(dict)
    for goal in goals:
        tag = goal.cmeTag
        goalcts = goal.creditTypeSet
        if not goalcts: # goal accept any (=all)
            goalcts = allCreditTypes
            ct_tuple = allct_tuple
        else:
            ct_tuple = tuple(goalcts) # hashable key for dict
        if tag not in grouped:
            grouped[tag][ct_tuple] = [goal,]
        else:
            gd = grouped[tag]
            added = False
            # does goal.creditTypes intersect with an existing key
            for ct in gd: # ct is a tuple of creditTypes pks
                ctset = set(ct)
                int_set = ctset.intersection(goalcts)
                if int_set:
                    # intersection exists: goal can fit in existing bucket
                    gd[ct].append(goal)
                    added = True
                    break
            if not added:
                # start new creditTypes bucket
                gd[ct_tuple] = [goal,]
    return grouped


class CmeGoalManager(models.Manager):

    def getMatchingGoalsForProfile(self, profile):
        """Find the goals that match the given profile which must have non-empty degrees
        Args:
            profile: Profile instance
        Returns: list of CmeGoals.
        """
        matchedGoals = []
        if not profile.degreeSet:
            return []
        profileDegrees = list(profile.degreeSet)
        profileTags = list(profile.activeCmeTagSet)
        profileSpecs = list(profile.specialtySet)
        profileSubSpecs = list(profile.subspecialtySet)
        base_qs = self.model.objects \
            .select_related('goal', 'cmeTag') \
            .prefetch_related(
                    'goal__degrees',
                    'goal__specialties',
                    'goal__subspecialties')
        Q_degree = Q(goal__degrees__in=profileDegrees) | Q(goal__degrees=None)
        Q_goal = Q_degree
        if profileSpecs:
            Q_spec = Q(goal__specialties__in=profileSpecs) | Q(goal__specialties=None)
            Q_goal &= Q_spec
            if profileSubSpecs:
                Q_subspec = Q(goal__subspecialties__in=profileSubSpecs) | Q(goal__subspecialties=None)
                Q_goal &= Q_subspec
        if profileTags:
            Q_tag = Q(cmeTag__in=profileTags) | Q(cmeTag__isnull=True)
            Q_goal &= Q_tag
        filter_kwargs = {'goal__is_active': True}
        qset = base_qs.filter(Q_goal, **filter_kwargs).order_by('pk')
        for goal in qset:
            if goal.isMatchProfile(profile):
                matchedGoals.append(goal)
        return matchedGoals

    def groupGoalsByTag(self, profile, goals):
        """Group the given goals by tag
        Args:
            profile: Profile instance
            goals: list of CmeGoals
        Returns: dict {tag.pk/None => (creditType.pks) => list of CmeGoals}
        """
        allCreditTypes = set([m.pk for m in CreditType.objects.all()])
        allct_tuple = tuple(allCreditTypes)
        goals2 = []; mapToSpec = []
        for goal in goals:
            if goal.cmeTag:
                goals2.append(goal)
            elif not goal.mapNullTagToSpecialty:
                goals2.append(goal) # None remains as None (ANY_TOPIC)
            else:
                mapToSpec.append(goal)
        # first pass
        grouped = groupGoalsByTagAndCreditType(goals2)
        # now handle mapNullTagToSpecialty goals
        profileSpecs = [ps.name for ps in profile.specialties.all()]
        if not profileSpecs:
            return grouped
        specTags = CmeTag.objects.filter(name__in=profileSpecs)
        for goal in mapToSpec:
            goalcts = goal.creditTypeSet
            if not goalcts: # goal accept any (=all)
                goalcts = allCreditTypes
                ct_tuple = allct_tuple
            else:
                ct_tuple = tuple(goalcts) # hashable key for dict
            for tag in specTags:
                # stand-in tag for curgoal
                if tag not in grouped:
                    grouped[tag][ct_tuple] = [goal,]
                else:
                    gd = grouped[tag]
                    added = False
                    # does goal.creditTypes intersect with an existing key
                    for ct in gd: # ct is a tuple of creditTypes pks
                        ctset = set(ct)
                        int_set = ctset.intersection(goalcts)
                        if int_set:
                            # goal can fit in existing bucket
                            gd[ct].append(goal)
                            added = True
                            break
                    if not added:
                        # start new creditTypes bucket
                        gd[ct_tuple] = [goal,]
        return grouped

@python_2_unicode_compatible
class CmeGoal(models.Model):
    BOARD = 0
    STATE = 1
    HOSPITAL = 2
    ENTITY_TYPE_CHOICES = (
        (BOARD, 'Board'),
        (STATE, 'State'),
        (HOSPITAL, 'Hospital')
    )
    # fields
    goal = models.OneToOneField(BaseGoal,
        on_delete=models.CASCADE,
        related_name='cmegoal',
        primary_key=True
    )
    entityType = models.IntegerField(
        choices=ENTITY_TYPE_CHOICES,
        help_text='Entity source. Then select the entity from the appropriate dropdown menu.'
    )
    board = models.ForeignKey(Board,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='cmegoals',
    )
    state = models.ForeignKey(State,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='cmegoals',
    )
    hospital = models.ForeignKey(Hospital,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='cmegoals',
    )
    cmeTag = models.ForeignKey(CmeTag,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='cmegoals',
        help_text="Null value means tag is either user specialty or Any Topic (see mapNullTagToSpecialty)"
    )
    mapNullTagToSpecialty = models.BooleanField(default=False,
            help_text="If True, null value for cmeTag in goal definition means the UserGoal will have tag set to the user's specialty. Otherwise null cmeTag means Any Topic.")
    licenseGoal = models.ForeignKey(LicenseGoal,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name='cmegoals',
        help_text="Must be selected if dueDate uses license expiration date. Null otherwise."
    )
    credits = models.DecimalField(max_digits=6, decimal_places=2,
            validators=[MinValueValidator(0.1)])
    creditTypes = models.ManyToManyField(CreditType,
            blank=True,
            related_name='cmegoals',
            help_text='Eligible creditTypes that satisfy this goal.')
    dueMonth = models.SmallIntegerField(blank=True, null=True,
            help_text='Must be specified if dueDateType is Fixed MMDD',
            validators=[
                MinValueValidator(1),
                MaxValueValidator(12)])
    dueDay = models.SmallIntegerField(blank=True, null=True,
            help_text='Must be specified if dueDateType is Fixed MMDD',
            validators=[
                MinValueValidator(1),
                MaxValueValidator(31)])
    objects = CmeGoalManager()

    def clean(self):
        """Validation checks"""
        if self.entityType == CmeGoal.BOARD and not self.board:
            raise ValidationError({'board': 'Board must be selected'})
        if self.entityType == CmeGoal.STATE and not self.state:
            raise ValidationError({'state': 'State must be selected'})
        if self.entityType == CmeGoal.HOSPITAL and not self.hospital:
            raise ValidationError({'board': 'Hospital must be selected'})

    @cached_property
    def valid(self):
        if self.goal.dueDateType == BaseGoal.RECUR_LICENSE_DATE and not self.licenseGoal:
            return False
        if self.goal.dueDateType == BaseGoal.RECUR_MMDD:
            if not self.dueMonth or not self.dueDay:
                return False
        return True

    @cached_property
    def entityName(self):
        if self.entityType == CmeGoal.BOARD:
            return self.board.name
        if self.entityType == CmeGoal.STATE:
            return self.state.name
        return self.hospital.display_name

    def __str__(self):
        return u"{0.entityType}|{0.entityName}".format(self)

    @cached_property
    def dueMMDD(self):
        if self.dueMonth:
            return "{0.dueMonth}/{0.dueDay}".format(self)
        return ''

    @cached_property
    def creditTypeSet(self):
        return set([m.pk for m in self.creditTypes.all()])

    def formatCreditTypes(self):
        """Returns string of comma separated CreditType abbrev values"""
        s = ','.join([m.abbrev for m in self.creditTypes.all()])
        if not s:
            return 'Any'
        return s

    def isMatchProfile(self, profile):
        """Checks if self matches profile attributes
        Returns: bool
        """
        basegoal = self.goal
        if self.entityType == CmeGoal.STATE:
            # check state match
            if not self.state_id in profile.stateSet:
                return False
        elif self.entityType == CmeGoal.HOSPITAL:
            # check hospital match
            if not self.hospital_id in profile.hospitalSet:
                return False
        # check basegoal
        if not basegoal.isMatchProfile(profile):
            return False
        # check tag
        if self.cmeTag:
            return self.cmeTag.pk in profile.activeCmeTagSet
        return True


    def computeCredits(self, numProfileSpecs):
        """If self.cmeTag: return self.credits
        else: goal is untagged. Split credits by numProfileSpecs
        Args:
            numProfileSpecs: int - number of profile.specialties
        Returns: float/Decimal
        """
        if self.cmeTag:
            return self.credits
        if not self.mapNullTagToSpecialty:
            return self.credits
        # else: untagged and split credits among specialties
        creditsDue = round(1.0*float(self.credits)/numProfileSpecs)
        return creditsDue

    def computeDueDateForProfile(self, profile, userLicense, now, dueYear=None):
        """Attempt to find a dueDate based on dueDateType, profile, and userLicense
        Args:
            profile: Profile instance
            userLicense: StateLicense/None
            now: datetime
            dueYear: int/None year to use for dueDate
        Returns: datetime
        Note: UNKNOWN_DATE is reserved for internal errors (e.g. unknown dueDateType)
        """
        if not dueYear:
            dueYear = now.year
        basegoal = self.goal
        if basegoal.isOneOff() or basegoal.isRecurAny():
            return now
        if basegoal.isRecurMMDD():
            dueDate = makeDueDate(dueYear, self.dueMonth, self.dueDay, now)
            return dueDate
        if basegoal.usesLicenseDate():
            if not userLicense or userLicense.isUnInitialized():
                return now
            else:
                return userLicense.expireDate
        if basegoal.usesBirthDate():
            if not profile.birthDate:
                return now
            dueDate = makeDueDate(dueYear, profile.birthDate.month, profile.birthDate.day, now)
            return dueDate
        return UNKNOWN_DATE

    def computeCreditsEarnedOverInterval(self, user, endDate, cmeTag):
        """Compute credits earned for user, tag, basegoal.interval, and self.creditTypes
        Args:
            user: User instance
            endDate: datetime
            cmeTag: CmeTag or None to count all credits
        Returns: decimal - total credits earned
        """
        basegoal = self.goal
        yrs = basegoal.interval if basegoal.interval else 100
        startDate = endDate - timedelta(days=365*float(yrs))
        brcme_credits = 0; srcme_credits = 0
        cset = self.creditTypeSet
        include_brcme = False
        if not cset:
            # accepts any type, so no filter
            cset=None
            include_brcme = True
        else:
            ama1 = CreditType.objects.get(name=CreditType.AMA_PRA_1)
            if ama1.pk in cset:
                include_brcme = True
        if include_brcme:
            # can count brcme_credits (which are always ama1)
            brcme_credits = Entry.objects.sumBrowserCme(user, startDate, endDate, tag=cmeTag)
        # Count srcme credits that satisfy self.creditTypes
        srcme_credits = Entry.objects.sumSRCme(user, startDate, endDate, tag=cmeTag, creditTypes=cset)
        total = brcme_credits + srcme_credits
        #print('- creditsEarned {0} over interval: {1} years'.format(total, yrs))
        return total


class SRCmeGoalManager(models.Manager):

    def getMatchingGoalsForProfile(self, profile):
        """Find the goals that match the given profile:
        Note: These goals are state-specific.
        Returns: list of SRCmeGoals.
        """
        matchedGoals = []
        if not profile.degreeSet:
            return []
        #stateids = list(profile.stateSet.union(profile.deaStateSet))
        # the requirements are set by profile.states. profile.deaStates
        # is used to populate user's ProfileCmetags.
        stateids = list(profile.stateSet)
        if not stateids:
            return []
        if not profile.activeSRCmeTagSet:
            return []
        profileDegrees = profile.degreeSet
        profileSpecs = profile.specialtySet
        profileSubSpecs = profile.subspecialtySet
        profileTags = profile.activeSRCmeTagSet
        base_qs = self.model.objects \
                .select_related('goal','cmeTag') \
                .prefetch_related(
                        'goal__degrees',
                        'goal__specialties',
                        'goal__subspecialties')

        Q_degree = Q(goal__degrees__in=profileDegrees) | Q(goal__degrees=None)
        Q_goal = Q_degree
        if profileSpecs:
            Q_spec = Q(goal__specialties__in=profileSpecs) | Q(goal__specialties=None)
            Q_goal &= Q_spec
            if profileSubSpecs:
                Q_subspec = Q(goal__subspecialties__in=profileSubSpecs) | Q(goal__subspecialties=None)
                Q_goal &= Q_subspec
        filter_kwargs = {
            'goal__is_active': True,
            'state__in': stateids,
            'cmeTag__in': profileTags
        }
        qset = base_qs.filter(Q_goal, **filter_kwargs).order_by('pk')
        for goal in qset:
            if goal.isMatchProfile(profile):
                matchedGoals.append(goal)
        return matchedGoals

    def groupGoalsByTag(self, goals):
        """Group the given goals by tag and common-intersection creditTypes
        Args:
            goals: list of SRCmeGoals
        Returns: dict {tag.pk/None => (creditType.pks) => list of SRCmeGoals}

        """
        grouped = groupGoalsByTagAndCreditType(goals)
        return grouped


@python_2_unicode_compatible
class SRCmeGoal(models.Model):
    DUEDATE_TYPE_CHOICES = (
        (BaseGoal.ONE_OFF, BaseGoal.ONE_OFF_LABEL),
        (BaseGoal.RECUR_MMDD, BaseGoal.RECUR_MMDD_LABEL),
        (BaseGoal.RECUR_BIRTH_DATE, BaseGoal.RECUR_BIRTH_DATE_LABEL),
        (BaseGoal.RECUR_LICENSE_DATE, BaseGoal.RECUR_LICENSE_DATE_LABEL),
    )
    goal = models.OneToOneField(BaseGoal,
        on_delete=models.CASCADE,
        related_name='srcmegoal',
        primary_key=True
    )
    state = models.ForeignKey(State,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='srcmegoals',
    )
    cmeTag = models.ForeignKey(CmeTag,
        on_delete=models.PROTECT,
        db_index=True,
        null=True,
        blank=True,
        related_name='srcmegoals',
        help_text='State-specific SR-CME Tag. Null means Any Topic'
    )
    licenseGoal = models.ForeignKey(LicenseGoal,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name='srcmegoals',
        help_text="Must be selected if dueDate uses license expiration date. Null otherwise."
    )
    credits = models.DecimalField(max_digits=6, decimal_places=2,
            validators=[MinValueValidator(0.1)])
    creditTypes = models.ManyToManyField(CreditType,
            blank=True,
            related_name='srcmegoals',
            help_text='Eligible creditTypes that satisfy this goal.')
    dueMonth = models.SmallIntegerField(blank=True, null=True,
            help_text='Must be specified if dueDateType is Fixed MMDD',
            validators=[
                MinValueValidator(1),
                MaxValueValidator(12)])
    dueDay = models.SmallIntegerField(blank=True, null=True,
            help_text='Must be specified if dueDateType is Fixed MMDD',
            validators=[
                MinValueValidator(1),
                MaxValueValidator(31)])
    objects = SRCmeGoalManager()

    def __str__(self):
        return u"{0.state}|{0.cmeTag}".format(self)

    @cached_property
    def valid(self):
        if self.goal.dueDateType == BaseGoal.RECUR_LICENSE_DATE and not self.licenseGoal:
            return False
        if self.goal.dueDateType == BaseGoal.RECUR_MMDD:
            if not self.dueMonth or not self.dueDay:
                return False
        return True

    @cached_property
    def dueMMDD(self):
        if self.dueMonth:
            return "{0.dueMonth}/{0.dueDay}".format(self)
        return ''

    @cached_property
    def creditTypeSet(self):
        return set([m.pk for m in self.creditTypes.all()])

    def formatCreditTypes(self):
        """Returns string of comma separated CreditType abbrev values"""
        s = ','.join([m.abbrev for m in self.creditTypes.all()])
        if not s:
            return 'Any'
        return s

    def isMatchProfile(self, profile):
        """Checks if self matches profile attributes
        Returns: bool
        """
        basegoal = self.goal
        # check state match
        if not self.state_id in profile.stateSet:
            return False
        # check tag
        if self.cmeTag and not self.cmeTag.pk in profile.activeSRCmeTagSet:
            return False
        if not basegoal.isMatchProfile(profile):
            return False
        return True

    def computeDueDateForProfile(self, profile, userLicense, now, dueYear=None):
        """Attempt to find a dueDate based on dueDateType, profile, and userLicense
        Args:
            profile: Profile instance
            userLicense: StateLicense/None
            now: datetime
            dueYear: int/None year to use for dueDate
        Returns: datetime
        Note: UNKNOWN_DATE is reserved for internal errors (e.g. unknown dueDateType)
        """
        if not dueYear:
            dueYear = now.year
        basegoal = self.goal
        if basegoal.isOneOff() or basegoal.isRecurAny():
            return now
        if basegoal.isRecurMMDD():
            dueDate = makeDueDate(dueYear, self.dueMonth, self.dueDay, now)
            return dueDate
        if basegoal.usesLicenseDate():
            if not userLicense or userLicense.isUnInitialized():
                return now
            else:
                return userLicense.expireDate
        if basegoal.usesBirthDate():
            if not profile.birthDate:
                return now
            dueDate = makeDueDate(dueYear, profile.birthDate.month, profile.birthDate.day, now)
            return dueDate
        return UNKNOWN_DATE

    def computeCreditsEarnedOverInterval(self, user, endDate, cmeTag):
        """Compute srcme credits earned for user, tag, basegoal.interval, and self.creditTypes
        Args:
            user: User instance
            endDate: datetime
            cmeTag: CmeTag
        Returns: decimal - total credits earned
        """
        basegoal = self.goal
        yrs = basegoal.interval if basegoal.interval else 100
        startDate = endDate - timedelta(days=365*float(yrs))
        # Count srcme credits that satisfy self.creditTypes
        cset = self.creditTypeSet
        if not cset:
            cset=None # accepts any type, so no filter
        srcme_credits = Entry.objects.sumSRCme(user, startDate, endDate, tag=cmeTag, creditTypes=cset)
        return srcme_credits


class UserGoalManager(models.Manager):

    def makeUserLicenseDict(self, user):
        """Find all user licensegoals and make {BaseGoal.pk => License instance} for self.user and goalType = LICENSE
        Returns: dict
        """
        userLicenseDict = dict()
        licenseGoalType = GoalType.objects.get(name=GoalType.LICENSE)
        # get user licensegoals
        qset = user.usergoals.select_related('goal','license').filter(goal__goalType=licenseGoalType)
        for m in qset:
            userLicenseDict[m.goal.pk] = m.license
        return userLicenseDict


    def assignLicenseGoals(self, profile):
        """Assign License UserGoals and create any uninitialized statelicenses for user as needed
        Steps:
            1. Find matching LicenseGoals based on profile
            2. If user StateLicense instance already exists for (state, licenseType): get it
                Else: create uninitialized StateLicense for user
            3. If UserGoal does not exist for this userLicense: create it
            4. Update status of usergoal
        Note: UserGoals can be removed by rematchGoals method, but userLicenses are preserved.
        Therefore a userLicense can be attached to different UserGoal instances over time.
        Returns: list of newly created usergoals
        """
        user = profile.user
        goals = LicenseGoal.objects.getMatchingGoalsForProfile(profile)
        usergoals = []
        now = timezone.now()
        for goal in goals:
            # goal is a LicenseGoal
            basegoal = goal.goal
            licenseType = goal.licenseType
            userLicense = None
            # does user license exist with a non-null expireDate
            qset = user.statelicenses.filter(state=goal.state, licenseType=licenseType, expireDate__isnull=False).order_by('-expireDate')
            if qset.exists():
                userLicense = qset[0]
                dueDate = userLicense.expireDate
                status = self.model.IN_PROGRESS
            else:
                dueDate = now
                status = self.model.PASTDUE
                # does uninitialized license already exist
                qset = user.statelicenses.filter(state=goal.state, licenseType=licenseType, expireDate__isnull=True)
                if qset.exists():
                    userLicense = qset[0]
                else:
                    # create uninitialized license
                    userLicense = StateLicense.objects.create(
                            user=user,
                            state=goal.state,
                            licenseType=licenseType
                        )
                    logger.info('Create uninitialized {0.licenseType} License for user {0.user}'.format(userLicense))
            # does UserGoal for this license already exist
            qs = self.model.objects.filter(user=user, goal=basegoal, license=userLicense)
            if qs.exists():
                usergoal = qs[0]
            else:
                # create UserGoal with associated license
                usergoal = self.model.objects.create(
                        user=user,
                        goal=basegoal,
                        state=goal.state, # State
                        dueDate=dueDate,
                        status=status,
                        license=userLicense
                    )
                logger.info('Created UserGoal: {0}'.format(usergoal))
                usergoals.append(usergoal)
            # check status
            status = usergoal.calcLicenseStatus(now)
            if usergoal.status != status:
                usergoal.status = status
                usergoal.save(update_fields=('status',))
        return usergoals

    def handleGoalsForTag(self, user, tag, goals, userLicenseDict):
        """Create or update composite goal and individual usergoals
        Args:
            tag: CmeTag or None
            goals: list of CmeGoals or SrCmeGoals
            userLicenseDict: dict {licenseBaseGoal.pk => StateLicense instance} for user
        """
        now = timezone.now()
        usergoals = [] # newly created
        consgoals = [] # all constituentGoals
        firstGoal = goals[0]
        goalType = firstGoal.goal.goalType
        basegoalids = [goal.goal.pk for goal in goals]
        # check individual goals
        for goal in goals:
            basegoal = goal.goal
            # Does UserGoal for (user, basegoal) already exist
            filter_kwargs = {
                'user': user,
                'goal': basegoal,
                'is_composite_goal': False
            }
            if tag:
                filter_kwargs['cmeTag'] = tag
            else:
                filter_kwargs['cmeTag__isnull'] = True
            # Does non-archived UserGoal for (user, basegoal) exist
            qs = self.model.objects.filter(**filter_kwargs).exclude(status=self.model.EXPIRED)
            if qs.exists():
                ug = qs[0]
                consgoals.append(ug)
                continue
            # create UserGoal for (user, basegoal) with initial dueDate=now
            usergoal = self.model.objects.create(
                    user=user,
                    goal=basegoal,
                    state=goal.state, # State or None
                    dueDate=now,
                    status=self.model.PASTDUE,
                    cmeTag=tag,
                    creditsDue=0,
                    creditsDueMonthly=0,
                    creditsEarned=0,
                )
            usergoal.creditTypes.set(goal.creditTypes.all())
            logger.info('Created UserGoal: {0}'.format(usergoal))
            usergoal.recompute(userLicenseDict)
            usergoals.append(usergoal)
            consgoals.append(usergoal)
        # composite goal : ug.state is always null. User can have several composite goals
        # but they should all satisfy the unique_together on model.
        filter_kwargs = {
            'user': user,
            'is_composite_goal': True,
            'goal__in': basegoalids, # to enable selection of the correct composite usergoal
        }
        if tag:
            filter_kwargs['cmeTag'] = tag
        else:
            filter_kwargs['cmeTag__isnull'] = True
        qs = self.model.objects.filter(**filter_kwargs).exclude(status=self.model.EXPIRED)
        if qs.exists():
            compositeGoal = qs[0]
            saved = compositeGoal.checkUpdate(firstGoal, consgoals, userLicenseDict)
            if saved:
                logger.info('Updated composite UserGoal: {0}'.format(compositeGoal))
        else:
            compositeGoal = self.model.objects.create(
                    user=user,
                    goal=firstGoal.goal,
                    state=None,
                    dueDate=now,
                    status=self.model.PASTDUE,
                    cmeTag=tag,
                    creditsDue=0,
                    creditsDueMonthly=0,
                    creditsEarned=0,
                    is_composite_goal=True
                )
            for ug in consgoals:
                compositeGoal.constituentGoals.add(ug)
            logger.info('Created composite UserGoal: {0}'.format(compositeGoal))
            compositeGoal.recompute(userLicenseDict)
            usergoals.append(compositeGoal)
        return usergoals

    def assignCmeGoals(self, profile, userLicenseDict):
        """Assign CME UserGoals by matching existing goals to the given profile. Note: license goals should be assigned first.
        Steps:
            1. Find matching CmeGoals based on profile
            2. Group matched goals by tag/creditType
            3. If dne: create constituent Cme UserGoals for basegoal, tag, else recompute
            4. If dne: create composite Cme UserGoal for this tag, else check for updates and recompute
        Returns: list of newly created usergoals
        """
        user = profile.user
        usergoals = []
        goals = CmeGoal.objects.getMatchingGoalsForProfile(profile)
        grouped = CmeGoal.objects.groupGoalsByTag(profile, goals)
        for tag in grouped:
            gd = grouped[tag]
            for cTypes in gd:
                goals = gd[cTypes] # list of cmegoals
                usergoals.extend(self.handleGoalsForTag(user, tag, goals, userLicenseDict))
        return usergoals

    def assignSRCmeGoals(self, profile, userLicenseDict):
        """Assign SRCme UserGoals for the given profile.
        Steps:
            1. Find matching LicenseGoals based on profile
            2. Group matched goals by tag
            3. If dne: create SRCme UserGoals for basegoal, tag, else recompute
            4. If dne: create composite UserGoal for this tag, else check for updates and recompute
        Returns: list of newly created usergoals
        """
        user = profile.user
        usergoals = []
        goals = SRCmeGoal.objects.getMatchingGoalsForProfile(profile)
        grouped = SRCmeGoal.objects.groupGoalsByTag(goals)
        for tag in grouped:
            gd = grouped[tag]
            for cTypes in gd:
                goals = gd[cTypes] # list of srcmegoals
                usergoals.extend(self.handleGoalsForTag(user, tag, goals, userLicenseDict))
        return usergoals

    def assignGoals(self, user):
        """Assign UserGoals for the given user
        Steps:
            1. Get user profile with prefetched m2m attributes
            2. Assign License UserGoals first so that all userLicense are created
            3. Assign CME UserGoals
        Returns: list of newly created UserGoals
        """
        usergoals = []
        profile = user.profile
        usergoals.extend(self.assignLicenseGoals(profile))
        # create userLicenseDict after assignment of license goals
        userLicenseDict = self.makeUserLicenseDict(user)
        usergoals.extend(self.assignCmeGoals(profile, userLicenseDict))
        usergoals.extend(self.assignSRCmeGoals(profile, userLicenseDict))
        return usergoals

    def rematchLicenseGoals(self, user):
        """Helper method for rematchGoals
        Returns: int - number of stale goals deleted
        """
        profile = user.profile
        stale = []
        existing = user.usergoals.select_related('goal').filter(goal__goalType__name=GoalType.LICENSE)
        for ug in existing:
            licensegoal = ug.goal.licensegoal
            if not licensegoal.isMatchProfile(profile):
                stale.append(ug)
        num_stale = len(stale)
        for ug in stale:
            # Note: this only removes the UserGoal (any associated StateLicense is retained)
            logger.info('Removing {0}'.format(ug))
            ug.delete()
        if num_stale:
            logger.info('Deleted {0} licensegoals for {1}'.format(num_stale, user))
        return num_stale

    def rematchCmeGoals(self, user):
        """Helper method for rematchGoals
        Returns: int - number of stale goals deleted
        """
        profile = user.profile
        stale = set([])
        # individual goals
        existing = user.usergoals.select_related('goal').filter(
                goal__goalType__name=GoalType.CME,
                is_composite_goal=False)
        for ug in existing:
            cmegoal = ug.goal.cmegoal
            if not cmegoal.isMatchProfile(profile):
                stale.add(ug)
        # composite cme goals: delete if all constituentGoals are stale
        existing = user.usergoals.select_related('goal').filter(
                goal__goalType__name=GoalType.CME,
                is_composite_goal=True)
        for compositeGoal in existing:
            consgoals = compositeGoal.constituentGoals.all()
            cons_stale = [ug in stale for ug in consgoals]
            if all(cons_stale):
                # all of its constituent goals match are stale
                stale.add(compositeGoal)
        num_stale = len(stale)
        # delete stale
        for ug in stale:
            logger.info('Removing {0}'.format(ug))
            ug.delete()
        if num_stale:
            logger.info('Deleted {0} cmegoals for {1}'.format(num_stale, user))
        return num_stale

    def rematchSRCmeGoals(self, user):
        """Helper method for rematchGoals
        Returns: int - number of stale goals deleted
        """
        profile = user.profile
        stale = set([])
        # individual goals
        existing = user.usergoals.select_related('goal').filter(
                goal__goalType__name=GoalType.SRCME,
                is_composite_goal=False)
        for ug in existing:
            cmegoal = ug.goal.srcmegoal
            if not cmegoal.isMatchProfile(profile):
                stale.add(ug)
        # composite cme goals: delete if all constituentGoals are stale
        existing = user.usergoals.select_related('goal').filter(
                goal__goalType__name=GoalType.SRCME,
                is_composite_goal=True)
        for compositeGoal in existing:
            consgoals = compositeGoal.constituentGoals.all()
            cons_stale = [ug in stale for ug in consgoals]
            if all(cons_stale):
                # all of its constituent goals match are stale
                stale.add(compositeGoal)
        num_stale = len(stale)
        # delete stale
        for ug in stale:
            logger.info('Removing {0}'.format(ug))
            ug.delete()
        if num_stale:
            logger.info('Deleted {0} srcmegoals for {1}'.format(num_stale, user))
        return num_stale


    def rematchGoals(self, user):
        """This should be called when user's profile changes, or when new goals are created (or existing goals inactivated).
        Steps:
            1. Remove stale UserGoals that no longer match the profile
            2. Call assignGoals to create new UserGoals/update existing ones.
        Returns: list of newly created UserGoals
        """
        logger.debug('rematchGoals for {0}'.format(user))
        num_stale = self.rematchLicenseGoals(user)
        num_stale = self.rematchCmeGoals(user)
        num_stale = self.rematchSRCmeGoals(user)
        # Assign goals (create/update)
        usergoals = []
        usergoals.extend(self.assignLicenseGoals(profile))
        # create userLicenseDict after assignment of license goals
        userLicenseDict = self.makeUserLicenseDict(user)
        usergoals.extend(self.assignCmeGoals(profile, userLicenseDict))
        usergoals.extend(self.assignSRCmeGoals(profile, userLicenseDict))
        return usergoals

@python_2_unicode_compatible
class UserGoal(models.Model):
    MAX_DUEDATE_DIFF_DAYS = 30 # used in recompute method for combining cmegoals grouped by tag
    PASTDUE = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    EXPIRED = 3
    STATUS_CHOICES = (
        (PASTDUE, 'Past Due'),
        (IN_PROGRESS, 'In Progress'),
        (COMPLETED, 'Completed'),
        (EXPIRED, 'Expired')
    )
    NON_COMPLIANT = 0
    MARGINAL_COMPLIANT = 1
    INCOMPLETE_PROFILE = 2
    INCOMPLETE_LICENSE = 3
    COMPLIANT = 4
    COMPLIANCE_LEVELS = (
        NON_COMPLIANT,
        MARGINAL_COMPLIANT,
        INCOMPLETE_PROFILE,
        INCOMPLETE_LICENSE,
        COMPLIANT
    )
    # fields
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='usergoals',
        db_index=True
    )
    goal = models.ForeignKey(BaseGoal,
        on_delete=models.CASCADE,
        related_name='usergoals',
        db_index=True,
    )
    state = models.ForeignKey(State,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='usergoals',
        help_text="Used to filter goals by state"
    )
    cmeTag = models.ForeignKey(CmeTag,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='usergoals',
        help_text="Used with CmeGoal/SRCmeGoal. Null means Any Topic."
    )
    license = models.ForeignKey(StateLicense,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='usergoals',
        db_index=True,
        help_text='Used for license goals'
    )
    status = models.PositiveSmallIntegerField(choices=STATUS_CHOICES, db_index=True)
    compliance = models.PositiveSmallIntegerField(default=1, db_index=True)
    dueDate = models.DateTimeField()
    valid = models.BooleanField(default=True, help_text='Set/clear flag instead of deleting to preserve information')
    completeDate= models.DateTimeField(blank=True, null=True)
    is_composite_goal = models.BooleanField(default=False,
            help_text='True if goal represents a composite of multiple goals')
    creditsDue = models.DecimalField(max_digits=6, decimal_places=2,
            null=True, blank=True,
            validators=[MinValueValidator(0)],
            help_text='Used for CMEGoals'
    )
    creditsDueMonthly = models.DecimalField(max_digits=6, decimal_places=2,
            null=True, blank=True,
            validators=[MinValueValidator(0)],
            help_text='Used for CMEGoals'
    )
    creditsEarned = models.DecimalField(max_digits=6, decimal_places=2,
            null=True, blank=True,
            validators=[MinValueValidator(0)],
            help_text='Used for CMEGoals'
    )
    creditTypes = models.ManyToManyField(CreditType,
            blank=True,
            related_name='usergoals',
            help_text='Eligible creditTypes that satisfy this goal (not used for composite goals).')
    documents = models.ManyToManyField(Document, related_name='usergoals')
    constituentGoals = models.ManyToManyField('self',
            blank=True,
            related_name='constituentGoals',
            help_text='Populated for composite goals')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = UserGoalManager()

    class Meta:
        unique_together = ('user','goal','dueDate', 'is_composite_goal', 'cmeTag')
        # custom permissions
        permissions = (
            (PERM_VIEW_GOAL, 'Can view Goal'),
        )

    @cached_property
    def title(self):
        """display_title of the goal"""
        basegoal = self.goal
        gtype = self.goal.goalType.name
        if gtype == GoalType.CME or gtype == GoalType.SRCME:
            return self.cmeTag.name if self.cmeTag else ANY_TOPIC
        elif gtype == GoalType.LICENSE:
            return basegoal.licensegoal.title
        return ''

    def __str__(self):
        return '{0.pk}|{0.user}|{0.goal.goalType}|{0.title}|{0.dueDate:%Y-%m-%d}|{0.is_composite_goal}'.format(self)

    def formatCreditTypes(self):
        """Returns string of comma separated CreditType abbrev values"""
        s = ','.join([m.abbrev for m in self.creditTypes.all()])
        if not s:
            return 'Any'
        return s

    @cached_property
    def daysLeft(self, now=None):
        """Returns: int number of days left until dueDate
        or 0 if dueDate is already past
        Args:
            now: datetime/None
        """
        if not now:
            now = timezone.now()
        if self.dueDate > now:
            td = self.dueDate - now
            return td.days
        return 0

    @cached_property
    def progress(self):
        """Returns: int between 0 and 100"""
        gtype = self.goal.goalType.name
        progress = 0
        if gtype == GoalType.CME:
            if self.creditsDue:
                progress = 100.0*float(self.creditsEarned)/float(self.creditsDue + self.creditsEarned)
            else:
                progress = 100
        elif self.goal.interval:
            totalDays = float(self.goal.interval*365)
            if totalDays > self.daysLeft:
                progress = 100.0*(totalDays - self.daysLeft)/totalDays
        return int(progress)

    def calcLicenseStatus(self, now):
        """Returns status based on now, expireDate, and daysBeforeDue"""
        expireDate = self.license.expireDate
        if not expireDate or expireDate < now:
            return UserGoal.PASTDUE
        licenseGoal = self.goal.licensegoal # LicenseGoal instance
        cutoff = expireDate - timedelta(days=licenseGoal.daysBeforeDue)
        if now < cutoff:
            return UserGoal.COMPLETED
        else:
            return UserGoal.IN_PROGRESS

    def calcCompliance(self, status):
        """Used by recompute for License/SRCme usergoal"""
        if status == UserGoal.PASTDUE:
            return UserGoal.NON_COMPLIANT
        elif status == UserGoal.IN_PROGRESS:
            return UserGoal.MARGINAL_COMPLIANT
        return UserGoal.COMPLIANT

    def recomputeLicenseGoal(self):
        """Called by recompute for License usergoal
        """
        now = timezone.now()
        if self.license.isUnInitialized():
            dueDate = now
            status = UserGoal.PASTDUE
            compliance = UserGoal.INCOMPLETE_LICENSE
        else:
            dueDate = self.license.expireDate
            status = self.calcLicenseStatus(now)
            compliance = self.calcCompliance(status)
        if status != self.status or compliance != self.compliance:
            self.status = status
            self.dueDate = dueDate
            self.compliance = compliance
            self.save(update_fields=('status', 'dueDate', 'compliance'))
        return

    def recomputeSRCmeGoal(self, userLicenseDict):
        """Recompute individual srcmegoal"""
        status = self.status
        compliance = self.compliance
        userLicense = None
        profile = self.user.profile
        basegoal = self.goal
        goal = basegoal.srcmegoal # SRCmeGoal
        now = timezone.now()
        if basegoal.usesLicenseDate():
            try:
                userLicense = userLicenseDict[goal.licenseGoal.pk]
            except KeyError:
                logger.exception("No userLicense found for usergoal {0}".format(self))
                return
        # TODO: add NEW status if status is New or RECUR_ANY then
        # dueYear = now.year, else preserve existing dueYear
        dueDate = goal.computeDueDateForProfile(profile, userLicense, now)
        credits = goal.credits
        # compute creditsEarned for self.tag over goal interval
        creditsEarned = goal.computeCreditsEarnedOverInterval(self.user, now, self.cmeTag)
        creditsLeft = float(credits) - float(creditsEarned)
        daysLeft = 0
        if creditsLeft <= 0:
            creditsDue = 0
            compliance = UserGoal.COMPLIANT
        else:
            creditsDue = nround(creditsLeft) # all creditsLeft due at this time
            if dueDate >= now:
                td = dueDate - now
                daysLeft = td.days
            if daysLeft <= SRCME_MARGINAL_COMPLIANT_CUTOFF_DAYS:
                if daysLeft <= 0:
                    compliance = UserGoal.NON_COMPLIANT
                else:
                    compliance = UserGoal.MARGINAL_COMPLIANT
            else:
                compliance = UserGoal.COMPLIANT
        #print(' - Tag {0.cmeTag}|creditsLeft: {1} | creditsDue: {2} for goal {3}'.format(self, creditsLeft, creditsDue, goal))
        # update compliance if incomplete info
        if basegoal.usesLicenseDate() and userLicense.isUnInitialized():
            compliance = UserGoal.INCOMPLETE_LICENSE
        elif basegoal.usesBirthDate() and not profile.birthDate:
            compliance = UserGoal.INCOMPLETE_PROFILE
        # compute status
        if not creditsDue:
            status = UserGoal.COMPLETED # for now
        elif not daysLeft or not creditsEarned:
            status = UserGoal.PASTDUE
        else:
            status = UserGoal.IN_PROGRESS
        self.status = status
        self.dueDate = dueDate
        self.compliance = compliance
        self.creditsDue = creditsDue
        self.creditsDueMonthly = creditsDue
        self.creditsEarned = creditsEarned
        self.save(update_fields=('status', 'dueDate', 'compliance','creditsDue','creditsDueMonthly','creditsEarned'))
        logger.debug('recompute {0} creditsDue: {0.creditsDue}.'.format(self))

    def recomputeCmeGoal(self, userLicenseDict, numProfileSpecs):
        """Recompute individual cmegoal"""
        status = self.status
        compliance = self.compliance
        userLicense = None
        profile = self.user.profile
        basegoal = self.goal
        goal = basegoal.cmegoal # CmeGoal
        now = timezone.now()
        if basegoal.usesLicenseDate():
            try:
                userLicense = userLicenseDict[goal.licenseGoal.pk]
            except KeyError:
                logger.exception("No userLicense found for usergoal {0}".format(self))
                return
        # TODO: add NEW status if status is New or RECUR_ANY then
        # dueYear = now.year, else preserve existing dueYear
        dueDate = goal.computeDueDateForProfile(profile, userLicense, now)
        # this handles splitting credits among specialties if needed
        credits = goal.computeCredits(numProfileSpecs)
        # compute creditsEarned for self.tag over goal interval
        creditsEarned = goal.computeCreditsEarnedOverInterval(self.user, now, self.cmeTag)
        creditsLeft = float(credits) - float(creditsEarned)
        daysLeft = 0
        if creditsLeft <= 0:
            creditsDue = 0
            creditsDueMonthly = 0
            compliance = UserGoal.COMPLIANT
        else:
            creditsDue = nround(creditsLeft) # full creditsLeft
            if dueDate >= now:
                td = dueDate - now
                daysLeft = td.days
            if daysLeft <= 30:
                # all creditsLeft due at this time
                creditsDueMonthly = creditsDue
                if daysLeft <= 0:
                    compliance = UserGoal.NON_COMPLIANT
                else:
                    compliance = UserGoal.MARGINAL_COMPLIANT
            else:
                # articles per month needed to earn creditsLeft by daysLeft
                monthsLeft = math.floor(daysLeft/30) # take floor to ensure we don't underestimate apm
                articlesLeft = creditsLeft/ARTICLE_CREDIT
                apm = round(articlesLeft/monthsLeft) # round to nearest int
                creditsDueMonthly = apm*ARTICLE_CREDIT # due this month
                compliance = UserGoal.COMPLIANT
        #print(' - Tag {0.cmeTag}|creditsLeft: {1} | creditsDue: {2} for goal {3}'.format(self, creditsLeft, creditsDue, goal))
        # update compliance if incomplete info
        if basegoal.usesLicenseDate() and userLicense.isUnInitialized():
            compliance = UserGoal.INCOMPLETE_LICENSE
        elif basegoal.usesBirthDate() and not profile.birthDate:
            compliance = UserGoal.INCOMPLETE_PROFILE
        # compute status
        if not creditsDueMonthly:
            status = UserGoal.COMPLETED # for now
        elif not daysLeft or not creditsEarned:
            status = UserGoal.PASTDUE
        else:
            status = UserGoal.IN_PROGRESS
        self.status = status
        self.dueDate = dueDate
        self.compliance = compliance
        self.creditsDue = creditsDue
        self.creditsDueMonthly = creditsDueMonthly
        self.creditsEarned = creditsEarned
        self.save(update_fields=('status', 'dueDate', 'compliance','creditsDue','creditsDueMonthly','creditsEarned'))
        logger.debug('recompute {0} creditsDue: {0.creditsDue} Monthly: {0.creditsDueMonthly}.'.format(self))

    def recomputeCompositeCmeGoal(self, userLicenseDict, numProfileSpecs):
        """Recompute composite cme usergoal
        """
        consgoals = self.constituentGoals.all()
        data = []
        creditsDue = 0 # init to 0 since status expects var to be set even if no cmegoals
        daysLeft = 0
        for goal in consgoals:
            data.append({
                'goal': goal,
                'dueDate': goal.dueDate,
                'daysLeft': goal.daysLeft,
                'creditsDue': goal.creditsDue,
                'creditsDueMonthly': goal.creditsDueMonthly,
                'creditsEarned': goal.creditsEarned,
                'subCompliance': goal.compliance
            })
        data.sort(key=itemgetter('dueDate'))
        dueDate = data[0]['dueDate'] # earliest
        daysLeft = data[0]['daysLeft']
        creditsDue = data[0]['creditsDue']
        creditsDueMonthly = data[0]['creditsDueMonthly']
        creditsEarned = data[0]['creditsEarned']
        if len(data) > 1:
            # compare creditsDue for the two earliest dueDates
            dueDate1 = data[1]['dueDate'] # 2nd-earliest
            creditsDue1 = data[1]['creditsDue']
            td = dueDate1 - dueDate
            dayDiff = td.days
            if dayDiff < UserGoal.MAX_DUEDATE_DIFF_DAYS:
                # get max of (creditsDue, creditsDue1)
                if creditsDue1 > creditsDue:
                    creditsDue = creditsDue1
                    creditsEarned = data[1]['creditsEarned'] # paired with creditsDue1
                    creditsDueMonthly = data[1]['creditsDueMonthly']
        # compute status
        if not creditsDueMonthly:
            status = UserGoal.COMPLETED # for now
        elif not daysLeft or not creditsEarned:
            status = UserGoal.PASTDUE
        else:
            status = UserGoal.IN_PROGRESS
        # update model instance
        self.dueDate = dueDate # earliest
        self.creditsDue = creditsDue
        self.creditsDueMonthly = creditsDueMonthly
        self.creditsEarned = creditsEarned
        self.status = status
        self.compliance = min([d['subCompliance'] for d in data])
        self.save(update_fields=('status', 'dueDate', 'compliance','creditsDue','creditsDueMonthly','creditsEarned'))
        logger.debug('recompute compositeCmeGoal {0} creditsDue: {0.creditsDue}.'.format(self))
        return data

    def recomputeCompositeSRCmeGoal(self, userLicenseDict):
        """Recompute composite srcme usergoal. This should be called after the individual goals are recomputed.
        """
        consgoals = self.constituentGoals.all()
        data = []
        creditsDue = 0 # init to 0 since status expects var to be set even if no cmegoals
        daysLeft = 0
        for goal in consgoals:
            data.append({
                'goal': goal,
                'dueDate': goal.dueDate,
                'daysLeft': goal.daysLeft,
                'creditsDue': goal.creditsDue,
                'creditsDueMonthly': goal.creditsDueMonthly,
                'creditsEarned': goal.creditsEarned,
                'subCompliance': goal.compliance
            })
        data.sort(key=itemgetter('dueDate'))
        dueDate = data[0]['dueDate'] # earliest
        daysLeft = data[0]['daysLeft']
        creditsDue = data[0]['creditsDue']
        creditsEarned = data[0]['creditsEarned']
        if len(data) > 1:
            # compare creditsDue for the two earliest dueDates
            dueDate1 = data[1]['dueDate'] # 2nd-earliest
            creditsDue1 = data[1]['creditsDue']
            td = dueDate1 - dueDate
            dayDiff = td.days
            if dayDiff < UserGoal.MAX_DUEDATE_DIFF_DAYS:
                # get max of (creditsDue, creditsDue1)
                if creditsDue1 > creditsDue:
                    creditsDue = creditsDue1
                    creditsEarned = data[1]['creditsEarned'] # paired with creditsDue1
        # compute status
        if not creditsDue:
            status = UserGoal.COMPLETED
        elif not daysLeft or not creditsEarned:
            status = UserGoal.PASTDUE
        else:
            status = UserGoal.IN_PROGRESS
        # update model instance
        self.dueDate = dueDate # earliest
        self.creditsDue = creditsDue
        self.creditsDueMonthly = creditsDue
        self.creditsEarned = creditsEarned
        self.status = status
        self.compliance = min([d['subCompliance'] for d in data])
        self.save()
        self.save(update_fields=('status', 'dueDate', 'compliance','creditsDue','creditsDueMonthly','creditsEarned'))
        logger.debug('recompute compositeSRCmeGoal {0} creditsDue: {0.creditsDue}.'.format(self))
        return data


    def recompute(self, userLicenseDict=None, numProfileSpecs=None):
        """Recompute dueDate, status, creditsDue, creditsEarned for the month and update self.
        Args:
            userLicenseDict: dict/None. If None, makeUserLicenseDict will be called.
            numProfileSpecs: int/None. If None, will be computed
        Precomputed args passed in by batch recomputation of usergoals.
        """
        now = timezone.now()
        gtype = self.goal.goalType.name
        status = self.status
        compliance = self.compliance
        if gtype == GoalType.LICENSE:
            self.recomputeLicenseGoal()
            return
        profile = self.user.profile
        if not userLicenseDict:
            userLicenseDict = UserGoal.objects.makeUserLicenseDict(self.user)
        if not numProfileSpecs:
            numProfileSpecs = len(profile.specialtySet)
        if gtype == GoalType.CME:
            if self.is_composite_goal:
                self.recomputeCompositeCmeGoal(userLicenseDict, numProfileSpecs)
                return
            else:
                self.recomputeCmeGoal(userLicenseDict, numProfileSpecs)
                return
        if gtype == GoalType.SRCME:
            if self.is_composite_goal:
                self.recomputeCompositeSRCmeGoal(userLicenseDict)
            else:
                self.recomputeSRCmeGoal(userLicenseDict)
        return

    def needsCompletion(self):
        return self.status in (UserGoal.PASTDUE, UserGoal.IN_PROGRESS)

    def handleRedeemOffer(self):
        """Called when an offer is redeemed to subtract one ARTICLE_CREDIT from creditsDue"""
        v = Decimal(str(ARTICLE_CREDIT))
        goalType = self.goal.goalType
        is_cme = goalType.name == GoalType.CME
        if self.creditsDue >= v:
            self.creditsDue -= v
            self.creditsDueMonthly -= v
            self.creditsEarned += v
            # For CME goals: mark as completed if dueMonthly is 0
            # SRCME goals: full due must be 0 for completion
            compValue = self.creditsDueMonthly if is_cme else self.creditsDue
            if not compValue and self.needsCompletion():
                self.status = UserGoal.COMPLETED
            self.save(update_fields=('creditsDue','creditsDueMonthly', 'creditsEarned','status'))

    def checkUpdate(self, firstGoal, usergoals, userLicenseDict):
        """Check and update fields if needed for a composite cmegoal
        Returns: bool True if model instance was updated
        """
        saved = False
        basegoal = firstGoal.goal
        if self.goal != basegoal:
            self.goal = basegoal
            saved = True
        if saved:
            self.save(update_fields=('goal',))
        dest = self.constituentGoals
        curgoalids = set([g.pk for g in dest.all()])
        newgoalids = set([g.pk for g in usergoals])

        to_del = curgoalids.difference(newgoalids)
        to_add = newgoalids.difference(curgoalids)
        if to_del or to_add:
            saved  = True
        for goalid in to_del:
            dest.remove(goalid)
        for goalid in to_add:
            dest.add(goalid)
        if saved:
            self.recompute(userLicenseDict)
        return saved

@python_2_unicode_compatible
class GoalRecommendation(models.Model):
    goal = models.ForeignKey(BaseGoal,
        on_delete=models.CASCADE,
        db_index=True,
        related_name='recommendations'
    )
    domainTitle = models.CharField(max_length=100,
        help_text='Domain title e.g. Orbit Blog')
    pageTitle = models.CharField(max_length=300, help_text='Page title')
    url = models.URLField(max_length=1000)
    pubDate = models.DateField(null=True, blank=True, help_text='Publish Date')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('goal','url')

    def __str__(self):
        return self.url

#
# obsolete
#
@python_2_unicode_compatible
class TrainingGoal(models.Model):
    DUEDATE_TYPE_CHOICES = (
        (BaseGoal.ONE_OFF, BaseGoal.ONE_OFF_LABEL),
        (BaseGoal.RECUR_MMDD, BaseGoal.RECUR_MMDD_LABEL),
        (BaseGoal.RECUR_BIRTH_DATE, BaseGoal.RECUR_BIRTH_DATE_LABEL),
        (BaseGoal.RECUR_LICENSE_DATE, BaseGoal.RECUR_LICENSE_DATE_LABEL),
    )
    goal = models.OneToOneField(BaseGoal,
        on_delete=models.CASCADE,
        related_name='traingoal',
        primary_key=True
    )
    state = models.ForeignKey(State,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='traingoals',
    )
    title = models.CharField(max_length=120, help_text='Name of the course or training to be done')
    licenseGoal = models.ForeignKey(LicenseGoal,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_index=True,
        related_name='traingoals',
        help_text="Must be selected if dueDate uses license expiration date. Null otherwise."
    )
    dueMonth = models.SmallIntegerField(blank=True, null=True,
            help_text='Must be specified if dueDateType is Fixed MMDD',
            validators=[
                MinValueValidator(1),
                MaxValueValidator(12)])
    dueDay = models.SmallIntegerField(blank=True, null=True,
            help_text='Must be specified if dueDateType is Fixed MMDD',
            validators=[
                MinValueValidator(1),
                MaxValueValidator(31)])
    daysBeforeDue = models.PositiveIntegerField(default=180,
            help_text='days before nextDueDate at which the next usergoal in a recurring series is created')

    def __str__(self):
        return self.title


