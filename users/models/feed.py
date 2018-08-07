# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import logging
from collections import namedtuple
from datetime import datetime
from dateutil.relativedelta import *
import pytz
import random
from urlparse import urlparse
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.db.models import Q, Prefetch, Count, Sum
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from .base import (
    CMETAG_SACME,
    SACME_SPECIALTIES,
    LOCAL_TZ,
    CmeTag,
    Document,
    StateLicense,
)

logger = logging.getLogger('gen.models')

from common.appconstants import (
    SELF_REPORTED_AUTHORITY,
    AMA_PRA_CATEGORY_LABEL,
    PERM_VIEW_OFFER,
    PERM_VIEW_FEED,
    PERM_VIEW_DASH,
    PERM_POST_SRCME,
    PERM_POST_BRCME,
    PERM_DELETE_BRCME,
    PERM_EDIT_BRCME,
    PERM_PRINT_AUDIT_REPORT,
    PERM_PRINT_BRCME_CERT,
)
#
# constants (should match the database values)
#
ENTRYTYPE_BRCME = 'browser-cme'
ENTRYTYPE_SRCME = 'sr-cme'
ENTRYTYPE_STORY_CME = 'story-cme'
ENTRYTYPE_NOTIFICATION = 'notification'
SPONSOR_BRCME = 'TUSM'
ACTIVE_OFFDATE = datetime(3000,1,1,tzinfo=pytz.utc)

# Extensible list of entry types that can appear in a user's feed
@python_2_unicode_compatible
class EntryType(models.Model):
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=100, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

# Sponsors for entries in feed
@python_2_unicode_compatible
class Sponsor(models.Model):
    abbrev = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200, unique=True)
    url = models.URLField(max_length=1000, blank=True, help_text='Link to website of sponsor')
    logo_url = models.URLField(max_length=1000, help_text='Link to logo of sponsor')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name



AuditReportResult = namedtuple('AuditReportResult',
    'saEntries brcmeEntries otherSrCmeEntries saCmeTotal otherCmeTotal creditSumByTag'
)

# Base class for all feed entries (contains fields common to all entry types)
class EntryManager(models.Manager):

    def prepareDataForAuditReport(self, user, startDate, endDate):
        """
        Filter entries by user and activityDate range, and order by activityDate desc.
        Partition the qset into:
            saEntries: entries with tag=CMETAG_SACME
            The non SA-CME entries are further partitioned into:
            brcmeEntries: entries with entryType=ENTRYTYPE_BRCME
            otherSrCmeEntries: non SA-CME entries (sr-cme only)
        Note that for some users, their br-cme entries will fall into the saEntries bucket.
        Returns AuditReportResult
        """
        satag = CmeTag.objects.get(name=CMETAG_SACME)
        filter_kwargs = dict(
            user=user,
            activityDate__gte=startDate,
            activityDate__lte=endDate,
            valid=True
        )
        p_docs = Prefetch('documents',
            queryset=Document.objects.filter(user=user, is_certificate=True, is_thumb=False).order_by('-created'),
            to_attr='cert_docs'
        )
        qset = self.model.objects \
            .select_related('entryType', 'sponsor') \
            .filter(**filter_kwargs) \
            .exclude(entryType__name=ENTRYTYPE_NOTIFICATION) \
            .prefetch_related('tags', p_docs) \
            .order_by('-activityDate')
        saEntries = []  # list of Entry instances having CMETAG_SACME in their tags
        brcmeEntries = []
        otherSrCmeEntries = []
        creditSumByTag = {}
        otherCmeTotal = 0
        #print('Num entries: {0}'.format(qset.count()))
        try:
            for m in qset:
                credits = 0
                entry_tags = m.tags.all()
                tagids = set([t.pk for t in entry_tags])
                #tagnames = [t.name for t in entry_tags]
                #print('{0.pk} {0}|{1}'.format(m, ','.join(tagnames)))
                if satag.pk in tagids:
                    saEntries.append(m)
                    logger.debug('-- Add entry {0.pk} {0.entryType} to saEntries'.format(m))
                else:
                    if m.entryType.name == ENTRYTYPE_BRCME:
                        brcmeEntries.append(m)
                        credits = m.brcme.credits
                    else:
                        otherSrCmeEntries.append(m)
                        credits = m.srcme.credits
                    otherCmeTotal += credits
                #print('-- credits: {0}'.format(credits))
                # add credits to creditSumByTag
                for t in entry_tags:
                    if t.pk == satag.pk:
                        continue
                    creditSumByTag[t.name] = creditSumByTag.setdefault(t.name, 0) + credits
                    #print('---- {0.name} : {1}'.format(t, creditSumByTag[t.name]))
            # sum credit totals
            saCmeTotal = sum([m.getCredits() for m in saEntries])
        except Exception:
            logger.exception('prepareDataForAuditReport exception')
        else:
            logger.debug('saCmeTotal: {0}'.format(saCmeTotal))
            #logger.debug('otherCmeTotal: {0}'.format(otherCmeTotal))
            res = AuditReportResult(
                saEntries=saEntries,
                brcmeEntries=brcmeEntries,
                otherSrCmeEntries=otherSrCmeEntries,
                saCmeTotal=saCmeTotal,
                otherCmeTotal=otherCmeTotal,
                creditSumByTag=creditSumByTag
            )
            return res

    def sumSRCme(self, user, startDate, endDate, tag=None, untaggedOnly=False):
        """
        Total valid Srcme credits over the given time period for the given user.
        Optional filter by specific tag (cmeTag object).
        Optional filter by untagged only. This arg cannot be specified together with tag.
        """
        filter_kwargs = dict(
            valid=True,
            user=user,
            entryType__name=ENTRYTYPE_SRCME,
            activityDate__gte=startDate,
            activityDate__lte=endDate
        )
        if tag:
            filter_kwargs['tags__exact'] = tag
        qset = self.model.objects.select_related('entryType').filter(**filter_kwargs)
        if untaggedOnly:
            qset = qset.annotate(num_tags=Count('tags')).filter(num_tags=0)
        total = qset.aggregate(credit_sum=Sum('srcme__credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0


    def sumStoryCme(self, user, startDate, endDate):
        """
        Total valid StoryCme credits over the given time period for the given user.
        """
        filter_kwargs = dict(
            valid=True,
            user=user,
            entryType__name=ENTRYTYPE_STORY_CME,
            activityDate__gte=startDate,
            activityDate__lte=endDate
        )
        qset = self.model.objects.select_related('entryType').filter(**filter_kwargs)
        total = qset.aggregate(credit_sum=Sum('storycme__credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0


    def sumBrowserCme(self, user, startDate, endDate, tag=None, untaggedOnly=False):
        """
        Total valid BrowserCme credits over the given time period for the given user.
        Optional filter by specific tag (cmeTag object).
        Optional filter by untagged only. This arg cannot be specified together with tag.
        """
        filter_kwargs = dict(
            entry__valid=True,
            entry__user=user,
            entry__activityDate__gte=startDate,
            entry__activityDate__lte=endDate
        )
        if tag:
            filter_kwargs['entry__tags__exact'] = tag
        qset = BrowserCme.objects.select_related('entry').filter(**filter_kwargs)
        if untaggedOnly:
            qset = qset.annotate(num_tags=Count('entry__tags')).filter(num_tags=0)
        total = qset.aggregate(credit_sum=Sum('credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0


@python_2_unicode_compatible
class Entry(models.Model):
    CREDIT_CATEGORY_1 = u'1'
    CREDIT_CATEGORY_1_LABEL = AMA_PRA_CATEGORY_LABEL + u'1 Credit'
    CREDIT_OTHER = u'0'
    CREDIT_OTHER_LABEL = u'Other' # choice label in form
    CREDIT_OTHER_TAGNAME = u'non-Category 1 Credit' # in audit report
    # fields
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='entries',
        db_index=True
    )
    entryType = models.ForeignKey(EntryType,
        on_delete=models.PROTECT,
        db_index=True
    )
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        null=True,
        db_index=True
    )
    activityDate = models.DateTimeField()
    description = models.CharField(max_length=500)
    valid = models.BooleanField(default=True)
    tags = models.ManyToManyField(CmeTag, related_name='entries')
    documents = models.ManyToManyField(Document, related_name='entries')
    ama_pra_catg = models.CharField(max_length=2, blank=True, help_text='AMA PRA Category')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = EntryManager()

    def __str__(self):
        return '{0.pk}|{0.entryType}|{0.user}|{0.activityDate}'.format(self)

    def asLocalTz(self):
        return self.created.astimezone(LOCAL_TZ)

    def formatTags(self):
        """Returns a comma-separated string of self.tags ordered by tag name"""
        names = [t.name for t in self.tags.all()]  # should use default ordering on CmeTag model
        return u', '.join(names)
    formatTags.short_description = "CmeTags"

    def formatNonSATags(self):
        """Returns a comma-separated string of self.tags ordered by tag name excluding SA-CME"""
        names = [t.name for t in self.tags.all() if t.name != CMETAG_SACME]  # should use default ordering on CmeTag model
        return u', '.join(names)

    def formatCreditType(self):
        """The CREDIT_OTHER is formatted for the audit report"""
        if self.ama_pra_catg == Entry.CREDIT_CATEGORY_1:
            return Entry.CREDIT_CATEGORY_1_LABEL
        if self.ama_pra_catg == Entry.CREDIT_OTHER:
            return Entry.CREDIT_OTHER_TAGNAME
        return u''

    def getCredits(self):
        """Returns credit:Decimal value"""
        if self.entryType.name == ENTRYTYPE_SRCME:
            return self.srcme.credits
        if self.entryType.name == ENTRYTYPE_BRCME:
            return self.brcme.credits
        if self.entryType.name == ENTRYTYPE_STORY_CME:
            return self.storycme.credits
        return 0

    def getCertDocReferenceId(self):
        """This expects attr cert_docs:list from prefetch_related.
        This is used by the CreateAuditReport view
        Returns referenceId for the first item in the list or empty str
        """
        if self.cert_docs:
            return self.cert_docs[0].referenceId
        return u''

    def getCertifyingAuthority(self):
        """If sponsor, use sponsor name, else
        use SELF_REPORTED_AUTHORITY
        """
        if self.sponsor:
            return self.sponsor.name
        return SELF_REPORTED_AUTHORITY

    def getNumDocuments(self):
        """Returns number of associated documents"""
        return self.documents.all().count()

    class Meta:
        verbose_name_plural = 'Entries'
        # custom permissions
        # https://docs.djangoproject.com/en/1.10/topics/auth/customizing/#custom-permissions
        permissions = (
            (PERM_VIEW_FEED, 'Can view Feed'),
            (PERM_VIEW_DASH, 'Can view Dashboard'),
            (PERM_POST_BRCME, 'Can redeem BrowserCmeOffer'),
            (PERM_DELETE_BRCME, 'Can delete BrowserCme entry'),
            (PERM_EDIT_BRCME, 'Can edit BrowserCme entry'),
            (PERM_POST_SRCME, 'Can post Self-reported Cme entry'),
            (PERM_PRINT_AUDIT_REPORT, 'Can print/share audit report'),
            (PERM_PRINT_BRCME_CERT, 'Can print/share BrowserCme certificate'),
        )

# Notification entry (in-feed message to user)
@python_2_unicode_compatible
class Notification(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='notification',
        primary_key=True
    )
    expireDate = models.DateTimeField(default=ACTIVE_OFFDATE)

    def __str__(self):
        return self.entry.activityDate

# Self-reported CME
# Earned credits are self-reported
@python_2_unicode_compatible
class SRCme(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='srcme',
        primary_key=True
    )
    credits = models.DecimalField(max_digits=6, decimal_places=2)

    def __str__(self):
        return str(self.credits)


class BrowserCmeManager(models.Manager):

    def hasEarnedMonthLimit(self, user_subs, year, month):
        """Returns True if user has reached the monthly limit set by user_subs.plan
        Note: this should only be called for LimitedCme plans.
        Args:
            user_subs: UserSubscription instance
            year:int
            month:int
        """
        user = user_subs.user
        plan = user_subs.plan
        qs = self.model.objects.select_related('entry').filter(
            entry__user=user,
            entry__created__year=year,
            entry__created__month=month,
            entry__valid=True
        ).aggregate(cme_total=Sum('credits'))
        return qs['cme_total'] >= plan.maxCmeMonth

    def hasEarnedYearLimit(self, user_subs, year):
        """Returns True if user has reached the monthly limit set by user_subs.plan
        Note: this should only be called for LimitedCme plans.
        Args:
            user_subs: UserSubscription instance
            dt: datetime - used for year count
        """
        user = user_subs.user
        plan = user_subs.plan
        qs = self.model.objects.select_related('entry').filter(
            entry__user=user,
            entry__created__year=year,
            entry__valid=True
        ).aggregate(cme_total=Sum('credits'))
        return qs['cme_total'] >= plan.maxCmeYear

    def totalCredits(self):
        """Calculate total BrowserCme credits earned over all time
        Returns: Decimal
        """
        qs = self.model.objects.select_related('entry').filter(
            entry__valid=True
        ).aggregate(cme_total=Sum('credits'))
        return qs['cme_total']

    def randResponse(self):
        return random.randint(0, 2)

    def getDefaultPlanText(self, user):
        """Args:
            user: User instance
        Returns: str default value for planText based on user specialty
        """
        profile = user.profile
        ps = set([p.name for p in profile.specialties.all()])
        s = ps.intersection(SACME_SPECIALTIES)
        if s:
            planText = self.model.DIFFERENTIAL_DIAGNOSIS
        else:
            planText = self.model.TREATMENT_PLAN
        return planText

    def randPlanChange(self, user):
        """Args:
        user: User instance
        Returns: tuple (planEffect:int, planText:str)
        """
        planEffect = random.randint(0, 1)
        planText = ''
        if planEffect:
            planText = self.getDefaultPlanText(user)
        return (planEffect, planText)

# Browser CME entry
# An entry is created when a Browser CME offer is redeemed by the user
@python_2_unicode_compatible
class BrowserCme(models.Model):
    RESPONSE_NO = 0
    RESPONSE_YES = 1
    RESPONSE_UNSURE = 2
    RESPONSE_CHOICES = (
        (RESPONSE_YES, 'Yes'),
        (RESPONSE_NO, 'No'),
        (RESPONSE_UNSURE, 'Unsure')
    )
    PURPOSE_DX = 0  # Diagnosis
    PURPOSE_TX = 1 # Treatment
    PURPOSE_CHOICES = (
        (PURPOSE_DX, 'DX'),
        (PURPOSE_TX, 'TX')
    )
    PLAN_EFFECT_CHOICES = (
        (RESPONSE_NO, 'No change'),
        (RESPONSE_YES, 'Change')
    )
    DIFFERENTIAL_DIAGNOSIS = u'Differential diagnosis'
    TREATMENT_PLAN = u'Treatment plan'
    DIAGNOSTIC_TEST = u'Diagnostic tests'
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='brcme',
        primary_key=True
    )
    offerId = models.PositiveIntegerField(null=True, default=None)
    credits = models.DecimalField(max_digits=5, decimal_places=2)
    url = models.URLField(max_length=500)
    pageTitle = models.TextField()
    purpose = models.IntegerField(
        default=0,
        choices=PURPOSE_CHOICES,
        help_text='DX = Diagnosis. TX = Treatment'
    )
    competence = models.IntegerField(
        default=1,
        choices=RESPONSE_CHOICES,
        help_text='Change in competence - conceptual understanding'
    )
    performance = models.IntegerField(
        default=1,
        choices=RESPONSE_CHOICES,
        help_text='Change in performance - transfer of knowledge to practice'
    )
    planEffect = models.IntegerField(
        default=0,
        choices=PLAN_EFFECT_CHOICES
    )
    planText = models.CharField(max_length=500, blank=True, default='',
            help_text='Explanation of changes to clinical plan'
    )
    commercialBias = models.IntegerField(
        default=0,
        choices=RESPONSE_CHOICES,
        help_text='Commercial bias in content'
    )
    commercialBiasText = models.CharField(max_length=500, blank=True, default='',
            help_text='Explanation of commercial bias in content'
    )
    objects = BrowserCmeManager()

    def __str__(self):
        return self.url

    def formatActivity(self):
        res = urlparse(self.url)
        return res.netloc + ' - ' + self.entry.description

# A Story is broadcast to many users.
# The launch_url must be customized to include the user id when sending
# it in the response for a given user.
@python_2_unicode_compatible
class Story(models.Model):
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        db_index=True
    )
    title = models.CharField(max_length=500)
    description = models.CharField(max_length=2000)
    credits = models.DecimalField(max_digits=4, decimal_places=2, default=1, blank=True,
        help_text='CME credits to be awarded upon completion (default = 1)')
    startDate = models.DateTimeField()
    expireDate = models.DateField(help_text='Expiration date for display')
    endDate = models.DateTimeField(help_text='Expiration timestamp used by server')
    launch_url = models.URLField(max_length=1000, help_text='Form URL')
    entry_url = models.URLField(max_length=1000, help_text='Article URL will be copied to the feed entries.')
    entry_title = models.CharField(max_length=1000, help_text='Article title will be copied to the feed entries.')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Stories'

    def __str__(self):
        return self.title

# Story CME entry
# An entry is created by a script for users who completed a particular Story
@python_2_unicode_compatible
class StoryCme(models.Model):
    entry = models.OneToOneField(Entry,
        on_delete=models.CASCADE,
        related_name='storycme',
        primary_key=True
    )
    story = models.ForeignKey(Story,
        on_delete=models.PROTECT,
        related_name='storycme',
        db_index=True
    )
    credits = models.DecimalField(max_digits=5, decimal_places=2)
    url = models.URLField(max_length=500)
    title = models.TextField()

    def __str__(self):
        return self.url


@python_2_unicode_compatible
class UserFeedback(models.Model):
    SNIPPET_MAX_CHARS = 80
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        db_index=True
    )
    entry = models.OneToOneField(Entry,
        on_delete=models.SET_NULL,
        related_name='feedback',
        null=True,
        blank=True,
        default=None
    )
    message = models.CharField(max_length=500)
    hasBias = models.BooleanField(default=False)
    hasUnfairContent = models.BooleanField(default=False)
    reviewed = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.message

    def message_snippet(self):
        if len(self.message) > UserFeedback.SNIPPET_MAX_CHARS:
            return self.message[0:UserFeedback.SNIPPET_MAX_CHARS] + '...'
        return self.message
    message_snippet.short_description = "Message Snippet"

    def asLocalTz(self):
        return self.created.astimezone(LOCAL_TZ)

    class Meta:
        verbose_name_plural = 'User Feedback'



def certificate_document_path(instance, filename):
    return '{0}/uid_{1}/{2}'.format(settings.CERTIFICATE_MEDIA_BASEDIR, instance.user.id, filename)

# BrowserCme certificate - generated file
@python_2_unicode_compatible
class Certificate(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='certificates',
        db_index=True
    )
    tag = models.ForeignKey(CmeTag,
        on_delete=models.PROTECT,
        related_name='certificates',
        null=True,
        default=None,
        db_index=True
    )
    state_license = models.ForeignKey(StateLicense,
        on_delete=models.PROTECT,
        related_name='certificates',
        null=True,
        default=None,
        db_index=True
    )
    referenceId = models.CharField(max_length=64,
        null=True,
        blank=True,
        unique=True,
        default=None,
        help_text='alphanum unique key generated from the certificate id')
    name = models.CharField(max_length=255, help_text='Name on certificate')
    startDate = models.DateTimeField()
    endDate = models.DateTimeField()
    credits = models.DecimalField(max_digits=6, decimal_places=2)
    document = models.FileField(upload_to=certificate_document_path)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def getAccessUrl(self):
        """Returns the front-end URL to access this certificate"""
        return "https://{0}/certificate/{1}".format(settings.SERVER_HOSTNAME, self.referenceId)

def audit_report_document_path(instance, filename):
    return '{0}/uid_{1}/{2}'.format(settings.AUDIT_REPORT_MEDIA_BASEDIR, instance.user.id, filename)

# Audit Report - raw data for the report is saved in JSONField
@python_2_unicode_compatible
class AuditReport(models.Model):
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='auditreports',
        db_index=True
    )
    certificate = models.ForeignKey(Certificate,
        on_delete=models.PROTECT,
        null=True,
        db_index=True,
        related_name='auditreports',
        help_text='BrowserCme Certificate generated for the same date range'
    )
    referenceId = models.CharField(max_length=64,
        null=True,
        blank=True,
        unique=True,
        default=None,
        help_text='alphanum unique key generated from the pk')
    name = models.CharField(max_length=255, help_text='Name/title of the report')
    startDate = models.DateTimeField()
    endDate = models.DateTimeField()
    saCredits = models.DecimalField(max_digits=6, decimal_places=2, help_text='Calculated number of SA-CME credits')
    otherCredits = models.DecimalField(max_digits=6, decimal_places=2, help_text='Calculated number of other credits')
    data = JSONField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.referenceId

