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
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from common.appconstants import PERM_VIEW_GOAL
from common.dateutils import UNKNOWN_DATE, makeAwareDatetime
from users.models import (
    ARTICLE_CREDIT,
    CMETAG_SACME,
    CmeTag,
    Degree,
    Document,
    Entry,
    Hospital,
    Profile,
    PracticeSpecialty,
    LicenseType,
    State,
    StateLicense,
)

logger = logging.getLogger('gen.goals')

INTERVAL_ERROR = u'Interval in years must be specified for recurring dueDateType'
DUE_MONTH_ERROR = u'dueMonth must be a valid month in range 1-12'
DUE_DAY_ERROR = u'dueDay must be a valid day for the selected month in range 1-31'
LICENSE_GRACE_PERIOD_DAYS = 365
NEW_PROFILE_GRACE_PERIOD_DAYS = 60

def makeDueDate(month, day, now):
    """Create dueDate as (now.year,month,day) and advance to next year if dueDate is < now
    Returns: datetime
    """
    dueDate = makeAwareDatetime(now.year, month, day)
    if dueDate < now:
        # advance dueDate to next year
        dueDate = makeAwareDatetime(now.year+1, month, day)
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
    WELLNESS = 'Wellness'
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
            help_text='Applicable primary roles. No selection means any')
    specialties = models.ManyToManyField(PracticeSpecialty, blank=True,
            help_text='Applicable specialties. No selection means any')
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

    def getDegreesForMatching(self):
        """Returns queryset of self.degrees or all"""
        degrees = self.degrees.all() if self.degrees.exists() else Degree.objects.all()
        return degrees

    def getSpecialtiesForMatching(self):
        """Returns queryset of self.specialties or all"""
        specs = self.specialties.all() if self.specialties.exists() else PracticeSpecialty.objects.all()
        return specs

    def isMatchProfile(self, profileDegrees, profileSpecs):
        """Returns True if intersection exists with profile specialties AND degrees.
        Args:
            profileSpecs: set of PracticeSpecialty pkeyids
            profileDegrees: set of Degree pkeyids
        Returns: bool
        """
        specs = set([m.pk for m in self.getSpecialtiesForMatching()])
        degrees = set([m.pk for m in self.getDegreesForMatching()])
        if degrees.isdisjoint(profileDegrees):
            return False
        if specs.isdisjoint(profileSpecs):
            return False
        return True

#
# Proxy models to BaseGoal used by Admin interface
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
        """Validation checks"""
        if not self.interval:
            raise ValidationError({'interval': 'Duration of license in years is required'})
        if self.dueDateType != BaseGoal.RECUR_LICENSE_DATE:
            raise ValidationError({'dueDateType': 'dueDateType must be {0}'.format(BaseGoal.RECUR_LICENSE_DATE_LABEL)})


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
        """Validation checks"""
        if self.dueDateType > BaseGoal.ONE_OFF and not self.interval:
            raise ValidationError({'interval': INTERVAL_ERROR})

class LicenseGoalManager(models.Manager):

    def getMatchingGoalsForProfile(self, profile):
        """Find the goals that match the given profile:
        Returns: list of LicenseGoals.
        """
        matchedGoals = []
        profileDegrees = set([m.pk for m in profile.degrees.all()])
        profileSpecs = set([m.pk for m in profile.specialties.all()])
        profileStates = set([m.pk for m in profile.states.all()])
        qset = self.model.objects.filter(goal__is_active=True)
        for licensegoal in qset:
            if licensegoal.isMatchProfile(profileDegrees, profileSpecs, profileStates):
                matchedGoals.append(licensegoal)
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
    cmeTag = models.ForeignKey(CmeTag,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='licensegoals',
        help_text="If specified, goal applies only to profile whose active tags contain this tag"
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

    def isMatchProfile(self, profileDegrees, profileSpecs, profileStates):
        """Checks if self matches profile attributes
        Returns: bool
        """
        basegoal = self.goal
        # check state match
        if not self.state.pk in profileStates:
            return False
        # check specialties/degrees intersection
        if not basegoal.isMatchProfile(profileDegrees, profileSpecs):
            return False
        return True


class CmeGoalManager(models.Manager):

    def getMatchingGoalsForProfile(self, profile):
        """Find the goals that match the given profile:
        Returns: list of CmeGoals.
        """
        matchedGoals = []
        profileDegrees = set([m.pk for m in profile.degrees.all()])
        profileSpecs = set([m.pk for m in profile.specialties.all()])
        profileStates = set([m.pk for m in profile.states.all()])
        profileHospitals = set([m.pk for m in profile.hospitals.all()])
        profileTags = set([m.tag.pk for m in profile.getActiveCmetags()])
        qset = self.model.objects.filter(goal__is_active=True)
        for goal in qset:
            if not goal.valid:
                logger.error('Invalid CmeGoal {0.pk}|{0}.'.format(goal))
                continue
            if goal.isMatchProfile(
                    profileDegrees,
                    profileSpecs,
                    profileStates,
                    profileTags,
                    profileHospitals):
                matchedGoals.append(goal)
        return matchedGoals

    def groupGoalsByTag(self, profile, goals):
        """Group the given goals by tag
        Args:
            profile: Profile instance
            goals: list of CmeGoals
            now: aware datetime
        Returns: dict {tag => list of CmeGoals}
        """
        now = timezone.now()
        grouped = defaultdict(list)
        untagged = [g for g in goals if not g.cmeTag]
        for goal in goals:
            if goal.cmeTag:
                tag = goal.cmeTag
                grouped[tag].append(goal)
        profileSpecs = [ps.name for ps in profile.specialties.all()]
        specTags = []
        if profileSpecs:
            specTags = CmeTag.objects.filter(name__in=profileSpecs)
            for goal in untagged:
                for tag in specTags:
                    grouped[tag].append(goal)
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
        help_text="Null value means the tag will be selected from the user's specialty"
    )
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
        if self.dueMonth and not self.dueDay:
            raise ValidationError({'dueDay': DUE_DAY_ERROR})
        if self.dueDay and not self.dueMonth:
                raise ValidationError({'dueMonth': DUE_MONTH_ERROR})
        if self.dueMonth and self.dueDay:
            try:
                d = makeAwareDatetime(2020, self.dueMonth, self.dueDay)
            except ValueError:
                raise ValidationError({'dueDay': DUE_DAY_ERROR})

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

    def isTagMatchProfile(self, profileTags):
        """Args:
            profileTags: set of CmeTag pkeyids
        Returns: bool
        """
        if not self.cmeTag:
            return True # null tag matches any
        return self.cmeTag.pk in profileTags


    def isMatchProfile(self, profileDegrees, profileSpecs, profileStates, profileTags, profileHospitals):
        """Checks if self matches profile attributes
        Returns: bool
        """
        basegoal = self.goal
        if self.entityType == CmeGoal.STATE:
            # check state match
            if not self.state.pk in profileStates:
                return False
        elif self.entityType == CmeGoal.HOSPITAL:
            # check hospital match
            if not self.hospital.pk in profileHospitals:
                return False
        # check specialties/degrees intersection
        if not basegoal.isMatchProfile(profileDegrees, profileSpecs):
            return False
        # check tag match
        if not self.isTagMatchProfile(profileTags):
            return False
        return True


    def computeCredits(self, numProfileSpecs):
        """If self.cmeTag: return self.credits
        else: goal is untagged. Split credits by numProfileSpecs
        Args:
            numProfileSpecs: int - number of profile.specialties
        Returns: float/Decimal
        """
        if self.cmeTag:
            creditsDue = self.credits
        else:
            # untagged = any Tag: split credits among user specialties
            creditsDue = round(1.0*float(self.credits)/numProfileSpecs)
        return creditsDue

    def computeDueDateForProfile(self, profile, userLicense, now):
        """Attempt to find a dueDate based on dueDateType, profile, and userLicense
        Args:
            profile: Profile instance
            userLicense: StateLicense/None
            now: datetime
        Returns: datetime
        Note: UNKNOWN_DATE is reserved for internal errors (such as invalid RECUR_MMDD date or unknown dueDateType
        """
        basegoal = self.goal
        if basegoal.isOneOff() or basegoal.isRecurAny():
            td = now - profile.user.date_joined
            if td.days < NEW_PROFILE_GRACE_PERIOD_DAYS:
                return now + timedelta(days=NEW_PROFILE_GRACE_PERIOD_DAYS)
            return now
        if basegoal.isRecurMMDD():
            dueDate = makeDueDate(self.dueMonth, self.dueDay, now)
            return dueDate
        if basegoal.usesLicenseDate():
            if not userLicense or userLicense.isUnInitialized():
                # allow grace period to update license
                return now + timedelta(days=LICENSE_GRACE_PERIOD_DAYS)
            else:
                return userLicense.expireDate
        if basegoal.usesBirthDate():
            if not profile.birthDate:
                return now
            dueDate = makeDueDate(profile.birthDate.month, profile.birthDate.day, now)
            return dueDate
        return UNKNOWN_DATE

    def getTagDataForProfile(self, profile):
        """
        If self.cmeTag is set, return it
        If null: then select from profile.specialties
        Returns:list of 2-tuples [(cmeTag, credits:Decimal),]
        """
        if self.cmeTag:
            return [(self.cmeTag, self.credits),]
        numspecs = profile.specialties.count()
        if not numspecs:
            logger.warning("CmeGoal {0.pk} has null tag and user {1} has no specialties".format(self, profile.user))
            return []
        tagData = []


class WellnessGoalManager(models.Manager):

    def getMatchingGoalsForProfile(self, profile):
        """Find the goals that match the given profile:
        Returns: list of WellnessGoals.
        """
        matchedGoals = []
        profileDegrees = set([m.pk for m in profile.degrees.all()])
        profileSpecs = set([m.pk for m in profile.specialties.all()])
        profileHospitals = set([m.pk for m in profile.hospitals.all()])
        qset = self.model.objects.filter(goal__is_active=True)
        for wgoal in qset:
            basegoal = wgoal.goal
            # check state match
            if not wgoal.hospital.pk in profileHospitals:
                continue
            # check specialties/degrees intersection
            if not basegoal.isMatchProfile(profileDegrees, profileSpecs):
                continue
            matchedGoals.append(wgoal)
        return matchedGoals

@python_2_unicode_compatible
class WellnessGoal(models.Model):
    DUEDATE_TYPE_CHOICES = (
        (BaseGoal.ONE_OFF, BaseGoal.ONE_OFF_LABEL),
        (BaseGoal.RECUR_MMDD, BaseGoal.RECUR_MMDD_LABEL),
        (BaseGoal.RECUR_BIRTH_DATE, BaseGoal.RECUR_BIRTH_DATE_LABEL),
    )
    goal = models.OneToOneField(BaseGoal,
        on_delete=models.CASCADE,
        related_name='wellnessgoal',
        primary_key=True
    )
    hospital = models.ForeignKey(Hospital,
        on_delete=models.PROTECT,
        db_index=True,
        related_name='wellnessgoals',
    )
    title = models.CharField(max_length=100, help_text='Title of goal e.g. Annual Flu Shot')
    dueMonth = models.SmallIntegerField(blank=True, null=True,
            validators=[
                MinValueValidator(1),
                MaxValueValidator(12)])
    dueDay = models.SmallIntegerField(blank=True, null=True,
            validators=[
                MinValueValidator(1),
                MaxValueValidator(31)])
    objects = WellnessGoalManager()

    def clean(self):
        """Validation checks"""
        if self.goal.dueDateType == BaseGoal.RECUR_MMDD:
            if not self.dueMonth:
                raise ValidationError({'dueMonth': DUE_MONTH_ERROR})
            if not self.dueDay:
                raise ValidationError({'dueDay': DUE_DAY_ERROR})
            try:
                d = makeAwareDatetime(2020, self.dueMonth, self.dueDay)
            except ValueError:
                raise ValidationError({'dueDay': DUE_DAY_ERROR})

    def __str__(self):
        return self.title


class UserGoalManager(models.Manager):
    def assignCmeGoals(self, profile):
        """Assign CME UserGoals by matching existing goals to the given profile.
        Steps:
            1. Find matching CmeGoals based on profile
            2. Group matched goals by tag (multiple CmeGoals consolidated by tag)
            3. If UserGoal for this tag already exists: update/recompute it
                Else create new UserGoal.
        Returns: list of newly created usergoals
        """
        user = profile.user
        usergoals = []
        goals = CmeGoal.objects.getMatchingGoalsForProfile(profile)
        now = timezone.now()
        grouped = CmeGoal.objects.groupGoalsByTag(profile, goals)
        for tag in grouped:
            goals = grouped[tag] # list of cmegoals
            goal = goals[0]
            basegoal = goal.goal
            # Does UserGoal for (user, tag) already exist
            qset = self.model.objects.filter(user=user, cmeTag=tag)
            if qset.exists():
                usergoal = qset[0]
                saved = usergoal.checkUpdate(goal, goals)
                if saved:
                    logger.info("assignCmeGoals: update existing UserGoal {0.pk} for user {0.user}, tag {0.cmeTag}.".format(usergoal))
                else:
                    logger.debug("assignCmeGoals: no-change for UserGoal {0.pk} for user {0.user}, tag {0.cmeTag}.".format(usergoal))
                continue
            usergoal = self.model.objects.create(
                    user=user,
                    goal=basegoal,
                    dueDate=now,
                    status=self.model.PASTDUE,
                    cmeTag=tag,
                    creditsDue=0,
                    creditsEarned=0
                )
            for goal in goals:
                usergoal.cmeGoals.add(goal)
            logger.info('Created UserGoal: {0}'.format(usergoal))
            usergoal.recompute()
            usergoals.append(usergoal)
        return usergoals

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
                    # create unintialized license
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


    def assignGoals(self, user):
        """Assign UserGoals for the given user
        Steps:
            1. Get user profile with prefetched m2m attributes
            2. Assign License UserGoals first so that all userLicense are created
            3. Assign CME UserGoals
        Returns: list of newly created UserGoals
        """
        qset = Profile.objects.filter(user=user).prefetch_related('degrees','specialties','states','hospitals')
        if not qset.exists():
            return []
        profile = qset[0]
        usergoals = []
        usergoals.extend(self.assignLicenseGoals(profile))
        usergoals.extend(self.assignCmeGoals(profile))
        return usergoals

    def rematchGoals(self, user):
        """This should be called when user's profile changes, or when new goals are created (or existing goals inactivated).
        Steps:
            1. Remove stale UserGoals that no longer match the profile
            2. Call assignGoals to create new UserGoals/update existing ones.
        Returns: list of newly created UserGoals
        """
        qset = Profile.objects.filter(user=user).prefetch_related('degrees','specialties','states','hospitals')
        if not qset.exists():
            return []
        profile = qset[0]
        profileDegrees = set([m.pk for m in profile.degrees.all()])
        profileSpecs = set([m.pk for m in profile.specialties.all()])
        profileStates = set([m.pk for m in profile.states.all()])
        profileHospitals = set([m.pk for m in profile.hospitals.all()])
        profileTags = set([m.tag.pk for m in profile.getActiveCmetags()])
        # remove stale license goals
        stale = []
        existing = user.usergoals.select_related('goal').filter(goal__goalType__name=GoalType.LICENSE)
        for ug in existing:
            licensegoal = ug.goal.licensegoal
            if not licensegoal.isMatchProfile(profileDegrees, profileSpecs, profileStates):
                stale.append(ug)
        for ug in stale:
            # Note: this only removes the UserGoal (any associated StateLicense is retained)
            logger.info('Removing {0}'.format(ug))
            ug.delete()
        # for cme goals, only delete if all cmeGoals no longer apply
        stale = []
        existing = user.usergoals.select_related('goal').filter(goal__goalType__name=GoalType.CME)
        for ug in existing:
            matchCount = 0
            for cmegoal in ug.cmeGoals.all():
                if cmegoal.isMatchProfile(
                        profileDegrees,
                        profileSpecs,
                        profileStates,
                        profileTags,
                        profileHospitals):
                    matchCount += 1
            if not matchCount:
                # none of the cmegoals match this profile anymore
                # if only some no longer match, the usergoal will be updated and recomputed below
                stale.append(ug)
        for ug in stale:
            logger.info('Removing {0}'.format(ug))
            ug.delete()
        # Assign goals (create/update)
        usergoals = []
        usergoals.extend(self.assignLicenseGoals(profile))
        usergoals.extend(self.assignCmeGoals(profile))
        return usergoals

@python_2_unicode_compatible
class UserGoal(models.Model):
    MAX_DUEDATE_DIFF_DAYS = 30 # used in recompute calculation
    PASTDUE = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    STATUS_CHOICES = (
        (PASTDUE, 'Past Due'),
        (IN_PROGRESS, 'In Progress'),
        (COMPLETED, 'Completed')
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
        db_index=True
    )
    cmeTag = models.ForeignKey(CmeTag,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        db_index=True,
        related_name='usergoals',
        help_text="Used with CmeGoal"
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
    completeDate= models.DateTimeField(blank=True, null=True,
            help_text='Used for Wellness goal completion date.')
    creditsDue = models.DecimalField(max_digits=6, decimal_places=2,
            null=True, blank=True,
            validators=[MinValueValidator(0)],
            help_text='Used for CMEGoals'
    )
    creditsEarned = models.DecimalField(max_digits=6, decimal_places=2,
            null=True, blank=True,
            validators=[MinValueValidator(0)],
            help_text='Used for CMEGoals'
    )
    documents = models.ManyToManyField(Document, related_name='usergoals')
    cmeGoals = models.ManyToManyField(CmeGoal, related_name='usercmegoals')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = UserGoalManager()

    class Meta:
        unique_together = ('user','goal','dueDate')
        # custom permissions
        permissions = (
            (PERM_VIEW_GOAL, 'Can view Goal'),
        )

    @cached_property
    def title(self):
        """display_title of the goal"""
        basegoal = self.goal
        gtype = self.goal.goalType.name
        if gtype == GoalType.CME:
            return self.cmeTag.name
        elif gtype == GoalType.LICENSE:
            return basegoal.licensegoal.title
        else:
            return basegoal.wellnessgoal.title

    def __str__(self):
        return '{0.pk}|{0.user}|{0.goal.goalType}|{0.title}|{0.dueDate:%Y-%m-%d}'.format(self)

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


    def makeUserLicenseDict(self):
        """Helper method for recompute
        Find all user licensegoals and make {BaseGoal.pk => License instance} for self.user and goalType = LICENSE
        Returns: dict
        """
        userLicenseDict = dict()
        licenseGoalType = GoalType.objects.get(name=GoalType.LICENSE)
        # get user licensegoals (must be created before user cmegoals)
        qset = self.user.usergoals.select_related('goal','license').filter(goal__goalType=licenseGoalType)
        for m in qset:
            userLicenseDict[m.goal.pk] = m.license
        return userLicenseDict

    def getCreditSumOverInterval(self, basegoal, endDate):
        """Calls Entry.object.sumSRCme and sumBrowserCme for self.user, tag, and basegoal.interval
        Returns: decimal - total credits earned
        """
        yrs = basegoal.interval if basegoal.interval else 10
        startDate = endDate - timedelta(days=365*float(yrs))
        srcme_credits = Entry.objects.sumSRCme(self.user, startDate, endDate, self.cmeTag)
        brcme_credits = Entry.objects.sumBrowserCme(self.user, startDate, endDate, self.cmeTag)
        total = brcme_credits + srcme_credits
        #print('- creditsEarned {0} over interval: {1} years'.format(total, yrs))
        return total

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

    def recompute(self, userLicenseDict=None, numProfileSpecs=None):
        """Recompute dueDate, status, creditsDue, creditsEarned for the month and update self.
        Args:
            userLicenseDict: dict/None. If None, makeUserLicenseDict will be called.
            numProfileSpecs: int/None. If None, profile.specialties.count() will be called
        Precomputed args passed in by batch recomputation of usergoals.
        """
        now = timezone.now()
        gtype = self.goal.goalType.name
        status = self.status
        compliance = self.compliance
        if gtype == GoalType.LICENSE:
            if self.license.isUnInitialized():
                dueDate = now
                status = UserGoal.PASTDUE
                compliance = UserGoal.INCOMPLETE_LICENSE
            else:
                dueDate = self.license.expireDate
                status = self.calcLicenseStatus(now)
                if status == UserGoal.PASTDUE:
                    compliance = UserGoal.NON_COMPLIANT
                elif status == UserGoal.IN_PROGRESS:
                    compliance = UserGoal.MARGINAL_COMPLIANT
                else: # completed
                    compliance = UserGoal.COMPLIANT
            if status != self.status or compliance != self.compliance:
                self.status = status
                self.dueDate = dueDate
                self.compliance = compliance
                self.save(update_fields=('status', 'dueDate', 'compliance'))
            return
        profile = self.user.profile
        if not numProfileSpecs:
            numProfileSpecs = profile.specialties.count()
        if not userLicenseDict:
            userLicenseDict = self.makeUserLicenseDict()
        userLicense = None
        cmegoals = self.cmeGoals.all()
        data = []
        for goal in cmegoals:
            basegoal = goal.goal
            if basegoal.usesLicenseDate():
                try:
                    userLicense = userLicenseDict[goal.licenseGoal.pk]
                except KeyError:
                    logger.exception("No userLicense found for user {0.user} and CmeGoal {1.pk} that uses LicenseGoal {2.pk}".format(self, goal, goal.licenseGoal))
                    return
            dueDate = goal.computeDueDateForProfile(profile, userLicense, now)
            credits = goal.computeCredits(numProfileSpecs)
            # compute creditsEarned for self.tag over goal interval
            creditsEarned = self.getCreditSumOverInterval(basegoal, now)
            creditsLeft = float(credits) - float(creditsEarned)
            daysLeft = 0
            if creditsLeft <= 0:
                creditsDue = 0
                subCompliance = UserGoal.COMPLIANT
            else:
                if dueDate >= now:
                    td = dueDate - now
                    daysLeft = td.days
                if daysLeft <= 30:
                    creditsDue = nround(creditsLeft) # all creditsLeft due at this time
                    if daysLeft <= 0:
                        subCompliance = UserGoal.NON_COMPLIANT
                    else:
                        subCompliance = UserGoal.MARGINAL_COMPLIANT

                else:
                    # articles per month needed to earn creditsLeft by daysLeft
                    monthsLeft = math.floor(daysLeft/30) # take floor to ensure we don't underestimate apm
                    articlesLeft = creditsLeft/ARTICLE_CREDIT
                    apm = round(articlesLeft/monthsLeft) # round to nearest int
                    creditsDue = apm*ARTICLE_CREDIT # creditsDue can be converted to an integer number of articles due
                    subCompliance = UserGoal.COMPLIANT
            #print(' - Tag {0.cmeTag}|creditsLeft: {1} | creditsDue: {2} for goal {3}'.format(self, creditsLeft, creditsDue, goal))
            # update subCompliance if incomplete info
            if basegoal.usesLicenseDate() and userLicense.isUnInitialized():
                subCompliance = UserGoal.INCOMPLETE_LICENSE
            elif basegoal.usesBirthDate() and not profile.birthDate:
                subCompliance = UserGoal.INCOMPLETE_PROFILE
            data.append({
                'goal': goal,
                'dueDate': dueDate,
                'daysLeft': daysLeft,
                'creditsDue': creditsDue,
                'creditsEarned': creditsEarned,
                'subCompliance': subCompliance
            })
        if len(data) > 1:
            data.sort(key=itemgetter('dueDate'))
            # compare creditsDue for the two earliest dueDates
            daysLeft = data[0]['daysLeft'] # daysLeft for the earliest
            dueDate = data[0]['dueDate'] # earliest
            dueDate1 = data[1]['dueDate'] # 2nd-earliest
            creditsDue = data[0]['creditsDue']
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
            status = UserGoal.COMPLETED # for now
        elif not daysLeft or not creditsEarned:
            status = UserGoal.PASTDUE
        else:
            status = UserGoal.IN_PROGRESS
        # update model instance
        self.dueDate = dueDate # earliest
        self.creditsDue = creditsDue
        self.creditsEarned = creditsEarned
        self.status = status
        self.compliance = min([d['subCompliance'] for d in data])
        self.save()
        logger.debug('recompute User {0.user} creditsDue: {0.creditsDue} for Tag {0.cmeTag}.'.format(self))
        return data

    def handleRedeemOffer(self):
        """Called when an offer is redeemed to subtract one ARTICLE_CREDIT from creditsDue"""
        v = Decimal(str(ARTICLE_CREDIT))
        if self.creditsDue >= v:
            self.creditsDue -= v
            self.creditsEarned += v
            self.status = UserGoal.IN_PROGRESS
            self.save(update_fields=('creditsDue','creditsEarned','status'))
            logger.debug('handleRedeemOffer: User {0.user} creditsDue: {0.creditsDue} for Tag {0.cmeTag}.'.format(self))

    def checkUpdate(self, goal, cmegoals):
        """Used by assignCmeGoals manager method to check and update fields if needed
        Returns: bool True if model instance was updated
        """
        saved = False
        basegoal = goal.goal
        if self.goal != basegoal:
            self.goal = basegoal
            saved = True
        if saved:
            self.save()
        curgoalids = set([g.pk for g in self.cmeGoals.all()])
        newgoalids = set([g.pk for g in cmegoals])
        to_del = curgoalids.difference(newgoalids)
        to_add = newgoalids.difference(curgoalids)
        if to_del or to_add:
            saved  = True
        for goalid in to_del:
            self.cmeGoals.remove(goalid)
        for goalid in to_add:
            self.cmeGoals.add(goalid)
        if saved:
            self.recompute()
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
