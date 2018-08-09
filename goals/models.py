# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging
from collections import defaultdict
from datetime import datetime
import pytz
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.functional import cached_property
from common.dateutils import UNKNOWN_DATE, makeAwareDatetime
from users.models import (
    CMETAG_SACME,
    CmeTag,
    Degree,
    Document,
    Hospital,
    PracticeSpecialty,
    LicenseType,
    State,
    StateLicense,
)


logger = logging.getLogger('gen.goals')

INTERVAL_ERROR = u'Interval in years must be specified for recurring dueDateType'
DUE_MONTH_ERROR = u'dueMonth must be a valid month in range 1-12'
DUE_DAY_ERROR = u'dueDay must be a valid day for the selected month in range 1-31'


def makeDueDate(month, day, now):
    """Create dueDate as (now.year,month,day) and advance to next year if dueDate is < now
    Returns: datetime
    """
    dueDate = makeAwareDatetime(now.year, month, day)
    if dueDate < now:
        # advance dueDate to next year
        dueDate = makeAwareDatetime(now.year+1, month, day)
    return dueDate


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
    RECUR_MMDD_LABEL = u'Recurring at set interval. Due on fixed MM/DD'
    RECUR_ANY_LABEL = u'Recurring at set interval. Due at any time counting back over interval'
    RECUR_BIRTH_DATE_LABEL = u'Recurring at set interval. Due on user birth date'
    RECUR_LICENSE_DATE_LABEL =  u'Recurring at set interval. Due on license expiration date'
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
        match = []
        profileDegrees = set([m.pk for m in profile.degrees.all()])
        profileSpecs = set([m.pk for m in profile.specialties.all()])
        profileStates = set([m.pk for m in profile.states.all()])
        qset = self.model.objects.filter(goal__is_active=True)
        for licensegoal in qset:
            basegoal = licensegoal.goal
            # check state match
            if not licensegoal.state.pk in profileStates:
                continue
            # check specialties/degrees intersection
            if not basegoal.isMatchProfile(profileDegrees, profileSpecs):
                continue
            match.append(licensegoal)
        return match


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
    objects = LicenseGoalManager()

    class Meta:
        unique_together = ('state','licenseType','title')

    def __str__(self):
        return self.title

    def clean(self):
        """Validation checks"""
        if not self.title:
            self.title = "{0.licenseType.name} License ({0.state.abbrev})".format(self)

class CmeGoalManager(models.Manager):

    def getMatchingGoalsForProfile(self, profile):
        """Find the goals that match the given profile:
        Returns: list of CmeGoals.
        """
        match = []
        profileDegrees = set([m.pk for m in profile.degrees.all()])
        profileSpecs = set([m.pk for m in profile.specialties.all()])
        profileStates = set([m.pk for m in profile.states.all()])
        profileHospitals = set([m.pk for m in profile.hospitals.all()])
        profileTags = set([m.tag.pk for m in profile.getActiveCmetags()])
        # order by credits DESC (max credits first)
        qset = self.model.objects.filter(goal__is_active=True).order_by('-credits')
        for cmegoal in qset:
            basegoal = cmegoal.goal
            if goal.entityType == self.model.STATE:
                # check state match
                if not cmegoal.state.pk in profileStates:
                    continue
            elif goal.entityType == self.model.HOSPITAL:
                # check hospital match
                if not cmegoal.hospital.pk in profileHospitals:
                    continue
            # check specialties/degrees intersection
            if not basegoal.isMatchProfile(profileDegrees, profileSpecs):
                continue
            # check tag match
            if self.isTagMatchProfile(profileTags):
                match.append(cmegoal)
        return match

    def groupGoalsByTag(self, profile, goals, userLicenseDict, now):
        """Group the given goals by tag
        Args:
            profile: Profile instance
            goals: list of CmeGoals
            userLicenseDict: dict {LicenseGoal.pk => StateLicense instance}
            now: aware datetime
        Returns: dict {tag => [{goal: CmeGoal, credits: float/Decimal, dueDate: datetime}]}
        """
        now = timezone.now()
        grouped = defaultdict(list)
        untagged = [g for g in goals if not g.cmeTag]
        for goal in goals:
            if goal.cmeTag:
                tag = goal.cmeTag
                userLicense = None
                if goal.licenseGoal:
                    userLicense = userLicenseDict.get(goal.licenseGoal.pk, None)
                dueDate = goal.computeDueDateForProfile(profile, userLicense, now)
                d = {'goal': goal, 'dueDate': dueDate, 'credits': goal.credits}
                grouped[tag].append(d)
        profileSpecs = [ps.name for ps in profile.specialties.all()]
        specTags = []
        if profileSpecs:
            specTags = CmeTag.objects.filter(name__in=profileSpecs)
        numTags = len(specTags)
        if numTags:
            for goal in untagged:
                dueDate = goal.computeDueDateForProfile(profile, userLicense, now)
                if numTags == 1:
                    tag = specTags[0]
                    d = {'goal': goal, 'dueDate': dueDate, 'credits': goal.credits}
                    grouped[tag].append(d)
                else:
                    # split credits evenly between tags
                    numCredits = round(goal.credits/numTags)
                    for tag in specTags:
                        d = {'goal': goal, 'dueDate': dueDate, 'credits': numCredits}
                        grouped[tag].append(d)
        # sort goals by dueDate (Note: dueDate cannot be None)
        for tag in grouped:
            grouped[tag].sort(key=itemgetter('dueDate','credits'))
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
        tagName = self.cmeTag.name if self.cmeTag else 'Any CmeTag'
        return u"{0.credits} credits in {1}".format(self, tagName)

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
            return now
        if basegoal.isRecurMMDD():
            try:
                dueDate = makeDueDate(self.dueMonth, self.dueDay, now)
            except ValueError, e:
                logger.error("computeDueDateForProfile: dueDate error from fixed MMDDD goal {0.pk} for user {1}".format(profile, user))
                return UNKNOWN_DATE
            else:
                return dueDate
        if basegoal.usesLicenseDate():
            if not userLicense or userLicense.isUninitialized() or userLicense.expireDate < now:
                # allow time to update license
                logger.warning('computeDueDateForProfile: dueDate requires licenseDate for goal {0.pk} and user {1.user}'.format(self, profile))
                return now + timedelta(days=30)
            else:
                return userLicense.expireDate
        if basegoal.usesBirthDate():
            if not profile.birthDate:
                logger.warning('computeDueDateForProfile: dueDate requires birthDate for goal {0.pk} and user {1.user}'.format(self, profile))
                return now
            try:
                dueDate = makeDueDate(profile.birthDate.month, profile.birthDate.day, now)
            except ValueError, e:
                logger.error("computeDueDateForProfile: dueDate error from birthDate: {0.birthDate} for user {0.user}".format(profile))
                return now
            else:
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
        match = []
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
            match.append(wgoal)
        return match

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
    def createCmeGoals(self, profile, userLicenseDict):
        """Create CME UserGoals for the given profile
        """
        user = profile.user
        usergoals = []
        goals = CmeGoal.objects.getMatchingGoalsForProfile(profile)
        now = timezone.now()
        grouped = CmeGoal.objects.groupGoalsByTag(profile, goals, userLicenseDict, now)
        for tag in grouped:
            data = grouped[tag] # list of dicts sorted by dueDate
            d = data[0]
            credits=d['credits']
            dueDate=d['dueDate']
            goal = d['goal']
            numEntries = len(data)
            if numEntries > 1:
                # compare earliest and second-earliest dueDates
                d1 = data[1]
                td = d1['dueDate'] - dueDate
                dayDiff = td.days
                if dayDiff < MAX_DUEDATE_DIFF_DAYS:
                    # take the max of d[credits] and d1[credits]
                    if d1['credits'] > credits:
                        credits = d1['credits']
                        # will use d1 as the goal FK
                        goal = d1['goal']
            basegoal = goal.goal
            status = self.model.PASTDUE if dueDate < now else self.model.IN_PROGRESS
            # Does UserGoal for (user, tag) already exist
            qset = self.model.objects.filter(user=user, cmeTag=tag).order_by('created')
            if qset.exists():
                usergoal = qset[0]
                saved = usergoal.checkUpdate(basegoal, dueDate, status, creditsDue)
                if saved:
                    logger.info("createCmeGoals: update existing UserGoal {0.pk} for user {0.user}, tag {0.cmeTag}.".format(usergoal))
                else:
                    logger.debug("createCmeGoals: UserGoal {0.pk} for user {0.user}, tag {0.cmeTag} no-change.".format(usergoal))
                for d in data:
                    usergoal.cmeGoals.add(d['goal'])
                continue
            usergoal = self.model.objects.create(
                    user=user,
                    goal=basegoal,
                    dueDate=dueDate,
                    status=status,
                    cmeTag=tag,
                    creditsDue=credits
                )
            for d in data:
                usergoal.cmeGoals.add(d['goal'])
            logger.info('Created UserGoal: {0}'.format(usergoal))
            usergoals.append(usergoal)
        return usergoals

    def createLicenseGoals(self, profile):
        """Create statelicenses for user and license goals
        """
        user = profile.user
        goals = LicenseGoal.objects.getMatchingGoalsForProfile(profile)
        usergoals = []
        now = timezone.now()
        for goal in goals:
            # goal is a LicenseGoal
            basegoal = goal.goal
            licenseType = goal.licenseType
            dueDate = None
            userLicense = None
            # does user license exist with a non-null expireDate
            qset = user.statelicenses.filter(state=goal.state, licenseType=licenseType, expireDate__isnull=False).order_by('-expireDate')
            if qset.exists():
                userLicense = qset[0]
                # does UserGoal for this license already exist
                if self.model.objects.filter(user=user, goal=basegoal, license=userLicense).exists():
                    logger.debug("UserGoal for User {0}|Goal {1}|License {2} already exists.".format(user, goal, userLicense))
                    continue
                # else
                dueDate = userLicense.expireDate
                if dueDate < now:
                    status = self.model.PASTDUE
                else:
                    status = self.model.IN_PROGRESS
            else:
                # does uninitialized license already exist
                qset = user.statelicenses.filter(state=goal.state, licenseType=licenseType, expireDate__isnull=True)
                if qset.exists():
                    userLicense = qset[0]
                    # does UserGoal for this license already exist
                    if self.model.objects.filter(user=user, goal=basegoal, license=userLicense).exists():
                        logger.debug("UserGoal for User {0}|Goal {1}|uninitialized License {2.pk} already exists.".format(user, goal, userLicense))
                        continue
                else:
                    # create unintialized license
                    userLicense = StateLicense.objects.create(
                            user=user,
                            state=goal.state,
                            licenseType=licenseType
                        )
                    logger.info('Create uninitialized {0.licenseType} License for user {0.user}'.format(userLicense))
                # status is PASTDUE until user initializes their license
                dueDate = now
                status = self.model.PASTDUE
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
        return usergoals

    def createWellnessGoals(self, profile):
        user = profile.user
        goals = WellnessGoal.objects.getMatchingGoalsForProfile(profile)
        usergoals = []
        now = timezone.now()
        for goal in goals:
            print(u'createWellnessGoals process: {0}'.format(goal))
            basegoal = goal.goal
            dueDate = None
            if basegoal.isOneOff():
                # Exactly one instance should exist
                if self.model.objects.filter(user=user, goal=goal).exists():
                    logger.debug('OneOff WellnessGoal {0.pk}/{0.title} already exists for user {1}'.format(goal, user))
                    continue
                status = self.model.PASTDUE
                dueDate = now
            elif basegoal.usesBirthDate():
                status = self.model.IN_PROGRESS
                if not profile.birthDate:
                    logger.warning('WellnessGoal {0.pk} needs birthDate from user {1}'.format(goal, user))
                    continue
                try:
                    dueDate = makeDueDate(profile.birthDate.month, profile.birthDate.day, now)
                except ValueError, e:
                    logger.error("createWellnessGoals: dueDate error from birthDate: for user {0}".format(user))
                    continue
                # check unique constraint
                if self.model.objects.filter(user=user, goal=basegoal, dueDate=dueDate).exists():
                    logger.debug('Birthdate WellnessGoal {0.pk}/{0.title} already exists for user {1}'.format(goal, user))
                    continue
            else:
                # fixed MM/DD
                status = self.model.IN_PROGRESS
                try:
                    dueDate = makeDueDate(goal.dueMonth, goal.dueDay, now)
                except ValueError, e:
                    logger.error("createWellnessGoals: dueDate error from fixed MMDDD goal {0.pk} for user {1}".format(profile, user))
                    continue
                # check unique constraint
                if self.model.objects.filter(user=user, goal=basegoal, dueDate=dueDate).exists():
                    logger.debug('RecurMMDD WellnessGoal {0.pk}/{0.title} already exists for user {1}'.format(goal, user))
                    continue
            usergoal = self.model.objects.create(
                    user=user,
                    goal=basegoal,
                    dueDate=dueDate,
                    status=status,
                )
            logger.info('Created UserGoal: {0}'.format(usergoal))
            usergoals.append(usergoal)
        return usergoals

    def createGoals(self, user):
        """Create UserGoals for the given user
        """
        qset = Profile.objects.filter(user=user).prefetch_related('degrees','specialties','states','hospitals')
        if not qset.exists():
            return []
        profile = qset[0]
        self.createLicenseGoals(profile)
        self.createWellnessGoals(profile)
        userLicenseDict = dict()
        # populate from all existing user license goals
        userLicenseGoals = self.model.objects.select_related('goal','license').filter(goal__goalType=licenseGoalType).order_by('id')
        for m in userLicenseGoals:
            userLicenseDict[m.goal.pk] = m.license
        pprint(userLicenseDict)
        self.createCmeGoals(profile, userLicenseDict)

@python_2_unicode_compatible
class UserGoal(models.Model):
    PASTDUE = 0
    IN_PROGRESS = 1
    COMPLETED = 2
    STATUS_CHOICES = (
        (PASTDUE, 'Past Due'),
        (IN_PROGRESS, 'In Progress'),
        (COMPLETED, 'Completed')
    )
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
    status = models.SmallIntegerField(choices=STATUS_CHOICES)
    dueDate = models.DateTimeField()
    completeDate= models.DateTimeField(blank=True, null=True,
            help_text='Date the goal was completed')
    creditsDue = models.DecimalField(max_digits=6, decimal_places=2,
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

    def __str__(self):
        return '{0.pk}|{0.goal.goalType}|{0.user}|{0.dueDate:%Y-%m-%d}'.format(self)

    @cached_property
    def title(self):
        """display_title of the goal"""
        gtype = self.goal.goalType.name
        if gtype == GoalType.CME:
            return self.cmeTag.name
        elif gtype == GoalType.LICENSE:
            return self.goal.licensegoal.title
        else:
            return self.goal.wellnessgoal.title

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
        if gtype == GoalType.CME:
            # TODO: monthly calculation
            return 70
        totalDays = float(self.goal.interval*365)
        progress = 100.0*(totalDays - self.daysLeft)/totalDays
        return int(progress)

    def checkUpdate(self, basegoal, dueDate, status, creditsDue):
        """Check fields and update if needed
        Returns: bool True if model instance was updated
        """
        saved = False
        if self.goal != basegoal:
            self.goal = basegoal
            saved = True
        if self.dueDate != dueDate:
            self.dueDate = dueDate
            saved = True
        if self.status != status:
            self.status = status
            saved = True
        if self.creditsDue != creditsDue:
            self.creditsDue = creditsDue
            saved = True
        if saved:
            self.save()
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
