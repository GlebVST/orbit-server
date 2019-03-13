"""Models managed by the plugin_server project"""
from __future__ import unicode_literals
import logging
from datetime import datetime, timedelta
import pytz
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Q, Subquery, Sum
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.contrib.postgres.fields import JSONField

from common.appconstants import MAX_URL_LENGTH
from .base import (
    CMETAG_SACME,
    SACME_SPECIALTIES,
    CmeTag,
    EligibleSite,
    Organization
)
from .feed import Sponsor, ARTICLE_CREDIT

logger = logging.getLogger('gen.models')

OFFER_LOOKBACK_DAYS = 365*3

@python_2_unicode_compatible
class AllowedHost(models.Model):
    id = models.AutoField(primary_key=True)
    hostname = models.CharField(max_length=100, unique=True, help_text='netloc only. No scheme')
    main_host = models.ForeignKey('self', null=True, blank=True, help_text='Main host for which this host is a proxy')
    description = models.CharField(max_length=500, blank=True, default='')
    accept_query_keys = models.TextField(blank=True, default='', help_text='accepted keys in url query')
    has_paywall = models.BooleanField(blank=True, default=False, help_text='True if full text is behind paywall')
    allow_page_download = models.BooleanField(blank=True, default=False,
            help_text='False if pages under this host should not be downloaded')
    is_secure = models.BooleanField(blank=True, default=False, help_text='True if site uses a secure connection (https).')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_allowedhost'

    def __str__(self):
        return self.hostname

@python_2_unicode_compatible
class HostPattern(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost,
        on_delete=models.CASCADE,
        related_name='hostpatterns',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        related_name='hostpatterns',
        db_index=True)
    path_contains = models.CharField(max_length=200, blank=True, default='',
        help_text='If given, url path part must contain this term. No trailing slash.')
    path_reject = models.CharField(max_length=200, blank=True, default='',
        help_text='If given, url path part must not contain this term. No trailing slash.')
    pattern_key = models.CharField(max_length=40, help_text='valid key in URL_PATTERNS dict')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_hostpattern'
        ordering = ['host','eligible_site','pattern_key','path_contains']

    def __str__(self):
        return '{0.host}|{0.eligible_site.domain_name}|{0.pattern_key}|pc:{0.path_contains}|pr: {0.path_reject}'.format(self)

@python_2_unicode_compatible
class AllowedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost,
        on_delete=models.CASCADE,
        related_name='aurls',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.CASCADE,
        related_name='aurls',
        db_index=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    valid = models.BooleanField(default=True)
    page_title = models.TextField(blank=True, default='')
    metadata = models.TextField(blank=True, default='')
    doi = models.CharField(max_length=100, blank=True,
        help_text='Digital Object Identifier e.g. 10.1371/journal.pmed.1002234')
    pmid = models.CharField(max_length=20, blank=True, help_text='PubMed Identifier (PMID)')
    pmcid = models.CharField(max_length=20, blank=True, help_text='PubMedCentral Identifier (PMCID)')
    set_id = models.CharField(max_length=500, blank=True,
        help_text='Used to group a set of URLs that point to the same resource')
    content_type = models.CharField(max_length=100, blank=True, help_text='page content_type')
    cmeTags = models.ManyToManyField(CmeTag, blank=True, related_name='aurls')
    pubDate = models.DateField(null=True, blank=True, help_text='article publication date')
    numOffers = models.IntegerField(default=1, help_text='cached number of redeemed offers')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_allowedurl'

    def __str__(self):
        return self.url

    def cleanPageTitle(self):
        esite = self.eligible_site
        title_suffix = esite.page_title_suffix
        if title_suffix:
            return self.page_title.replace(title_suffix, '')
        return self.page_title

class RejectedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    host = models.ForeignKey(AllowedHost, db_index=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    starts_with = models.BooleanField(default=False, help_text='True if any sub URL under it should also be rejected')
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_rejectedurl'

    def __str__(self):
        return self.url

# ActivitySet is a collection of 1+ ActivityLogs for a (user, url)
@python_2_unicode_compatible
class ActivitySet(models.Model):
    MAX_EXTENT_SECONDS = 60*60*8 # max time extent of an activity set
    TOTAL_SECONDS_THRESHOLD = 20
    ENGAGED_SECONDS_THRESHOLD = 1
    # fields
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activitysets')
    url = models.ForeignKey(AllowedUrl, on_delete=models.CASCADE, related_name='activitysets')
    total_tracking_seconds = models.PositiveIntegerField(help_text='Sum of x_tracking_seconds over a set of logs')
    computed_value = models.DecimalField(max_digits=9, decimal_places=2, help_text='Total number of engaged seconds')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_activityset'

    def __str__(self):
        return '{0}/{1} on {2}'.format(self.user, self.url, self.created)

    def meetsThreshold(self):
        """Returns True if cumulative values meet or exceed threshold"""
        return self.total_tracking_seconds >= ActivitySet.TOTAL_SECONDS_THRESHOLD and self.computed_value >= ActivitySet.ENGAGED_SECONDS_THRESHOLD

# ActivityLog is a log sent by the plugin client upon page load and every x_tracking_seconds while user is on the page
@python_2_unicode_compatible
class ActivityLog(models.Model):
    id = models.AutoField(primary_key=True)
    activity_set = models.ForeignKey(ActivitySet, on_delete=models.CASCADE, related_name='logs')
    valid = models.BooleanField(default=True)
    x_tracking_seconds = models.PositiveIntegerField()
    browser_extensions = JSONField(blank=True)
    # user stats recorded by the plugin
    num_highlight = models.PositiveIntegerField(default=0)
    num_mouse_click = models.PositiveIntegerField(default=0)
    num_mouse_move = models.PositiveIntegerField(default=0)
    num_start_scroll = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True, blank=True)
    modified = models.DateTimeField(auto_now=True, blank=True)

    class Meta:
        managed = False
        db_table = 'trackers_activitylog'

    def __str__(self):
        return '{0.activity_set} on {0.created}'.format(self)

    def isEngaged(self):
        return self.valid and any([self.num_highlight + self.num_mouse_click + self.num_mouse_move + self.num_start_scroll])

# Requests made by plugin users for new AllowedUrl entries
@python_2_unicode_compatible
class RequestedUrl(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.URLField(max_length=MAX_URL_LENGTH, unique=True)
    valid = models.NullBooleanField(default=None)
    users = models.ManyToManyField(User, through='WhitelistRequest')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_requestedurl'

    def __str__(self):
        return self.url

# User-RequestedUrl association
@python_2_unicode_compatible
class WhitelistRequest(models.Model):
    id = models.AutoField(primary_key=True)
    req_url = models.ForeignKey(RequestedUrl, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'trackers_whitelistrequest'
        unique_together = ('req_url', 'user')

    def __str__(self):
        return '{0}-{1}'.format(self.user, self.req_url.url)

class OrbitCmeOfferManager(models.Manager):
    def makeOffer(self, aurl, user, activityDate, expireDate):
        esite = aurl.eligible_site
        with transaction.atomic():
            offer = OrbitCmeOffer.objects.create(
                user=user,
                eligible_site=esite,
                url=aurl,
                activityDate=activityDate,
                expireDate=expireDate,
                suggestedDescr=aurl.page_title,
                credits=ARTICLE_CREDIT,
                sponsor_id=1
            )
            offer.assignCmeTags()
        return offer

    def makeDebugOffer(self, aurl, user):
        now = timezone.now()
        activityDate = now + timedelta(seconds=20)
        expireDate = now + timedelta(days=365)
        return self.makeOffer(aurl, user, activityDate, expireDate)

    def makeWelcomeOffer(self, user):
        aurl = None
        # Need to be sure that welcome article exists in this db instance
        qset = AllowedUrl.objects.filter(url=settings.WELCOME_ARTICLE_URL)
        if qset.exists():
            aurl = qset[0]
        if not aurl:
            logger.warn("No Welcome article listed in allowed urls!")
            return None
        now = timezone.now()
        activityDate = now - timedelta(seconds=10)
        expireDate = now + timedelta(days=365)
        return self.makeOffer(aurl, user, activityDate, expireDate)

    def sumCredits(self, user, startDate, endDate):
        """Total valid offer credits over the given time period for the given user
        Returns: Float
        """
        now = timezone.now()
        filter_kwargs = {
            'valid': True,
            'user': user,
            'activityDate__gte': startDate,
            'activityDate__lte': endDate,
            'expireDate__gt': now
        }
        qset = self.model.objects.filter(**filter_kwargs)
        total = qset.aggregate(credit_sum=Sum('credits'))
        credit_sum = total['credit_sum']
        if credit_sum:
            return float(credit_sum)
        return 0

# OrbitCmeOffer
# An offer for a user is generated based on the user's plugin activity.
@python_2_unicode_compatible
class OrbitCmeOffer(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User,
        on_delete=models.CASCADE,
        related_name='new_offers',
        db_index=True
    )
    sponsor = models.ForeignKey(Sponsor,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True
    )
    eligible_site = models.ForeignKey(EligibleSite,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True)
    url = models.ForeignKey(AllowedUrl,
        on_delete=models.PROTECT,
        related_name='new_offers',
        db_index=True)
    activityDate = models.DateTimeField()
    suggestedDescr = models.TextField(blank=True, default='')
    expireDate = models.DateTimeField()
    redeemed = models.BooleanField(default=False)
    valid = models.BooleanField(default=True)
    credits = models.DecimalField(max_digits=5, decimal_places=2,
        help_text='CME credits to be awarded upon redemption')
    tags = models.ManyToManyField(
        CmeTag,
        blank=True,
        related_name='new_offers',
        help_text='Suggested tags (intersected with user cmeTags by UI)'
    )
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    objects = OrbitCmeOfferManager()

    class Meta:
        managed = False
        db_table = 'trackers_orbitcmeoffer'
        verbose_name_plural = 'OrbitCME Offers'

    def __str__(self):
        return self.url.url

    def formatSuggestedTags(self):
        return ", ".join([t.name for t in self.tags.all()])
    formatSuggestedTags.short_description = "suggestedTags"

    def assignCmeTags(self):
        """Assign tags based on: eligible_site, url, and user"""
        esite = self.eligible_site
        # get suggested cmetags from the eligible_site.specialties
        specnames = [p.name for p in esite.specialties.all()]
        spectags = CmeTag.objects.filter(name__in=specnames) # tags whose name=pracspec.name
        self.tags.set(list(spectags))
        # tags from allowed_url
        for t in self.url.cmeTags.all():
            self.tags.add(t)
        # check if can add SA-CME tag
        profile = self.user.profile
        if profile.isPhysician() and profile.specialties.filter(name__in=SACME_SPECIALTIES).exists():
            self.tags.add(CmeTag.objects.get(name=CMETAG_SACME))


# OrbitCmeOffer stats per org
@python_2_unicode_compatible
class OrbitCmeOfferAgg(models.Model):
    id = models.AutoField(primary_key=True)
    organization = models.ForeignKey(Organization,
        on_delete=models.CASCADE,
        db_index=True
    )
    day = models.DateField()
    offers = models.PositiveIntegerField(default=0,
        help_text='Number of offers generated for this day (counted from 00:00:00 UTC - 23:59:59 UTC)')
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'trackers_orbitcmeofferagg'
        verbose_name_plural = 'OrbitCME Offer Stats'

    def __str__(self):
        return "{0.day}".format(self)


# User recommendations for AllowedUrls by tag
class RecAllowedUrlManager(models.Manager):
    def updateRecsForUser(self, user, tag):
        """Maintain a list of upto MAX_RECS_PER_USERTAG recommended aurls for the given user and tag
        Args:
            user: User instance
            tag: CmeTag instance
        Returns: int - number of recs created
        """
        num_recs = self.model.MAX_RECS_PER_USERTAG - user.recaurls.filter(cmeTag=tag).count()
        if num_recs <= 0:
            return 0
        num_created = 0
        # exclude_offers: of the given tag redeemed by user since OFFER_LOOKBACK_DAYS. This is used as a subquery below
        now = timezone.now()
        startdate = now - timedelta(days=OFFER_LOOKBACK_DAYS)
        filter_kwargs = dict(
            user=user,
            redeemed=True,
            valid=True,
            activityDate__gte=startdate,
            tags=tag
        )
        Q_offer_setid = Q(url__set_id='')
        # redeemed offers whose aurl.set_id is blank
        offers_blank_setid = OrbitCmeOffer.objects.select_related('url').filter(Q_offer_setid, **filter_kwargs)
        # redeemed offers whose aurl.set_id is not blank (e.g. abs/pdf versions of the same article have the same set_id)
        offers_setid = OrbitCmeOffer.objects.select_related('url').filter(~Q_offer_setid, **filter_kwargs)
        aurl_kwargs = dict(
            valid=True,
            cmeTags=tag,
            host__has_paywall=False, # omit paywalled articles since not all users have access to them
            host__main_host__isnull=True, # omit proxy hosts
        )
        Q_setid = Q(set_id='')
        # This query gets distinct AllowedUrls with blank set_id for the given tag and excludes
        # any urls with the same pk as those contained in offers_blank_setid
        aurls_blank_setid = AllowedUrl.objects \
                .select_related('host') \
                .filter(Q_setid, **aurl_kwargs) \
                .exclude(pk__in=Subquery(offers_blank_setid.values('pk'))) \
                .order_by('-created')
        # This query gets distinct AllowedUrls with non-blank set_id for the given tag and excludes
        # any urls with the same set_id as those contained in exclude_offers
        aurls_setid = AllowedUrl.objects \
                .select_related('host') \
                .filter(~Q_setid, **aurl_kwargs) \
                .exclude(set_id__in=Subquery(offers_setid.values('url__set_id').distinct())) \
                .order_by('-created')
        # evaluate aurls_blank_setid first
        for aurl in aurls_blank_setid:
            m, created = self.model.objects.get_or_create(user=user, cmeTag=tag, url=aurl)
            if created:
                #print('blank set_id recaurl {0}'.format(m))
                num_created += 1
                if num_created >= num_recs:
                    break
        if num_created >= num_recs:
            return num_created
        #print('Num aurl blank set_id: {0}'.format(num_created))
        # evalute aurls_setid if still need more recs
        for aurl in aurls_setid:
            if aurl.set_id:
                # check if user already has a rec with this set_id
                qs = user.recaurls.select_related('url').filter(url__set_id=aurl.set_id)
                if qs.exists():
                    continue
            m, created = self.model.objects.get_or_create(user=user, cmeTag=tag, url=aurl)
            if created:
                #print('set_id recaurl {0}'.format(m))
                num_created += 1
                if num_created >= num_recs:
                    break
        return num_created

@python_2_unicode_compatible
class RecAllowedUrl(models.Model):
    MAX_RECS_PER_USERTAG = 20
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recaurls')
    url = models.ForeignKey(AllowedUrl, on_delete=models.CASCADE, related_name='recaurls')
    cmeTag = models.ForeignKey(CmeTag, on_delete=models.CASCADE, related_name='recaurls')
    offer = models.ForeignKey(OrbitCmeOffer, on_delete=models.CASCADE, null=True, blank=True, related_name='recaurls')
    objects = RecAllowedUrlManager()

    class Meta:
        managed = False
        db_table = 'trackers_recallowedurl'
        unique_together = ('user','url','cmeTag')

    def __str__(self):
        return '{0.user}|{0.cmeTag}|{0.url}'.format(self)


